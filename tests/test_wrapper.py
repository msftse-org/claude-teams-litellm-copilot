import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'_engine'))
import cli,admin
from unittest.mock import patch
from gateway import Error,load_catalog

class WrapperTests(unittest.TestCase):
    def test_dragged_invitation_with_spaces(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'my invitation.json';p.touch()
            self.assertEqual(cli.input_path("'"+str(p)+"'"),p)
            self.assertEqual(cli.input_path(str(p).replace(' ','\\ ')),p)
            self.assertEqual(cli.input_path(str(p)),p)
    def test_doctor_before_join_explains_next_step(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Path,'home',return_value=Path(d)),patch.object(cli.developer,'preflight'):
            with self.assertRaisesRegex(Error,'./setup developer'):cli.developer.doctor()
    def test_executable_entrypoint(self):
        p=subprocess.run([str(ROOT/'setup'),'--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0);self.assertIn('Guided Claude Teams',p.stdout)
    def test_custom_policy_all_spellings(self):
        c=cli.catalog_policy(False,{'opus':'claude-copilot-haiku'})
        rules={k:v for e in c['fallbacks'] for k,v in e.items()}
        for name in ['claude-opus-5-5','claude-opus-5.5','anthropic/claude-opus-5-5','anthropic/claude-opus-5.5']:
            self.assertEqual(rules[name],['claude-copilot-haiku'])
        self.assertEqual(rules['claude-sonnet-5'],['claude-copilot-sonnet-5'])
        self.assertEqual(rules['claude-copilot-haiku'],[])
    def test_unauthorized_backup_not_accepted(self):
        with self.assertRaises(Error):cli.catalog_policy(False,{'opus':'claude-copilot-opus'})
        with self.assertRaises(Error):cli.catalog_policy(False,{'opus':'anthropic/*'})
    def test_new_invitation_uses_unique_key_alias(self):
        class API:
            url='https://gateway.example'
            def __init__(self):self.aliases=[];self.users=[];self.keys=[]
            def call(self,path,method='GET',body=None,missing=False):
                if path.startswith('/v2/model/info'):return {'data':load_catalog()['models'],'total_pages':1}
                if path.startswith('/user/info'):return None
                if path=='/user/new':self.users.append(body);return {}
                if path=='/key/generate':
                    self.keys.append(body)
                    self.aliases.append(body['key_alias']);return {'key':'sk-unit-test-placeholder','expires':'2099-01-01'}
                raise AssertionError(path)
        api=API()
        with tempfile.TemporaryDirectory() as d:
            for name,email in [('one.json','Developer@Example.com'),('two.json',' developer@example.com ')]:
                admin.enroll(api,load_catalog(),email,'developer',Path(d)/name)
        self.assertEqual(len(set(api.aliases)),2)
        self.assertEqual(len({u['user_id'] for u in api.users}),1)
        self.assertTrue(all(u['user_email']=='developer@example.com' and u['send_invite_email'] is False for u in api.users))
        self.assertTrue(all(k['send_invite_email'] is False for k in api.keys))
    def test_invalid_email_rejected_before_api_calls(self):
        class NoCalls:
            def call(self,*a,**k):raise AssertionError('Invalid input reached the gateway')
        for email in ['@','name@','@company.example','a@@company.example','a b@company.example']:
            with self.subTest(email=email),self.assertRaises(Error):
                admin.enroll(NoCalls(),load_catalog(),email,'developer',Path('unused.json'))
    def test_malformed_invitation_has_actionable_error(self):
        for value in [[],None,{'format':1},{'format':1,'gateway':12}]:
            with self.subTest(value=value),self.assertRaises(Error):cli.developer.validate_invitation_shape(value)

if __name__=='__main__':unittest.main()
