"""Called under unshare --net by the trusted queue worker, never directly by a model."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import sys
import socket
import socketserver
import subprocess
import tempfile
import threading
from model_gateway import SOCKET_PATH
from state import ROOT,ROLES,config
from process_control import proxy_idle_timeout
from skill_loader import prepare_workspace,prepare_native_workspace,native_session_instruction

from state import ROLE_USERS
from action_schema import ACTION_SCHEMA,WIRE_SCHEMA,WIRE_OBJECT_SCHEMA,phase_schema


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        import select
        upstream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            upstream.connect(SOCKET_PATH)
            peers=[upstream,self.request]
            while True:
                ready,_,_=select.select(peers,[],[],self.server.idle_timeout)
                if not ready: return
                for source in ready:
                    data=source.recv(65536)
                    if not data: return
                    (self.request if source is upstream else upstream).sendall(data)
        finally: upstream.close()

class RelayServer(socketserver.ThreadingMixIn,socketserver.TCPServer):
    daemon_threads=True

def _launch(role,model,media_request=None,decision_payload=False,decision_object=False):
    if os.geteuid()!=0: raise RuntimeError('Trusted launcher needs root for network namespace setup')
    # Check unshare actually created a distinct network namespace. Refuse host namespace.
    if os.readlink('/proc/self/ns/net')==os.readlink('/proc/1/ns/net'):
        raise RuntimeError('CLI must run inside an isolated network namespace')
    subprocess.run(['/usr/sbin/ip','link','set','lo','up'],check=True)
    account=pwd.getpwnam(ROLE_USERS[role])
    with tempfile.TemporaryDirectory(prefix='agent-cli-',dir=os.environ.get('AGENT_MODEL_TEMP_PARENT')) as tmp:
        os.chmod(tmp,0o711)
        home=Path(tmp)/'home'; credentials=home/'.gemini'/'antigravity-cli'
        workspace=prepare_workspace(ROOT,role,Path(tmp)/'workspace')
        media=json.loads(Path(media_request).read_text()) if media_request else None
        if media:
            workspace=Path(media['workspace']).resolve()
            if not workspace.is_relative_to((ROOT/'media-staging').resolve()) or workspace.is_symlink():raise ValueError('Invalid trusted media staging directory')
            prepare_native_workspace(ROOT,media['mode'],workspace,account.pw_uid,account.pw_gid)
        credentials.mkdir(mode=0o700,parents=True); home.chmod(0o700)
        original=Path(account.pw_dir)/'.gemini'/'antigravity-cli'
        hosts=Path(tmp)/'hosts'; hosts.write_text('127.0.0.1 localhost\n::1 localhost\n'); hosts.chmod(0o644)
        # No historical conversations, project configs, MCP tools, or host SSH credentials.
        for name in ('antigravity-oauth-token','installation_id','jetski_state.pbtxt'):
            path=original/name
            if path.exists():
                shutil.copy2(path,credentials/name); (credentials/name).chmod(0o600)
        permissions={'deny':['command(*)','mcp(*)','read_url(*)','execute_url(*)','read_file('+str(account.pw_dir)+'/.gemini/)'],'allow':['read_file(/workspace/)','write_file(/workspace/)']}
        (credentials/'settings.json').write_text(json.dumps({'permissions':permissions}))
        mcp=home/'.gemini'/'config'; mcp.mkdir(parents=True)
        if not media:
            agent_dir=mcp/'agents';agent_dir.mkdir()
            definition=(ROOT/'agents'/'cw-controller.md').read_text()
            if decision_object:
                definition=definition.split("For the native finish tool's output schema")[0]+"\nFor native finish, put the COMPLETE external action OBJECT in the required payload field, including ALL parameters. Do not JSON-serialize it to a string. Keep nested file contents, deck data and acceptance criteria intact.\n"
            elif not decision_payload:definition=definition.split("For the native finish tool's output schema")[0]
            (agent_dir/'cw-controller.md').write_text(definition)
        (mcp/'mcp_config.json').write_text('{"mcpServers":{}}')
        for path in [home,*home.rglob('*')]: os.chown(path,account.pw_uid,account.pw_gid)
        with RelayServer(('127.0.0.1',0),Relay) as relay:
            relay.idle_timeout=proxy_idle_timeout(config(ROOT)['model_timeout'])
            threading.Thread(target=relay.serve_forever,daemon=True).start()
            proxy='http://127.0.0.1:'+str(relay.server_address[1])
            argv=['/usr/bin/bwrap','--die-with-parent','--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts',
                  '--cap-drop','ALL',
                  '--ro-bind','/usr','/usr','--ro-bind','/lib','/lib',
                  '--symlink','usr/bin','/bin','--symlink','usr/sbin','/sbin',
                  '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run',
                  '--dir','/etc','--ro-bind','/etc/ssl','/etc/ssl',
                  '--ro-bind',str(hosts),'/etc/hosts',
                  '--ro-bind','/etc/passwd','/etc/passwd','--ro-bind','/etc/group','/etc/group',
                  '--dir','/home','--bind',str(home),account.pw_dir,
                  '--ro-bind',str(workspace),'/workspace','--chdir','/workspace','--clearenv',
                  '--setenv','PATH','/usr/local/bin:/usr/bin:/bin',
                  '--setenv','HOME',account.pw_dir,'--setenv','HTTPS_PROXY',proxy,
                  '--setenv','HTTP_PROXY',proxy,'--setenv','https_proxy',proxy,
                  '--setenv','NO_PROXY','localhost,127.0.0.1',
                  '--uid',str(account.pw_uid),'--gid',str(account.pw_gid),
                  '/usr/local/bin/agy','--mode','accept-edits' if media and media['mode']=='generate' else 'plan','--sandbox',
                  '--model',model,'--output-format','stream-json','--input-format','stream-json',
                  '--print-timeout',os.environ.get('AGENT_MODEL_PRINT_TIMEOUT','300s')]
            if not media:argv+=['--agent','cw-controller','--disable-slash-commands']
            if media:
                position=argv.index(str(workspace));argv[position-1]='--bind' if media['mode']=='generate' else '--ro-bind'
                argv+=['--add-dir','/workspace']
            schema_path=home/'response-schema.json';schema_path.write_text(json.dumps(media['schema'] if media else (WIRE_OBJECT_SCHEMA if decision_object else (WIRE_SCHEMA if decision_payload else ACTION_SCHEMA))));schema_path.chmod(0o644)
            argv+=['--json-schema',str(Path(account.pw_dir)/'response-schema.json')]
            if Path('/lib64').exists(): argv[1:1]=['--ro-bind','/lib64','/lib64']
            argv=['/usr/sbin/runuser','-u',account.pw_name,'--']+argv
            try:
                if media:
                    message=json.loads(sys.stdin.readline())
                    message['message']['content']=native_session_instruction(ROOT,media['mode'],message['message']['content'])
                    if media['mode']=='inspect':
                        message['message']['content']='REVIEW SCOPE: This is a partial batch from a larger artifact. Open every supplied image. Judge only the visible pixels and content of these images. Do not reject because other slides/files are absent or because each individual slide does not contain every requested visual. Overall topic coverage is assessed separately by the main reviewer. Speaker notes, citations stored in notes and file metadata are outside this pixel-only check; do not claim they are missing because they are not visible in a slide image. The main reviewer checks those from actual artifact data. Prior review issues and repair notes are historical hypotheses, not proof that those defects persist. Judge the CURRENT supplied pixels independently. For each actual defect identify the input filename and visible location; do not repeat a past issue that is no longer visible. Report genuine visible defects. Account for normal perspective and occlusion: a hidden far-side wheel or partially hidden brake caliper is not automatically missing; assess physical plausibility and report uncertainty separately. Do not invent identifiable logos, text or exact production-model identity from generic styling. Specific duplication, recognizable branding and malformed geometry still fail.\n'+message['message']['content']
                    return subprocess.run(argv,input=json.dumps(message)+'\n',text=True).returncode
                if decision_object:
                    message=json.loads(sys.stdin.readline())
                    content=message.get('message',{}).get('content','')
                    if isinstance(content,str) and 'UNTRUSTED TASK DATA' in content:
                        try:context=json.loads(content.rsplit('\n',1)[-1])
                        except ValueError:context=None
                        if isinstance(context,dict) and context.get('role')==role:
                            current_schema,guidance=phase_schema(role,context);schema_path.write_text(json.dumps(current_schema))
                            message['message']['content']='CONTROLLER PHASE: '+guidance+'\n'+content
                    return subprocess.run(argv,input=json.dumps(message)+'\n',text=True).returncode
                return subprocess.call(argv)
            finally:
                relay.shutdown()
                if media and media['mode']=='generate':
                    from media import inspect_image
                    import hashlib
                    export=Path(media['export']).resolve()
                    if not export.is_relative_to((ROOT/'private').resolve()) or export.is_symlink():raise ValueError('Invalid private media export directory')
                    manifest={'images':[],'errors':[]};known={}
                    for path in home.rglob('*'):
                        if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'):continue
                        try:
                            source=path.resolve()
                            if not source.is_relative_to(home.resolve()) or not source.is_file() or source.stat().st_size>16*1024**2:continue
                            meta=inspect_image(source,{'min_width':1,'min_height':1,'allow_extension_mismatch':True})
                            uri=str(Path(account.pw_dir)/path.relative_to(home))
                            if meta['sha256'] in known:
                                known[meta['sha256']]['source_paths'].append(uri);continue
                            if len(known)>=4:continue
                            name=str(len(known))+{'JPEG':'.jpg','PNG':'.png','WEBP':'.webp'}[meta['format']]
                            shutil.copyfile(source,export/name)
                            item={'path':name,'source_paths':[uri],'sha256':meta['sha256'],'width':meta['width'],'height':meta['height']}
                            known[meta['sha256']]=item;manifest['images'].append(item)
                        except (ValueError,OSError):continue
                    for transcript in home.rglob('transcript.jsonl'):
                        if transcript.stat().st_size>2*1024**2:continue
                        for line in transcript.read_text(errors='replace').splitlines():
                            try:record=json.loads(line)
                            except ValueError:continue
                            if record.get('error'):manifest['errors'].append(str(record['error'])[:700])
                    manifest['errors']=manifest['errors'][-8:]
                    (export/'manifest.json').write_text(json.dumps(manifest))
                refreshed=credentials/'antigravity-oauth-token'
                if refreshed.exists() and os.environ.get('AGENT_MODEL_PERSIST_REFRESH','1')=='1':
                    pending=original/('antigravity-oauth-token.coding-refresh-'+str(os.getpid()))
                    try:
                        shutil.copyfile(refreshed,pending);pending.chmod(0o600)
                        os.chown(pending,account.pw_uid,account.pw_gid)
                        os.replace(pending,original/'antigravity-oauth-token')
                    finally:pending.unlink(missing_ok=True)

def launch(role,model,media_request=None,decision_payload=False,decision_object=False):
    import fcntl
    inherited=os.environ.get('AGENT_ACCOUNT_LOCK_FD')
    if inherited is not None:
        from process_control import validate_account_fd
        validate_account_fd(int(inherited),ROLE_USERS[role])
        return _launch(role,model,media_request,decision_payload,decision_object)
    locks=Path('/run/agy-account-locks');locks.mkdir(mode=0o700,exist_ok=True)
    with open(locks/(ROLE_USERS[role]+'.lock'),'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _launch(role,model,media_request,decision_payload,decision_object)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--role',choices=ROLES,required=True); p.add_argument('--model',required=True)
    p.add_argument('--media-request');p.add_argument('--decision-payload',action='store_true');p.add_argument('--decision-object',action='store_true')
    args=p.parse_args(); raise SystemExit(launch(args.role,args.model,args.media_request,args.decision_payload,args.decision_object))
