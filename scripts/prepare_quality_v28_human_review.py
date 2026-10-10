"""Create blind human-review packets after the frozen holdout has run once."""
import argparse
import secrets
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,require
from casepilot.evaluation_completion import candidate_key
from prepare_quality_v28_remaining import DATA,RUN,sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--split',choices=['holdout'],default='holdout')
    args=parser.parse_args()
    require(not (RUN/'human_review_blind.json').exists() and not (RUN/'human_review_key.json').exists(),
        'human_packet_frozen','بستهٔ کور قبلاً ساخته شده و نباید دوباره قرعه‌کشی شود.')
    selection=read_json(RUN/'selection.json')
    inputs=read_json(DATA/'holdout_inputs.json')
    labels=read_json(DATA/'holdout_labels.json')
    require(len(inputs)==2 and len(labels)==2,'incomplete_holdout','holdout منجمد شامل دو پرونده است.')
    packets=[];key=[];retrieval_pools=[];retrieval_key=[];seen=set()
    for case in inputs:
        paired=[]
        for variant,index in (('A','v2'),('B','v3')):
            stem='holdout_r0_'+case['id']+'_'+variant
            record_path=RUN/'turns'/(stem+'.json')
            require(record_path.exists(),'incomplete_holdout','هر چهار اجرای نهایی باید پیش از بازبینی موجود باشند.')
            record=read_json(record_path)
            require(record['code_hash']==selection['active_hash'] and record['input_hash'],
                'holdout_hash_mismatch','خروجی holdout با نسخهٔ منتخب توسعه سازگار نیست.')
            blind_id='BR_'+secrets.token_hex(8)
            require(blind_id not in seen,'duplicate_blind_id','شناسهٔ بازبینی تکراری شد.')
            seen.add(blind_id)
            output=record.get('output') or {}
            paired.append((variant,record))
            citations=(output.get('summary') or {}).get('sources',[])
            packets.append({'blind_id':blind_id,
                'user_messages':[row['text'] for row in (record.get('state') or {}).get('messages',[])
                    if row.get('role')=='user'],
                'answer':output.get('response',''),
                'selected_evidence':[{'quote':row.get('quote'),'section':row.get('section'),
                    'revision':row.get('revision'),'product_version':row.get('product_version'),
                    'version_limit':row.get('version_limit'),'url':row.get('url')}
                    for row in citations],
                'review_form':{'report_quote_lineage':'pass|fail|uncertain',
                    'report_quote_relevance':'pass|fail|uncertain',
                    'technical_claim_coverage':'pass|fail|uncertain',
                    'selected_quote_support':'pass|fail|uncertain',
                    'version_limit_per_unit':'pass|fail|uncertain',
                    'answer_route_and_usefulness':'pass|fail|uncertain',
                    'fresh_nonrepeated_question_or_test':'pass|fail|uncertain',
                    'notes':''}})
            key.append({'blind_id':blind_id,'case_id':case['id'],'variant':variant,'index':index,
                'artifact':record_path.name,'artifact_sha256':sha(record_path)})
        pool={}
        for _,record in paired:
            for row in record.get('initial_candidates',[])[:8]:
                pool.setdefault(candidate_key(row),row)
        aliases=[]
        for identity,row in pool.items():
            alias='RE_'+secrets.token_hex(7)
            aliases.append({'evidence_alias':alias,'title':row.get('title',''),
                'section':row.get('section',''),'text':row.get('text',''),
                'product_version':row.get('product_version'),'version_relation':row.get('version_relation')})
            retrieval_key.append({'evidence_alias':alias,'case_id':case['id'],
                'candidate_key':identity,'source_id':row.get('source_id')})
        secrets.SystemRandom().shuffle(aliases)
        retrieval_pools.append({'blind_pool_id':'RP_'+secrets.token_hex(8),
            'user_messages':[case['initial_message']],
            'candidates':aliases,
            'relevance_rubric':{'0':'نامرتبط','1':'فقط هم‌موضوع، بدون کمک مستقیم','2':'مرتبط اما شاهد محدود','3':'شاهد مستقیم یا راهنمایی روشن برای همین درخواست'},
            'review_form':{'candidate_grades':[{'evidence_alias':row['evidence_alias'],
                'relevance_grade':None,'version_fit':'pass|fail|uncertain'} for row in aliases]}})
    secrets.SystemRandom().shuffle(packets)
    write_json(RUN/'human_review_blind.json',{'suite_manifest_sha256':sha(DATA/'manifest.json'),
        'holdout_code_hash':selection['active_hash'],'answer_items':packets,
        'retrieval_pools':retrieval_pools})
    write_json(RUN/'human_review_key.json',{'suite_manifest_sha256':sha(DATA/'manifest.json'),
        'holdout_code_hash':selection['active_hash'],'answer_items':key,
        'retrieval_candidates':retrieval_key})
    print('Created four randomized blind review items. The separate key remains evaluator-side.')


if __name__=='__main__':main()
