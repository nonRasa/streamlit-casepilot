"""Offline integrity checks for the fresh, family-disjoint V28 follow-up suite."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'eval'/'quality_v28_remaining'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FrozenFollowupSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
        cls.protocol=json.loads((DATA/'protocol.json').read_text(encoding='utf-8'))

    def test_all_frozen_inputs_labels_protocol_and_tariff_match_the_manifest(self):
        for name,expected in self.manifest['files'].items():
            with self.subTest(file=name):
                self.assertEqual(sha(DATA/name),expected)
        self.assertEqual(self.manifest['base_commit'],self.protocol['base_commit'])
        self.assertEqual(self.protocol['pricing_snapshot'],'pricing.json')
        self.assertEqual(self.protocol['hard_cost_cap_usd'],1.10)

    def test_holdout_is_family_disjoint_and_labels_do_not_enter_product_inputs(self):
        for split in ('dev','holdout'):
            inputs=json.loads((DATA/(split+'_inputs.json')).read_text(encoding='utf-8'))
            labels=json.loads((DATA/(split+'_labels.json')).read_text(encoding='utf-8'))
            self.assertEqual({row['id'] for row in inputs},{row['id'] for row in labels})
            for case,label in zip(inputs,labels):
                model_input=json.dumps(case,ensure_ascii=False)
                self.assertEqual(case['id'],label['id'])
                self.assertNotIn(label['expected_behavior'],model_input)
                for witness in label['required_evidence']:
                    self.assertNotIn(witness['quote'],model_input)
        dev={row['family'] for row in json.loads((DATA/'dev_labels.json').read_text(encoding='utf-8'))}
        holdout={row['family'] for row in json.loads((DATA/'holdout_labels.json').read_text(encoding='utf-8'))}
        self.assertTrue(dev.isdisjoint(holdout))
        self.assertEqual(self.manifest['families'],{'dev':sorted(dev),'holdout':sorted(holdout)})

    def test_required_source_witness_is_exact_and_version_metadata_is_not_inferred(self):
        sources={row['id']:row for row in json.loads(
            (ROOT/'data'/'corpus_v3.sources.json').read_text(encoding='utf-8'))}
        labels=json.loads((DATA/'dev_labels.json').read_text(encoding='utf-8'))
        for label in labels:
            for witness in label['required_evidence']:
                source=sources[witness['source_id']]
                start,end=witness['source_span']
                self.assertEqual(source['text'][start:end],witness['quote'])
                self.assertEqual(witness['revision'],source.get('revision'))
                self.assertEqual(witness['product_version'],source.get('product_version'))
                self.assertIsNone(witness['product_version'])

    def test_aggregate_limits_are_partitioned_and_match_correction_protocol(self):
        self.assertEqual(self.protocol['max_development_correction_rounds'],2)
        self.assertEqual(self.protocol['max_calls_per_turn'],8)
        self.assertEqual(self.protocol['turn_cost_cap_usd'],0.04)
        self.assertEqual(self.protocol['max_provider_requests'],208)
        phases=self.protocol['phase_limits']
        self.assertEqual(sum(row['requests'] for row in phases.values()),208)
        self.assertAlmostEqual(sum(row['usd'] for row in phases.values()),1.10)
        self.assertFalse(self.protocol['embedding_rebuild'])
        self.assertEqual(self.protocol['direct_stored_draft_probes'],0)


if __name__=='__main__':
    unittest.main()
