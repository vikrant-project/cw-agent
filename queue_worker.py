"""Second bounded queue lane; uses the same autonomous pipeline and quality gates."""
import fcntl,json,subprocess,time
from state import ROOT,connect,config,initialize,claim,audit
from process_control import kill_tree

def main():
    initialize()
    lock=open(ROOT/'private'/'queue-lane.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=connect();key='queue_lane_active'
    previous=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    if previous:
        row=c.execute("SELECT * FROM tasks WHERE id=? AND status='working'",(previous[0],)).fetchone()
        if row:
            retry=not row['cancel'] and row['recovery_attempts']<1 and row['model_calls']<config()['max_model_calls']
            status='queued' if retry else ('cancelled' if row['cancel'] else 'needs_attention')
            reason='Queue lane interrupted; bounded recovery retains source and model budget' if retry else 'Queue lane recovery exhausted; saved work needs attention'
            c.execute('UPDATE tasks SET status=?,role=NULL,recovery_attempts=recovery_attempts+1,error=?,updated=? WHERE id=?',(status,reason,time.time(),row['id']))
            audit(c,'coordinator','queue_lane_recovery',row['id'],reason)
        c.execute('DELETE FROM settings WHERE key=?',(key,))
    while True:
        task=claim(c,max_active=config().get('max_concurrent_tasks',2))
        if not task:time.sleep(2);continue
        c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,task['id']))
        try:
            logdir=ROOT/'private'/'task-logs';logdir.mkdir(exist_ok=True)
            with open(logdir/(task['id']+'.log'),'w') as log:
                proc=subprocess.Popen(['/usr/bin/python3',str(ROOT/'task_runner.py'),task['id']],stdout=log,stderr=log)
                try:proc.wait(timeout=config()['task_deadline']+config()['model_timeout']+60)
                except subprocess.TimeoutExpired:kill_tree(proc);raise TimeoutError('Task exceeded hard deadline')
            if proc.returncode:raise RuntimeError('Task process failed; private operator log retained')
        except Exception as error:
            reason=str(error)[:1200];audit(c,'coordinator','failed',task['id'],reason)
            c.execute("UPDATE tasks SET status=CASE WHEN cancel=1 THEN 'cancelled' ELSE 'needs_attention' END,role=NULL,error=?,updated=? WHERE id=?",(reason,time.time(),task['id']))
            c.execute("INSERT INTO notifications(task_id) VALUES(?) ON CONFLICT(task_id) DO UPDATE SET status='pending',error=NULL WHERE notifications.status NOT IN ('sending','uncertain')",(task['id'],))
        finally:
            c.execute('DELETE FROM settings WHERE key=? AND value=?',(key,task['id']))
            c.execute("UPDATE heartbeats SET status='idle',task_id=NULL,updated=? WHERE task_id=?",(time.time(),task['id']))

if __name__=='__main__':main()
