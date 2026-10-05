"""Model-facing operations are confined to one task's project."""
import hashlib, http.client, ipaddress, json, os, re, socket, ssl, subprocess, tempfile, uuid, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from process_control import kill_tree

class Project:
    def __init__(self,root,task,cfg):
        if not re.fullmatch('[0-9a-f]{32}',task):raise ValueError('Invalid task ID')
        self.base=Path(root)/'projects'/task;self.base.mkdir(parents=True,exist_ok=True)
        self.cfg=cfg;self.root=Path(root);self.task=task
    def path(self,name):
        if not isinstance(name,str) or '\\' in name or '\x00' in name or len(name)>240:raise ValueError('Invalid path')
        p=PurePosixPath(name)
        if p.is_absolute() or not p.parts or any(x in ('.','..') or (x.startswith('.') and x not in ('.gitignore','.env.example')) for x in p.parts):raise ValueError('Use relative project paths; secrets and hidden tool configs are excluded')
        candidate=self.base.joinpath(*p.parts)
        if any(p.is_symlink() for p in [candidate,*candidate.parents] if p!=self.base.parent):raise ValueError('Symlink rejected')
        if not candidate.resolve().is_relative_to(self.base.resolve()):raise ValueError('Path escapes project')
        return candidate
    def files(self):
        result=[];total=0
        for p in self.base.rglob('*'):
            relative=p.relative_to(self.base)
            if any(part in ('__pycache__','.git','.pytest_cache','.mypy_cache','.ruff_cache') for part in relative.parts):continue
            if p.is_symlink():raise ValueError('Project contains a symlink')
            if p.is_file():
                size=p.stat().st_size;total+=size
                result.append({'path':p.relative_to(self.base).as_posix(),'size':size})
            if len(result)>1000 or total>self.cfg['max_project_bytes']:raise ValueError('Project size limit exceeded')
        return sorted(result,key=lambda x:x['path'])
    def write(self,files):
        if not isinstance(files,list) or not 1<=len(files)<=20:raise ValueError('Write 1–20 files')
        validated=[]
        for f in files:
            p=self.path(f['path']);content=f['content']
            if not isinstance(content,str) or len(content.encode())>self.cfg['max_file_bytes']:raise ValueError('File too large')
            validated.append((p,content))
        total=sum(x['size'] for x in self.files())+sum(len(s.encode())-(p.stat().st_size if p.exists() else 0) for p,s in validated)
        if total>self.cfg['max_project_bytes']:raise ValueError('Project size limit exceeded')
        for p,s in validated:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
        return {'written':[p.relative_to(self.base).as_posix() for p,s in validated]}
    def read(self,name):
        p=self.path(name)
        if p.stat().st_size>self.cfg['max_file_bytes']:raise ValueError('File too large to read')
        return p.read_text(encoding='utf-8')
    def command(self,argv,browser=None):
        if not isinstance(argv,list) or not 1<=len(argv)<=32 or not all(isinstance(a,str) and len(a)<=1000 and '\x00' not in a for a in argv):raise ValueError('Invalid argv')
        if argv[0] not in ('python3','node','php','npm','git','sh','bash','pytest','dart','flutter','javac'):raise ValueError('Unsupported executable')
        # A generated command can use a shell only inside this network/filesystem sandbox.
        request={'project':str(self.base),'argv':argv,'browser':browser,'timeout':self.cfg['command_timeout'],'runner_user':self.cfg['runner_user']}
        with tempfile.TemporaryDirectory(prefix='coding-exec-') as tmp:
            request_file=Path(tmp)/'request.json';request_file.write_text(json.dumps(request))
            proc=subprocess.Popen(['/usr/bin/systemd-run','--quiet','--scope','--unit=coding-exec-'+uuid.uuid4().hex[:12],'-p','MemoryMax=2G','-p','MemorySwapMax=0','-p','TasksMax=256','--','/usr/bin/unshare','--net','--','/usr/bin/python3',str(self.root/'exec_sandbox.py'),str(request_file)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:out,err=proc.communicate(timeout=self.cfg['command_timeout']+20)
            except subprocess.TimeoutExpired:kill_tree(proc);raise TimeoutError('Command sandbox deadline exceeded')
        if proc.returncode:raise RuntimeError('Sandbox infrastructure error: '+err[-500:])
        answer=json.loads(out)
        # Executed projects cannot introduce symlinks into subsequent trusted reads.
        self.files();return answer
    def presentation(self,deck,requirement):
        if not requirement or requirement['kind']!='presentation':raise ValueError('No presentation requested')
        if not isinstance(deck,dict) or not isinstance(deck.get('slides'),list) or not 1<=len(deck['slides'])<=40:raise ValueError('Invalid presentation data')
        if requirement.get('slides') is not None and len(deck['slides'])!=requirement['slides']:raise ValueError('Produce exactly the requested number of slides')
        self.write([{'path':'presentation.json','content':json.dumps(deck,ensure_ascii=False)}])
        result=self.command(['node','/opt/coding-artifacts/render_presentation.cjs','presentation.json'])
        if result['exit_code']==0:
            from deliverables import inspect_pptx
            result['presentation']=inspect_pptx(self.path(deck.get('filename','presentation.pptx')),requirement.get('slides'),requirement.get('charts',False),requirement.get('required_topics'))
        return result
    def check_presentation(self,name,requirement):
        if not requirement:raise ValueError('No presentation output contract')
        from deliverables import inspect_pptx
        metadata=inspect_pptx(self.path(name),requirement.get('slides'),requirement.get('charts',False),requirement.get('required_topics'))
        result=self.command(['node','/opt/coding-artifacts/check_presentation.cjs',name])
        try:proof=json.loads(result['stdout'])
        except ValueError:proof={'passed':False,'error':'Renderer did not produce valid evidence'}
        proof.update(metadata);proof['passed']=bool(proof.get('passed') and proof.get('pages')==metadata['slides'] and result['exit_code']==0 and not result['timed_out'])
        proof['preview_sha256s']={f['path']:hashlib.sha256(self.path(f['path']).read_bytes()).hexdigest() for f in self.files() if f['path'].startswith('presentation-preview/') and f['path'].endswith('.png')}
        result['presentation']=proof;return result
    def package(self,destination):
        items=self.files()
        if not items:raise ValueError('No generated project files')
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
            for f in items:
                # Runtime test databases and bytecode are not delivered as application source.
                if f['path'].startswith('image-candidates/'):continue
                if f['path'].endswith(('.pyc','.pyo','.db','.sqlite','.sqlite3','.db-wal','.db-shm','.sqlite-wal','.sqlite-shm','.sqlite3-wal','.sqlite3-shm')):continue
                z.write(self.path(f['path']),f['path'])
        return hashlib.sha256(Path(destination).read_bytes()).hexdigest()

def research(url,cfg,focus=None):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.hostname not in cfg['research_hosts'] or '\\' in url or any(ord(c)<33 for c in url):raise ValueError('Choose an allowed primary documentation HTTPS URL')
    ips={r[4][0] for r in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise ValueError('Non-public research destination')
    class Pinned(http.client.HTTPSConnection):
        def connect(self):self.sock=ssl.create_default_context().wrap_socket(socket.create_connection((sorted(ips)[0],443),15),server_hostname=u.hostname)
    c=Pinned(u.hostname,timeout=15)
    try:
        c.request('GET',(u.path or '/')+('?' + u.query if u.query else ''),headers={'User-Agent':'CodingWorkshop/1.0'})
        r=c.getresponse();data=r.read(1048577)
        if len(data)>1048576:raise ValueError('Documentation response too large')
        content=data.decode(errors='replace')
        if focus:
            if not isinstance(focus,str) or not 2<=len(focus)<=100:raise ValueError('Focus must be a short source-text search term')
            matches=list(re.finditer(re.escape(focus),content,re.I))[:12]
            content='\n...\n'.join(content[max(0,m.start()-700):m.end()+1700] for m in matches) if matches else 'Requested term was not found in source.'
        return {'url':url,'status':r.status,'content':content[:24000],'redirect_followed':False}
    finally:c.close()
