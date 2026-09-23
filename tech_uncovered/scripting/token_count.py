"""Local token counting only; never downloads vocabulary or sends text to a service."""
from functools import lru_cache
import json
import subprocess
from pathlib import Path
from .costs import ProviderFailure


def count_tokens(text,config):
    if config.get('tokenizer_encoding','o200k_base')!='o200k_base':
        raise ProviderFailure('Unsupported local tokenizer encoding; configure a validated counter')
    return _count(text,config.get('tokenizer_node','node'))


@lru_cache(maxsize=32)
def _count(text,node):
    try:
        result=subprocess.run([node,str(Path(__file__).with_suffix('.cjs'))],
            input=text,text=True,capture_output=True,timeout=10,check=True)
        return json.loads(result.stdout)['input_tokens']
    except (OSError,subprocess.SubprocessError,ValueError,KeyError):
        raise ProviderFailure('Local tokenizer unavailable; no paid request sent') from None
