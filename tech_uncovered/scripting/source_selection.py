"""Deterministic requirement-relative retrieval scores, not evidence verification."""
import math
import re
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlunsplit,unquote
from .sources import canonical_url
from .authority import classify

WEIGHTS={'requirement_match':.30,'entity_match':.30,'authority':.20,'document_type_fit':.15,'freshness':.05}
FIT={
 'IDENTITY_EVENT':{'LAUNCH':100,'PRODUCT':95,'API_DOCS':90,'DOCUMENTATION':85,'TECHNICAL':80,'NEWS':70,'COMMUNITY':45,'ACADEMY':30,'GENERIC':15,'PDF':5},
 'PRIMARY_DOCUMENTATION':{'PRODUCT':100,'API_DOCS':95,'TECHNICAL':90,'DOCUMENTATION':85,'LAUNCH':75,'ACADEMY':60,'NEWS':50,'COMMUNITY':25,'GENERIC':10,'PDF':5},
 'COMPARISON':{'PRODUCT':90,'API_DOCS':90,'SPECIFICATION':100,'BENCHMARK':95,'TECHNICAL':85,'DOCUMENTATION':80,'LAUNCH':60,'NEWS':60,'ACADEMY':25,'COMMUNITY':20,'GENERIC':10,'PDF':10},
}


def normalized(value):return ' '.join(re.findall(r'[^\W_]+',unquote(value or '').casefold()))

def contains(subject,text):
    needle=normalized(subject);return bool(needle and (' '+needle+' ') in (' '+normalized(text)+' '))


def group_url(url):
    p=urlsplit(canonical_url(url))
    path=re.sub(r'^/(?:[a-z]{2}(?:-[A-Za-z]{2,4}){0,2})(?=/)', '', p.path)
    if p.hostname=='community.openai.com':path=re.sub(r'(/t/[^/]+/\d+)/\d+$',r'\1',path)
    return urlunsplit((p.scheme,p.netloc,path or '/','',''))


def document_type(url,authority):
    p=urlsplit(url);path=p.path.casefold();host=p.hostname or ''
    if authority=='COMMUNITY':return 'COMMUNITY'
    if host.startswith('academy.'):return 'ACADEMY'
    if any(w in path for w in ('safety','system-card','technical','research-paper')):return 'TECHNICAL'
    if any(w in path for w in ('pricing','specifications','availability')):return 'SPECIFICATION'
    if 'benchmark' in path or 'evaluation' in path:return 'BENCHMARK'
    if '/models/' in path or '/products/' in path:return 'PRODUCT'
    if '/api/' in path:return 'API_DOCS'
    if any(w in path for w in ('/docs/','/guides/','/help/','release-notes')):return 'DOCUMENTATION'
    if '/index/' in path or '/releases/' in path or '/launch' in path:return 'LAUNCH'
    if path.endswith('.pdf'):return 'PDF'
    if authority=='REPUTABLE_SECONDARY':return 'NEWS'
    return 'GENERIC'


def score_result(hit,requirement,subjects,config,*,source=None,now=None):
    result=dict(hit);url=hit['url'];meta=classify(url,config.get('resolution_authorities'),source)
    result.update(meta,canonical_url=canonical_url(url),source_group=group_url(url))
    doc=document_type(url,meta['authority_type'])
    title=(source or {}).get('title') or hit.get('result_title') or hit.get('title') or ''
    headings=' '.join((source or {}).get('headings',[]));body=(source or {}).get('text','')
    # Body-only matches may be navigation/footer references, so cannot earn exact-match priority.
    exact=any(contains(s,url+' '+title+' '+headings) for s in subjects)
    body_match=any(contains(s,body) for s in subjects)
    entity=100 if exact else 45 if body_match else 0
    authority={'FIRST_PARTY':95,'REPUTABLE_SECONDARY':80,'COMMUNITY':30,'HOSTED_DOCUMENT':40,'UNKNOWN':20}.get(meta['authority_type'],10)
    category=requirement.get('category','PRIMARY_DOCUMENTATION')
    family='COMPARISON' if category.startswith('COMPARISON') else category if category in FIT else 'PRIMARY_DOCUMENTATION'
    fit=FIT[family].get(doc,45)
    if doc=='LAUNCH' and not any(normalized(urlsplit(url).path.rstrip('/').split('/')[-1])==normalized(s) for s in subjects):
        fit=min(fit,75)
    match=fit if exact else min(fit,40) if body_match else 5
    warnings=list(hit.get('selection_warnings',[]))
    # Version-bearing URL identity which disagrees with prominent fetched identity.
    path=normalized(urlsplit(url).path)
    prominent=title+' '+headings+' '+body[:1600]
    for subject in subjects:
        family_word=next((w for w in normalized(subject).split() if w.isalpha() and len(w)>2),None)
        if source and contains(subject,prominent) and not contains(subject,path) and family_word and family_word in path:
            normalized_subject=normalized(subject)
            prefix=re.split(r'\d',normalized_subject,1)[0].strip()
            pattern=re.escape(prefix)+r'\s+(\d+(?:\s+\d+)*)'
            expected=re.search(pattern,normalized_subject);actual=re.search(pattern,path)
            if expected and actual and expected.group(1)!=actual.group(1):warnings.append('CONTENT_URL_MISMATCH')
    date=hit.get('publication_date') or (source or {}).get('publication_date')
    freshness=0
    if date and now:
        try:
            parsed=datetime.fromisoformat(date.replace('Z','+00:00'));current=datetime.fromisoformat(now.replace('Z','+00:00'))
            if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
            age=(current-parsed).total_seconds()/86400
            freshness=100 if 0<=age<=7 else 80 if 0<=age<=30 else 30 if age>=0 else 0
        except (ValueError,TypeError):pass
    components={'requirement_match':match,'entity_match':entity,'authority':authority,'document_type_fit':fit,'freshness':freshness}
    weights=config.get('source_selection_weights',WEIGHTS)
    if set(weights)!=set(WEIGHTS) or not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in weights.values()) or not math.isclose(sum(weights.values()),1):
        raise ValueError('Invalid source_selection_weights')
    score=sum(weights[k]*components[k] for k in weights)
    if 'CONTENT_URL_MISMATCH' in warnings:score=max(0,score-25)
    rejected=not exact and not body_match and (doc=='PDF' or bool(re.search(r'\d',path)))
    result.update(exact_entity_match=exact,requirement_match=match,document_type=doc,
        freshness_hint=freshness,selection_components=components,selection_score=round(score,2),
        selection_warnings=sorted(set(warnings)),eligible_for_primary_identity='CONTENT_URL_MISMATCH' not in warnings,
        selection_rejection='REQUIREMENT_MISMATCH' if rejected else None,
        authority_score=authority,relevance_score=match,freshness_score=freshness)
    return result


def rank_results(hits,requirement,subjects,config,*,now=None):
    ranked=[score_result(h,requirement,subjects,config,now=now) for h in hits]
    ranked.sort(key=lambda h:(bool(h['selection_rejection']),-h['selection_score'],h['source_group']!=h['canonical_url'],h['canonical_url'],h['url']))
    groups={}
    for hit in ranked:
        group=hit['source_group']
        if group in groups:
            hit['selection_rejection']='LOCALIZED_OR_URL_DUPLICATE'
            hit['duplicate_of']=groups[group]['url'];groups[group]['fallback_urls'].append(hit['url'])
        else:groups[group]=hit;hit['fallback_urls']=[]
    ranked.sort(key=lambda h:(bool(h['selection_rejection']),-h['selection_score'],h['canonical_url']))
    rank=0
    for hit in ranked:
        if not hit['selection_rejection']:rank+=1;hit['rank']=rank
        else:hit['rank']=None
    return ranked
