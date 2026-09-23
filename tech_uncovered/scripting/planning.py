from ..intelligence.models import stable_id


class BoundedResearchPlanner:
    name,version='bounded-questions','2'
    def plan(self, selected, config, now):
        idea=selected['idea']
        refs=selected['competitor_references']
        lead=refs[0]['title'] if refs else idea['topic']
        questions=[('identity','What actually happened, who announced it, and when?',lead+' official announcement'),
                   ('mechanism','What changed technically and under what conditions?',lead+' documentation technical details'),
                   ('limits','What limitations or contradictory evidence affect this angle?',lead+' limitations independent analysis'),
                   ('relevance',idea['audience_question'],lead+' '+idea['proposed_angle'])]
        claims=[]
        for b in idea.get('story_context',[]):
            for c in b.get('factual_claims',[])+b.get('uncertain_claims',[]):
                claims.append({'claim_id':c['claim_id'],'text':c['text'],'status':'UNVERIFIED','prior_status':c.get('status'),'materiality':'CRITICAL' if c.get('material',True) else 'SUPPORTING'})
        requirements=[{'requirement_id':stable_id('requirement',text),'text':text} for text in dict.fromkeys(idea.get('required_research',[]))]
        plan = {'idea_id':idea['idea_id'],'canonical_topic':idea['topic'],
                'key_questions':[{'question_id':q,'question':text,'query':query} for q,text,query in questions],
                'claims_to_verify':claims,'entities':sorted({e for b in idea.get('story_context',[]) for e in b.get('entities',[])}),
                'likely_primary_sources':['Official announcement','Product documentation','Original paper or release'],
                'freshness_requirement':{'window_days':config['freshness_window_days'],'as_of':now},
                'minimum_evidence_threshold':'Direct credible passage for the core event; all critical claims scoped to evidence',
                'requirements':requirements,'stop_conditions':['Canonical story resolved','Critical claims supported','Freshness established','No remaining material question'],
                'max_search_calls':config['max_search_calls'],'max_sources':config['max_sources'],
                'max_searches_per_requirement':config.get('max_searches_per_requirement',2),
                'planned_at':now,'planner_version':self.version}
        from .requirements import prepare
        prepare(plan,selected)
        return plan
