"""One Agnes job, dry-run by default. No automatic retries or paid fallback."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tech_uncovered.production.agnes import AgnesVideoProvider, AgnesVideoRequest
from tech_uncovered.production.assets import AssetRouter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--free-access-confirmed', action='store_true')
    parser.add_argument('--output', default='reports/agnes/one-free-test')
    parser.add_argument('--prompt', default='A small orange origami boat gently floating on a calm pond, soft daylight, slow camera movement, no people, no text or logos.')
    parser.add_argument('--image-url')
    args = parser.parse_args()
    # Read only the dedicated key; never print or persist credentials.
    key = os.getenv('AGNES_API_KEY', '')
    if not key and Path('.env').exists():
        for line in Path('.env').read_text().splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == 'AGNES_API_KEY':
                key = value.strip().strip('\"\'')
    provider = AgnesVideoProvider(key, dry_run=not args.live,
                                  free_access_confirmed=args.free_access_confirmed)
    asset = AssetRouter().generate_video('agnes-test', AgnesVideoRequest(args.prompt, first_frame=args.image_url),
                                        provider=provider, output=args.output)
    print(json.dumps(asset.to_dict(), indent=2))


if __name__ == '__main__':
    main()
