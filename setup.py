"""Initialize a deployment without importing any credentials into source control."""
import json,os,pwd,secrets,shutil,subprocess
from pathlib import Path
from state import initialize,ROLE_USERS

def main():
 root=Path(__file__).resolve().parent
 if os.geteuid()!=0 or root!=Path('/opt/coding-workshop'):raise RuntimeError('Run as root after placing source at /opt/coding-workshop')
 missing=[name for name in ('php','node','bwrap','unshare','caddy','systemd-run') if not shutil.which(name)]
 if missing:raise RuntimeError('Install required tools first: '+', '.join(missing))
 if not Path('/usr/local/bin/agy').is_file():raise RuntimeError('Install and log in to AntiGravity CLI first')
 for username in ROLE_USERS.values():
  account=pwd.getpwnam(username)
  if not (Path(account.pw_dir)/'.gemini/antigravity-cli/antigravity-oauth-token').exists():raise RuntimeError('Required model account is not logged in: '+username)
 for username in ('coding-portal','coding-runner','coding-whatsapp'):
  try:pwd.getpwnam(username)
  except KeyError:subprocess.run(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin',username],check=True)
 portal=pwd.getpwnam('coding-portal');wa=pwd.getpwnam('coding-whatsapp')
 for folder,mode,uid,gid in [('private',0o700,0,0),('projects',0o711,0,0),('portal-data',0o2770,0,portal.pw_gid),('downloads',0o2750,0,portal.pw_gid),('bridge-private',0o700,wa.pw_uid,wa.pw_gid)]:
  p=root/folder;p.mkdir(exist_ok=True);p.chmod(mode);os.chown(p,uid,gid)
 for name,token in [('private/bridge.key',secrets.token_hex(32)),('portal-data/invite.key',secrets.token_hex(16)),('bridge-private/wa-encryption.key',secrets.token_hex(32))]:
  p=root/name
  if not p.exists():p.write_text(token)
  owner=wa if name.startswith('bridge-private') else portal if name.startswith('portal-data') else None
  p.chmod(0o640 if name.startswith('portal-data') else 0o600);os.chown(p,wa.pw_uid if name.startswith('bridge-private') else 0,owner.pw_gid if owner else 0)
 secret=root/'bridge-private/bridge.key'
 if not secret.exists():shutil.copyfile(root/'private/bridge.key',secret)
 secret.chmod(0o600);os.chown(secret,wa.pw_uid,wa.pw_gid)
 initialize(root)
 for p in (root/'portal-data').glob('portal.sqlite3*'):p.chmod(0o660);os.chown(p,0,portal.pw_gid)
 print(json.dumps({'initialized':True,'model_accounts':10,'services_started':False,'invitation_file':'/opt/coding-workshop/portal-data/invite.key'}))
if __name__=='__main__':main()
