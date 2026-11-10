#!/usr/bin/env python3
"""Join once; afterwards launch Claude Code normally. Python 3 standard library only."""
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys, time, webbrowser
from pathlib import Path
from gateway import API, Error, connected, key_info, origin, private_write, read

CONFLICTS=['ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_MODEL','ANTHROPIC_DEFAULT_MODEL',
           'CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY']

def validate_invitation_shape(invite):
    if not isinstance(invite,dict):raise Error('The invitation must be a JSON object. Use the private .invite.json file supplied by your administrator.')
    if invite.get('format')!=1:raise Error('Unsupported invitation format.')
    for field in ('gateway','key','user_id','github_login','credential'):
        if not isinstance(invite.get(field),str) or not invite[field].strip():
            raise Error('The invitation is missing a valid '+field+'. Ask your administrator for a new invitation.')
    if not isinstance(invite.get('models'),list) or not invite['models'] or any(not isinstance(m,str) or not m for m in invite['models']):
        raise Error('The invitation has no valid model list. Ask your administrator for a new invitation.')
    origin(invite['gateway'])
    if not invite['key'].startswith('sk-'):raise Error('Invalid personal key in invitation.')

def validate_invite(invite):
    validate_invitation_shape(invite)
    api=API(invite['gateway'],invite['key']);info=key_info(api)
    if info['user_id']!=invite['user_id']:raise Error('Invitation and key owner do not match.')
    u=api.call('/user/info').get('user_info',{})
    if u.get('user_id')!=invite['user_id'] or u.get('user_role') not in ('internal_user','internal_user_viewer'):
        raise Error('This invitation is not for a developer account.')
    if (u.get('metadata') or {}).get('github_login')!=invite['github_login']:
        raise Error('Invitation GitHub identity does not match the gateway user.')
    if not set(invite['models'])<=set(info.get('models',[])):
        raise Error('The personal key does not allow the invitation models.')
    return api

def connect(api,invite,no_browser=False):
    credential=invite['credential'];connection=connected(api,credential)
    fresh=False
    if not connection:
        flow=api.call('/credentials/'+credential+'/user_connection/start','POST')
        if flow.get('verification_uri')!='https://github.com/login/device':raise Error('Unexpected GitHub authorization URL. This package supports github.com.')
        interval=int(flow['interval']);expiry=int(flow['expires_in'])
        if not 1<=interval<=60 or not 1<=expiry<=1800:raise Error('Invalid device-flow timing.')
        print('Sign in as '+invite['github_login']+'. Open '+flow['verification_uri'],flush=True)
        print('Enter this one-time code: '+flow['user_code'],flush=True)
        if not no_browser:webbrowser.open(flow['verification_uri'])
        deadline=time.monotonic()+expiry
        while time.monotonic()+interval<deadline:
            time.sleep(interval)
            result=api.call('/credentials/'+credential+'/user_connection/poll','POST',{'flow_handle':flow['flow_handle']})
            status=result.get('status')
            if status=='connected':connection=result;fresh=True;break
            if status not in ('pending','slow_down'):raise Error('GitHub sign-in did not complete: '+str(status)+'. Rerun join.')
            interval=max(interval+(5 if status=='slow_down' else 0),int(result.get('interval',interval)))
            if interval>60:raise Error('GitHub sign-in is rate limited. Rerun join later.')
        if not connection:raise Error('GitHub authorization expired. Rerun join.')
    if connection.get('github_login','').lower()!=invite['github_login'].lower():
        if fresh:api.call('/credentials/'+credential+'/user_connection','DELETE')
        raise Error('Wrong GitHub account connected. Contact the administrator; local settings were not changed.')
    print('GitHub Copilot connection verified.',flush=True)

def probe_copilot(api,model='claude-copilot-sonnet'):
    response=api.call('/v1/messages','POST',{'model':model,'max_tokens':256,
        'messages':[{'role':'user','content':'Reply with exactly ONBOARDING_COPILOT_OK'}]})
    text=''.join(b.get('text','') for b in response.get('content',[]) if b.get('type')=='text')
    if 'ONBOARDING_COPILOT_OK' not in text:raise Error('Copilot replied but did not pass the onboarding marker check.')
    return {'success':True,'requested_model':model,'response_model':response.get('model'),'request_id':response.get('id')}

def configure(invite,directory):
    directory=Path(directory);settings=directory/'settings.json';state=directory/'gateway-onboarding.json'
    if settings.is_symlink():raise Error('settings.json is a symlink. Ask IT to update its managed source.')
    existed=settings.exists();before=read(settings) if existed else {}
    updated=json.loads(json.dumps(before));updated.pop('apiKeyHelper',None)
    env=updated.setdefault('env',{})
    for k in CONFLICTS:env.pop(k,None)
    headers=[line for line in env.get('ANTHROPIC_CUSTOM_HEADERS','').splitlines()
             if line.strip() and line.split(':',1)[0].strip().lower()!='x-litellm-api-key']
    headers.append('x-litellm-api-key: Bearer '+invite['key'])
    env.update({'ANTHROPIC_BASE_URL':invite['gateway'],'ANTHROPIC_CUSTOM_HEADERS':'\n'.join(headers),
        'ANTHROPIC_DEFAULT_SONNET_MODEL':'claude-sonnet-5-5',
        'ANTHROPIC_DEFAULT_OPUS_MODEL':'claude-opus-5-5',
        'ANTHROPIC_DEFAULT_HAIKU_MODEL':'claude-haiku-5-5',
        'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY':'1','CLAUDE_CODE_AUTO_MODE_SERVER':'0'})
    updated['model']='sonnet'
    previous=read(state) if state.exists() else {}
    if before==updated and previous.get('gateway')==invite['gateway']:
        print('Claude Code settings already configured; no duplicate backup created.');return settings
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup=directory/'backups'/('gateway-'+stamp)
    backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    private_write(backup/'settings.json',before)
    private_write(settings,updated)
    private_write(state,{'gateway':invite['gateway'],'user_id':invite['user_id'],
        'github_login':invite['github_login'],'credential':invite['credential'],'models':invite['models'],
        'backup':str(backup/'settings.json'),'previously_existed':existed,
        'installed_hash':hashlib.sha256(settings.read_bytes()).hexdigest()})
    print('Claude Code configured. Private backup: '+str(backup/'settings.json'),flush=True)
    return settings

def smoke(settings=None):
    command=['claude','-p','Reply with exactly ONBOARDING_PRIMARY_ROUTE_OK',
             '--model','sonnet','--effort','low','--tools','',
             '--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
             '--max-turns','1','--output-format','json','--no-session-persistence']
    if settings:command+=['--settings',str(settings)]
    try:r=subprocess.run(command,capture_output=True,text=True,timeout=180)
    except subprocess.TimeoutExpired:raise Error('Claude test timed out. Settings are installed; run doctor after checking gateway Logs.') from None
    try:result=json.loads(r.stdout)
    except ValueError:raise Error('Claude did not return a test result. Run claude auth login, then developer.py doctor.') from None
    if r.returncode or result.get('is_error') or 'ONBOARDING_PRIMARY_ROUTE_OK' not in result.get('result',''):
        raise Error('Claude test failed. Run claude auth login and check gateway Logs, then rerun doctor.')
    return {'success':True,'requested_model':'sonnet','marker':'ONBOARDING_PRIMARY_ROUTE_OK',
            'meaning':'Primary route answered; inspect gateway Logs to distinguish primary from fallback.'}

def preflight():
    if not shutil.which('claude'):raise Error('Install Claude Code first, then rerun this command.')
    if os.environ.get('CLAUDE_CONFIG_DIR'):raise Error('A custom CLAUDE_CONFIG_DIR is active. Use the standard Claude profile for this installer.')
    conflicts=[k for k in CONFLICTS if os.environ.get(k)]
    if conflicts:raise Error('Clear these shell overrides and their shell-profile entries: '+', '.join(conflicts))

def join(invite,no_browser=False):
    preflight()
    if os.environ.get('ANTHROPIC_BASE_URL') and os.environ['ANTHROPIC_BASE_URL'].rstrip('/')!=invite['gateway']:
        raise Error('Unset the conflicting ANTHROPIC_BASE_URL shell override before joining.')
    if os.environ.get('ANTHROPIC_CUSTOM_HEADERS'):
        raise Error('Unset ANTHROPIC_CUSTOM_HEADERS in this shell before joining; the installer preserves headers already in settings.json.')
    print('[1/4] Checking your personal invitation…',flush=True);api=validate_invite(invite)
    print('[2/4] Connecting your GitHub account…',flush=True);connect(api,invite,no_browser)
    print('[3/4] Testing Copilot before changing local settings…',flush=True);direct=probe_copilot(api)
    configure(invite,Path.home()/'.claude')
    print('[4/4] Testing Claude Code through your new gateway…',flush=True)
    auth=subprocess.run(['claude','auth','status','--json'],capture_output=True,text=True)
    try:status=json.loads(auth.stdout);logged=status.get('loggedIn')
    except ValueError:status={};logged=False
    if logged and status.get('authMethod')!='claude.ai':
        raise Error('Claude is using API credentials, not the subscription. Check project/managed overrides and run claude auth login, then doctor.')
    if not logged:
        print('Complete Claude subscription sign-in in your browser.',flush=True)
        if subprocess.run(['claude','auth','login']).returncode:raise Error('Claude login incomplete. Run claude auth login, then developer.py doctor.')
        check=subprocess.run(['claude','auth','status','--json'],capture_output=True,text=True)
        try:after=json.loads(check.stdout)
        except ValueError:after={}
        if not after.get('loggedIn') or after.get('authMethod')!='claude.ai':
            raise Error('Choose a Claude subscription account during login, then rerun doctor.')
    result={'copilot':direct,'claude_code':smoke()}
    print('Ready. Restart any open Claude sessions, then run: claude')
    return result

def doctor():
    preflight();d=Path.home()/'.claude'
    if not (d/'gateway-onboarding.json').exists():
        raise Error('This machine has not joined yet. Run ./setup developer and choose Join with my invitation.')
    state=read(d/'gateway-onboarding.json');settings=read(d/'settings.json')
    env=settings.get('env',{})
    if env.get('ANTHROPIC_BASE_URL')!=state['gateway']:raise Error('Gateway settings changed. Rerun join with your invitation.')
    if os.environ.get('ANTHROPIC_BASE_URL') and os.environ['ANTHROPIC_BASE_URL'].rstrip('/')!=state['gateway']:
        raise Error('A shell ANTHROPIC_BASE_URL overrides your installed gateway.')
    if os.environ.get('ANTHROPIC_CUSTOM_HEADERS'):raise Error('Unset shell ANTHROPIC_CUSTOM_HEADERS before running doctor.')
    auth=subprocess.run(['claude','auth','status','--json'],capture_output=True,text=True)
    try:status=json.loads(auth.stdout)
    except ValueError:status={}
    if not status.get('loggedIn') or status.get('authMethod')!='claude.ai':raise Error('Sign in with your Claude subscription using claude auth login, then rerun doctor.')
    headers=env.get('ANTHROPIC_CUSTOM_HEADERS','').splitlines()
    line=next((x for x in headers if x.lower().startswith('x-litellm-api-key:')),None)
    if not line:raise Error('Personal gateway key header is missing.')
    key=line.split(':',1)[1].strip().removeprefix('Bearer ').strip()
    api=validate_invite(dict(state,format=1,key=key))
    conn=connected(api,state['credential'])
    if not conn or conn.get('github_login','').lower()!=state['github_login'].lower():raise Error('GitHub connection is missing or mismatched. Rerun join.')
    result={'copilot':probe_copilot(api),'claude_code':smoke()}
    print('PASS: personal identity, GitHub connection, Copilot inference and Claude Code reply.')
    return result

def undo():
    d=Path.home()/'.claude';state=read(d/'gateway-onboarding.json');settings=d/'settings.json'
    if hashlib.sha256(settings.read_bytes()).hexdigest()!=state['installed_hash']:
        raise Error('Settings changed since onboarding. Merge the private backup manually: '+state['backup'])
    if state['previously_existed']:private_write(settings,read(state['backup']))
    else:settings.unlink()
    (d/'gateway-onboarding.json').unlink()
    print('Previous Claude settings restored. This does not revoke the key or disconnect GitHub.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['join','doctor','undo'])
    p.add_argument('--invite',type=Path);p.add_argument('--no-browser',action='store_true');p.add_argument('--report',type=Path)
    a=p.parse_args()
    if a.command=='join' and not a.invite:p.error('join requires --invite /path/to/private-invitation.json')
    result=join(read(a.invite),a.no_browser) if a.command=='join' else doctor() if a.command=='doctor' else undo()
    if a.report and result:private_write(a.report,result)

if __name__=='__main__':
    try:main()
    except (Error,ValueError,KeyError,FileNotFoundError) as e:print('ERROR: '+str(e),file=sys.stderr);sys.exit(1)
