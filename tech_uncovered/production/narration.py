"""Offline narration contract. Live providers are injected, never called implicitly."""
from dataclasses import dataclass,field,asdict
from typing import Protocol
from pathlib import Path
import hashlib,math,wave

@dataclass
class WordTimestamp:
    text:str
    start_seconds:float
    end_seconds:float
    sentence_id:str
    emphasis:bool=False

@dataclass
class SentenceTimestamp:
    sentence_id:str
    text:str
    start_seconds:float
    end_seconds:float

@dataclass
class NarrationResult:
    audio_path:str
    duration_seconds:float
    words:list[WordTimestamp]
    sentences:list[SentenceTimestamp]
    provider:str
    model_voice_id:str|None=None
    provenance:dict=field(default_factory=dict)
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,data):
        result=cls(**dict(data,words=[WordTimestamp(**w) for w in data['words']],sentences=[SentenceTimestamp(**s) for s in data['sentences']]))
        return result

class NarrationProvider(Protocol):
    def narrate(self,draft:dict,output:Path)->NarrationResult:...

class ExternalNarrationAdapter:
    """Adapter boundary only. Import local audio/alignment exports via from_dict."""
    def narrate(self,draft,output):raise NotImplementedError('No live narration provider is connected')

def script_hash(draft):return hashlib.sha256(draft['full_script'].encode()).hexdigest()

def validate(result,draft):
    rows=[s for section in draft['sections'] for s in section['sentences']]
    if not result.audio_path or not Path(result.audio_path).is_file():raise ValueError('Narration audio is missing')
    if not math.isfinite(result.duration_seconds) or not 45<=result.duration_seconds<=60:raise ValueError('Narration duration must be 45–60 seconds')
    if Path(result.audio_path).suffix.lower()=='.wav':
        with wave.open(result.audio_path,'rb') as audio:
            actual_duration=audio.getnframes()/audio.getframerate()
            if abs(actual_duration-result.duration_seconds)>1/audio.getframerate():raise ValueError('Audio duration differs from timing metadata')
    if result.provenance.get('script_sha256')!=script_hash(draft):raise ValueError('Narration script provenance mismatch')
    if result.provenance.get('audio_sha256')!=hashlib.sha256(Path(result.audio_path).read_bytes()).hexdigest():raise ValueError('Narration audio hash mismatch')
    if [s.sentence_id for s in result.sentences]!=[r['sentence_id'] for r in rows]:raise ValueError('Sentence alignment does not cover script in order')
    if [w.text for w in result.words]!=draft['full_script'].split():raise ValueError('Word alignment does not match exact narration')
    previous=0
    for word in result.words:
        if not all(math.isfinite(v) for v in (word.start_seconds,word.end_seconds)) or not previous<=word.start_seconds<word.end_seconds<=result.duration_seconds+1e-8:raise ValueError('Invalid or overlapping word timestamps')
        previous=word.end_seconds
    previous=0
    for sent,row in zip(result.sentences,rows):
        words=[w for w in result.words if w.sentence_id==sent.sentence_id]
        if not words or ' '.join(w.text for w in words)!=row['text'].strip() or sent.text!=row['text']:raise ValueError('Sentence/word identity mismatch')
        if not all(math.isfinite(v) for v in (sent.start_seconds,sent.end_seconds)) or not previous<=sent.start_seconds<sent.end_seconds<=result.duration_seconds+1e-8:raise ValueError('Invalid sentence timestamps')
        if sent.start_seconds>words[0].start_seconds or sent.end_seconds<words[-1].end_seconds:raise ValueError('Sentence clips word timestamps')
        previous=sent.end_seconds
    if len({s.sentence_id for s in result.sentences})!=len(rows):raise ValueError('Duplicate sentence alignment')
    return result

class MockNarrationProvider:
    """Deterministic silent WAV with synthetic timing, never masquerades as speech."""
    def narrate(self,draft,output):
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        duration=draft['estimated_duration'];tokens=draft['full_script'].split();step=duration/len(tokens);words=[];sentences=[];index=0
        for section in draft['sections']:
            for row in section['sentences']:
                start=index*step
                for token in row['text'].split():
                    words.append(WordTimestamp(token,index*step,(index+1)*step,row['sentence_id']));index+=1
                sentences.append(SentenceTimestamp(row['sentence_id'],row['text'],start,index*step))
        with wave.open(str(output),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0\0'*round(duration*24000))
        result=NarrationResult(str(output.resolve()),duration,words,sentences,'deterministic-mock','silence-v1',dict(script_sha256=script_hash(draft),audio_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),synthetic=True,notes='Silence with synthetic alignment; replace with recorded narration and real word alignment'))
        return validate(result,draft)
