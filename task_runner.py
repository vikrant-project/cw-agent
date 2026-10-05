import sys,time
from state import ROOT,connect,audit
from worker import process
if __name__=='__main__':
 c=connect();task=dict(c.execute("SELECT * FROM tasks WHERE id=? AND status='working'",(sys.argv[1],)).fetchone())
 try:process(ROOT,c,task)
 except Exception as e:
  error=str(e)[:1200];audit(c,'coordinator','failed',task['id'],error)
  c.execute("UPDATE tasks SET status=CASE WHEN cancel=1 THEN 'cancelled' ELSE 'needs_attention' END,error=?,role=NULL,updated=? WHERE id=?",(error,time.time(),task['id']))
  c.execute("INSERT INTO notifications(task_id) VALUES(?) ON CONFLICT(task_id) DO UPDATE SET status='pending',error=NULL WHERE notifications.status NOT IN ('sending','uncertain')",(task['id'],))
 finally:c.close()
