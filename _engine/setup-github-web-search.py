#!/usr/bin/env python3
"""Install user-scoped GitHub MCP web search without changing model routing."""
import datetime,json,os,shlex,shutil,subprocess,sys,tempfile
from pathlib import Path

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.search-setup-',delete=False) as f:
        json.dump(value,f,indent=2);f.write('\n');tmp=Path(f.name)
    tmp.chmod(0o600);os.replace(tmp,path)

def main():
    if os.environ.get('CLAUDE_CONFIG_DIR'):
        raise SystemExit('This installer targets the default Claude profile. Review custom CLAUDE_CONFIG_DIR separately.')
    gh=shutil.which('gh');claude=shutil.which('claude');python=shutil.which('python3')
    if not gh or not claude or not python:raise SystemExit('Install GitHub CLI, Claude Code and Python 3 first.')
    auth=subprocess.run([gh,'auth','status','--hostname','github.com'],capture_output=True,text=True)
    if auth.returncode:raise SystemExit('Run gh auth login --hostname github.com, then run this setup again.')
    config=Path.home()/'.claude';account=Path.home()/'.claude.json'
    settings=config/'settings.json';memory=config/'CLAUDE.md'
    state=json.loads(account.read_text()) if account.exists() else {}
    before=json.loads(settings.read_text()) if settings.exists() else {}
    helper=config/'github-web-search-headers.py'
    server={'type':'http','url':'https://api.githubcopilot.com/mcp/readonly',
            'headers':{'X-MCP-Toolsets':'web_search'},
            'headersHelper':shlex.join([python,str(helper)])}
    existing=state.get('mcpServers',{}).get('github')
    if existing and existing!=server:
        raise SystemExit('A different user-scoped github MCP server already exists. Review and merge it instead of overwriting it.')
    backup=config/'backups'/('github-web-search-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    for f in [settings,account,memory,helper]:
        if f.exists():
            dest=backup/f.name;shutil.copyfile(f,dest);dest.chmod(0o600)
    helper_source='''#!/usr/bin/env python3
import json,subprocess,sys
GH = GH_PATH
try:
    p=subprocess.run([GH,"auth","token","--hostname","github.com"],capture_output=True,text=True,check=True,timeout=8)
    token=p.stdout.strip()
    if not token:raise RuntimeError("Empty credential")
    print(json.dumps({"Authorization":"Bearer "+token}))
except Exception:
    print("GitHub MCP authentication failed; run gh auth login --hostname github.com.",file=sys.stderr)
    raise SystemExit(1)
'''
    helper.write_text(helper_source.replace('GH_PATH',repr(gh)));helper.chmod(0o700)
    if not existing:
        p=subprocess.run([claude,'mcp','add-json','github',json.dumps(server),'--scope','user'],capture_output=True,text=True)
        if p.returncode:raise SystemExit('Claude MCP registration failed: '+p.stderr[:500])
    d=json.loads(settings.read_text()) if settings.exists() else {}
    perms=d.setdefault('permissions',{})
    perms['allow']=list(dict.fromkeys([*perms.get('allow',[]),'mcp__github__web_search']))
    perms['deny']=list(dict.fromkeys([*perms.get('deny',[]),'WebSearch']))
    atomic_json(settings,d)
    begin='<!-- BEGIN TEAM GITHUB WEB SEARCH -->';end='<!-- END TEAM GITHUB WEB SEARCH -->'
    block=begin+'''
# Web search
For web searches, always use mcp__github__web_search. Load it through ToolSearch if deferred.
Native WebSearch is disabled by policy. Do not use native model search or substitute
another search provider. If GitHub search is unavailable, report the problem rather
than claiming to have searched. For answers based on a web search, end with a
"Sources:" list of the cited URLs.
'''+end
    text=memory.read_text() if memory.exists() else ''
    if begin in text and end in text:
        a=text.index(begin);b=text.index(end,a)+len(end);text=text[:a]+block+text[b:]
    else:text=text.rstrip()+'\n\n'+block+'\n'
    memory.write_text(text.lstrip());memory.chmod(0o600)
    assert d.get('env',{}).get('ANTHROPIC_BASE_URL')==before.get('env',{}).get('ANTHROPIC_BASE_URL')
    assert d.get('apiKeyHelper')==before.get('apiKeyHelper')
    print(json.dumps({'installed':True,'scope':'user (all projects for this user)','server':'github',
                      'tool':'mcp__github__web_search','native_WebSearch':'denied',
                      'model_gateway_unchanged':True,'backup_directory':str(backup),
                      'next':'Restart Claude Code and check /mcp.'},indent=2))

if __name__=='__main__':main()

