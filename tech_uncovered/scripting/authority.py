"""Shared domain ownership, separate from claim-relative factual verification."""
from urllib.parse import urlsplit

DEFAULTS = {
    'openai.com': {'owner':'OpenAI','authority_type':'FIRST_PARTY'},
    'community.openai.com': {'owner':'OpenAI Community','authority_type':'COMMUNITY'},
    'cdn.openai.com': {'owner':'OpenAI','authority_type':'HOSTED_DOCUMENT'},
}


def classify(url, authorities=None, source=None):
    registry=dict(DEFAULTS)
    for domain,value in (authorities or {}).items():
        registry[domain.casefold()]=({'owner':value,'authority_type':'FIRST_PARTY'} if isinstance(value,str) else value)
    host=(urlsplit(url).hostname or '').casefold()
    match=next((value for domain,value in sorted(registry.items(),key=lambda x:(-len(x[0]),x[0]))
                if host==domain or host.endswith('.'+domain)),None)
    owner=(match or {}).get('owner',host);kind=(match or {}).get('authority_type','UNKNOWN')
    if source and source.get('metadata_basis')=='fictional_fixture' and not match:
        owner=source.get('publisher',host);kind='FIRST_PARTY'
    # CDN storage alone never establishes authorship. Explicit document provenance is needed.
    if kind=='HOSTED_DOCUMENT' and source and source.get('document_provenance',{}).get('verified_owner')==owner:
        kind=source['document_provenance'].get('authority_type','HOSTED_DOCUMENT')
    return {'source_owner':owner,'authority_type':kind,'domain':host}
