"""Explicit synthetic reviewer fixture; never a semantic quality oracle."""
from casepilot.roles import CRITERIA

def bind_fixture_report_quotes(answer,state):
    """Translate frozen fixture excerpts to allowed IDs for the active V2 path."""
    from copy import deepcopy
    from casepilot.report_quotes import catalog,resolve
    out=deepcopy(answer); feature=out.get('feature_proposal')
    if not isinstance(feature,dict): return out
    rows=catalog(state); old=feature.get('report_quotes',[]); selected=[]
    if all(isinstance(row,dict) and 'section_id' in row for row in old):
        selected=[row['section_id'] for row in old]
    else:
        for quote in old:
            if not isinstance(quote,str): continue
            match=next((row for row in rows if row['text'] in quote or quote in row['text']),None)
            if match and match['section_id'] not in selected: selected.append(match['section_id'])
            if len(selected)==4: break
    feature['report_quotes']=selected
    return resolve(out,rows,state)

def wire_review(result,packet=None):
    """Encode an explicit test judgement in the current keyed transport."""
    from copy import deepcopy
    result=deepcopy(result)
    if packet is not None:
        units={u['unit_id']:u for u in packet['draft']['units']}
        messages={s['span_id']:s['text'] for s in packet['spans']['messages']}
        if packet['draft'].get('unit_contract')=='citation-units-v1':
            existing={e['unit_id'] for e in result['unit_reviews']}
            for u in packet['draft']['units']:
                if u['field'].startswith('feature_proposal.report_quotes.') and u['unit_id'] not in existing:
                    result['unit_reviews'].append({'unit_id':u['unit_id'],'kind':'request_summary',
                        'support':'supported','source_ids':[],'message_ids':[],'premise':False,
                        'standalone':True,'reason':'بررسی: گزیدهٔ دقیق گزارش برای رابطهٔ مشخصه بررسی شد.',
                        'version_dependent':False,'version_limit':''})
        for e in result['unit_reviews']:
            u=units[e['unit_id']]
            if packet['draft'].get('unit_contract')=='citation-units-v1' and \
                    u['field'].startswith('feature_proposal.report_quotes.'):
                e['kind']='request_summary';e['premise']=False;e['source_ids']=[]
            technical=e['kind'] in ('technical_claim','hypothesis') or e['premise']
            e['premise']=technical
            e['meaning']={'act':'technical' if technical else ('request' if e['kind']=='request_summary' else ('diagnostic' if e['kind']=='question' else 'procedure')),
                'assertion_text':u['text'] if technical else '',
                'user_quote':next((messages[s][:150] for s in e['message_ids'] if s in messages),'') if e['kind']=='request_summary' else '', 'depends_on':[]}
            if packet['draft'].get('unit_contract')=='citation-units-v1' and e['kind']=='request_summary':
                from casepilot.semantics import UNKNOWN
                if u['text']!=UNKNOWN:
                    quote_unit=next((row for row in packet['draft']['units']
                        if row['field'].startswith('feature_proposal.report_quotes.')),None)
                    if quote_unit:
                        spans=[span for span in packet['spans']['messages'] if quote_unit['text'] in span['text']]
                        if spans:
                            e['message_ids']=[spans[0]['span_id']]
                            e['meaning'].update(act='request',user_quote=quote_unit['text'],assertion_text='')
                            if u['field'].startswith('feature_proposal.report_quotes.'):
                                e['source_ids']=[];e['premise']=False
                                desired=next((row['unit_id'] for row in packet['draft']['units']
                                    if row['field']=='feature_proposal.desired_behavior'),None)
                                e['meaning']['depends_on']=[desired] if desired else []
            from casepilot.semantics import UNKNOWN
            if u['text']==UNKNOWN:
                e['meaning'].update(act='unknown')
    if packet is not None and 'compact_contract' in packet:
        from casepilot.compact_review import contract, encode_fixture, descriptive_fixture
        return descriptive_fixture(encode_fixture(result,contract(packet['draft'],packet['spans'])))
    return dict(result,unit_reviews={e['unit_id']:{k:v for k,v in e.items() if k!='unit_id'} for e in result['unit_reviews']})

def current_review(packet):
    source_ids=[s['span_id'] for s in packet['spans']['sources']][:1]
    return {'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: بدل کنترل جریان است.'} for k in CRITERIA},
        'draft_version':packet['draft']['draft_version'],
        'unit_reviews':[{'unit_id':u['unit_id'],'kind':'question' if u['field']=='question' else ('next_step' if u['field']=='next_step' else 'technical_claim'),
            'support':'unknown' if u['field']=='question' else 'supported','source_ids':[] if u['field']=='question' else source_ids,
            'message_ids':[],'premise':False,'standalone':False,'reason':'توضیح: بدل آزمون است.',
            'version_dependent':False,'version_limit':''} for u in packet['draft']['units']],
        'novelty':{'useful':True,'status':'new','message_ids':[],'relation':'unknown','reason':'پرسش: مشخصهٔ تازه لازم است.'}}
