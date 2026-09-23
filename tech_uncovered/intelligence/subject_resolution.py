"""Deterministic title-only research leads. No factual verification or IO providers."""
import json
import re
from pathlib import Path


def has(text, term):
    return bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)', text, re.I))


class MetadataSubjectResolver:
    name, version = 'metadata-subject-resolver', '1.0'

    def __init__(self, rules=None):
        self.rules = rules if rules is not None else json.loads(
            (Path(__file__).resolve().parents[2]/'config/radar_rules.json').read_text())

    def resolve(self, candidate):
        title = candidate.get('title', '')
        cohort = candidate.get('market_cohort')
        entities = {k:list(v) for k,v in self.rules['entities'].items()}
        entities.update({'AMD':['amd','advanced micro devices'], 'NVIDIA':['nvidia'],
                         'GitHub':['github'], 'Meta':['meta','meta platforms'],
                         'LG':['lg'], 'Exxon':['exxon','exxonmobil']})
        products = {**self.rules['products'], 'NVIDIA DSX':['nvidia dsx'], 'NVIDIA RTX Spark':['nvidia rtx spark'], 'Xbox':['xbox']}
        names = [name for name, aliases in entities.items() if any(has(title,a) for a in aliases)]
        if re.search(r'\bmeta[- ]analysis\b',title,re.I):names=[n for n in names if n!='Meta']
        if re.search(r'\bapple (?:pie|fruit)\b',title,re.I):names=[n for n in names if n!='Apple']
        found_products = [name for name, aliases in products.items() if any(has(title,a) for a in aliases)]
        if 'GeForce RTX' in found_products and not has(title,'geforce'):
            found_products[found_products.index('GeForce RTX')]='RTX'
        versions = re.findall(r'\bCVE-\d{4}-\d{4,}\b|\b(?:GPT|RTX|RX|Ryzen|Claude|Gemini|Llama|Windows|iPhone|Python|Node|Bun|Deno|Linux|CUDA)[ -]?\d+(?:\.\d+)*(?:[ -]+(?:Astra|Sonnet|Opus|Pro|Max|Ti|XT|XTX|\d+GB))*\b|\bV\d+(?:\.\d+)*\b', title, re.I)
        if cohort=='HARDWARE_CHIPS' or has(title,'GPU'):
            versions += re.findall(r'\b\d{4}\s+(?:XT|XTX|Ti)(?:\s+\d+GB)?\b',title,re.I)
        def normalize_version(value):
            if value.lower().startswith('cve-'):return value.upper()
            for canonical in ('GPT','RTX','RX','Ryzen','Claude','Gemini','Llama','Windows','iPhone','Python','Node','Bun','Deno','Linux','CUDA'):
                value=re.sub(r'^'+canonical+r'(?=[ -]?\d)',canonical,value,flags=re.I)
            for canonical in ('Astra','Sonnet','Opus','Pro','Max','Ti','XT','XTX'):
                value=re.sub(r'\b'+canonical+r'\b',canonical,value,flags=re.I)
            return value
        versions = sorted(set(normalize_version(v) for v in versions),key=str.casefold)
        versions = [v for v in versions if not any(v!=w and v.casefold() in w.casefold() for w in versions)]
        tech_rules = {
            'software engineering': ['software engineering'], 'programming':['programming'],
            'browser cache':['browser cache'], 'device code phishing':['device code phishing'],
            'MCP':['mcp'], 'RAG':['rag','retrieval augmented generation','retrieval-augmented generation'],
            'AI agents':['ai agents','ai agent'], 'AI engineering':['ai engineer','ai engineering'],
            'smart TVs':['smart tv','smart tvs'], 'semiconductor fabrication':['semiconductor fab'],
        }
        technologies = [k for k,aliases in tech_rules.items() if any(has(title,a) for a in aliases)]
        if cohort=='DEV_SOFTWARE' and has(title,'engineer') and not technologies:
            technologies.append('software engineering')
        if re.search(r'\bAI\b',title) and re.search(r'\b(simplified|concepts|explained)\b',title,re.I):
            technologies.append('AI fundamentals')
        # Raw GPU generations are literal identifiers, never guessed manufacturers.
        specific = versions or found_products
        subject_parts = names + specific + technologies
        method = 'explicit_title_patterns'
        # Existing Radar hints may cover projects absent from our aliases. Require
        # a title anchor and retain the previous bounded proper-name expansion.
        if not subject_parts or (not names and not found_products and not technologies and candidate.get('named_entity_hints')):
            expanded=[]
            for hint in candidate.get('named_entity_hints', []):
                if hint.casefold() in {'ai','software','technology','computing','model','gpu','chip','hardware'} or not has(title,hint):continue
                match=re.search(re.escape(hint)+r'(?:\s+(?:[A-Z][a-zA-Z0-9-]*|[A-Z]*\d+[A-Z0-9-]*)){0,3}',title)
                value=match.group() if match else hint
                value=re.split(r'\s+(?:Is|Changes|Review|Impressions|Actually|Finally|And|The|With|In|At|Scams|Gamers|CEO|Hacker|EXPOSED|BY|Doesn)\b',value)[0]
                expanded.append(value)
            subject_parts=expanded
            if expanded:method='title_anchored_radar_hints'
        # Remove aliases contained in a more specific explicit model/project.
        subject_parts=list(dict.fromkeys(subject_parts))
        subject_parts=[p for p in subject_parts if not any(p!=q and p.casefold() in q.casefold() for q in subject_parts)]
        event=None
        event_patterns=[
            (r'legal troubles','legal troubles'), (r'\blawsuit\b','lawsuit'),
            (r'\b(?:before the foldable|copied this phone)\b','historical product/design comparison'),
            (r'\b(?:CVE-\d{4}-\d+|vulnerabilit\w*)\b','vulnerability'),
            (r'\b(?:breach|hacked|hacker|hack)\b','security incident allegation'),
            (r'\binfected\b','infection allegation'), (r'\bspy\b','privacy allegation'),
            (r'\bfake news\b','public dispute'),
            (r'\bscams?\b','consumer allegation'),
            (r'\b(?:math breakthrough|research paper|study)\b','research development'),
            (r'\b(?:vs\.?|versus|compared|comparison)\b','comparison'),
            (r'\b(?:launch\w*|release[ds]?|announc\w*|unveil\w*|introducing|is (?:finally )?here|are here)\b','release/announcement'),
            (r'\bupdate[ds]?\b','update'), (r'\bban(?:ned)?\b','ban'),
            (r'\b(?:acquisition|acquir\w*)\b','acquisition'),
            (r'\b(?:shutdown|shuts down)\b','shutdown'), (r'\bearnings\b','earnings'),
            (r'\b(?:layoffs|quitting|resigns)\b','staff departure'),
            (r'\bpartnership\b','partnership'), (r'\barchitecture\b','architecture'),
            (r'\bsummit\b','summit appearance'), (r'\b(?:just changed|changes everything)\b','unspecified change'),
        ]
        for pattern,label in event_patterns:
            if re.search(pattern,title,re.I):event=label;break
        anchored_events = [event_hint for event_hint in candidate.get('event_hints', [])
            if has(title,event_hint) or any(has(title,alias) for alias in self.rules['events'].get(event_hint,[]))]
        if method=='title_anchored_radar_hints' and anchored_events:
            event='; '.join(anchored_events)
        elif event is None and subject_parts and anchored_events:
            event='; '.join(anchored_events)
        evergreen = bool(re.search(r'\b(how to|explained|simplified|concepts|essential skills|what .* need to know|why\b|the end of|another great day of|first look|to its limits|building|editing faster)\b',title,re.I))
        if event and event!='comparison':evergreen=False
        if technologies and not names and not versions and event=='comparison':evergreen=True
        if evergreen:event=None
        unresolved=[]
        status='EVERGREEN_TOPIC' if subject_parts and evergreen else 'CONCRETE_STORY' if subject_parts and event else 'INSUFFICIENT_CONTEXT'
        # Financial anecdotes without an actor cannot identify an external story.
        if re.search(r'\b(?:billion|million|office fling)\b',title,re.I) and (not names or has(title,'office fling')):
            status='INSUFFICIENT_CONTEXT';event=None;unresolved.append('Actor or incident identity is not established by the title')
        # A multi-news roundup is not one canonical story. Educational lists are
        # allowed only as explicitly evergreen topics.
        if not evergreen and re.search(r',.*(?: & | and )| & .*’s',title,re.I):
            status='INSUFFICIENT_CONTEXT';unresolved.append('Multiple developments; one story must be selected')
        if subject_parts and all(re.fullmatch(r'v\d+(?:\.\d+)*',p,re.I) for p in subject_parts):
            status='INSUFFICIENT_CONTEXT';unresolved.append('Version has no identified product/project')
        if not subject_parts:
            status='INSUFFICIENT_CONTEXT';event=None;unresolved.append('No sufficiently specific title-anchored subject')
        elif status=='INSUFFICIENT_CONTEXT':unresolved.append('No sufficiently identified event or explicit evergreen treatment')
        if has(title,'this phone'):unresolved.append('Phone model is unnamed')
        if event=='legal troubles':unresolved.append('Specific case and outcome are unnamed')
        if status=='CONCRETE_STORY':unresolved.append('Event is a metadata allegation; independently verify details and date')
        subject=' / '.join(subject_parts) or None
        if versions and any(v.startswith('CVE-') for v in versions):kind='SECURITY_EVENT'
        elif technologies and not names and not versions:kind='DEVELOPER_TOPIC' if any(t in technologies for t in ['programming','software engineering','AI engineering']) else 'TECHNOLOGY'
        elif versions:kind='MODEL' if any(re.match(r'(GPT|Claude|Gemini|Llama)',v,re.I) for v in versions) else 'HARDWARE' if cohort=='HARDWARE_CHIPS' else 'PRODUCT'
        elif found_products:kind='PRODUCT'
        elif names and all(n in {'Linux','Docker','Kubernetes','React','Python','Rust','TypeScript','JavaScript','PostgreSQL','Redis','Vulkan','CUDA'} for n in names):kind='PROJECT'
        elif names:kind='PERSON' if all(' ' in n and n not in {'Meta Platforms','Advanced Micro Devices','Raspberry Pi'} for n in names) else 'COMPANY'
        elif subject:kind='PROJECT'
        else:kind='UNKNOWN'
        # Entity labels describe literal title subjects, not factual confidence.
        confidence='LOW' if status=='INSUFFICIENT_CONTEXT' else 'MEDIUM' if evergreen or (event and ('allegation' in event or event in {'public dispute','unspecified change'})) or unresolved and any('unnamed' in x for x in unresolved) else 'HIGH'
        channel=candidate.get('channel','')
        source_owner=next((n for n in ['NVIDIA','IBM'] if candidate.get('source_role')=='vendor_official' and has(channel,n)),None)
        return dict(canonical_subject=subject,subject_type=kind,named_entities=subject_parts,
            product_or_project=list(dict.fromkeys(specific)),event_or_change=event,
            version_or_generation=versions,temporal_marker=re.findall(r'\b(?:20\d{2}|today|yesterday|new|just|before)\b',title,re.I),
            confidence=confidence,extraction_method=method,unresolved_reasons=unresolved,
            story_context_status=status,story_type='EVENT_STORY' if status=='CONCRETE_STORY' else status,
            technologies=technologies,channel_context={'market_cohort':cohort,'source_role':candidate.get('source_role'),'source_owner':source_owner},
            resolver_version=self.version)
