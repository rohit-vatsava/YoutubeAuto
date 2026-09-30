def decide(packet,draft,check,quality,angle,config):
    reasons=[];advisories=[]
    if packet and packet['research_status']=='CONTRADICTED':return {'status':'REJECTED','reasons':['CORE_STORY_CONTRADICTED']}
    if not packet or packet['research_status']!='SUFFICIENT':return {'status':'RESEARCH_REQUIRED','reasons':['INSUFFICIENT_RESEARCH']}
    if not draft:return {'status':'EDITORIAL_REVIEW','reasons':['MISSING_SCRIPT']}
    if not check:return {'status':'RESEARCH_REQUIRED','reasons':['MISSING_FACT_CHECK']}
    if check['verdict'] in ('FAIL','RESEARCH_REQUIRED'):return {'status':'RESEARCH_REQUIRED','reasons':['REVIEW_REQUIRED','FACT_CHECK_'+check['verdict']]}
    if not quality:return {'status':'EDITORIAL_REVIEW','reasons':['MISSING_QUALITY_REVIEW']}
    if check['verdict']!='PASS':reasons.append('MINOR_EDITS_NOT_ACCEPTED')
    if angle.get('originality_status')=='REJECT' or quality.get('originality_status')=='REJECT':return {'status':'REJECTED','reasons':['ORIGINALITY_REJECTION']}
    if quality.get('originality_status')=='REVIEW':advisories.append('ORIGINALITY_REVIEW')
    elif quality.get('originality_status')!='CLEAR':reasons.append('INVALID_ORIGINALITY_STATUS')
    if packet.get('unresolved_requirements') or packet.get('research_gaps'):return {'status':'RESEARCH_REQUIRED','reasons':['UNRESOLVED_RESEARCH']}
    if quality['score']<max(75,config['quality_threshold']):reasons.append('QUALITY_BELOW_THRESHOLD')
    from .quality import naturalness_findings
    findings=naturalness_findings(quality.get('spoken_naturalness',{}))
    if any(f['blocking'] for f in findings):reasons.append('SPOKEN_NATURALNESS_REVIEW')
    if any(not f['blocking'] for f in findings):advisories.append('SPOKEN_NATURALNESS_ADVISORY')
    if not config['script_word_min']<=draft['word_count']<=config['script_word_max']:reasons.append('WORD_COUNT_OUTSIDE_BOUNDS')
    if not config['duration_min_seconds']<=draft['estimated_duration']<=config['duration_max_seconds']:reasons.append('DURATION_OUTSIDE_BOUNDS')
    from .quality import normalize_warnings
    if any(w['blocking'] for w in normalize_warnings(quality.get('warnings',[]))):reasons.append('EDITORIAL_WARNINGS')
    return {'status':'EDITORIAL_REVIEW' if reasons else 'READY_FOR_PRODUCTION','reasons':reasons,'advisories':advisories}
