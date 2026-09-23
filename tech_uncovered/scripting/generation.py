import re
from .hooks import score_hooks
from .models import GENERATION_VERSION


def normalize_draft(raw,packet,angle,config,script_id,revision):
    hook=score_hooks(raw['hook_candidates'],packet)
    sections=[s for s in raw['sections'] if s['name']!='HOOK']
    hook_sentence={k:hook[k] for k in ('text','claim_ids','source_ids','evidence_passage_ids')}
    if 'factual' in hook:hook_sentence['factual']=hook['factual']
    hook_sentence.update(sentence_id='selected-hook',statement_type='FACT',materiality='CRITICAL')
    sections.insert(0,{'name':'HOOK','sentences':[hook_sentence]})
    sentences=[s for section in sections for s in section['sentences']]
    ids=[s['sentence_id'] for s in sentences+raw.get('on_screen_text',[])]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate script sentence ID')
    full=' '.join(s['text'].strip() for s in sentences)
    count=len(re.findall(r"\b[\w]+(?:['’−-][\w]+)*\b",full))
    raw.update(script_id=script_id,revision=revision,idea_id=packet['idea_id'],research_packet_id=packet['research_packet_id'],
        final_angle=angle,selected_hook=hook,selected_hook_id=hook['hook_id'],sections=sections,full_script=full,
        word_count=count,estimated_duration=round(count/config['words_per_minute']*60,1),
        material_claim_ids=sorted({c for s in sentences for c in s.get('claim_ids',[])}),generation_version=GENERATION_VERSION)
    return raw


def sentences(draft):
    return [s for section in draft['sections'] for s in section['sentences']]+draft.get('on_screen_text',[])


def scope_propositions(raw):
    """Inventory publishable surfaces; entailment belongs to pivot_scope.classify."""
    from copy import deepcopy
    rows=[]
    def add(item,surface):
        if isinstance(item,str):item={'text':item}
        row=deepcopy(item)
        row.update(surface=surface,evidence_ids=item.get('source_ids',item.get('evidence_ids',[])),
                   passage_ids=item.get('evidence_passage_ids',item.get('passage_ids',[])))
        row.setdefault('claim_ids',[])
        rows.append(row)
    for section in raw.get('sections',[]):
        for item in section.get('sentences',[]):add(item,'body/'+section['name']+'/'+item.get('sentence_id',''))
    title=raw.get('title_proposition',{})
    add(title if title.get('text')==raw.get('title_working') else {'text':raw.get('title_working','')},'title')
    for key in ('on_screen_text','captions','visual_text','cta'):
        values=raw.get(key,[])
        if not isinstance(values,list):values=[values]
        for i,item in enumerate(values):add(item,key+'/'+str(i))
    for i,note in enumerate(raw.get('visual_notes',[])):
        # Production instructions and every literal displayed string are checked.
        add(dict(text=note,factual=False),'visual_notes/'+str(i))
        for j,text in enumerate(re.findall(r'“([^”]+)”|"([^"]+)"',note)):
            add(dict(text=next(x for x in text if x),factual=False),f'visual_notes/{i}/display/{j}')
    return rows
