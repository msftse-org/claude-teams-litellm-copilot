#!/usr/bin/env python3
"""Configure an existing LiteLLM gateway and issue private developer invitations."""
import argparse, getpass, json, re, sys, time, uuid
from pathlib import Path
from urllib.parse import quote
from gateway import API, Error, load_catalog, origin, private_write, read

OWNER='claude-subscription-onboarding-v1'

def model_rows(api):
    rows=[];page=1
    while True:
        result=api.call('/v2/model/info?page='+str(page)+'&size=100')
        rows.extend(result.get('data',[]))
        if page>=result.get('total_pages',1):return rows
        page+=1

def same_route(existing,wanted):
    a=existing.get('litellm_params',{}); b=wanted['litellm_params']
    return all(a.get(k)==v for k,v in b.items()) and existing.get('model_info',{}).get('cooldown_time')==0

def setup(api,c,apply):
    cred=api.call('/credentials/by_name/'+c['credential'],missing=True)
    if cred and (cred.get('credential_values',{}).get('github_copilot_auth_type')!='per_user_oauth'
                 or cred.get('credential_info',{}).get('custom_llm_provider')!='github_copilot'):
        raise Error('Credential name already exists with a different authentication configuration.')
    # /model/info can fail on an empty gateway; /v1/models distinguishes that case.
    existing=model_rows(api)
    create=[]
    for model in c['models']:
        found=[x for x in existing if x['model_name']==model['model_name']]
        if found and not all(same_route(x,model) for x in found):
            raise Error('Conflicting route '+model['model_name']+'. Review it with the administrator; nothing was changed.')
        if not found:create.append(model)
    print(f'Plan: {int(not bool(cred))} credential and {len(create)} models to add. Fallback policy is attached to each issued developer key.',flush=True)
    if not apply:
        print('Preview only. Add --apply to install this plan.');return
    if not cred:
        api.call('/credentials','POST',{'credential_name':c['credential'],
            'credential_values':{'github_copilot_auth_type':'per_user_oauth'},
            'credential_info':{'custom_llm_provider':'github_copilot'}})
    for model in create:api.call('/model/new','POST',model)
    expected={m['model_name'] for m in c['models']}
    for _ in range(24):
        actual={m['model_name'] for m in model_rows(api)}
        if expected<=actual:break
        time.sleep(5)
    else:raise Error('Configuration saved, but model discovery has not synchronized. Rerun setup after checking the gateway.')
    print('Setup complete. Existing gateway infrastructure and unrelated routes were preserved.')

def enroll(api,c,email,login,path):
    email=email.strip().lower()
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?',login):raise Error('Invalid GitHub login.')
    if not re.fullmatch(r'[^@\s]+@[^@\s]+',email):raise Error('Enter a work email with a name and domain. It identifies the gateway user; no email is sent.')
    # Stable ownership scoped to this gateway and email; no shared admin identity.
    uid=str(uuid.uuid5(uuid.NAMESPACE_URL,api.url+'|'+email.lower()))
    path=Path(path)
    if path.exists():
        old=read(path)
        if (old.get('gateway'),old.get('user_id'),old.get('github_login'))!=(api.url,uid,login.lower()):
            raise Error('Output file belongs to a different enrollment. Use another filename.')
        from gateway import key_info
        info=key_info(API(api.url,old['key']))
        if info['user_id']!=uid:raise Error('Existing invitation key ownership mismatch.')
        expected={m['model_name'] for m in c['models']}
        if set(info.get('models',[]))!=expected or info.get('router_settings',{}).get('fallbacks')!=c['fallbacks']:
            raise Error('Existing invitation has a different catalog or policy. Revoke its key and enroll to a new invitation file.')
        path.chmod(0o600)
        print('Existing invitation is valid; reused without issuing another key.');return
    models=[m['model_name'] for m in c['models']]
    registered={x['model_name'] for x in model_rows(api)}
    if not set(models)<=registered:raise Error('Run admin setup --apply with the same model options first.')
    user=api.call('/user/info?user_id='+quote(uid),missing=True)
    if user and user.get('user_info'):
        u=user['user_info'];md=u.get('metadata') or {}
        if md.get('onboarding_package')!=OWNER or md.get('github_login')!=login.lower():
            raise Error('The existing user does not match this enrollment.')
    else:
        api.call('/user/new','POST',{'user_id':uid,'user_email':email,'user_alias':login.lower(),
            'user_role':'internal_user','auto_create_key':False,'send_invite_email':False,
            'metadata':{'onboarding_package':OWNER,'github_login':login.lower()},'models':models})
    routes=['/v1/messages','/v1/messages/count_tokens','/v1/models','/v1/model/info','/model/info',
            '/key/info','/user/info','/credentials/user_connections',
            '/credentials/'+c['credential']+'/user_connection/start',
            '/credentials/'+c['credential']+'/user_connection/poll',
            '/credentials/'+c['credential']+'/user_connection']
    # Key-scoped policy makes fallback behavior independent of unrelated global rules.
    key=api.call('/key/generate','POST',{'user_id':uid,'key_alias':'claude-'+login.lower()+'-'+uuid.uuid4().hex[:8],
        'duration':'90d','models':models,'allowed_routes':routes,'send_invite_email':False,
        'metadata':{'onboarding_package':OWNER},
        'router_settings':{'num_retries':0,'fallbacks':c['fallbacks'],
                           'context_window_fallbacks':[]}})
    private_write(path,{'format':1,'gateway':api.url,'user_id':uid,'github_login':login.lower(),
        'credential':c['credential'],'models':models,'key':key['key'],'expires':key.get('expires'),
        'fallback_policy':c['fallbacks']})
    print('Invitation saved with owner-only permissions: '+str(path))
    print('No email was sent. The email address identifies the user in LiteLLM.')
    print('Deliver this private file to that developer. It contains their personal 90-day key.')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['setup','enroll']);p.add_argument('--gateway',required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--include-opus',action='store_true',help='Enable Copilot Opus and Opus-to-Opus fallback only after entitlement is verified.')
    p.add_argument('--email');p.add_argument('--github-login');p.add_argument('--out',type=Path)
    a=p.parse_args();origin(a.gateway)
    if a.command=='enroll' and not all([a.email,a.github_login,a.out]):p.error('enroll requires --email, --github-login and --out')
    key=getpass.getpass('LiteLLM administrator key (hidden): ').strip()
    if not key:raise Error('No administrator key supplied.')
    api=API(a.gateway,key);c=load_catalog(a.include_opus)
    if a.command=='setup':setup(api,c,a.apply)
    else:enroll(api,c,a.email,a.github_login,a.out)

if __name__=='__main__':
    try:main()
    except (Error,ValueError,KeyError) as e:print('ERROR: '+str(e),file=sys.stderr);sys.exit(1)
