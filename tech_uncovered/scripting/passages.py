"""Conservative repair for missing documentation links; never infer performance.

Offsets address the persisted fetched text (not HTML bytes). Structured table
observations replace broader wording explicitly; unsupported prose stays unverified.
"""
import re
from .models import stable_id


def passage(source, start, end, claim_id, support='DIRECT'):
    text=source['text'][start:end]
    return dict(passage_id=stable_id('passage',source['source_id']+' '.join(text.split())),
                source_id=source['source_id'],claim_ids=[claim_id],text=text,
                start_offset=start,end_offset=end,support_type=support,
                quote=text,relation='CONTRADICTS' if support=='CONTRADICTING' else 'SUPPORTS')


def locate(source, quote, claim_id, support='DIRECT'):
    # Whitespace-normalized model quotations map back to exact original offsets.
    words=quote.split()
    if not words:return None
    match=re.search(r'\s+'.join(re.escape(w) for w in words),source.get('text',''))
    if not match or len(' '.join(words))<20:return None
    return passage(source,match.start(),match.end(),claim_id,support)


def repair_documentation(claim, sources, assessments, subject):
    if claim.get('passages') or not claim.get('supported_wording') or not subject:return
    kind=claim.get('claim_type');cid=claim['claim_id']
    kind={'IDENTITY_AVAILABILITY':'IDENTITY_EVENT','TECHNICAL_DOCUMENTATION':'DOCUMENTATION_DETAILS'}.get(kind,kind)
    if kind not in ('IDENTITY_EVENT','CAPABILITY','CONSTRAINT','SPECIFICATION','RESEARCH_QUESTION','DOCUMENTATION_DETAILS'):return
    for assessment in assessments:
        source=sources.get(assessment['source_id'],{})
        if (cid not in assessment.get('credible_for_claim_ids',[]) or not assessment.get('rationale')
            or assessment.get('source_type')!='DOCUMENTATION' or assessment.get('primary_or_secondary')!='PRIMARY'
            or source.get('authority_type')!='FIRST_PARTY' or not source.get('eligible_for_primary_identity',True)
            or source.get('acquisition_state')=='DISCOVERED' or subject.casefold() not in source.get('title','').casefold()):continue
        text=source.get('text','');matches=[];topics=[]
        def add(pattern, label):
            match=re.search(pattern,text,re.I)
            if match:matches.append(match);topics.append(label)
            return match
        wording=claim['supported_wording'].casefold()
        if kind=='IDENTITY_EVENT':
            add(re.escape(subject)+r' is [^.]{1,180}\.', 'documented identity')
        elif kind=='DOCUMENTATION_DETAILS':
            # Extract only bounded, attributed product observations, never outcome prose.
            add(r'Use it for [^.]{1,180}\.', 'documented intended uses')
            add(r'reasoning\.effort supports [^.]{1,120}\.', 'configurable reasoning effort')
            add(r'Tools supported by this model when using the Responses API\. (?:[A-Za-z ]+ (?:Not supported|Supported) ?)+(?=Snapshots)', 'Responses API tool support')
        elif kind=='CAPABILITY':
            # Require a named tool row AND the API scope, never the navigation list.
            scope=re.search(r'Tools supported by this model when using the [^.]{1,50} API\.',text)
            if not scope:continue
            for row in re.finditer(r'([A-Z][a-z]+(?: [a-z]+){0,2}) (?:Not supported|Supported)',text[scope.end():]):
                name=row.group(1)
                if name.casefold() in wording:
                    matches.append(scope)
                    match=re.search(re.escape(row.group(0)),text[scope.end():])
                    start=scope.end()+match.start();end=scope.end()+match.end()
                    # Store offsets directly for rows shorter than the legacy quote limit.
                    matches.append((start,end));topics.append(name.lower()+' in the documented API scope')
                    break
        elif kind=='CONSTRAINT':
            if 'modalit' in wording or any(w in wording for w in ('audio','video','image input','text output')):
                add(r'Modalities Text (?:Input and output|Input only|Output only) Image (?:Input and output|Input only|Not supported) Audio (?:Not supported|Input and output) Video (?:Not supported|Input and output)', 'modality constraints')
            if 'fine-tuning' in wording:add(r'Fine-tuning (?:Not supported|Supported)', 'fine-tuning support')
        elif kind=='SPECIFICATION':
            if 'context' in wording:add(r'[\d,]+ context window [\d,]+ max output tokens', 'context and output limits')
            if 'input' in wording and ('price' in wording or '$' in wording):
                add(r'Text tokens Per 1M tokens Input \$[\d.]+ Cached input \$[\d.]+(?: Cache writes \$[\d.]+)? Output \$[\d.]+', 'listed base token prices')
        elif kind=='RESEARCH_QUESTION':
            if not ('document' in wording and any(w in wording for w in ('tools','constraints','limits'))):continue
            add(r'[\d,]+ context window [\d,]+ max output tokens', 'documented token limits')
            add(r'Fine-tuning (?:Not supported|Supported)', 'documented feature constraints')
        if not matches:continue
        partial=kind in ('IDENTITY_EVENT','RESEARCH_QUESTION')
        spans=[m if isinstance(m,tuple) else m.span() for m in matches]
        claim['passages']=[passage(source,a,b,cid,'PARTIAL' if partial else 'DIRECT') for a,b in spans]
        claim['original_supported_wording']=claim['supported_wording']
        # Exact attributed observations make the repair auditable, instead of treating
        # lexical overlap or the synthesis confidence as semantic entailment.
        owner=source.get('source_owner') or 'The publisher'
        quotes='; '.join('“'+p['text']+'”' for p in claim['passages'])
        claim['supported_wording']=f'{owner}’s documentation for {subject} lists: {quotes}.'
        if claim.get('claim_type')=='IDENTITY_AVAILABILITY':
            claim['supported_wording']=f'{owner}’s documentation identifies {subject} as a model.'
        claim['verification_scope']='SUPPORTED_WORDING_ONLY'
        claim['evidence_link_method']='STRUCTURED_DOCUMENTATION_OBSERVATION'
        claim['documented_topics']=topics
        claim['status']='PARTIALLY_VERIFIED' if partial else 'VERIFIED'
        claim['requires_attribution']=True
        claim['limitations']=list(dict.fromkeys(claim.get('limitations',[])+[
            'Verification is limited to the exact attributed documentation observations; broader original wording is not established.',
            'Observed at '+str(source.get('retrieved_at'))+'; not evidence of launch timing or independent performance.']))
        return
