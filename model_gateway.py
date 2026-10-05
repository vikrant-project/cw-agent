"""UNIX CONNECT broker for CLI sandboxes. Only exact provider scope origins pass."""
import os
import select
import socket
import socketserver
from pathlib import Path
from state import ROOT, audit, config, connect
from scope_transport import Transport
from process_control import proxy_idle_timeout

SOCKET_PATH=os.environ.get('AGENT_MODEL_PROXY_SOCKET','/run/coding-workshop/model-proxy.sock')

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        c=connect(self.server.root)
        try:
            line=self.rfile.readline(4097)
            if len(line)>4096: raise ValueError('Oversized CONNECT line')
            method,authority,version=line.decode('ascii').strip().split(' ')
            if method!='CONNECT' or version!='HTTP/1.1': raise ValueError('CONNECT only')
            total=0
            while True:
                line=self.rfile.readline(4097); total+=len(line)
                if total>16384: raise ValueError('Oversized headers')
                if line in (b'\r\n',b'\n'): break
                if not line: raise ValueError('Incomplete headers')
            # Userinfo, URL paths and queries cannot be smuggled through CONNECT authority.
            if any(ch in authority for ch in '/@?#\\'): raise ValueError('Malformed authority')
            cfg=config(self.server.root)
            u,host,port,ip,rule=Transport(self.server.root,c,cfg).check('https://'+authority,'provider')
            if port!=443: raise ValueError('Provider TLS only')
            upstream=socket.create_connection((ip,port),timeout=20)
            self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n'); self.wfile.flush()
            with upstream:
                peers=[self.connection,upstream]
                while True:
                    ready,_,_=select.select(peers,[],[],proxy_idle_timeout(cfg['model_timeout']))
                    if not ready: break
                    for source in ready:
                        data=source.recv(65536)
                        if not data: return
                        (upstream if source is self.connection else self.connection).sendall(data)
        except Exception as exc:
            import re
            safe_authority=authority if 'authority' in locals() and re.fullmatch(r'[a-zA-Z0-9.:-]{1,253}',authority) else ''
            audit(c,'model-gateway','provider_block',safe_authority,detail=type(exc).__name__)
            try: self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
            except OSError: pass
        finally: c.close()

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True

def serve(root=ROOT,path=SOCKET_PATH):
    path=Path(path); path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.exists(): path.unlink()
    with Server(str(path),Handler) as server:
        os.chmod(path,0o600); server.root=Path(root); server.serve_forever()

if __name__=='__main__': serve()
