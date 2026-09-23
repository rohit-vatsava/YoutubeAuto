"""Independent fictional oracle for full M3 lifecycle; never imports a live provider."""
from copy import deepcopy
import hashlib
from tests.script_helpers import fixture,config,selected
from tech_uncovered.scripting.models import stable_id
from tech_uncovered.scripting.providers.fixtures import *
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.pipeline import run

NOW='2026-09-20T12:00:00+00:00'
FACTS=[
 ('claim-product-identity','Atlas Works introduced AtlasDB 3 on September 18, 2026, as a database with a documented API.'),
 ('claim-feature-list','AtlasDB 3 supports SQL queries, JSON import, backups, and read replicas.'),
 ('claim-consistency-settings','The AtlasDB 3 API supports three consistency settings: eventual, session, strong.'),
 ('claim-backups','Backups are created when a user requests one, and the user chooses which saved backup to restore.'),
 ('claim-import','JSON import reads a file supplied by the user and reports records that could not be imported.'),
 ('claim-limits','The documented read replicas accept queries but do not accept writes from applications connected to those replicas.'),
 ('claim-export','Export writes a JSON file that the user can save locally and inspect before sharing with another application at a later time.'),
 ('claim-price','The listed monthly subscription costs ten dollars for the fictional standard plan, with no claim about other plans.'),
]
def bundle():
    b=fixture();b['as_of']=NOW;b['synthetic']=True
    text=' '.join(t for _,t in FACTS);s=deepcopy(b['sources'][0])
    s.update(source_id='atlas-source',url='https://atlas.example/releases/atlasdb-3',title='AtlasDB 3 database API release documentation',
        publisher='Atlas Works',text=text,content_hash=hashlib.sha256(text.encode()).hexdigest())
    b['sources']=[s];claims=[]
    for cid,t in FACTS:
        c=deepcopy(b['packet']['claims'][0]);c.update(claim_id=cid,text=t,supported_wording=t,claim_type='FACT',evidence_ids=['atlas-source'],passages=[dict(source_id='atlas-source',quote=t,relation='SUPPORTS')])
        claims.append(c)
    b['packet'].update(topic='AtlasDB 3',claims=claims,core_claim_ids=[c['claim_id'] for c in claims],
        canonical_story_resolved=True,remaining_questions_material=False,research_gaps=[],
        freshness={'established':True,'event_date':'2026-09-18T09:00:00+00:00','evidence_ids':['atlas-source']},
        source_assessments=[dict(source_id='atlas-source',source_type='DOCUMENTATION',primary_or_secondary='PRIMARY',
            credible_for_claim_ids=[c['claim_id'] for c in claims],authority_score=100,relevance_score=100,freshness_score=100,rationale='Fictional authoritative release specification.')])
    b['story_resolution']=dict(canonical_subject='AtlasDB 3',named_entities=['AtlasDB 3','Atlas Works'],alleged_event='AtlasDB 3 database API introduction',
        event_date_if_known='2026-09-18T09:00:00+00:00',identifiers={'products':['AtlasDB 3'],'companies':['Atlas Works'],'people':[]},
        resolvability_score=95,ambiguity_flags=[],suggested_queries=[],status='RESOLVED',
        evidence=[dict(url=s['url'],quote=FACTS[0][1],source_type='OFFICIAL',independent_of_competitor=True,indicates_event=True,authority_reason='Fictional source')])
    def row(i,text=None):
        cid,t=FACTS[i];return dict(text=text or t,claim_ids=[cid],source_ids=['atlas-source'],evidence_passage_ids=[stable_id('passage','atlas-source'+' '.join(t.split()))],factual=True)
    def prop(i,surface,text=None):
        r=row(i,text);r.update(evidence_ids=r.pop('source_ids'),passage_ids=r.pop('evidence_passage_ids'),surface=surface);return r
    b['angle']=dict(scope_contract_version=2,angle=FACTS[1][1],payoff=FACTS[2][1],evidence_basis=[c for c,_ in FACTS],
        propositions=[prop(1,'angle'),prop(2,'payoff')],originality_status='CLEAR',editorial_status='READY')
    b['outline']=dict(scope_contract_version=2,beats=[dict(name='Explanation',purpose=t,claim_ids=[cid]) for cid,t in FACTS[1:]],
        propositions=[prop(i,str(i-1)) for i in range(1,len(FACTS))])
    # Includes exactly five candidates; all initial candidates are known-good.
    hooks=[dict(row(i),hook_id=f'hook-{i}',scores={k:95-i for k in b['draft']['hook_candidates'][0]['scores']}) for i in range(1,6)]
    rows=[dict(row(i),sentence_id=f's{i}',statement_type='FACT',materiality='HIGH') for i in range(2,len(FACTS))]
    b['draft']=dict(scope_contract_version=2,title_working='AtlasDB 3: What the Docs Actually List',title_claim_ids=['claim-feature-list'],
        title_proposition={'text':'AtlasDB 3: What the Docs Actually List','factual':False},
        hook_candidates=hooks,sections=[{'name':'EXPLANATION','sentences':rows}],visual_notes=[],on_screen_text=[])
    b['quality']['components']={k:85 for k in b['quality']['components']};b['quality']['warnings']=[]
    b['approved_sentence_texts']=[t for _,t in FACTS];b['approved_title']=b['draft']['title_working']
    return b

class Synthesizer(FixtureResearchSynthesizer):
    def synthesize(self,plan,sources,selected):
        raw=super().synthesize(plan,sources,selected)
        raw['requirement_resolutions']=[dict(requirement_id=q['requirement_id'],claim_ids=['claim-product-identity','claim-feature-list'],rationale='Direct fixture source establishes requirements.') for q in plan['requirements']]
        return raw
class Generator(FixtureScriptGenerator):
    scope_contract_version=2

def setup(db):
    b=bundle();cfg=config();cfg['resolution_authorities']['atlas.example']='Atlas Works'
    cfg['max_revision_attempts']=0
    choice=selected(db);choice['idea'].update(canonical_topic='AtlasDB 3',canonical_subject='AtlasDB 3',proposed_angle='explanation',
        story_context=[dict(canonical_subject='AtlasDB 3',entities=['Atlas Works'],products_models=['AtlasDB 3'],companies=['Atlas Works'],core_event='AtlasDB 3 database API introduction',confidence=1)])
    # Planner consumes canonical_topic from the selection.
    choice['idea']['supporting_facts']=[]
    return b,cfg,choice

def execute(db,b,cfg,choice,**kwargs):
    return run(db,choice,cfg,FixtureResearchProvider(b),Synthesizer(b),Generator(b),
        FixtureScriptFactChecker(b),FixtureQualityReviewer(b),Budget(cfg,offline=True,clock=lambda:0),NOW,'synthetic',**kwargs)
