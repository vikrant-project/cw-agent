"""Durable, tenant-owned work queue. Models never receive the portal database."""
import json, os, sqlite3, time, uuid
from pathlib import Path

ROOT=Path(os.environ.get('CODING_ROOT','/opt/coding-workshop'))
ROLES=('intake','research','architect','backend','frontend','mobile','testing','debugging','review','release')
ROLE_USERS=dict(zip(ROLES,('agy-specification','agy-research','agy-planner','agy-implementation','agy-documentation','agy-android-verification','agy-testing','agy-verification','agy-defensive-review','agy-coordinator')))

def config(root=ROOT): return json.loads((Path(root)/'config.json').read_text())
class Database(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()
def connect(root=ROOT):
    c=sqlite3.connect(Path(root)/'portal-data'/'portal.sqlite3',timeout=30,isolation_level=None,factory=Database)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=30000');c.execute('PRAGMA foreign_keys=ON');return c
def initialize(root=ROOT):
    root=Path(root);(root/'private').mkdir(parents=True,exist_ok=True)
    (root/'portal-data').mkdir(parents=True,exist_ok=True)
    with connect(root) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),prompt TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',role TEXT,cycle INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL,error TEXT,summary TEXT,model_calls INTEGER NOT NULL DEFAULT 0,cancel INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,task_id TEXT REFERENCES tasks(id),role TEXT,kind TEXT,detail TEXT,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS deliverables(task_id TEXT REFERENCES tasks(id),path TEXT,mime TEXT,size INTEGER,PRIMARY KEY(task_id,path));
        CREATE TABLE IF NOT EXISTS artifacts(task_id TEXT PRIMARY KEY REFERENCES tasks(id),sha256 TEXT,size INTEGER,created REAL);
        CREATE TABLE IF NOT EXISTS whatsapp(user_id TEXT PRIMARY KEY REFERENCES users(id),status TEXT DEFAULT 'disconnected',qr TEXT,qr_expires REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS messages(user_id TEXT,remote_id TEXT,task_id TEXT,PRIMARY KEY(user_id,remote_id));
        CREATE TABLE IF NOT EXISTS notifications(task_id TEXT PRIMARY KEY REFERENCES tasks(id),status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,error TEXT);
        CREATE TABLE IF NOT EXISTS heartbeats(role TEXT PRIMARY KEY,status TEXT,task_id TEXT,updated REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY,count INTEGER,expires REAL);
        ''')
        if 'mode' not in {r[1] for r in c.execute('PRAGMA table_info(tasks)')}:c.execute("ALTER TABLE tasks ADD COLUMN mode TEXT DEFAULT 'pending'")
        if 'team' not in {r[1] for r in c.execute('PRAGMA table_info(tasks)')}:c.execute("ALTER TABLE tasks ADD COLUMN team TEXT DEFAULT '[]'")
        if 'parent_id' not in {r[1] for r in c.execute('PRAGMA table_info(tasks)')}:c.execute('ALTER TABLE tasks ADD COLUMN parent_id TEXT REFERENCES tasks(id)')
        if 'progress' not in {r[1] for r in c.execute('PRAGMA table_info(tasks)')}:c.execute("ALTER TABLE tasks ADD COLUMN progress TEXT DEFAULT '{}'")
        if 'recovery_attempts' not in {r[1] for r in c.execute('PRAGMA table_info(tasks)')}:c.execute('ALTER TABLE tasks ADD COLUMN recovery_attempts INTEGER DEFAULT 0')

def recover_interrupted(c,cfg,exclude=()):
    """One automatic crash recovery; reuse source, never stale successful evidence."""
    rows=c.execute("SELECT id,cancel,model_calls,recovery_attempts FROM tasks WHERE status='working'").fetchall()
    recovered=0
    for row in rows:
        if row['id'] in exclude:continue
        recovered+=1
        retry=not row['cancel'] and row['recovery_attempts']<1 and row['model_calls']<cfg['max_model_calls']
        status='queued' if retry else ('cancelled' if row['cancel'] else 'needs_attention')
        error='Worker interrupted; automatically replanning from saved files with fresh verification' if retry else 'Worker interrupted again or recovery budget exhausted; saved source remains available'
        c.execute('UPDATE tasks SET status=?,role=NULL,recovery_attempts=recovery_attempts+1,error=?,updated=? WHERE id=?',(status,error,time.time(),row['id']))
        audit(c,'coordinator','recovery_queued' if retry else 'recovery_exhausted',row['id'],error)
    return recovered
def audit(c,role,kind,task_id=None,detail=''):
    # Provider transport audit does not create foreign-key-invalid task IDs.
    if task_id and not c.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():task_id=None
    c.execute('INSERT INTO events(task_id,role,kind,detail,created) VALUES(?,?,?,?,?)',(task_id,role,kind,str(detail)[:12000],time.time()))
def heartbeat(c,role,status,task_id=None):
    c.execute('INSERT INTO heartbeats VALUES(?,?,?,?) ON CONFLICT(role) DO UPDATE SET status=excluded.status,task_id=excluded.task_id,updated=excluded.updated',(role,status,task_id,time.time()))
def submit(c,user_id,prompt,message_id=None,parent_id=None):
    if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=12000:raise ValueError('Task must contain 1–12,000 characters')
    c.execute('BEGIN IMMEDIATE')
    try:
        if message_id:
            old=c.execute('SELECT task_id FROM messages WHERE user_id=? AND remote_id=?',(user_id,message_id)).fetchone()
            if old:c.execute('COMMIT');return old[0]
        if not c.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone():raise ValueError('Unknown user')
        if parent_id and not c.execute('SELECT 1 FROM tasks WHERE id=? AND user_id=?',(parent_id,user_id)).fetchone():raise ValueError('Parent project does not belong to this user')
        if c.execute("SELECT count(*) FROM tasks WHERE user_id=? AND status IN ('queued','working')",(user_id,)).fetchone()[0]>=3:raise ValueError('Three tasks already queued or working')
        task=uuid.uuid4().hex;now=time.time()
        c.execute('INSERT INTO tasks(id,user_id,prompt,created,updated,parent_id) VALUES(?,?,?,?,?,?)',(task,user_id,prompt.strip(),now,now,parent_id))
        if message_id:c.execute('INSERT INTO messages VALUES(?,?,?)',(user_id,message_id,task))
        c.execute('COMMIT');return task
    except BaseException:c.execute('ROLLBACK');raise
def claim(c,max_active=2):
    c.execute('BEGIN IMMEDIATE')
    if c.execute("SELECT count(*) FROM tasks WHERE status='working'").fetchone()[0]>=max_active:
        c.execute('COMMIT');return None
    row=c.execute("SELECT * FROM tasks WHERE status='queued' AND cancel=0 ORDER BY created LIMIT 1").fetchone()
    if row:c.execute("UPDATE tasks SET status='working',updated=?,error=NULL WHERE id=?",(time.time(),row['id']))
    c.execute('COMMIT');return dict(row) if row else None
def reserve(c,cfg,task_id,purpose):
    if purpose!='model':return
    c.execute('BEGIN IMMEDIATE')
    try:
        row=c.execute('SELECT model_calls,cancel FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row or row['cancel']:raise RuntimeError('Task cancelled')
        if row['model_calls']>=cfg['max_model_calls']:raise RuntimeError('Task model budget reached')
        day=int(time.time()//86400)*86400
        actual=c.execute("SELECT count(*) FROM events WHERE kind='model_started' AND created>=?",(day,)).fetchone()[0]
        key='model-day:'+str(day)
        c.execute('INSERT OR IGNORE INTO rate_limits VALUES(?,?,?)',(key,actual,day+86400))
        tickets=max(actual,c.execute('SELECT count FROM rate_limits WHERE key=?',(key,)).fetchone()[0])
        if tickets>=cfg.get('daily_model_calls',600):raise RuntimeError('Daily model budget reached')
        c.execute('UPDATE rate_limits SET count=? WHERE key=?',(tickets+1,key))
        c.execute('UPDATE tasks SET model_calls=model_calls+1,updated=? WHERE id=?',(time.time(),task_id))
        c.execute('COMMIT')
    except BaseException:c.execute('ROLLBACK');raise

def stamp():return str(time.time())
