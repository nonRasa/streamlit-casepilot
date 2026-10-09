"""Explicit synthetic reviewer fixture; never a semantic quality oracle."""
from casepilot.roles import CRITERIA

def wire_review(result):
    """Encode an explicit test judgement in the current keyed transport."""
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
