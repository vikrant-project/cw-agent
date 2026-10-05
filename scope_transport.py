"""The only target/model HTTP transport: exact origins, pinned IPs, no redirects/proxies."""
import base64
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from state import audit, reserve, stamp

class ScopeBlocked(RuntimeError): pass

class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host,port,timeout=timeout); self.ip=ip
    def connect(self):
        self.sock=socket.create_connection((self.ip,self.port),self.timeout)

class PinnedHTTPS(PinnedHTTP):
    def connect(self):
        super().connect()
        self.sock=ssl.create_default_context().wrap_socket(self.sock,server_hostname=self.host)

class Transport:
    def __init__(self,root,c,cfg):
        self.root=Path(root); self.c=c; self.cfg=cfg

    def check(self,url,purpose):
        try:
            u=urlsplit(url)
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.fragment:
                raise ValueError('Invalid origin')
            if any(ord(x)<33 or x=='\\' for x in url): raise ValueError('Malformed URL')
            host=u.hostname.lower().encode('idna').decode()
            port=u.port or (443 if u.scheme=='https' else 80)
            scope=json.loads((self.root/'scope.json').read_text())
            matches=[r for r in scope['allowed'] if r['hostname']==host and r['port']==port
                     and r['scheme']==u.scheme and r['purpose']==purpose]
            if len(matches)!=1: raise ValueError('Origin not explicitly allowed')
            rule=matches[0]
            ips={str(ipaddress.ip_address(ip)) for ip in rule['ips']}
            resolved={str(ipaddress.ip_address(r[4][0])) for r in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
            if purpose=='provider' and rule.get('dns_policy')=='public-provider':
                if not resolved or any(not ipaddress.ip_address(ip).is_global for ip in resolved):
                    raise ValueError('Provider DNS resolved to non-public IP')
            elif not ips or not resolved or not resolved<=ips:
                raise ValueError('DNS result outside allowed IP pins')
            if purpose=='model' and any(not ipaddress.ip_address(ip).is_loopback for ip in ips):
                raise ValueError('Local model service must use loopback')
            return u,host,port,sorted(resolved)[0],rule
        except (ValueError,KeyError,OSError,TypeError) as exc:
            # Log only origin hash: URLs can contain credentials in query strings.
            audit(self.c,'transport','scope_block',hashlib.sha256(url.encode()).hexdigest(),type(exc).__name__)
            raise ScopeBlocked('Request blocked by scope.json') from exc

