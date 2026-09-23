import math
import re
from collections import Counter
from .generation import sentences
from .models import QUALITY_WEIGHTS


def spoken_diagnostics(draft):
    texts=[s['text'] for s in sentences(draft)];text=' '.join(texts).lower();flags=[]
    if any(len(t.split())>27 for t in texts):flags.append('OVERLY_LONG_SENTENCES')
    if any(p in text for p in ('furthermore','moreover','in conclusion')):flags.append('UNNATURAL_TRANSITIONS')
    starts=Counter(' '.join(t.lower().split()[:2]) for t in texts)
    if any(n>=3 for n in starts.values()):flags.append('REPEATED_SENTENCE_STRUCTURES')
    if sum(text.count(w) for w in ('synergy','paradigm','orchestration','inference','latency','throughput','tokenization'))>3:flags.append('EXCESSIVE_JARGON')
    if sum(len(s['text'].split()) for sec in draft['sections'] if sec['name'] in ('CONTEXT','SETUP') for s in sec['sentences'])>30:flags.append('EXCESSIVE_SETUP_BEFORE_PAYOFF')
    if any(p in text for p in ('in today’s rapidly','in today\'s rapidly','game-changer','delve into','ever-evolving','changes everything')):flags.append('GENERIC_AI_PHRASES')
    if sum(text.count(w) for w in ('incredible','revolutionary','groundbreaking','amazing','unprecedented','ultimate'))>1:flags.append('UNNECESSARY_SUPERLATIVES')
    if any(p in text for p in ('smash that','like and subscribe','stay tuned for more','don’t forget to subscribe')):flags.append('ROBOTIC_CTA')
    return flags


def review_quality(raw,draft):
    values=raw['components']
    if set(values)!=set(QUALITY_WEIGHTS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=100 for v in values.values()):raise ValueError('Invalid editorial score')
    raw['score']=round(sum(values[k]*v for k,v in QUALITY_WEIGHTS.items()),3)
    raw['spoken_naturalness']['flags']=sorted(set(raw['spoken_naturalness']['flags']+spoken_diagnostics(draft)))
    raw.update(script_id=draft['script_id'],revision=draft['revision'])
    return raw
