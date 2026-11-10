#!/usr/bin/env python3
"""Guided administrator and developer onboarding, with no third-party packages."""
import argparse,contextlib,getpass,io,json,os,shlex,subprocess,sys,threading,time,webbrowser
from pathlib import Path
import admin,developer
from gateway import API,Error,connected,key_info,load_catalog,origin,private_write,read

MODELS=[('Sonnet 5.5','claude-copilot-sonnet'),('Haiku 5.5','claude-copilot-haiku'),
        ('Sonnet 5','claude-copilot-sonnet-5'),('Haiku 4.5','claude-copilot-haiku-4-5'),
        ('Opus 5.5 (requires access)','claude-copilot-opus')]

def input_path(value):
    # Accept a file dragged from Finder, which may arrive shell-quoted.
    raw=Path(value).expanduser()
    if raw.exists():return raw
    try:parts=shlex.split(value)
    except ValueError:return raw
    return Path(parts[0]).expanduser() if len(parts)==1 else raw

class Console:
    def __init__(self):self.out=sys.stdout;self.color=self.out.isatty() and 'NO_COLOR' not in os.environ
    def style(self,text,code):return '\033['+code+'m'+text+'\033[0m' if self.color else text
    def line(self,text=''):print(text,file=self.out,flush=True)
    def header(self,role='Welcome'):
        self.line();self.line(self.style('  CLAUDE GATEWAY  /  '+role.upper(),'1;36'))
        self.line(self.style('  ─────────────────────────────────────────────────────────────','36'))
    def note(self,text):self.line('  '+text)
    def good(self,text):self.line(self.style('  ✓ '+text,'32'))
    def warn(self,text):self.line(self.style('  ! '+text,'33'))
    def ask(self,prompt,default=''):
        answer=input(self.style('  '+prompt+(' ['+default+']' if default else '')+': ','1')).strip()
        return answer or default
    def yes(self,prompt,default=False):return self.ask(prompt,'yes' if default else 'no').lower() in ('y','yes')
    def choose(self,prompt,options,default=1):
        self.line();self.note(prompt)
        for n,item in enumerate(options,1):self.note('  '+str(n)+') '+item)
        while True:
            value=self.ask('Choose',str(default))
            if value.isdigit() and 1<=int(value)<=len(options):return int(value)-1
            self.warn('Enter a number from 1 to '+str(len(options))+'.')
    def step(self,label,action):
        stop=threading.Event();thread=None
        if self.color:
            def animate():
                symbols='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏';n=0
                while not stop.wait(.12):
                    self.out.write('\r\033[2K  '+symbols[n%len(symbols)]+' '+label);self.out.flush();n+=1
            thread=threading.Thread(target=animate,daemon=True);thread.start()
        else:self.note('… '+label)
        try:
            with contextlib.redirect_stdout(io.StringIO()):result=action()
        except BaseException:
            stop.set()
            if thread:thread.join();self.out.write('\r\033[2K')
            self.warn(label+' — did not complete');raise
        stop.set()
        if thread:thread.join();self.out.write('\r\033[2K')
        self.good(label);return result

def catalog_policy(include_opus=False,choices=None):
    c=load_catalog(include_opus)
    if choices:
        available={m['model_name'] for m in c['models'] if m['model_name'].startswith('claude-copilot-')}
        for family,target in choices.items():
            if family not in ('sonnet','opus','haiku') or target not in available:raise Error('Invalid fallback choice.')
        for rule in c['fallbacks']:
            name=next(iter(rule));bare=name.removeprefix('anthropic/')
            for family,target in choices.items():
                if bare in ('claude-'+family+'-5-5','claude-'+family+'-5.5'):rule[name]=[target]
    return c

def show_policy(ui,policy):
    rules={k:v for item in policy for k,v in item.items()};labels={alias:name for name,alias in MODELS}
    ui.line();ui.note('PRIMARY ON CLAUDE TEAMS       BACKUP ON GITHUB COPILOT')
    ui.note('──────────────────────────   ─────────────────────────────')
    for family in ['sonnet','opus','haiku']:
        target=rules.get('claude-'+family+'-5-5',[])
        ui.note((family.title()+' 5.5').ljust(29)+(' → '.join(labels.get(t,t) for t in target) or 'Not configured'))
    ui.line()

class Wizard:
    def __init__(self,ui=None):
        self.ui=ui or Console();self.admin_session=None
        self.preferences=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'claude-gateway/admin.json'
    def prefs(self):return read(self.preferences) if self.preferences.exists() else {}
    def admin_api(self):
        url=origin(self.ui.ask('Customer gateway URL',self.prefs().get('gateway','https://litellm.customer.example')))
        if self.admin_session and self.admin_session.url==url:return self.admin_session
        key=getpass.getpass('  Administrator key (hidden; kept in memory): ').strip()
        if not key:raise Error('No administrator key supplied.')
        self.admin_session=API(url,key);return self.admin_session
    def catalog(self,custom=False):
        opus=self.ui.yes('Include Copilot Opus? Only if customer access is verified',self.prefs().get('include_opus',False))
        choices={'sonnet':'claude-copilot-sonnet','haiku':'claude-copilot-haiku','opus':'claude-copilot-opus' if opus else 'claude-copilot-sonnet'}
        if custom and self.ui.choose('Fallback policy',['Use recommended model mapping','Choose a backup for each primary family'])==1:
            offered=MODELS if opus else MODELS[:-1]
            for family in ['sonnet','opus','haiku']:
                default=next(n+1 for n,(_,alias) in enumerate(offered) if alias==choices[family])
                selected=self.ui.choose('When Teams '+family.title()+' 5.5 fails, use:',[label for label,_ in offered],default)
                choices[family]=offered[selected][1]
        return catalog_policy(opus,choices),opus
    def prepare(self):
        ui=self.ui;ui.header('Administrator · prepare gateway')
        api=self.admin_api();c,opus=self.catalog()
        with contextlib.redirect_stdout(io.StringIO()) as capture:admin.setup(api,c,False)
        preview=capture.getvalue().replace('Preview only. Add --apply to install this plan.','').strip()
        ui.note(preview);show_policy(ui,c['fallbacks'])
        if not ui.yes('Apply this configuration to '+api.url+'?'):ui.note('Cancelled. Nothing was changed.');return
        ui.step('Register credential and model routes',lambda:admin.setup(api,c,True))
        private_write(self.preferences,{'gateway':api.url,'include_opus':opus})
        ui.good('Gateway ready. Next: Invite a developer.');ui.note('No administrator key was saved.')
    def invite(self):
        ui=self.ui;ui.header('Administrator · invite developer')
        api=self.admin_api()
        ui.note('Work email identifies the developer in LiteLLM. This wizard does not send email.')
        email=ui.ask('Developer work email');login=ui.ask('Developer GitHub username')
        c,opus=self.catalog(custom=True)
        destination=Path(ui.ask('Save private invitation to','private/'+login+'.invite.json')).expanduser()
        show_policy(ui,c['fallbacks']);ui.note('Developer: '+email+'  |  GitHub: '+login);ui.note('Gateway: '+api.url)
        if not ui.yes('Create or reuse this personal 90-day invitation?'):ui.note('Cancelled.');return
        ui.step('Issue developer invitation',lambda:admin.enroll(api,c,email,login,destination))
        private_write(self.preferences,{'gateway':api.url,'include_opus':opus})
        ui.line();ui.good('Invitation ready: '+str(destination))
        ui.note('DELIVERY No email was sent. You must deliver the invitation yourself.')
        ui.note('HANDOFF  Share the CLI package and invitation through an approved private channel.')
        ui.note('NEXT     Developer runs ./setup and chooses Developer → Join.')
        ui.warn('The invitation contains their personal key. Deliver it privately.')
    def join(self):
        ui=self.ui;ui.header('Developer · join gateway');developer.preflight()
        ui.note('You need: your private invitation, Claude Teams access and Copilot access.')
        ui.note('Paste the invitation path or drag its file into this terminal.')
        path=input_path(ui.ask('Path to your private invitation'));inv=read(path)
        developer.validate_invitation_shape(inv)
        ui.note('Gateway: '+origin(inv['gateway']));ui.note('GitHub identity: '+inv['github_login'])
        if os.environ.get('ANTHROPIC_BASE_URL') and os.environ['ANTHROPIC_BASE_URL'].rstrip('/')!=inv['gateway']:
            raise Error('Unset the conflicting ANTHROPIC_BASE_URL shell override before joining.')
        if os.environ.get('ANTHROPIC_CUSTOM_HEADERS'):raise Error('Unset shell ANTHROPIC_CUSTOM_HEADERS before joining.')
        if not ui.yes('Back up settings, connect accounts and run small live checks?',True):return
        api=ui.step('1/5 · Verify personal invitation',lambda:developer.validate_invite(inv))
        info=key_info(api);show_policy(ui,info.get('router_settings',{}).get('fallbacks',[]))
        if connected(api,inv['credential']):ui.step('2/5 · Verify GitHub identity',lambda:developer.connect(api,inv))
        else:
            ui.note('2/5 · Approve your GitHub account in the browser.');developer.connect(api,inv)
        direct=[]
        for alias in inv['models']:
            if alias.startswith('claude-copilot-'):
                direct.append(ui.step('3/5 · Test '+alias,lambda model=alias:developer.probe_copilot(api,model)))
        ui.step('4/5 · Back up and configure Claude Code',lambda:developer.configure(inv,Path.home()/'.claude'))
        self.ensure_subscription()
        primary=ui.step('5/5 · Test Claude Code through the gateway',developer.smoke)
        private_write(Path.home()/'.claude/gateway-onboarding-report.json',{'copilot_models':direct,'claude_code':primary})
        ui.line();ui.good('READY — restart open Claude sessions, then run: claude')
        ui.note('Use /model sonnet, /model opus or /model haiku. No launcher is needed.')
        ui.note('Gateway Logs show the actual provider; this reply alone is not failover proof.')
    def ensure_subscription(self):
        def status():
            p=subprocess.run(['claude','auth','status','--json'],capture_output=True,text=True,timeout=30)
            try:return json.loads(p.stdout)
            except ValueError:return {}
        s=status()
        if s.get('loggedIn') and s.get('authMethod')=='claude.ai':return
        self.ui.note('Sign in with your Claude subscription account in the browser.')
        if not self.ui.yes('Start Claude subscription sign-in now?',True):raise Error('Sign-in required. Complete claude auth login, then run ./setup doctor.')
        if subprocess.run(['claude','auth','login']).returncode:raise Error('Claude sign-in did not complete.')
        s=status()
        if not s.get('loggedIn') or s.get('authMethod')!='claude.ai':raise Error('Select a Claude subscription account, then run ./setup doctor.')
    def doctor(self):
        self.ui.header('Developer · connection check')
        result=self.ui.step('Check identity, subscription login and both routes',developer.doctor)
        private_write(Path.home()/'.claude/gateway-onboarding-report.json',result)
        self.ui.good('Connection checks passed.');self.ui.note('Read gateway Logs to confirm the serving provider and fallback attempts.')
    def models(self):
        ui=self.ui;ui.header('Models and fallback policy')
        state=Path.home()/'.claude/gateway-onboarding.json'
        if state.exists():
            profile=read(state);settings=read(state.parent/'settings.json')
            line=next((l for l in settings.get('env',{}).get('ANTHROPIC_CUSTOM_HEADERS','').splitlines() if l.lower().startswith('x-litellm-api-key:')),None)
            if not line:raise Error('Installed personal key header is missing.')
            key=line.split(':',1)[1].strip().removeprefix('Bearer ')
            info=key_info(API(profile['gateway'],key));policy=info.get('router_settings',{}).get('fallbacks',[])
            ui.note('LIVE POLICY · '+profile['gateway']);show_policy(ui,policy)
            permitted=set(info.get('models',[]))
        else:
            ui.note('STARTER DEFAULTS · no joined profile found');show_policy(ui,load_catalog()['fallbacks'])
            permitted={m['model_name'] for m in load_catalog()['models']}
        ui.note('DIRECT COPILOT OPTIONS')
        for label,alias in MODELS:
            if alias in permitted:ui.note('  '+label.ljust(28)+'/model '+alias)
        ui.note('Opus requires verified Copilot entitlement and administrator enablement.')
    def restore(self):
        self.ui.header('Restore previous local settings')
        if self.ui.yes('Restore the previous settings? This does not revoke gateway access.'):
            self.ui.step('Restore settings without overwriting later changes',developer.undo)
    def run(self,role=None):
        while True:
            try:
                if role is None:
                    self.ui.header();self.ui.note('Claude Teams first. Personal Copilot fallback. One-time onboarding.')
                    self.ui.note('ADMIN: prepare the gateway → invite each developer')
                    self.ui.note('DEVELOPER: join → check → run claude normally')
                    pick=self.ui.choose('Who is setting up?',['Administrator','Developer','Show default model options','Exit'])
                    if pick==3:return
                    if pick==2:self.models();continue
                    role='admin' if pick==0 else 'developer'
                self.ui.header('Administrator' if role=='admin' else 'Developer')
                choices=['Prepare customer gateway','Invite a new developer','Show model options','Back'] if role=='admin' else ['Join with my invitation','Check my connection','Show my models and fallback policy','Restore previous settings','Back']
                pick=self.ui.choose('Choose an action',choices)
                if pick==len(choices)-1:self.admin_session=None;role=None;continue
                action=[self.prepare,self.invite,self.models][pick] if role=='admin' else [self.join,self.doctor,self.models,self.restore][pick]
                action()
            except (Error,ValueError,KeyError,OSError) as e:self.ui.warn(str(e));self.ui.note('Correct the issue and retry. No key is included in this message.')

def main():
    p=argparse.ArgumentParser(prog='./setup',description='Guided Claude Teams + LiteLLM + Copilot onboarding')
    p.add_argument('role',nargs='?',choices=['admin','developer','doctor','models']);args=p.parse_args()
    w=Wizard()
    if args.role=='doctor':w.doctor()
    elif args.role=='models':w.models()
    else:w.run(args.role)

if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError):print('\n  Setup cancelled. You can rerun ./setup.');sys.exit(130)
    except (Error,ValueError,KeyError,OSError) as e:print('\n  Setup needs attention: '+str(e),file=sys.stderr);sys.exit(1)
