"""Public-document fetching; source priority is never a verification vote."""
import hashlib
import ipaddress
import re
import socket
import ssl
import http.client
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .models import SourceRecord, stable_id
from .costs import ProviderFailure


def priority(source):
    return .50*source['authority_score']+.30*source['relevance_score']+.20*source['freshness_score']


def public_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ProviderFailure('Only public HTTPS documents are supported')
    addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ProviderFailure('Private or reserved network destination blocked')
    return sorted({a[4][0] for a in addresses})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ProviderFailure('Redirect blocked; use the canonical HTTPS URL')


class Document(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.skip=0;self.meta={};self.title=[];self.in_title=False;self.headings=[];self.in_heading=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'):self.skip+=1
        if tag=='title':self.in_title=True
        if tag in ('h1','h2'):self.in_heading=True
        if tag=='meta':self.meta[a.get('property',a.get('name',''))]=a.get('content','')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.skip=max(0,self.skip-1)
        if tag=='title':self.in_title=False
        if tag in ('h1','h2'):self.in_heading=False
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)
        if self.in_title:self.title.append(data)
        if self.in_heading:self.headings.append(data)


def fetch_document(url, config, budget, now):
    budget.check_time();addresses=public_url(url);budget.record.fetch_attempts+=1
    parsed=urlsplit(url)
    # Pin the validated address while retaining TLS hostname validation and SNI.
    # No proxy, re-resolution, or redirects can switch to an internal destination.
    connection=http.client.HTTPSConnection(parsed.hostname,timeout=min(config['request_timeout_seconds'],budget.remaining_seconds()),context=ssl.create_default_context())
    def pinned_connect():
        raw_socket=socket.create_connection((addresses[0],443),connection.timeout)
        try:connection.sock=connection._context.wrap_socket(raw_socket,server_hostname=parsed.hostname)
        except Exception:raw_socket.close();raise
    connection.connect=pinned_connect
    try:
        path=parsed.path or '/'
        if parsed.query:path+='?'+parsed.query
        connection.request('GET',path,headers={'User-Agent':'TechUncoveredResearch/1.0 (public evidence retrieval)','Accept':'text/html,text/plain'})
        response=connection.getresponse()
        if response.status!=200:raise ProviderFailure('Source HTTP status '+str(response.status)+'; redirects are not followed')
        kind=response.headers.get_content_type()
        if kind not in ('text/html','text/plain'):raise ProviderFailure('Unsupported source format: '+kind)
        raw=response.read(config['max_page_bytes']+1)
        if len(raw)>config['max_page_bytes']:raise ProviderFailure('Source exceeds document size limit')
        text=raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
    finally:connection.close()
    doc=Document()
    if kind=='text/html':doc.feed(text);text=' '.join(doc.parts)
    text=' '.join(text.split())[:config['max_source_chars']]
    if len(text)<80:raise ProviderFailure('Source has insufficient readable text')
    budget.record.fetched_pages+=1;budget.check_time()
    date=doc.meta.get('article:published_time') or doc.meta.get('date') or None
    s=SourceRecord(stable_id('source',url),url,doc.meta.get('og:title') or ''.join(doc.title) or url,
                   doc.meta.get('og:site_name') or urlsplit(url).hostname,date,now,text=text,
                   content_hash=hashlib.sha256(text.encode()).hexdigest())
    from .authority import classify
    identity=classify(url,config.get('resolution_authorities'))
    s.source_owner=identity['source_owner'];s.authority_type=identity['authority_type'];s.headings=doc.headings
    # Ownership is not claim-relative verification.
    s.notes=['Publisher/date are document assertions; authority must be assessed claim by claim.']
    return s


def independent_sources(sources):
    """Collapse exact or near copied documents; explicit syndication identity wins."""
    result=[];seen=set();shingles=[]
    for s in sources:
        words=re.findall(r'\w+',s.get('text','').lower())
        grams={tuple(words[i:i+5]) for i in range(max(0,len(words)-4))}
        key=s.get('syndication_group') or s.get('content_hash') or s['url']
        if key in seen or any(grams and len(grams & other)/max(1,min(len(grams),len(other)))>.85 for other in shingles):continue
        seen.add(key);shingles.append(grams);result.append(s)
    return result


def canonical_url(url):
    """Collapse query/fragment variants conservatively; retain exact retrieval URL separately.

    Query-addressed documents may be merged, never counted as extra corroboration.
    """
    from urllib.parse import urlunsplit
    p=urlsplit(url)
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/') or '/', '', ''))


def topic_relevance(source,resolution):
    """Conservative lexical drift guard; semantic verification remains separate."""
    if not resolution:return 100.0
    text=(source.get('title','')+' '+source.get('text','')).lower()
    entities=[n.lower() for n in resolution.get('named_entities',[]) if len(n)>2 and n.lower() not in ('ai','technology','software')]
    if not entities or not any(n in text for n in entities):return 0.0
    identifiers=resolution.get('identifiers',{})
    for group in ('products','companies'):
        names=identifiers.get(group,[])
        if names and not any(n.lower() in text for n in names):return 30.0
    stop={'the','and','with','that','this','from','into','its','was','has','have','for','new','a','an','of','to','in','on','is','ai'}
    words={w for w in re.findall(r'\w+',resolution.get('alleged_event','').lower()) if len(w)>2 and w not in stop and w not in entities}
    overlap=sum(w in text for w in words)/max(1,len(words))
    score=50+50*overlap
    date=resolution.get('event_date_if_known');published=source.get('publication_date')
    if date and published:
        try:
            a=datetime.fromisoformat(date.replace('Z','+00:00')).date();b=datetime.fromisoformat(published.replace('Z','+00:00')).date()
            if abs((a-b).days)>30:return min(score,30)
        except (ValueError,TypeError):return min(score,50)
    return round(score,2)
