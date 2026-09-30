import hashlib,json,re,html
from pathlib import Path
from .models import *

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def word_count(text):return len(re.findall(r"\b[\w]+(?:['’−-][\w]+)*\b",text))

def caption_chunks(text,max_chars=44):
    chunks=[];current=[]
    for word in text.split():
        if len(word)>max_chars:raise ValueError('Caption token exceeds safe bounds')
        if current and len(' '.join(current+[word]))>max_chars:chunks.append(' '.join(current));current=[]
        current.append(word)
    if current:chunks.append(' '.join(current))
    return chunks

def captions(text,start,end,beat_id):
    chunks=caption_chunks(text);weights=[len(c.split()) for c in chunks];total=sum(weights);cumulative=0;rows=[]
    for chunk,weight in zip(chunks,weights):
        a=start+round((end-start)*cumulative/total);cumulative+=weight;b=start+round((end-start)*cumulative/total)
        rows.append(CaptionSegment(chunk,a,b,beat_id))
    return rows

def visual(row):
    return VisualText(row['text'],row.get('factual',True),row['sentence_id'],list(row.get('claim_ids',[])),list(row.get('source_ids',[])),list(row.get('evidence_passage_ids',[])))

def build(draft,packet,readiness,output:Path,*,preview=False,selected=None):
    """Pure editorial assembly: copies source wording and provenance, never adds facts."""
    if not preview and readiness.get('status')!='READY_FOR_PRODUCTION':raise ValueError('M3 is not READY_FOR_PRODUCTION; use explicit preview')
    output=Path(output)
    rows=[row for section in draft['sections'] for row in section['sentences']]
    if not 7<=len(rows)<=10:raise ValueError('V1 requires 7–10 existing narration beats; editorial segmentation required')
    if len({r['sentence_id'] for r in rows})!=len(rows):raise ValueError('Duplicate narration IDs')
    narration=' '.join(r['text'].strip() for r in rows)
    if narration!=draft['full_script'] or word_count(narration)!=draft['word_count']:raise ValueError('Narration integrity mismatch')
    fps=30;frames=round(draft['estimated_duration']*fps)
    if not 45*fps<=frames<=60*fps:raise ValueError('Hard duration limit')
    output.mkdir(parents=True,exist_ok=True);(output/'assets').mkdir(exist_ok=True)
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920"><rect width="1080" height="1920" fill="#081321"/><g stroke="#15293d" stroke-width="1">'+''.join(f'<path d="M{x} 0V1920"/>' for x in range(0,1081,72))+''.join(f'<path d="M0 {y}H1080"/>' for y in range(0,1921,72))+'</g></svg>'
    assetpath=output/'assets/grid.svg';assetpath.write_text(svg)
    asset=AssetRequirement('grid','assets/grid.svg','svg',False,'Original project-generated graphic',hashlib.sha256(svg.encode()).hexdigest())
    total=sum(word_count(r['text']) for r in rows);cumulative=0;beats=[];scenes=[]
    types=['HeroReveal','DocumentationCard','FeatureList','ProductCard','ComparisonCards','QuoteCard','ThreeStepProcess','ArchitectureDiagram','FinalPayoff']
    texts=draft.get('on_screen_text',[]);used=set()
    for i,row in enumerate(rows):
        start=round(frames*cumulative/total);cumulative+=word_count(row['text']);end=round(frames*cumulative/total)
        beat=NarrationBeat('beat-'+row['sentence_id'],row['sentence_id'],row['text'],start,end,list(row.get('claim_ids',[])),list(row.get('source_ids',[])),list(row.get('evidence_passage_ids',[])),row.get('factual',True));beats.append(beat)
        matched=[t for t in texts if t['sentence_id'] not in used and set(t.get('evidence_passage_ids',[]))&set(row.get('evidence_passage_ids',[]))]
        # One mapped display surface per scene; remaining surfaces remain in later matched scenes.
        screen=matched[:1]
        if screen:used.add(screen[0]['sentence_id'])
        else:screen=[row]
        kind=types[min(i,len(types)-1)] if i<len(rows)-1 else 'FinalPayoff'
        if '•' in screen[0]['text']:kind='FeatureList'
        cap=captions(row['text'],start,end,beat.beat_id)
        scenes.append(ScenePlan(f'scene-{i+1:02}',kind,[beat.beat_id],row['text'],[visual(t) for t in screen],
             'Progressively reveal existing text on geometric cards; use abstract graphics only, no implied measurements or fabricated screenshots.',
             ['grid'],start,end,'fade-through-background',cap,sorted(set(beat.claim_ids)|{c for t in screen for c in t.get('claim_ids',[])}),
             [dict(start_frame=start,end_frame=end,status='UNASSIGNED',duck_under_voice=True)],
             [dict(frame=start,status='UNASSIGNED',intent='soft transition')]))
    # Preserve the complete supplied display inventory, including any not assigned above.
    for t in texts:
        if t['sentence_id'] not in used:
            candidates=[s for s in scenes if set(t.get('claim_ids',[]))&set(s.claim_ids)]
            if not candidates:raise ValueError('Display surface has no corresponding scene provenance')
            candidates[-1].on_screen_text.append(visual(t));used.add(t['sentence_id'])
    idea=(selected or {}).get('idea',{})
    dna=dict(topic=idea.get('topic'),cohort=next(iter(idea.get('source_opportunities',[])),{}).get('market_cohort'),story_type=idea.get('story_type'),angle_type=idea.get('angle_type'),hook_type=idea.get('hook_type','unclassified'),hook_text=draft['selected_hook']['text'],word_count=draft['word_count'],duration=frames/fps,scene_count=len(scenes),scene_archetypes=[s.scene_type for s in scenes],CTA_type='evaluation_guidance',visual_density=round(sum(len(s.on_screen_text) for s in scenes)/len(scenes),2),spoken_list_count=sum(r['text'].count(',')>=2 for r in rows),payoff_timestamp=next((b.start_frame/fps for b in beats if 'guidance' in next(r for r in rows if r['sentence_id']==b.sentence_id).get('statement_type','')),beats[-1].start_frame/fps),source='deterministic-production-plan-v1',notes='Creative labels are local editorial descriptors, not measured performance')
    spec=ProductionSpec('video-'+digest({'script_id':draft['script_id'],'revision':draft['revision'],'draft':digest(draft)})[:16],draft['script_id'],draft['revision'],draft['title_working'],frames/fps,beats,sorted({c for b in beats for c in b.claim_ids}),scenes,[asset],dict(draft_sha256=digest(draft),packet_sha256=digest(packet),research_packet_id=packet.get('research_packet_id'),m3_readiness=readiness.get('status'),source_surface_ids=[r['sentence_id'] for r in rows+texts],synthetic=packet.get('synthetic',False)),dna,production_status='PREVIEW_ONLY' if preview else 'SCRIPT_APPROVED_AUDIO_PENDING')
    return spec
