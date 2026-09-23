"""Context-preserving decomposition of attributed documentation enumerations."""
import re
from .scope_language import atomic_texts, normalize


def support(text, parent, claim, passages, packet):
    """Return only cited passages entailing this atom in its parent's grammar."""
    value=normalize(text).rstrip(';');whole=normalize(parent).rstrip(';')
    generic=enumeration_support(value,whole,claim,passages)
    if generic:return generic
    value=value.replace(' • ', ', ');whole=whole.replace(' • ', ', ')
    value=re.sub(r'^responses api listed tools: ', 'for developers using the responses api, the documentation lists support for ', value)
    whole=re.sub(r'^responses api listed tools: ', 'for developers using the responses api, the documentation lists support for ', whole)
    value=re.sub(r'^reasoning\.effort: ', 'it lists reasoning.effort settings of ', value)
    whole=re.sub(r'^reasoning\.effort: ', 'it lists reasoning.effort settings of ', whole)
    value=value.replace('for the responses api, the documentation lists ', 'for developers using the responses api, the documentation lists support for ')
    whole=whole.replace('for the responses api, the documentation lists ', 'for developers using the responses api, the documentation lists support for ')
    subject=re.escape(normalize(packet['topic']))
    owners={normalize(s.get('source_owner','')) for s in packet.get('source_records',[]) if s.get('source_owner')}
    # Canonicalize equivalent attributed list constructions before the shared rules.
    for owner in owners:
        lead=owner+"'s documentation "
        def canonical(t):
            t=t.replace(lead+'identifies '+normalize(packet['topic'])+' as a model for ',lead+'identifies '+normalize(packet['topic'])+' as a model and lists it for ')
            t=t.replace(lead+'lists '+normalize(packet['topic'])+' as a model',lead+'identifies '+normalize(packet['topic'])+' as a model')
            t=t.replace(lead+'lists '+normalize(packet['topic'])+' for ',lead+'identifies '+normalize(packet['topic'])+' as a model and lists it for ')
            t=t.replace('for the responses api, '+lead+'lists ','for developers using the responses api, the documentation lists support for ')
            if t.startswith(lead+'lists ') and whole.startswith('for the responses api, '):
                t='the documentation lists support for '+t[len(lead+'lists '):]
            if t=='for the responses api':t='for developers using the responses api'
            return t
        value=canonical(value);whole=canonical(whole)
    for owner in owners:
        identity=re.escape(owner)+r"'s documentation identifies "+subject+r" as a model"
        if re.fullmatch(identity,value):
            authorized=normalize(claim['supported_wording']).replace("the publisher's",owner+"'s")
            if authorized==value:
                return passages
        prefix=identity+r' and lists it for '
        match=re.fullmatch(prefix+r'([a-z ,]+)',whole)
        if match:
            items=[normalize(x) for x in atomic_texts(match[1])]
            atom=re.sub(r'^(?:'+prefix+r'|lists it for )','',value)
            if atom not in items:return []
            return [p for p in passages if (m:=re.fullmatch(r'Use it for ([^.]+)\.',p['quote']))
                    and atom in [normalize(x) for x in atomic_texts(m[1])]]
    tools=re.fullmatch(r'for developers using the responses api, the documentation lists support for ([a-z ,]+)',whole)
    if tools:
        scope='Tools supported by this model when using the Responses API.'
        atom=re.sub(r'^(?:for developers using the responses api, )?the documentation lists (?:support for )?','',value)
        for p in passages:
            if not p['quote'].startswith(scope):continue
            if value=='for developers using the responses api':return [p]
            if atom in [normalize(x) for x in atomic_texts(tools[1])]:
                rows=re.findall(r'([A-Za-z]+(?: [A-Za-z]+)*?) (Not supported|Supported)(?: |$)',p['quote'][len(scope):].strip())
                if any(normalize(name)==atom and status=='Supported' for name,status in rows):return [p]
    settings=re.fullmatch(r'it (?:also lists (?:(\w+) )?reasoning\.effort settings: |lists reasoning\.effort settings of )([a-z ,]+)',whole)
    if settings:
        items=[normalize(x) for x in atomic_texts(settings[2])]
        counts={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6}
        if (settings[1] and counts.get(settings[1])!=len(items)) or len(set(items))!=len(items):return []
        atom=re.sub(r'^it (?:also lists (?:\w+ )?reasoning\.effort settings: |lists reasoning\.effort settings of )','',value)
        if atom not in items:return []
        return [p for p in passages if (m:=re.fullmatch(r'reasoning\.effort supports ([^.]+)\.',p['quote']))
                and items==[normalize(x) for x in atomic_texts(m[1])]]
    return []


def concise_support(text, claim, passages, packet):
    """Bounded hook paraphrases; source text and authorized mappings remain required."""
    value=normalize(text)
    subject=re.escape(normalize(packet['topic']))
    owners={normalize(s.get('source_owner','')) for s in packet.get('source_records',[]) if s.get('source_owner')}
    for owner in owners:
        m=re.fullmatch(re.escape(owner)+r' lists (one|two|three|four|five|six) reasoning settings for '+subject,value)
        if m:
            count={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6}[m[1]]
            return [p for p in passages if (row:=re.fullmatch(r'reasoning\.effort supports ([^.]+)\.',p['quote']))
                    and len(set(normalize(x) for x in atomic_texts(row[1])))==count]
    m=re.fullmatch(subject+r' is documented for ([a-z ,]+)',value)
    if m:
        requested={normalize(x) for x in atomic_texts(m[1])}
        return [p for p in passages if (row:=re.fullmatch(r'Use it for ([^.]+)\.',p['quote']))
                and requested<={normalize(x) for x in atomic_texts(row[1])}]
    return []

def enumeration_support(value,whole,claim,passages):
    """A declared subject/predicate and exact list members; no semantic guessing."""
    split=lambda s:[normalize(x) for x in re.split(r'\s*[;,•]\s*(?:and\s+)?|\s+and\s+',s) if x.strip()]
    statement=normalize(claim['supported_wording'])
    m=re.fullmatch(r'(.+? supports )(.+)',statement)
    if not m:return []
    prefix=m[1]
    if not whole.startswith(prefix):return []
    items=split(whole[len(prefix):]);allowed=split(m[2])
    atom=value[len(prefix):] if value.startswith(prefix) else value
    if atom not in items or not set(items)<=set(allowed):return []
    return [p for p in passages if normalize(p['quote'])==statement]
