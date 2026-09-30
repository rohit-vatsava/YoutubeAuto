import math
import re
from collections import Counter
from .models import QUALITY_WEIGHTS


def spoken_sentences(draft):
    rows=[s for sec in draft.get('sections',[]) if sec.get('spoken',True) is not False
          for s in sec.get('sentences',[]) if s.get('spoken',True) is not False]
    hook=draft.get('selected_hook')
    if hook and not any(s.get('sentence_id')=='selected-hook' or s.get('text')==hook.get('text') for s in rows):rows.insert(0,hook)
    cta=draft.get('cta',[])
    if not isinstance(cta,list):cta=[cta]
    rows += [s for s in cta if isinstance(s,dict) and s.get('spoken') is True and s not in rows]
    return rows


def normalize_warnings(warnings):
    # Explicit types only. Never infer blocking status from warning prose.
    from .fact_check import normalize_findings
    return normalize_findings(warnings,'EDITORIAL_WARNING')


def naturalness_findings(naturalness):
    """Legacy flags are observations, not explicit blocking assessments."""
    from .fact_check import normalize_findings
    result=[]
    for value in naturalness.get('findings',[])+naturalness.get('flags',[]):
        if isinstance(value,str):
            result.append(dict(category='NATURALNESS_OBSERVATION',severity='INFO',blocking=False,text=value,legacy_untyped=True))
        else:result.extend(normalize_findings([value],'SPOKEN_NATURALNESS'))
    return result


def spoken_diagnostics(draft):
    texts=[s['text'] for s in spoken_sentences(draft)];text=' '.join(texts).lower();flags=[]
    if any(len(t.split())>27 for t in texts):flags.append('OVERLY_LONG_SENTENCES')
    if any(p in text for p in ('furthermore','moreover','in conclusion')):flags.append('UNNATURAL_TRANSITIONS')
    starts=Counter(' '.join(t.lower().split()[:2]) for t in texts)
    if any(n>=3 for n in starts.values()):flags.append('REPEATED_SENTENCE_STRUCTURES')
    if sum(text.count(w) for w in ('synergy','paradigm','orchestration','inference','latency','throughput','tokenization'))>3:flags.append('EXCESSIVE_JARGON')
    if sum(len(s['text'].split()) for sec in draft['sections'] if sec['name'] in ('CONTEXT','SETUP') for s in sec['sentences'] if sec.get('spoken',True) is not False and s.get('spoken',True) is not False)>30:flags.append('EXCESSIVE_SETUP_BEFORE_PAYOFF')
    if any(p in text for p in ('in today’s rapidly','in today\'s rapidly','game-changer','delve into','ever-evolving','changes everything')):flags.append('GENERIC_AI_PHRASES')
    if sum(text.count(w) for w in ('incredible','revolutionary','groundbreaking','amazing','unprecedented','ultimate'))>1:flags.append('UNNECESSARY_SUPERLATIVES')
    if any(p in text for p in ('smash that','like and subscribe','stay tuned for more','don’t forget to subscribe')):flags.append('ROBOTIC_CTA')
    return flags


def review_quality(raw,draft):
    values=raw['components']
    if set(values)!=set(QUALITY_WEIGHTS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=100 for v in values.values()):raise ValueError('Invalid editorial score')
    raw['score']=round(sum(values[k]*v for k,v in QUALITY_WEIGHTS.items()),3)
    findings=naturalness_findings(raw['spoken_naturalness'])
    findings += [dict(category=flag,severity='WARNING',blocking=False,text=flag,source='deterministic_diagnostic') for flag in spoken_diagnostics(draft)]
    raw['spoken_naturalness']['findings']=findings
    raw['spoken_naturalness']['flags']=[]  # Migrated observations remain visible in findings.
    raw['warnings']=normalize_warnings(raw.get('warnings',[]))
    raw.update(script_id=draft['script_id'],revision=draft['revision'])
    return raw
