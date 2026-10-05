"""Kill a trusted subprocess tree, including children that create their own sessions."""
import os
from pathlib import Path
import signal
import time
from contextlib import contextmanager

def proxy_idle_timeout(model_timeout):
    seconds=int(model_timeout)
    if seconds<=0:raise ValueError('Model timeout must be positive')
    return max(45,seconds+30)

@contextmanager
def account_admission(account,timeout,cancelled=lambda:False,on_wait=lambda:None,directory='/run/agy-account-locks'):
    """Wait before starting a model timer or reserving a model submission."""
    import fcntl,re
    if not re.fullmatch('[a-z0-9_-]+',account):raise ValueError('Invalid account lock name')
    root=Path(directory);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(root/(account+'.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    deadline=time.monotonic()+timeout;waiting=False
    try:
        while True:
            if cancelled():raise RuntimeError('Task cancelled')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if not waiting:on_wait();waiting=True
                if time.monotonic()>=deadline:raise RuntimeError('CLI process failed: existing account remains busy; bounded admission wait expired')
                time.sleep(min(.2,max(0,deadline-time.monotonic())))
        yield fd
    finally:os.close(fd)

def validate_account_fd(fd,account,directory='/run/agy-account-locks'):
    import stat
    expected=(Path(directory)/(account+'.lock')).resolve()
    if not stat.S_ISREG(os.fstat(fd).st_mode) or Path(os.readlink('/proc/self/fd/'+str(fd))).resolve()!=expected:
        raise RuntimeError('Invalid inherited account admission lock')

def identity(pid):
    raw=Path('/proc')/str(pid)/'stat'
    try:
        # comm can contain spaces/parentheses: split after its closing parenthesis.
        fields=raw.read_text().rsplit(')',1)[1].split()
        return int(fields[1]),fields[19] # PPID and kernel start time
    except (OSError,IndexError,ValueError): return None

def kill_tree(process):
    snapshots={}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            value=identity(int(path.name))
            if value: snapshots[int(path.name)]=value
    selected=[process.pid]; cursor=0
    while cursor<len(selected):
        parent=selected[cursor]; cursor+=1
        selected.extend(pid for pid,(ppid,started) in snapshots.items() if ppid==parent and pid not in selected)
    for pid in reversed(selected):
        if pid not in snapshots or identity(pid)!=snapshots[pid]: continue
        try: os.kill(pid,signal.SIGKILL)
        except ProcessLookupError: pass
    process.wait(timeout=5)
