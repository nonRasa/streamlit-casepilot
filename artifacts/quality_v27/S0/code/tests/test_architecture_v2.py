import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import *
from casepilot.chunking import chunks
from casepilot.embeddings import EmbeddingCache, FixtureEmbedder, unit, cosine
from casepilot.hybrid import HybridRetriever, embedding_text, version_relation
from casepilot.model import ReplayClient, MetisClient, MetisEmbedder
from casepilot.agent import Agent
from casepilot.store import Store
from casepilot.roles import checked_extraction, rerank_ids, checked_judge, CRITERIA
from casepilot import pipeline

SOURCE={'id':'docs:widget','kind':'docs','title':'Widget','text':'Widgets preserve their identity with stable keys. Use explicit keys for predictable state.',
        'url':'https://docs.streamlit.io/','revision':'frozen','product_version':'1.49.0','issue_number':None}
def row(text=None): return chunks(dict(SOURCE,text=text or SOURCE['text']))[0]
class TinyHybrid:
    def __init__(self): self.rows=[row()]; self.last_trace={'method':'test-fixture'}
    def search(self,*args,**kwargs): return self.rows

class ChunkTests(unittest.TestCase):
    def test_fences_and_source_lines_are_preserved(self):
        text='# Widgets\n\nIntroductory text with sufficient length.\n\n```python\n'+('x = 123456789\n'*60)+'```\n\nTail paragraph with sufficient length.'
        rows=chunks(dict(SOURCE,text=text),target=180,overlap=60)
        code=[r for r in rows if '```python' in r['text']]
        self.assertEqual(len(code),1); self.assertTrue(code[0]['oversized_block']); self.assertEqual(code[0]['text'].count('```'),2)
        lines=text.splitlines()
        for r in rows: self.assertEqual(r['text'],'\n'.join(lines[r['lines'][0]-1:r['lines'][1]]))
    def test_section_boundaries_and_overlap_are_deterministic(self):
        text='# One\n\nFirst paragraph has content.\n\nSecond paragraph has content.\n\nThird paragraph has content.\n\n# Two\n\nFinal paragraph has content.'
        rows=chunks(dict(SOURCE,text=text),target=70,overlap=40)
        self.assertEqual(rows,chunks(dict(SOURCE,text=text),target=70,overlap=40))
        self.assertTrue(any('Second paragraph' in a['text'] and 'Second paragraph' in b['text'] for a,b in zip(rows,rows[1:])))
        self.assertFalse(any('# One' in r['text'] and '# Two' in r['text'] for r in rows))
    def test_table_is_atomic(self):
        table='| API | Version |\n| --- | --- |\n'+('| st.foo | 1.49 |\n'*30)
        rows=chunks(dict(SOURCE,text=table),target=100)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['text'],table.rstrip('\n'))

class EmbeddingTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_deduplicated_normalized_content_cached_across_restart(self):
        embedder=FixtureEmbedder(); cache=EmbeddingCache(self.path/'cache.sqlite3',embedder)
        with patch.object(embedder,'embed',wraps=embedder.embed) as call:
            first=cache.get_many(['stable keys','stable   keys']); self.assertEqual(call.call_count,1); self.assertEqual(first[0],first[1])
        cache=EmbeddingCache(self.path/'cache.sqlite3',embedder)
        with patch.object(embedder,'embed',side_effect=AssertionError('must not call')): self.assertEqual(cache.get_many(['stable keys']),first[:1])
    def test_model_identity_invalidates_cache(self):
        embedder=FixtureEmbedder(); cache=EmbeddingCache(self.path/'cache.sqlite3',embedder); cache.get_many(['hello'])
        embedder.identity=dict(embedder.identity,model='different')
        with self.assertRaises(CasePilotError) as err: cache.get_many(['hello'],allow_create=False)
        self.assertEqual(err.exception.code,'embedding_index_not_ready')
    def test_invalid_vectors_and_dimension_rejected(self):
        for value in ([0,0],[float('nan'),1],[True,1],[]):
            with self.subTest(value=value),self.assertRaises(CasePilotError): unit(value)
        with self.assertRaises(CasePilotError): cosine([1],[1,0])
    def test_invalid_batch_never_saved(self):
        embedder=FixtureEmbedder(); cache=EmbeddingCache(self.path/'cache.sqlite3',embedder)
        with patch.object(embedder,'embed',return_value=[[1,0],[1,0,0]]),self.assertRaises(CasePilotError): cache.get_many(['one','two'])
        with self.assertRaises(CasePilotError): cache.get_many(['one'],allow_create=False)
    def test_hybrid_source_version_metadata_and_ties(self):
        path=self.path/'corpus.json'; rows=[row(),dict(row('Another widget uses a key for identity.'),id='docs:widget2:v2',source_id='docs:widget2')]; write_json(path,rows)
        retriever=HybridRetriever(ReplayClient(),path,self.path/'emb.sqlite3')
        a=retriever.search('stable widget key',version='1.18.1'); b=retriever.search('stable widget key',version='1.18.1')
        self.assertEqual(a,b); self.assertTrue(all(r['version_relation']=='mismatch' for r in a)); self.assertEqual(retriever.last_trace['embedding']['batches'],0)
        self.assertEqual(version_relation(dict(row(),product_version=None),'1.18.1'),'unknown')

class RoleTests(unittest.TestCase):
    def test_foreign_duplicate_empty_rerank_ids_fall_back_contract(self):
        rows=[row()]
        for ids in ([],['foreign'],[rows[0]['id']]*2):
            with self.subTest(ids=ids),self.assertRaises(CasePilotError): rerank_ids({'ordered_ids':ids},rows)
    def test_extraction_requires_exact_quote_and_rejects_permission(self):
        with self.assertRaises(CasePilotError): checked_extraction({'facts':[{'key':'resolved','value':'true','quote':'problem fixed'}],'completed_checks':[],'ambiguities':[]},'problem fixed')
        for fact in ({'key':'deployment','value':'docker','quote':'invented'}, {'key':'python_version','value':'9.99','quote':'Python 3.11'}):
            with self.subTest(fact=fact):
                facts,_,ambiguities=checked_extraction({'facts':[fact],'completed_checks':[],'ambiguities':[]},'Python 3.11 problem fixed')
                self.assertFalse(facts); self.assertTrue(ambiguities)
    def test_partial_extraction_keeps_only_verbatim_facts_and_no_boilerplate_reproduction(self):
        message='Python 3.11. I have provided sufficient information below to help reproduce this issue.'
        facts,checks,ambiguities=checked_extraction({'facts':[{'key':'python_version','value':'3.11','quote':'Python 3.11'},
            {'key':'reproducible','value':'true','quote':message},{'key':'symptom_scope','value':'invented summary','quote':message}],
            'completed_checks':['I have provided sufficient information below to help reproduce this issue.'],'ambiguities':[]},message)
        self.assertEqual(facts,{'python_version':'3.11'}); self.assertFalse(checks); self.assertEqual(len(ambiguities),2)
    def test_extraction_conflicts_remain_unknown(self):
        message='Python 3.11 versus Python 3.12'
        facts,_,_=checked_extraction({'facts':[{'key':'python_version','value':v,'quote':message} for v in ('3.11','3.12')],'completed_checks':[],'ambiguities':[]},message)
        self.assertNotIn('python_version',facts)
    def test_accept_label_cannot_override_bad_score_or_code_gate(self):
        result={'verdict':'accept','assessments':{k:{'score':2,'reason':'توضیح: بررسی موفق است.'} for k in CRITERIA}}
        self.assertEqual(checked_judge(result)['verdict'],'accept'); self.assertEqual(checked_judge(result)['findings'],[])
        result['assessments']['version_fit']['score']=0; self.assertEqual(checked_judge(result)['verdict'],'repair')
        result['assessments']['version_fit']['score']=2
        self.assertEqual(checked_judge(result,[{'criterion':'claim_support','reason':'خطای شاهد'}])['verdict'],'repair')
    def test_reproduction_instructions_are_not_observed_results(self):
        for quote in ('Run the code above in streamlit','Please reproduce this issue','This is not reproducible'):
            facts,_,_=checked_extraction({'facts':[{'key':'reproducible','value':'true','quote':quote}],'completed_checks':[],'ambiguities':[]},quote)
            self.assertNotIn('reproducible',facts)
        quote='I reproduced the issue in a clean environment.'
        facts,_,_=checked_extraction({'facts':[{'key':'reproducible','value':'true','quote':quote}],'completed_checks':[],'ambiguities':[]},quote)
        self.assertIs(facts['reproducible'],True)
    def test_mentioning_known_version_is_not_asking_for_it(self):
        answer=ReplayClient().generate({'messages':[{'text':'widget'}],'facts':{'streamlit_version':'1.44.0'},'checks':[]},[row()])
        state={'facts':{'streamlit_version':'1.44.0'},'checks':[]}
        answer.update(decision='ask',question='پرسش: آیا این آزمایش در نسخهٔ `Streamlit` رفتار دیگری نشان می‌دهد؟',next_step='بررسی: نتیجهٔ آزمایش تازه را مقایسه کنید.')
        self.assertFalse(pipeline.deterministic_findings(answer,[row()],state))
        answer['question']='پرسش: نسخهٔ دقیق `Streamlit` چیست؟'
        self.assertTrue(pipeline.deterministic_findings(answer,[row()],state))

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'tracker.sqlite3'); self.client=ReplayClient(); self.hybrid=TinyHybrid()
        self.agent=Agent(self.store,client=self.client,hybrid=self.hybrid)
    def tearDown(self): self.tmp.cleanup()
    def turn(self): return self.agent.turn('A','Streamlit 1.49.0 widget key issue','r1',facts={'reproducible':True})
    def test_default_pipeline_has_separate_judge_no_write_and_idempotency(self):
        out=self.turn(); self.assertEqual(out['architecture'],'v2'); self.assertEqual(out['judge']['verdict'],'accept')
        self.assertEqual([s['stage'] for s in out['pipeline']],['extract','read_case','retrieve','rerank','context_pack','draft','judge','prepare_proposal'])
        self.assertEqual(out['model_calls'],4); self.assertEqual(out['usage']['provider_requests'],0); self.assertFalse(self.store.get('A')['comments'])
        calls=self.client.calls; again=self.turn(); self.assertEqual(again['proposal']['hash'],out['proposal']['hash']); self.assertEqual(calls,self.client.calls)
    def test_repair_at_most_once_then_fails_closed(self):
        original=pipeline.fixture_role
        def role(name,packet):
            if name=='judge': return {'verdict':'repair','assessments':{k:{'score':1,'reason':'ابهام: کاربرد شاهد روشن نیست.'} for k in CRITERIA}}
            return original(name,packet)
        with patch.object(pipeline,'fixture_role',side_effect=role): out=self.turn()
        self.assertEqual(out['repair_count'],1); self.assertEqual(out['model_calls'],6); self.assertEqual(out['validation_error'],'judge_rejected'); self.assertEqual(out['decision'],'escalate'); self.assertFalse(out['summary']['sources'])
    def test_successful_repair_is_judged_again(self):
        original=pipeline.fixture_role; reviews=[]
        def role(name,packet):
            if name=='judge':
                reviews.append(1)
                if len(reviews)==1: return {'verdict':'repair','assessments':{k:{'score':1,'reason':'ابهام: کاربرد شاهد روشن نیست.'} for k in CRITERIA}}
            return original(name,packet)
        with patch.object(pipeline,'fixture_role',side_effect=role): out=self.turn()
        self.assertEqual(len(reviews),2); self.assertEqual(out['repair_count'],1); self.assertEqual(out['judge']['verdict'],'accept'); self.assertIsNone(out['validation_error'])
    def test_rerank_foreign_id_retains_original_candidates(self):
        original=pipeline.fixture_role
        with patch.object(pipeline,'fixture_role',side_effect=lambda n,p: {'ordered_ids':['invented']} if n=='rerank' else original(n,p)): out=self.turn()
        self.assertEqual(out['retrieved'][0]['id'],self.hybrid.rows[0]['id']); self.assertTrue(any(s.get('error')=='invalid_rerank' for s in out['pipeline']))
    def test_version_mismatch_cannot_be_accepted_by_fixture_judge(self):
        out=self.agent.turn('A','Streamlit 1.18.1 widget problem','r1',facts={'reproducible':True})
        # Production retriever supplies mismatch metadata; direct fixture emulates it.
        self.hybrid.rows[0]['version_relation']='mismatch'
        out=self.agent.turn('A','same issue persists','r2')
        self.assertEqual(out['decision'],'escalate'); self.assertEqual(out['validation_error'],'judge_rejected')
    def test_invalid_citation_never_reaches_approval(self):
        original=self.client.generate
        def broken(*args,**kwargs):
            out=original(*args,**kwargs); out['claims']=[{'evidence_id':'foreign','quote':'Invented untrusted technical source content.'}]; return out
        with patch.object(self.client,'generate',side_effect=broken): out=self.turn()
        self.assertEqual(out['decision'],'escalate'); self.assertEqual(out['validation_error'],'unsupported_answer'); self.assertFalse(self.store.get('A')['comments'])
        self.assertTrue(any(s['stage']=='drop_invalid_citation' for s in out['pipeline']))
    def test_judge_transport_failure_returns_safe_draft_without_retry(self):
        original=pipeline.fixture_role; invoked=[]
        def role(name,packet):
            if name=='judge': invoked.append(1); raise CasePilotError('provider_error','خطای آزمایشی داور')
            return original(name,packet)
        with patch.object(pipeline,'fixture_role',side_effect=role): out=self.turn()
        self.assertEqual(len(invoked),1); self.assertEqual(out['validation_error'],'provider_error'); self.assertEqual(out['decision'],'escalate')
    def test_pack_skips_oversize_deduplicates_and_keeps_code_intact(self):
        large=row('```python\n'+('x=1\n'*2000)+'```'); small=row()
        selected=pipeline.pack([large,small,small],max_bytes=500)
        self.assertEqual(selected,[small])
    def test_new_fact_invalidates_old_approval(self):
        out=self.turn(); p=out['proposal']; review=self.store.review('A',p['id'],p['hash'],'approve','بازبین آزمایشی')
        self.agent.turn('A','Correction: Streamlit 1.48.0','r2')
        with self.assertRaises(CasePilotError) as err: self.store.execute('A',p['id'],review['approval_id'])
        self.assertEqual(err.exception.code,'stale_approval')

if __name__=='__main__': unittest.main()
