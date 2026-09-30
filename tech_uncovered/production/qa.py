import hashlib,json
from pathlib import Path
from .models import ARCHETYPES
from .planning import digest

def check(spec,draft,packet,root):
    errors=[];root=Path(root).resolve()
    def require(condition,code):
        if not condition:errors.append(code)
    require((spec['width'],spec['height'],spec['fps'])==(1080,1920,30),'FORMAT')
    require(45<=spec['duration_target']<=60,'DURATION')
    require(7<=len(spec['scenes'])<=10,'SCENE_COUNT')
    require(spec['provenance']['draft_sha256']==digest(draft),'DRAFT_PROVENANCE')
    require(spec['provenance']['packet_sha256']==digest(packet),'PACKET_PROVENANCE')
    source={r['sentence_id']:r for sec in draft['sections'] for r in sec['sentences']}
    source.update({r['sentence_id']:r for r in draft.get('on_screen_text',[])})
    assets={a['asset_id']:a for a in spec['assets']};seen=[];displayed=set();previous=0;caption_text=[]
    for scene in spec['scenes']:
        require(scene['scene_type'] in ARCHETYPES,'UNKNOWN_ARCHETYPE')
        require(scene['start_frame']==previous and scene['end_frame']>previous,'SCENE_GAP_OR_OVERLAP');previous=scene['end_frame'];seen.append(scene['scene_id'])
        for aid in scene['asset_requirements']:require(aid in assets,'MISSING_ASSET')
        for text in scene['on_screen_text']:
            original=source.get(text['source_sentence_id']);displayed.add(text['source_sentence_id'])
            require(original is not None,'UNKNOWN_TEXT_SOURCE')
            if original:
                require(text['text']==original['text'],'NEW_FACTUAL_VISUAL_TEXT')
                for k in ('claim_ids','source_ids','evidence_passage_ids'):require(text[k]==original.get(k,[]),'ALTERED_'+k)
                require(text['factual']==original.get('factual',True),'ALTERED_FACTUALITY')
            require(all(len(w)<=44 for w in text['text'].split()),'VISUAL_TOKEN_OVERFLOW')
        cursor=scene['start_frame']
        for cap in scene['caption_segments']:
            require(cap['start_frame']==cursor and cap['end_frame']>cursor,'CAPTION_TIMING');cursor=cap['end_frame']
            require(len(cap['text'])<=44,'CAPTION_SAFE_LENGTH');caption_text.append(cap['text'])
        require(cursor==scene['end_frame'],'CAPTION_COVERAGE')
        require(' '.join(c['text'] for c in scene['caption_segments'])==scene['narration'],'CAPTION_NARRATION_MISMATCH')
    require(len(seen)==len(set(seen)),'DUPLICATE_SCENE')
    require(previous==round(spec['duration_target']*spec['fps']),'TIMELINE_END')
    require(' '.join(caption_text)==draft['full_script'],'NARRATION_COVERAGE')
    require({r['sentence_id'] for r in draft.get('on_screen_text',[])}<=displayed,'MISSING_UPSTREAM_DISPLAY')
    beats=spec['narration_beats'];require(len(beats)==len(spec['scenes']),'BEAT_COUNT')
    for b,scene in zip(beats,spec['scenes']):
        row=source.get(b['sentence_id'],{})
        require(b['narration']==row.get('text'),'ALTERED_NARRATION')
        require((b['start_frame'],b['end_frame'])==(scene['start_frame'],scene['end_frame']),'BEAT_SCENE_MISMATCH')
        for k in ('claim_ids','source_ids','evidence_passage_ids'):require(b[k]==row.get(k,[]),'BEAT_MAPPING')
    for asset in assets.values():
        path=(root/asset['path']).resolve();require(path.is_relative_to(root),'ASSET_PATH_ESCAPE')
        require(path.is_file(),'UNRESOLVED_ASSET')
        if path.is_file() and path.is_relative_to(root):require(hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256'],'ASSET_HASH')
    return dict(passed=not errors,errors=sorted(set(errors)),dimensions=[1080,1920],fps=30,duration=spec['duration_target'],scenes=len(seen),caption_coverage='complete' if 'CAPTION_COVERAGE' not in errors else 'failed',visual_geometry='Requires browser render QA',audio='Pending narration; preview is silent')
