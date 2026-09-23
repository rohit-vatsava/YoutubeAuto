import time
import math
from .models import CostRecord


class LimitReached(RuntimeError):pass
class ProviderFailure(RuntimeError):pass


class Budget:
    def __init__(self, config, *, offline=False, clock=time.monotonic):
        self.config,self.clock,self.offline=config,clock,offline
        self.record=CostRecord(pricing={} if offline else dict(config.get('pricing',{})))
        self.started=clock();self.research_active=True;self.reserved=0.;self.uncertain=False;self._pending=[]
    def check_time(self):
        if self.research_active and self.clock()-self.started>=self.config['max_research_seconds']:
            raise LimitReached('Research time limit reached')
    def remaining_seconds(self):
        self.check_time()
        return max(.01,self.config['max_research_seconds']-(self.clock()-self.started)) if self.research_active else self.config['request_timeout_seconds']
    def finish_research(self):
        self.record.total_research_seconds=self.clock()-self.started;self.research_active=False
    def _sync(self):
        r=self.record;r.actual_cost_usd=r.estimated_model_cost_usd+r.estimated_search_cost_usd
        r.known_cost_usd=r.actual_cost_usd;r.active_reservation_usd=self.reserved
        r.estimated_cost_upper_bound_usd=r.known_cost_usd+r.conservative_unknown_cost_usd+self.reserved
    def estimate(self,input_tokens,*,search=False,payload_bytes=None):
        self.check_time()
        if self.offline:return 0.
        p=self.record.pricing
        if p.get('model_name')!=self.config['model_name'] or any(not isinstance(p.get(k),(int,float)) or not math.isfinite(p[k]) or p[k]<0 for k in ('input_per_million','output_per_million','search_per_call')):
            raise LimitReached('Pricing unknown for configured model; configure rates before paid requests')
        if not isinstance(input_tokens,int) or input_tokens<0:raise ValueError('Invalid local input token count')
        # Counted payload plus explicit conservative allowance for encoding/framing uncertainty.
        tokens=max(input_tokens,payload_bytes or 0)+self.config.get('tokenizer_protocol_reserve',1024)
        if search:tokens+=self.config['search_context_token_reserve']
        return tokens*p['input_per_million']/1e6+self.config['max_output_tokens']*p['output_per_million']/1e6+(p['search_per_call'] if search else 0)
    def can_reserve(self,amount):
        self.check_time();self._sync()
        return self.record.estimated_cost_upper_bound_usd+amount<=self.config['max_model_cost_usd']+1e-12
    def reserve(self,input_tokens,*,search=False,payload_bytes=None,stage='request'):
        amount=self.estimate(input_tokens,search=search,payload_bytes=payload_bytes)
        if not self.can_reserve(amount):raise LimitReached('Cost budget cannot fund the next bounded request')
        entry={'stage':stage,'input_tokens_local':input_tokens,'tokenizer_encoding':self.config.get('tokenizer_encoding','o200k_base'),
            'payload_bytes':payload_bytes,'reserved_cost_usd':amount,'actual_cost_usd':None,'released_reserve_usd':0.,
            'conservative_unknown_cost_usd':0.,'status':'RESERVED'}
        self._pending.append(entry);self.record.attempts.append(entry)
        self.reserved+=amount;self.record.reserved_cost_usd+=amount;self._sync()
        return amount
    def _take(self,amount):
        for i in range(len(self._pending)-1,-1,-1):
            if self._pending[i]['reserved_cost_usd']==amount:
                entry=self._pending.pop(i);self.reserved=max(0.,self.reserved-amount);return entry
        raise ValueError('Reservation was not active')
    def unknown(self,stage,reservation=None):
        amount=self._pending[-1]['reserved_cost_usd'] if reservation is None else reservation
        entry=self._take(amount);self.uncertain=True;self.record.usage_complete=False
        self.record.conservative_unknown_cost_usd+=amount
        entry.update(stage=stage,status='BILLING_UNKNOWN',usage='unknown; full reservation retained',conservative_unknown_cost_usd=amount)
        self._sync();return entry
    def settle(self,reservation,response,stage):
        usage=response.get('usage') if isinstance(response,dict) else None
        valid=bool(isinstance(usage,dict) and all(isinstance(usage.get(k),int) and usage[k]>=0 for k in ('input_tokens','output_tokens')))
        cached=usage.get('input_tokens_details',{}).get('cached_tokens',0) if valid else 0
        if not valid or not isinstance(cached,int) or not 0<=cached<=usage['input_tokens']:
            self.unknown(stage,reservation);return False
        entry=self._take(reservation);inp,out=usage['input_tokens'],usage['output_tokens'];p=self.record.pricing
        cost=0. if self.offline else (inp-cached)*p['input_per_million']/1e6+cached*p.get('cached_input_per_million',p['input_per_million'])/1e6+out*p['output_per_million']/1e6
        searches=sum(o.get('type')=='web_search_call' for o in response.get('output',[]));search_cost=0. if self.offline else searches*p['search_per_call']
        actual=cost+search_cost;released=max(0.,reservation-actual)
        self.record.model_input_tokens+=inp;self.record.model_output_tokens+=out
        self.record.estimated_model_cost_usd+=cost;self.record.estimated_search_cost_usd+=search_cost
        self.record.released_reserve_usd+=released
        entry.update(stage=stage,status='RECONCILED',response_id=response.get('id'),input_tokens=inp,output_tokens=out,
            estimated_model_cost_usd=cost,billed_search_calls=searches,actual_cost_usd=actual,released_reserve_usd=released)
        self._sync()
        if actual>reservation+1e-12 or self.record.estimated_cost_upper_bound_usd>self.config['max_model_cost_usd']+1e-12:
            raise LimitReached('Provider usage exceeded conservative reservation; further work stopped')
        self.check_time();return True
    def retry_decision(self,amount,*,safe,attempt,max_attempts):
        try:
            if not safe:return False,'CALL_NOT_SAFE_TO_RETRY'
            if attempt+1>=min(2,max_attempts):return False,'RETRY_LIMIT'
            if self.remaining_seconds()<min(1.,self.config['request_timeout_seconds']):return False,'TIME_BUDGET'
            if not self.can_reserve(amount):return False,'ANOTHER_FULL_RESERVATION_DOES_NOT_FIT'
            return True,'SAFE_CALL_ANOTHER_FULL_RESERVATION_FITS'
        except LimitReached:return False,'TIME_BUDGET'
    def stage(self,name):
        from contextlib import contextmanager
        @contextmanager
        def measured():
            keys=('estimated_model_cost_usd','estimated_search_cost_usd','conservative_unknown_cost_usd','reserved_cost_usd','released_reserve_usd','model_input_tokens','model_output_tokens','model_calls','search_calls','fetched_pages','fetch_attempts')
            before={k:getattr(self.record,k) for k in keys};start=self.clock()
            try:yield
            finally:
                self._sync();target=getattr(self.record,name)
                for k in keys:target[k]=target.get(k,0)+getattr(self.record,k)-before[k]
                target['elapsed_seconds']=target.get('elapsed_seconds',0)+self.clock()-start
                target['estimated_cost_usd']=target['estimated_model_cost_usd']+target['estimated_search_cost_usd']
                target['estimated_cost_upper_bound_usd']=target['estimated_cost_usd']+target['conservative_unknown_cost_usd']
        return measured()
