"""M2 editorial requirements and compatibility with the unchanged event-only M3.

No evidence is verified here. Eligibility merely avoids known invalid entry.
"""
import re

VERSION = 'm2-m3-entry-v1'
TECH_TYPES = {'PRODUCT','MODEL','TOOL','PROJECT','TECHNOLOGY','HARDWARE','DEVELOPER_TOPIC'}
EVENT_TYPES = {'EVENT','SECURITY_EVENT','BUSINESS_EVENT'}
PEOPLE = {'jensen huang','sam altman','ilya sutskever','elon musk'}
COMPANIES = {'nvidia','amd','intel','anthropic','openai','google','adobe','meta','apple','microsoft','ibm','lg','exxon'}


def norm(value):return re.sub(r'\s+',' ',str(value or '').strip().casefold())


def subject_type(idea):
    explicit=idea.get('subject_type')
    if explicit and explicit!='UNKNOWN':return explicit
    kinds={c.get('metadata_subject_resolution',{}).get('subject_type') for c in idea.get('story_context',[])}-{'UNKNOWN',None}
    # Mixed company/person metadata must not inherit product affordances.
    names={norm(n) for n in idea.get('named_entities',[])}
    for context in idea.get('story_context',[]):
        names.update(norm(n) for n in context.get('named_entities',context.get('entities',[])))
    if names & PEOPLE and not kinds & TECH_TYPES:return 'PERSON'
    if len(kinds)==1:return next(iter(kinds))
    if kinds & TECH_TYPES:return sorted(kinds & TECH_TYPES)[0]
    if names & COMPANIES:return 'COMPANY'
    if idea.get('story_context'):
        if any(c.get('products_models') for c in idea['story_context']):return 'PRODUCT'
        if any(c.get('technologies') for c in idea['story_context']):return 'TECHNOLOGY'
    # Legacy supplied context often uses technical nouns without a typed field.
    subject=norm(idea.get('canonical_subject') or idea.get('topic'))
    if re.search(r'\b(model|compiler|database|search|processor|software|tool)\b',subject):return 'TECHNOLOGY'
    if subject in COMPANIES:return 'COMPANY'
    if subject in PEOPLE:return 'PERSON'
    return 'UNKNOWN'


def angle_type(idea):
    angle=norm(idea.get('angle_type') or idea.get('transformation') or idea.get('proposed_angle'))
    if angle.startswith('explain '):return 'explanation'
    return angle


def assess(idea):
    kind=subject_type(idea);angle=angle_type(idea)
    contexts=idea.get('story_context',[])
    story_type=idea.get('story_type') or next((c.get('story_type') for c in contexts if c.get('story_type')),None)
    if not story_type and contexts:
        story_type='EVERGREEN_TOPIC' if all(c.get('evergreen_or_news')=='evergreen' for c in contexts) else 'EVENT_STORY'
    subject=idea.get('canonical_subject') or next((c.get('canonical_subject') for c in contexts if c.get('canonical_subject')),None)
    names=idea.get('named_entities') or [n for c in contexts for n in c.get('entities',[])+c.get('products_models',[])]
    identity=bool(subject and norm(subject) not in {'ai','technology','software','unknown','company','person','model'} and (names or kind in TECH_TYPES))
    if idea.get('story_context_status')=='INSUFFICIENT_CONTEXT' or any(c.get('story_context_status')=='INSUFFICIENT_CONTEXT' for c in contexts):identity=False
    event=idea.get('alleged_event') or next((c.get('core_event') or c.get('alleged_event') or c.get('what_changed') for c in contexts if c.get('core_event') or c.get('alleged_event') or c.get('what_changed')),None)
    if 'NO_IDENTIFIABLE_EVENT' in idea.get('risk_flags',[])+idea.get('unresolved_flags',[]):event=None
    comparison=angle in {'comparison','trade-off','trade off','trade-off/comparison'}
    evergreen=story_type=='EVERGREEN_TOPIC'
    optional=angle in {'explanation','mechanism','misconception','strategy/mechanism','underlying technical/business idea'}
    if comparison:requirement='COMPARISON_CONTEXT_REQUIRED'
    elif evergreen and angle in {'practical lesson','explanation','mechanism','misconception'}:requirement='EVERGREEN_OK'
    elif optional:requirement='EVENT_OPTIONAL'
    else:requirement='EVENT_REQUIRED'
    blockers=[]
    if not identity:blockers.append('INSUFFICIENT_SUBJECT_IDENTITY')
    text=' '.join(str(idea.get(k) or '') for k in ('audience_question','one_sentence_premise'))
    allowed_angles={'explanation','mechanism','misconception','practical lesson','practical example','implications','comparison','trade-off','trade off','trade-off/comparison','history','what changed','why now','why it matters','what happened','launch/release analysis','incident/breach/legal-event analysis','strategy/mechanism','practical consequence','what they said / argued','underlying technical/business idea'}
    invalid=angle not in allowed_angles
    if kind in {'PERSON','COMPANY'}:
        # Inspect old persisted wording too, without rewriting its provenance.
        targets={str(idea.get('topic') or subject or '')}|{str(n) for n in names}
        invalid |= any(re.search(r'\b(?:workflow .*? to use|inside|use|using|test of)\s+'+re.escape(target)+r'(?=\W|$)',text,re.I) for target in targets if target)
        invalid |= angle=='practical lesson' and kind=='PERSON'
    if kind=='UNKNOWN':invalid=True
    if invalid:blockers.append('INVALID_ANGLE_FOR_SUBJECT_TYPE')
    if requirement=='EVENT_REQUIRED' and not event:blockers.append('NO_IDENTIFIABLE_EVENT')
    if requirement in {'EVERGREEN_OK','EVENT_OPTIONAL'} and not event and not (evergreen and kind in TECH_TYPES):
        blockers.append('INSUFFICIENT_EVERGREEN_SUBJECT_CONTEXT')
    if comparison:
        supplied=idea.get('comparison_context') or {}
        targets=supplied.get('subjects') or []
        criterion=supplied.get('criterion')
        if not (len(set(map(norm,targets)))>=2 and criterion):blockers.append('COMPARISON_CONTEXT_MISSING')
    satisfied=not blockers
    if comparison:mode='COMPARISON'
    elif evergreen and requirement!='EVENT_REQUIRED':mode='EVERGREEN_SUBJECT'
    elif kind=='SECURITY_EVENT' or re.search(r'breach|vulnerability|infection|security incident',str(event),re.I):mode='SECURITY_EVENT'
    elif kind=='BUSINESS_EVENT' or re.search(r'legal|lawsuit|staff departure|layoff|acquisition|earnings|partnership',str(event),re.I):mode='BUSINESS_EVENT'
    else:mode='EVENT'
    # M3 has no evergreen/comparison dispatch yet. Do not pretend a prepared
    # semantic contract is executable, or manufacture an event to pass its gate.
    if mode in {'EVERGREEN_SUBJECT','COMPARISON'}:blockers.append('STORY_RESOLUTION_MODE_NOT_SUPPORTED')
    elif not event and 'NO_IDENTIFIABLE_EVENT' not in blockers:blockers.append('NO_IDENTIFIABLE_EVENT')
    if re.search(r'\b(?:secret motive|real reason|why .*? (?:quit\w*|resign\w*|left)|what .*? (?:really wants|secretly wants))\b',text,re.I):
        blockers.append('MOTIVE_SPECULATION_REQUIRED')
    return dict(subject_type=kind,story_requirement=requirement,story_requirement_satisfied=satisfied,
                story_resolution_mode=mode,m3_entry_ready=not blockers,m3_entry_blockers=sorted(set(blockers)),m3_entry_contract_version=VERSION)


def apply(idea):
    result=assess(idea.to_dict())
    for key,value in result.items():setattr(idea,key,value)
    return result
