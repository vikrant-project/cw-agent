"""Trusted namespace launcher. No host credentials, root writes, or external network."""
import json, os, pwd, resource, shutil, subprocess, sys, tempfile
from pathlib import Path
from process_control import kill_tree

def limits():
    # Memory uses the parent systemd cgroup. Chromium needs a large virtual address space.
    for key,value in ((resource.RLIMIT_CPU,90),(resource.RLIMIT_FSIZE,8*1024**2),(resource.RLIMIT_NOFILE,256),(resource.RLIMIT_NPROC,256)):
        resource.setrlimit(key,(value,value))
def main(request):
    if os.geteuid()!=0 or os.readlink('/proc/self/ns/net')==os.readlink('/proc/1/ns/net'):raise RuntimeError('Network isolation required')
    subprocess.run(['/usr/sbin/ip','link','set','lo','up'],check=True)
    binary=shutil.which(request['argv'][0])
    if not binary:return {'exit_code':127,'timed_out':False,'stdout':'','stderr':'Requested runtime is not installed','network':'isolated','filesystem':'task-only'}
    request['argv'][0]=str(Path(binary).resolve())
    account=pwd.getpwnam(request['runner_user']);project=Path(request['project'])
    if project.is_symlink():raise ValueError('Symlink project')
    for p in [project,*project.rglob('*')]:
        if p.is_symlink():raise ValueError('Symlink project entry')
        os.chown(p,account.pw_uid,account.pw_gid);p.chmod(0o700 if p.is_dir() else 0o600)
    # bwrap is launched as the unprivileged execution account, not as root.
    argv=['/usr/sbin/runuser','-u',account.pw_name,'--','/usr/bin/bwrap','--die-with-parent','--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts','--cap-drop','ALL',
          '--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--symlink','usr/bin','/bin','--symlink','usr/sbin','/sbin',
          '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run','--dir','/home','--dir','/etc',
          '--bind',str(project),'/project','--chdir','/project','--clearenv','--setenv','PATH','/usr/local/bin:/usr/bin:/bin','--setenv','HOME','/tmp','--setenv','LANG','C.UTF-8']
    if Path('/lib64').exists():argv[5:5]=['--ro-bind','/lib64','/lib64']
    for folder in ('/etc/php','/etc/fonts','/etc/libreoffice','/opt/coding-artifacts'):
        if Path(folder).exists():argv+=['--ro-bind',folder,folder]
    if request.get('browser') is not None:
        argv+=['--ro-bind','/opt/coding-runtime','/opt/coding-runtime','--setenv','PLAYWRIGHT_BROWSERS_PATH','/opt/coding-runtime/browsers',
               '/opt/coding-runtime/venv/bin/python','/opt/coding-runtime/browser_runner.py',json.dumps({'server':request['argv'],'steps':request['browser']})]
    else:argv+=request['argv']
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        proc=subprocess.Popen(argv,stdout=out,stderr=err,preexec_fn=limits)
        timed_out=False
        try:proc.wait(timeout=request['timeout'])
        except subprocess.TimeoutExpired:timed_out=True;kill_tree(proc)
        out.seek(0);err.seek(0)
        result={'exit_code':proc.returncode,'timed_out':timed_out,'stdout':out.read(24000).decode(errors='replace'),'stderr':err.read(8000).decode(errors='replace'),'network':'isolated','filesystem':'task-only'}
        if request.get('browser') is not None:
            try:result['browser']=json.loads(result['stdout'])
            except ValueError:result['browser']={'passed':False,'error':'Browser harness did not return evidence'}
        return result
if __name__=='__main__':print(json.dumps(main(json.loads(Path(sys.argv[1]).read_text()))))
