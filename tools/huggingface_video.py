"""Single audited ZeroGPU Space. Default dry-run; never retries or uses HF credits."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.production.assets import AssetRouter
from tech_uncovered.production.huggingface_video import HuggingFaceVideoProvider,GeneratedVideoRequest

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--live',action='store_true')
 p.add_argument('--ffmpeg',default=os.getenv('FFMPEG_BINARY'))
 p.add_argument('--output',default='reports/huggingface/one-free-test')
 args=p.parse_args()
 request=GeneratedVideoRequest('Vertical macro cinematic view of an abstract dark circuit board with cyan light pulses moving smoothly along clean geometric traces. Slow camera push in, stable solid components, soft studio lighting. No text, no logos, no people. Technical background illustration, not a real product.')
 provider=HuggingFaceVideoProvider(dry_run=not args.live,ffmpeg=args.ffmpeg)
 result=AssetRouter().generate_video('hf-broll-test',request,provider=provider,output=args.output)
 Path(args.output,'routed-asset.json').write_text(json.dumps(result.to_dict(),indent=2))
 print(json.dumps(result.to_dict(),indent=2))
if __name__=='__main__':main()
