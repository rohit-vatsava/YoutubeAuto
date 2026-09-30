"""Local asset routing and host placement. No downloads or external integration."""
from dataclasses import dataclass,field,asdict
from pathlib import Path
import hashlib,math,shutil

SOURCE_TYPES={'avatar','official_documentation','official_screenshot','local_graphic','generated_image','generated_video','stock_licensed'}
@dataclass
class AvatarAsset:
    asset_id:str
    source_path:str|None=None
    crop:dict=field(default_factory=lambda:dict(x=0.,y=0.,width=1.,height=1.))
    position:str='right'
    width_fraction:float=.30
    transparent_background:bool|None=None
    style:str='host-cutout'
    version:str='1'
    provenance:dict=field(default_factory=lambda:dict(status='PLACEHOLDER',note='No identity or likeness generated'))
    def to_dict(self):return asdict(self)
    def bounds(self):
        if self.position not in ('left','right','center') or not math.isfinite(self.width_fraction) or not .2<=self.width_fraction<=.4:raise ValueError('Avatar position/width out of bounds')
        if set(self.crop)!={'x','y','width','height'} or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in self.crop.values()) or not (0<=self.crop['x']<1 and 0<=self.crop['y']<1 and 0<self.crop['width']<=1-self.crop['x'] and 0<self.crop['height']<=1-self.crop['y']):raise ValueError('Invalid normalized crop')
        width=1080*self.width_fraction;x={'left':104,'right':976-width,'center':540-width/2}[self.position]
        return dict(x=x,y=300,width=width,height=650)

@dataclass
class RoutedAsset:
    asset_id:str
    source_type:str
    path:str|None
    status:str
    license:str
    provenance:dict
    sha256:str|None=None
    def to_dict(self):return asdict(self)

class AssetRouter:
    def route(self,asset_id,source_type,source_path=None,*,provenance,license='UNCONFIRMED',output=None):
        if source_type not in SOURCE_TYPES or not provenance:raise ValueError('Asset source type and provenance required')
        if source_path is None:return RoutedAsset(asset_id,source_type,None,'PLACEHOLDER',license,provenance)
        path=Path(source_path)
        if not path.is_file():raise ValueError('Local asset missing; remote sources are not supported')
        hash=hashlib.sha256(path.read_bytes()).hexdigest()
        if output:
            target=Path(output)/'assets'/(hash[:16]+path.suffix.lower());target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);stored=str(target.relative_to(output))
        else:stored=str(path.resolve())
        return RoutedAsset(asset_id,source_type,stored,'LOCAL',license,provenance,hash)

    def generate_video(self, asset_id, request, *, provider, output):
        """Explicit opt-in provider boundary; ordinary local route() never calls it."""
        result = provider.generate(request, output)
        if hasattr(result, 'to_dict'):
            typed = result.to_dict()
            if result.path:
                source = 'local_graphic' if result.fallback == 'LOCAL_MOTION_GRAPHIC' else 'generated_video'
                routed = self.route(asset_id, source, result.path, provenance=typed)
                routed.status = result.status
                return routed
            result = typed
        return RoutedAsset(asset_id, 'generated_video', None,
                           'DRY_RUN' if result['status'] == 'DRY_RUN' else 'REMOTE_REVIEW_REQUIRED',
                           'UNCONFIRMED', result)
