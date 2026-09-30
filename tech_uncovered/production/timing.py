"""Phrase captions and deterministic visual events shared by estimated/audio timing."""
import math
from .models import CaptionSegment

def phrase_groups(words,max_words=6,max_chars=44):
    groups=[];current=[]
    for word in words:
        if len(word)>max_chars:raise ValueError('Caption token exceeds safe bounds')
        if current and (len(current)>=max_words or len(' '.join(current+[word]))>max_chars):groups.append(current);current=[]
        current.append(word)
        if len(current)>=2 and word.rstrip('”\"').endswith(('.', '?','!', ';', ':')):groups.append(current);current=[]
    if current:
        if len(current)==1 and groups and len(groups[-1])<max_words and len(' '.join(groups[-1]+current))<=max_chars:groups[-1]+=current
        else:groups.append(current)
    return groups

def phrase_captions(text,start,end,beat_id,words=None,fps=30):
    groups=phrase_groups(text.split());rows=[];index=0;total=len(text.split())
    for group in groups:
        a=words[index].start_seconds*fps if words else start+(end-start)*index/total
        last=index+len(group)-1
        b=words[last].end_seconds*fps if words else start+(end-start)*(last+1)/total
        emphasis=[i for i,w in enumerate(words[index:last+1]) if w.emphasis] if words else []
        a=max(start,round(a));b=min(end,round(b))
        if b<=a:raise ValueError('Caption phrase too short at target fps')
        rows.append(CaptionSegment(' '.join(group),a,b,beat_id,emphasis));index=last+1
    return rows

def visual_events(scene,fps=30):
    # Every 3–5 s on long scenes, with at most three list items emphasized at once.
    duration=scene.end_frame-scene.start_frame;count=max(1,math.ceil(duration/(5*fps)))
    groups=[]
    for surface in scene.on_screen_text:
        parts=surface.text.split(' • ')
        if len(parts)>1:
            for i in range(0,len(parts),3):groups.append(dict(source_sentence_id=surface.source_sentence_id,item_start=i,item_end=min(i+3,len(parts))))
    count=max(count,len(groups))
    events=[]
    for i in range(count):
        events.append(dict(frame=scene.start_frame+round(duration*i/count),type='LIST_GROUP' if groups else 'EMPHASIS',
                           focus=groups[i%len(groups)] if groups else dict(phrase_index=i),max_emphasis_items=3))
    return events
