import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_engine'))
import developer,admin
from gateway import Error,origin,private_write,read,load_catalog

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.directory=self.home/'.claude'
        self.inv={'gateway':'https://gateway.example','key':'sk-test-not-a-real-credential',
                  'user_id':'pilot','github_login':'pilot','credential':'github-copilot-user','models':['anthropic/*']}
    def tearDown(self):self.tmp.cleanup()
    def test_merge_and_private_backup(self):
        before={'theme':'dark','permissions':{'deny':['Bash(rm *)']},'apiKeyHelper':'old-helper',
                'env':{'CUSTOM_VALUE':'keep','ANTHROPIC_AUTH_TOKEN':'old','ANTHROPIC_CUSTOM_HEADERS':'other: keep\nx-litellm-api-key: old'}}
        private_write(self.directory/'settings.json',before)
        developer.configure(self.inv,self.directory);after=read(self.directory/'settings.json')
        self.assertEqual(after['theme'],'dark');self.assertEqual(after['permissions'],before['permissions'])
        self.assertNotIn('apiKeyHelper',after);self.assertNotIn('ANTHROPIC_AUTH_TOKEN',after['env'])
        self.assertIn('other: keep',after['env']['ANTHROPIC_CUSTOM_HEADERS'])
        self.assertEqual(after['env']['ANTHROPIC_CUSTOM_HEADERS'].count('x-litellm-api-key:'),1)
        self.assertEqual((self.directory/'settings.json').stat().st_mode&0o777,0o600)
        state=read(self.directory/'gateway-onboarding.json');self.assertEqual(read(state['backup']),before)
        with patch.object(Path,'home',return_value=self.home):developer.undo()
        self.assertEqual(read(self.directory/'settings.json'),before)
    def test_repeat_does_not_duplicate_backups(self):
        developer.configure(self.inv,self.directory);developer.configure(self.inv,self.directory)
        self.assertEqual(len(list((self.directory/'backups').iterdir())),1)
    def test_undo_removes_new_settings(self):
        developer.configure(self.inv,self.directory)
        with patch.object(Path,'home',return_value=self.home):developer.undo()
        self.assertFalse((self.directory/'settings.json').exists())
    def test_undo_refuses_to_overwrite_later_changes(self):
        developer.configure(self.inv,self.directory)
        p=self.directory/'settings.json';d=read(p);d['theme']='changed';private_write(p,d)
        with patch.object(Path,'home',return_value=self.home),self.assertRaises(Error):developer.undo()
    def test_rejects_insecure_or_credential_urls(self):
        for value in ['http://remote.example','https://key@gateway.example','https://gateway.example/v1','https://gateway.example?key=x']:
            with self.assertRaises(Error):origin(value)
        self.assertEqual(origin('http://127.0.0.1:4198/'),'http://127.0.0.1:4198')
    def test_wrong_github_connection_stops_before_settings(self):
        with patch.object(developer,'connected',return_value={'github_login':'someone-else'}),self.assertRaises(Error):
            developer.connect(object(),self.inv,True)
        self.assertFalse((self.directory/'settings.json').exists())
    def test_oauth_denial_is_not_success(self):
        class Fake:
            def call(self,path,method='GET',body=None):
                if path.endswith('/start'):return {'verification_uri':'https://github.com/login/device','interval':1,'expires_in':5,'user_code':'TEST-CODE','flow_handle':'test'}
                return {'status':'denied'}
        with patch.object(developer,'connected',return_value=None),patch.object(developer.time,'sleep'),self.assertRaises(Error):
            developer.connect(Fake(),self.inv,True)
    def test_symlink_settings_not_overwritten(self):
        target=self.home/'managed.json';private_write(target,{'theme':'dark'})
        self.directory.mkdir();(self.directory/'settings.json').symlink_to(target)
        with self.assertRaises(Error):developer.configure(self.inv,self.directory)
        self.assertEqual(read(target),{'theme':'dark'})
    def test_opus_is_opt_in_and_mapping_changes_together(self):
        basic=load_catalog();extra=load_catalog(True)
        self.assertNotIn('claude-copilot-opus',[m['model_name'] for m in basic['models']])
        self.assertIn('claude-copilot-opus',[m['model_name'] for m in extra['models']])
        for entry in extra['fallbacks']:
            name=next(iter(entry))
            if name.replace('anthropic/','').startswith('claude-opus-'):
                self.assertEqual(entry[name],['claude-copilot-opus'])

if __name__=='__main__':unittest.main()
