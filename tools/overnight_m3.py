"""One-shot, explicitly authorized review. Dry-run by default; no research tools."""
import argparse,copy,json,os,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tech_uncovered.database import Database
from tech_uncovered.scripting.cli import configuration
from tech_uncovered.scripting.editorial_revision import source,saved_revision,apply_edits,create,load,review
from tech_uncovered.scripting.generation import scope_propositions
from tech_uncovered.scripting.pivot_scope import validate_candidate
from tech_uncovered.scripting.hooks import mapping_errors
from tech_uncovered.scripting.quality import spoken_diagnostics
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.providers.openai_live import OpenAIModel,ModelScriptFactChecker,ModelScriptQualityReviewer,build_payload
from tech_uncovered.scripting.token_count import count_tokens
SID='script-a6d1cd2b-929d-456c-9536-9f396267e359'
ALLOWED=('script_fact_check','editorial_review')
EDITS={'sentence_moves':[{'sentence_id':'s7','target_section':'Explanation','before_sentence_id':'s4'}],
's7':'Pick the documented settings and tools you need. Test them in your environment. Measure task success. Compare the result with your requirements.'}

class Capture:
    def __init__(self,cfg):self.config=cfg;self.payloads=[]
    def request(self,stage,instructions,data,example=None,search=False):
        if stage not in ALLOWED or search:raise ValueError('Forbidden stage')
        self.payloads.append((stage,build_payload(self.config,stage,instructions,data,example,False)))
        return {}

class BoundedModel(OpenAIModel):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.stages=[]
    def request(self,stage,*args,**kwargs):
        if stage not in ALLOWED or stage in self.stages or kwargs.get('search') or self.stages!=list(ALLOWED[:len(self.stages)]):raise ValueError('Live stage budget exceeded')
        if stage!=ALLOWED[len(self.stages)]:raise ValueError('Invalid live stage order')
        self.stages.append(stage)
        return super().request(stage,*args,**kwargs)

class PassOnlyQuality:
    def __init__(self,reviewer,path):self.reviewer,self.path=reviewer,path
    def review(self,*args):
        if json.loads((self.path/'fact_check.json').read_text())['verdict']!='PASS':raise ValueError('Stop: fact-check must PASS')
        return self.reviewer.review(*args)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--live',action='store_true');args=ap.parse_args()
    out=ROOT/'reports/overnight';out.mkdir(exist_ok=True)
    cfg=configuration(ROOT/'config/script.json');cfg.update(max_attempts=1,max_revision_attempts=0,max_model_cost_usd=.35,max_search_calls=0)
    now=datetime.now(timezone.utc).isoformat();db=Database(ROOT/'data/intelligence.sqlite3')
    try:
        data,payload=source(ROOT/'reports/scripts',SID,db)
        base,_,_=saved_revision(ROOT/'reports/scripts',SID,6,db,data,payload)
        draft=apply_edits(base,EDITS,cfg);draft['revision']=7
        scope=validate_candidate({'propositions':scope_propositions(draft)},data['research_packet'],'script_generation','overnight-7')
        mapping=[e for sec in draft['sections'] for row in sec['sentences'] for e in mapping_errors(row,data['research_packet'])]
        safe=(scope['result']=='PASS' and scope['next_status']=='CONTINUE' and not mapping and cfg['script_word_min']<=draft['word_count']<=cfg['script_word_max'] and cfg['duration_min_seconds']<=draft['estimated_duration']<=cfg['duration_max_seconds'])
        capture=Capture(cfg);ModelScriptFactChecker(capture).check(draft,data['research_packet'],data['angle'],now);ModelScriptQualityReviewer(capture).review(draft,data['research_packet'],data['idea'])
        budget=Budget(cfg);reservations=[]
        for stage,p in capture.payloads:
            reservations.append({'stage':stage,'max_cost_usd':budget.estimate(count_tokens(json.dumps(p,ensure_ascii=False),cfg),payload_bytes=len(json.dumps(p).encode()))})
        total=sum(r['max_cost_usd'] for r in reservations)
        gate={'offline_safe':safe,'scope':scope['result'],'mapping_errors':mapping,'word_count':draft['word_count'],'duration':draft['estimated_duration'],'naturalness':spoken_diagnostics(draft),'reservations':reservations,'maximum_estimated_cost_usd':total,'within_budget':total<=.35,'first_stage':'FACT_CHECK'}
        (out/'m3-gate.json').write_text(json.dumps(gate,indent=2)+'\n');(out/'final-edits.json').write_text(json.dumps(EDITS,indent=2)+'\n');(out/'proposed_script.json').write_text(json.dumps(draft,indent=2)+'\n')
        print(json.dumps(gate,indent=2))
        if not args.live:return
        if not safe or total>.35:raise ValueError('Offline/cost gate failed; no live call')
        # External suite receipt must have been written after the complete green suite.
        receipt=json.loads((out/'offline-test-gate.json').read_text())
        if receipt.get('failures')!=0 or receipt.get('errors')!=0 or not receipt.get('tests'):raise ValueError('Full suite not green')
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env');key=os.getenv('OPENAI_API_KEY','').strip()
        if not key:raise ValueError('Missing API key; no live call')
        lock=out/'live-attempt.json'
        with lock.open('x') as f:json.dump({'started_at':now,'max_calls':2,'budget_usd':.35},f)
        manifest,folder=create(ROOT/'reports/scripts',SID,EDITS,db,now,cfg,base_revision=6)
        if manifest['revision']!=7:raise ValueError('Unexpected revision; stop')
        loaded=load(ROOT/'reports/scripts',SID,7,db,now,cfg)
        model=BoundedModel(key,cfg,budget)
        result=review(loaded,db,ModelScriptFactChecker(model),PassOnlyQuality(ModelScriptQualityReviewer(model),folder),budget,now,cfg)
        (out/'m3-live-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:db.close()
if __name__=='__main__':main()
