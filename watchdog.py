"""Independent health monitor, with persistent limits on service restarts."""
import json,subprocess,time
from state import ROOT,connect,config,audit,heartbeat
def main():
 while True:
  with connect() as c:
   heartbeat(c,'watchdog','working')
   now=time.time();rows=c.execute('SELECT updated FROM heartbeats WHERE role IN ("intake","testing")').fetchall()
   active=subprocess.run(['systemctl','is-active','coding-worker.service'],capture_output=True,text=True).stdout.strip()
   job=c.execute("SELECT id,updated FROM tasks WHERE status='working' LIMIT 1").fetchone()
   stale=rows and max(r['updated'] for r in rows)<now-90
   stalled=job and job['updated']<now-600
   if active!='active' or stale or stalled:
    old=c.execute("SELECT value FROM settings WHERE key='watchdog_restarts'").fetchone();restarts=json.loads(old[0]) if old else []
    restarts=[n for n in restarts if n>now-3600]
    if len(restarts)<3:
     restarts.append(now);c.execute("INSERT INTO settings VALUES('watchdog_restarts',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(restarts),))
     audit(c,'watchdog','restart',job['id'] if job else None,'Worker unhealthy or stalled')
     subprocess.run(['systemctl','restart','coding-worker.service'],timeout=30,check=False)
    else:heartbeat(c,'watchdog','restart_limit')
  time.sleep(20)
if __name__=='__main__':main()
