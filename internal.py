"""Loopback bridge for the authenticated WhatsApp sidecar, never a public API."""
import hmac, json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from state import ROOT, connect, submit
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,value,status=200):
        data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def authorized(self):
        expected='Bearer '+(ROOT/'private'/'bridge.key').read_text().strip()
        if not hmac.compare_digest(self.headers.get('Authorization',''),expected):self.reply({'error':'Unauthorized'},401);return False
        return True
    def do_GET(self):
        if not self.authorized():return
        with connect() as c:
            if self.path=='/sessions':self.reply([dict(r) for r in c.execute("SELECT user_id,status FROM whatsapp")]);return
            if self.path=='/notifications':
                tasks=[dict(r) for r in c.execute("SELECT t.id,t.user_id,t.status,t.summary,t.error FROM tasks t JOIN notifications n ON t.id=n.task_id JOIN whatsapp w ON w.user_id=t.user_id AND w.status='connected' WHERE n.status='pending' ORDER BY t.created LIMIT 20")]
                for task in tasks:task['deliverables']=[dict(r) for r in c.execute('SELECT path,mime,size FROM deliverables WHERE task_id=?',(task['id'],))] if task['status']=='ready' else []
                capable=ROOT/'bridge-private'/'capabilities.json'
                if not capable.exists():tasks=[task for task in tasks if not task['deliverables']]
                self.reply(tasks);return
        self.reply({'error':'Unknown route'},404)
    def do_POST(self):
        if not self.authorized():return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<200000:raise ValueError('Invalid body size')
            v=json.loads(self.rfile.read(length))
            with connect() as c:
                if self.path=='/status':
                    if v['status'] not in ('connecting','qr','connected','reconnecting','logged_out','disconnected','error'):raise ValueError('Invalid status')
                    c.execute('UPDATE whatsapp SET status=?,qr=?,qr_expires=?,updated=? WHERE user_id=?',(v['status'],v.get('qr'),time.time()+60 if v.get('qr') else None,time.time(),v['user_id']));self.reply({'ok':True})
                elif self.path=='/submit':
                    if not c.execute("SELECT 1 FROM whatsapp WHERE user_id=? AND status='connected'",(v['user_id'],)).fetchone():raise ValueError('WhatsApp session not linked')
                    self.reply({'task_id':submit(c,v['user_id'],v['prompt'],v['message_id'])})
                elif self.path=='/notification':
                    if v['status'] not in ('sending','sent','uncertain','failed'):raise ValueError('Invalid delivery status')
                    c.execute('UPDATE notifications SET status=?,attempts=attempts+1,error=? WHERE task_id=?',(v['status'],v.get('error'),v['task_id']));self.reply({'ok':True})
                else:self.reply({'error':'Unknown route'},404)
        except (ValueError,KeyError) as e:self.reply({'error':str(e)[:300]},400)
        except Exception:self.reply({'error':'Internal bridge error'},500)
if __name__=='__main__':
    with connect() as c:c.execute("UPDATE notifications SET status='uncertain',error='Bridge restarted during delivery' WHERE status='sending'")
    ThreadingHTTPServer(('127.0.0.1',9871),Handler).serve_forever()
