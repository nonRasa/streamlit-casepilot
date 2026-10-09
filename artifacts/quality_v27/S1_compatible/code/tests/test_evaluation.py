import importlib.util, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import CasePilotError, read_json, write_json
from casepilot.model import ReplayClient
spec=importlib.util.spec_from_file_location('casepilot_evaluate',ROOT/'scripts/evaluate.py')
evaluate=importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluate)

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        for folder in ('eval','data','schemas','scripts','src/casepilot'): (self.root/folder).mkdir(parents=True,exist_ok=True)
        self.case={'id':'DEV1','split':'dev','category':'ambiguous','initial_message':'upload issue','initial_facts':{},'initial_checks':[], 'relevant_source_ids':[], 'allowed_decisions':['ask','escalate']}
        write_json(self.root/'eval/cases.json',[self.case]); write_json(self.root/'eval/scenarios.json',[{'id':'S1','split':'dev','case_id':'DEV1'}])
        for name in ('data/corpus.json','schemas/answer.schema.json','schemas/model_selection.schema.json'): write_json(self.root/name,{})
        (self.root/'scripts/evaluate.py').write_text('pass',encoding='utf-8')
        (self.root/'src/casepilot/model.py').write_text('prompt = "frozen"',encoding='utf-8')
    def tearDown(self): self.tmp.cleanup()

    def test_provider_stop_preserves_answers_and_traces_and_is_incomplete(self):
        with patch.object(evaluate,'ROOT',self.root), patch.object(evaluate,'Retriever') as retriever, patch.object(evaluate,'make_client',return_value=ReplayClient()), patch.object(evaluate,'scenario_run',side_effect=CasePilotError('provider_error','stopped')), patch('builtins.print'):
            retriever.return_value.search.return_value=[]
            out=evaluate.run('dev',with_scenarios=True)
        self.assertFalse(out['complete']); self.assertEqual(out['stopped_reason'],'provider_error')
        folder=self.root/'artifacts/offline/dev'
        self.assertEqual(len((folder/'answers.jsonl').read_text(encoding='utf-8').splitlines()),2)
        self.assertEqual(set(read_json(folder/'traces.json')),{'baseline','final'})
        self.assertEqual(read_json(folder/'progress.json')['comparison_turns_done'],2)
        self.assertIn('src/casepilot/model.py',out['configuration']['files'])

    def test_existing_live_checkpoint_prevents_any_generation(self):
        folder=self.root/'artifacts/live/dev'; folder.mkdir(parents=True); write_json(folder/'progress.json',{'existing':True})
        client=ReplayClient()
        with patch.object(evaluate,'ROOT',self.root), patch.object(evaluate,'Retriever'), patch.object(evaluate,'make_client',return_value=client):
            with self.assertRaises(CasePilotError) as err: evaluate.run('dev',mode='live')
        self.assertEqual(err.exception.code,'evaluation_exists'); self.assertEqual(client.calls,0)
        self.assertEqual(read_json(folder/'progress.json'),{'existing':True})
