import copy
import json
import tempfile
import unittest
from pathlib import Path
from tech_uncovered.competitors import parse_config,effective_settings,resolve
from tech_uncovered.settings import Settings
from tech_uncovered.database import Database
from tech_uncovered.youtube import YouTubeClient
from tests.test_scoring import NOW
ROOT=Path(__file__).resolve().parents[1]

class CompetitorTests(unittest.TestCase):
    def setUp(self):
        self.cohorts=json.loads((ROOT/'config/cohorts.json').read_text());self.raw=json.loads((ROOT/'config/channels.json').read_text())
    def test_twenty_configured_and_vendor_roles(self):
        c=parse_config(self.raw,self.cohorts);self.assertEqual(len(c['channels']),20)
        self.assertEqual({x['display_name'] for x in c['channels'] if x['source_role']=='vendor_official'},{'NVIDIA','IBM Technology'})
    def test_legacy_list(self):
        c=parse_config([{'name':'Old','handle':'@old'}],self.cohorts)
        self.assertEqual(c['competitor_config_version'],'legacy-1.0');self.assertEqual(c['channels'][0]['cohort'],'UNASSIGNED')
    def test_unknown_cohort(self):
        self.raw['channels'][0]['cohort']='wrong'
        with self.assertRaises(ValueError):parse_config(self.raw,self.cohorts)
    def test_duplicate_identity(self):
        self.raw['channels'].append(self.raw['channels'][0])
        with self.assertRaises(ValueError):parse_config(self.raw,self.cohorts)
    def test_invalid_weight(self):
        self.raw['channels'][0]['weight']=float('nan')
        with self.assertRaises(ValueError):parse_config(self.raw,self.cohorts)
    def test_override_precedence(self):
        c=parse_config(self.raw,self.cohorts)['channels'][13]
        self.assertEqual(effective_settings(c,self.cohorts,Settings()).max_uploads,50)
        self.assertEqual(effective_settings(c,self.cohorts,Settings(),25,60).lookback_days,60)
    def test_exact_handle_id_and_canonical_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'test.db');calls=[]
            def fake(endpoint,params,key):
                calls.append(params);return {'items':[{'id':'exact-id','snippet':{'title':'Canonical Name'},'contentDetails':{'relatedPlaylists':{'uploads':'uploads'}}}]}
            client=YouTubeClient('test',db,Settings(),transport=fake,clock=lambda:NOW)
            c=dict(display_name='Requested',handle='@requested',channel_id='exact-id',cohort='AI_FRONTIER',source_role='independent_creator',enabled=True)
            r=resolve(client,c);self.assertEqual(r['status'],'RESOLVED');self.assertEqual(r['canonical_name'],'Canonical Name');self.assertEqual(calls[0]['forHandle'],'@requested');db.close()
    def test_handle_id_mismatch_unresolved(self):
        class Client:
            def resolve_channel(self,c):return {'channel_id':'different','name':'Other'}
        c=dict(display_name='Requested',handle='@requested',channel_id='wanted',cohort='AI_FRONTIER',source_role='independent_creator',enabled=True)
        self.assertEqual(resolve(Client(),c)['status'],'UNRESOLVED')
    def test_ambiguous_display_name_never_selected(self):
        class Client:
            def get(self,*args):return {'items':[{'id':{'channelId':'a'},'snippet':{'title':'Same'}},{'id':{'channelId':'b'},'snippet':{'title':'Same'}}]},'now'
        c=dict(display_name='Same',cohort='AI_FRONTIER',source_role='independent_creator',enabled=True)
        r=resolve(Client(),c);self.assertEqual(r['status'],'UNRESOLVED');self.assertEqual(len(r['alternatives']),2)
    def test_disabled_no_network(self):
        c=dict(display_name='Disabled',cohort='AI_FRONTIER',source_role='independent_creator',enabled=False)
        self.assertEqual(resolve(object(),c)['status'],'DISABLED')
