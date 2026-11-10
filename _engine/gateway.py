"""Shared, dependency-free helpers. No provider credentials are handled here."""
import json, os, tempfile, urllib.error, urllib.parse, urllib.request
from pathlib import Path

class Error(Exception):
    pass

def origin(value):
    u=urllib.parse.urlsplit(value)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
        raise Error('Gateway must be an HTTPS origin without a path or credentials.')
    if u.scheme=='http' and u.hostname not in ('localhost','127.0.0.1','::1'):
        raise Error('HTTP is allowed only for a loopback test gateway.')
    return value.rstrip('/')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class API:
    def __init__(self,url,key):
        self.url=origin(url); self.key=key
        self.opener=urllib.request.build_opener(NoRedirect)
    def call(self,path,method='GET',body=None,missing=False):
        req=urllib.request.Request(self.url+path,method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=90) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if missing and e.code==404:return None
            # Upstream errors may contain credentials or request bodies; do not echo them.
            raise Error(f'{method} {path.split("?")[0]} returned HTTP {e.code}. Check gateway Logs.') from None
        except (urllib.error.URLError,TimeoutError):
            raise Error('Gateway could not be reached. Check its URL, network and TLS certificate.') from None

def read(path): return json.loads(Path(path).read_text())

def private_write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
        os.chmod(f.name,0o600); json.dump(value,f,indent=2); f.write('\n'); tmp=f.name
    os.replace(tmp,path)

def load_catalog(include_opus=False):
    c=read(Path(__file__).with_name('catalog.json'))
    omitted=set() if include_opus else set(c['optional_models'])
    c['models']=[m for m in c['models'] if m['model_name'] not in omitted]
    # The management API rejects this server-owned parameter in a request body.
    # Its value is already defined on the stored per-user credential.
    for model in c['models']:model['litellm_params'].pop('github_copilot_auth_type',None)
    c['fallbacks']=[e for e in c['fallbacks'] if next(iter(e)) not in omitted]
    if include_opus:
        for e in c['fallbacks']:
            k=next(iter(e))
            if k.replace('anthropic/','').startswith('claude-opus-'):
                e[k]=['claude-copilot-opus']
    return c

def key_info(api):
    info=api.call('/key/info').get('info',{})
    if not info.get('user_id'): raise Error('Use a personal LiteLLM key with a user_id, not the master key.')
    return info

def connected(api,credential):
    return next((x for x in api.call('/credentials/user_connections').get('connections',[])
                 if x.get('credential_name')==credential and x.get('connected')),None)
