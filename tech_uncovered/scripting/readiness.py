def decide(packet,draft,check,quality,angle,config):
    reasons=[]
    if packet and packet['research_status']=='CONTRADICTED':return {'status':'REJECTED','reasons':['CORE_STORY_CONTRADICTED']}
    if not packet or packet['research_status']!='SUFFICIENT':return {'status':'RESEARCH_REQUIRED','reasons':['INSUFFICIENT_RESEARCH']}
    if not draft or not check or not quality:return {'status':'RESEARCH_REQUIRED','reasons':['INCOMPLETE_GENERATION_OR_REVIEW']}
    if check['verdict'] in ('FAIL','RESEARCH_REQUIRED'):return {'status':'RESEARCH_REQUIRED','reasons':['REVIEW_REQUIRED','FACT_CHECK_'+check['verdict']]}
    if check['verdict']!='PASS':reasons.append('MINOR_EDITS_NOT_ACCEPTED')
    if angle.get('originality_status')=='REJECT' or quality.get('originality_status')=='REJECT':return {'status':'REJECTED','reasons':['ORIGINALITY_REJECTION']}
    if angle.get('originality_status')!='CLEAR' or quality.get('originality_status')!='CLEAR':reasons.append('ORIGINALITY_REVIEW_REQUIRED')
    if packet.get('unresolved_requirements') or packet.get('research_gaps'):return {'status':'RESEARCH_REQUIRED','reasons':['UNRESOLVED_RESEARCH']}
    if quality['score']<config['quality_threshold']:reasons.append('QUALITY_BELOW_THRESHOLD')
    if quality['spoken_naturalness']['flags']:reasons.append('SPOKEN_NATURALNESS_REVIEW')
    if not config['script_word_min']<=draft['word_count']<=config['script_word_max']:reasons.append('WORD_COUNT_OUTSIDE_BOUNDS')
    if not config['duration_min_seconds']<=draft['estimated_duration']<=config['duration_max_seconds']:reasons.append('DURATION_OUTSIDE_BOUNDS')
    if quality.get('warnings'):reasons.append('EDITORIAL_WARNINGS')
    return {'status':'EDITORIAL_REVIEW' if reasons else 'READY_FOR_PRODUCTION','reasons':reasons}
