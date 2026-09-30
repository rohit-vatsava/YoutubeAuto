"""Mix plan only; no synthesis, fetching, or licensing assumptions."""
from dataclasses import dataclass,field,asdict
import math

@dataclass
class NarrationTrack:
    audio_path:str|None=None
    gain_db:float=0.
@dataclass
class BackgroundMusic:
    audio_path:str|None=None
    gain_db:float=-24.
    fade_in_seconds:float=1.
    fade_out_seconds:float=1.
    ducking_db:float=-9.
    duck_during_narration:bool=True
@dataclass
class SoundEffect:
    asset_id:str
    timestamp_seconds:float
    gain_db:float=-15.
@dataclass
class AudioMix:
    narration:NarrationTrack=field(default_factory=NarrationTrack)
    music:BackgroundMusic=field(default_factory=BackgroundMusic)
    sound_effects:list[SoundEffect]=field(default_factory=list)
    master_limiter_db:float=-1.
    normalization_lufs:float=-16.
    status:str='MIX_CONTRACT_ONLY'
    def validate(self,duration):
        numbers=[self.narration.gain_db,self.music.gain_db,self.music.ducking_db,self.master_limiter_db,self.normalization_lufs]
        if any(not math.isfinite(v) for v in numbers) or not all(-60<=v<=6 for v in numbers[:2]) or not -60<=self.music.ducking_db<=0 or not -12<=self.master_limiter_db<=0 or not -30<=self.normalization_lufs<=-5:raise ValueError('Invalid audio gain/normalization')
        if any(not math.isfinite(t) or not 0<=t<=duration for t in (self.music.fade_in_seconds,self.music.fade_out_seconds)):raise ValueError('Audio fades out of range')
        if self.music.fade_in_seconds+self.music.fade_out_seconds>duration:raise ValueError('Overlapping full-track fades')
        if any(not math.isfinite(c.timestamp_seconds) or not 0<=c.timestamp_seconds<duration or not math.isfinite(c.gain_db) or not -60<=c.gain_db<=6 for c in self.sound_effects):raise ValueError('SFX cue outside timeline/gain bounds')
        return self
    def to_dict(self):return asdict(self)
