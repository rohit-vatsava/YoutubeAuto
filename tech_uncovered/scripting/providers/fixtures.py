"""Fictional inputs only. The checker uses an independent approved-text oracle."""
from copy import deepcopy
from ..models import SourceRecord, CHECK_EXAMPLE
from ..generation import sentences
from ..costs import ProviderFailure


class FixtureResearchProvider:
    name,version='fictional-fixture','1'
    def __init__(self,bundle):
        if bundle.get('synthetic') is not True:raise ValueError('Fixture must declare synthetic=true')
        self.bundle=bundle
    def search(self,query,*,question_id):
        return [{'url':s['url'],'authority_score':s['authority_score'],'freshness_score':s['freshness_score'],'relevance_score':s['relevance_score']} for s in self.bundle['sources']]
    def resolve_story(self,selected,limits):
        from ..resolution import RESOLUTION_EXAMPLE
        raw=deepcopy(self.bundle.get('story_resolution',RESOLUTION_EXAMPLE))
        hits=self.search(' '.join(r['title'] for r in selected['competitor_references']),question_id='story_identity')
        return raw,hits
    def fetch(self,url):
        s=next((s for s in self.bundle['sources'] if s['url']==url),None)
        if not s:raise ProviderFailure('Fixture source missing')
        return SourceRecord(**deepcopy(s))


class FixtureResearchSynthesizer:
    name,version='fixture-synthesis','1'
    def __init__(self,bundle):self.bundle=bundle
    def synthesize(self,plan,sources,selected):return deepcopy(self.bundle['packet'])


class FixtureScriptGenerator:
    name,version='fixture-script','1'
    def __init__(self,bundle):self.bundle=bundle
    def refine(self,packet,selected):return deepcopy(self.bundle['angle'])
    def outline(self,packet,angle):return deepcopy(self.bundle['outline'])
    def generate(self,packet,angle,outline,feedback=None):return deepcopy(self.bundle['draft'])


class FixtureScriptFactChecker:
    name,version='fixture-approved-text-check','1'
    def __init__(self,bundle):self.approved=frozenset(bundle['approved_sentence_texts']);self.title=bundle['approved_title'];self.visual_notes=bundle['draft']['visual_notes']
    def check(self,draft,packet,angle,now):
        r=deepcopy(CHECK_EXAMPLE)
        r['sentence_checks']=[{'sentence_id':s['sentence_id'],'supported':s['text'] in self.approved,'material':True,'claim_ids':s['claim_ids'],'source_ids':s['source_ids'],'issues':[] if s['text'] in self.approved else ['Not in independent fixture oracle']} for s in sentences(draft)]
        r['hook_checks']=[{'hook_id':h['hook_id'],'supported':h['text'] in self.approved,'issues':[]} for h in draft['hook_candidates'] if h.get('eligible')]
        r['title_supported']=draft['title_working']==self.title
        r['visual_notes_supported']=draft['visual_notes']==self.visual_notes
        r['verdict']='PASS' if r['title_supported'] and all(s['supported'] for s in r['sentence_checks']+r['hook_checks']) else 'FAIL'
        return r


class FixtureQualityReviewer:
    name,version='fixture-human-rubric','1'
    def __init__(self,bundle):self.bundle=bundle
    def review(self,draft,packet,selected):return deepcopy(self.bundle['quality'])
