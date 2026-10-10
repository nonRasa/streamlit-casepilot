"""Offline E0-E2 ablation on frozen source text; never calls a model.

E0 labels are provisional, source-anchored spans. They are not human gold.
"""
import collections
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.agent import extract_facts
from casepilot.chunking import chunks
from casepilot.hybrid import HybridRetriever
from casepilot.pipeline import pack
from casepilot.quality import retrieval_query
from casepilot.retrieval import Retriever
from audit_chunk_reconstruction_v222 import reconstruct

BASE = ROOT / 'data/corpus_v2.json'
LABELS = ROOT / 'eval/e0_span_seed_v222.json'
CASES = ROOT / 'eval/cases.json'
OUTPUT = ROOT / 'artifacts/architecture_v2/offline/e0_e2_v222.json'
TARGETS = (400, 800, 1200, 1600, 2400)


def query_for(case):
    message = case['initial_message']
    facts = {**extract_facts(message), **case.get('initial_facts', {})}
    return retrieval_query({'messages': [{'text': message}], 'facts': facts}, message), facts.get('streamlit_version')


def search_packets(corpus, cases, path):
    path.write_text(json.dumps(corpus, ensure_ascii=False), encoding='utf-8')
    searcher = HybridRetriever.__new__(HybridRetriever)
    searcher.lexical = Retriever(path)
    outputs = {}
    for case in cases:
        query, version = query_for(case)
        rows = searcher.search(query, k=8, version=version, components={'dense': False})
        rows = [r for r in rows if not (version and r['version_relation'] == 'mismatch')]
        outputs[case['id']] = {'query': query, 'candidates': rows, 'packet': pack(rows, query=query)}
    return outputs


def overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)


def best_parent(child, parents):
    matches = [row for row in parents[child['source_id']] if overlap(child['lines'], row['lines'])]
    if not matches:
        return None
    return max(matches, key=lambda row: (overlap(child['lines'], row['lines']), -len(row['text']), row['id']))


def window_row(child, source_lines, radius=2):
    lines = source_lines[child['source_id']]
    start = max(1, child['lines'][0] - radius)
    end = min(len(lines), child['lines'][1] + radius)
    text = '\n'.join(lines[start - 1:end])
    return dict(child, id=child['id'] + ':window', text=text, lines=[start, end],
                sha256=hashlib.sha256(text.encode()).hexdigest())


def score(packets, labels, cases):
    by_case = collections.defaultdict(list)
    for label in labels:
        by_case[label['case_id']].append(label)
    per_case = {}
    for case in cases:
        case_id = case['id']
        packet = packets[case_id]
        labs = by_case[case_id]
        found = [any(row['source_id'] == lab['source_id'] and lab['needle'] in row['text'] for row in packet)
                 for lab in labs]
        source_hits = len({row['source_id'] for row in packet} & set(case['relevant_source_ids']))
        per_case[case_id] = {
            'span_hits': sum(found), 'span_total': len(labs), 'source_hits': source_hits,
            'context_utf8_bytes': sum(len(row['text'].encode()) for row in packet),
            'official_chunks': sum(row['kind'] == 'docs' for row in packet),
            'packet_ids': [row['id'] for row in packet],
        }
    labeled = [value for value in per_case.values() if value['span_total']]
    summary = {
        'labeled_cases': len(labeled), 'span_hits': sum(x['span_hits'] for x in labeled),
        'span_total': sum(x['span_total'] for x in labeled),
        'labeled_cases_with_span': sum(x['span_hits'] > 0 for x in labeled),
        'all_cases_with_labeled_source': sum(x['source_hits'] > 0 for x in per_case.values()),
        'labeled_source_hits_all_cases': sum(x['source_hits'] for x in per_case.values()),
        'official_chunks_all_cases': sum(x['official_chunks'] for x in per_case.values()),
        'context_utf8_bytes_all_cases': sum(x['context_utf8_bytes'] for x in per_case.values()),
    }
    return summary, per_case


def main():
    original = json.loads(BASE.read_text(encoding='utf-8'))
    cases = [c for c in json.loads(CASES.read_text(encoding='utf-8')) if c['split'] == 'dev']
    annotation = json.loads(LABELS.read_text(encoding='utf-8'))
    labels = annotation['labels']
    case_ids = {c['id'] for c in cases}
    by_source = collections.defaultdict(list)
    for row in original:
        by_source[row['source_id']].append(row)
    for label in labels:
        if label['case_id'] not in case_ids or not any(label['needle'] in row['text'] for row in by_source[label['source_id']]):
            raise ValueError('Label is not a verbatim span in the frozen corpus: ' + label['case_id'])
    sources, missing_line_slots = reconstruct(original)
    source_lines = {source['id']: source['text'].split('\n') for source in sources}
    indexed = {f'target_{target}': [row for source in sources for row in chunks(source, target=target, overlap=256)]
               for target in TARGETS}
    for overlap_size in (0, 512):
        indexed[f'target_1600_overlap_{overlap_size}'] = [
            row for source in sources for row in chunks(source, target=1600, overlap=overlap_size)]
    baseline_ids = {row['id'] for row in original}
    rebuilt_ids = {row['id'] for row in indexed['target_1600']}
    with tempfile.TemporaryDirectory(prefix='e0-e2-') as tmp:
        tmp = Path(tmp)
        runs = {'baseline_frozen': search_packets(original, cases, tmp / 'baseline.json')}
        for name, corpus in indexed.items():
            runs[name] = search_packets(corpus, cases, tmp / (name + '.json'))
    parents = collections.defaultdict(list)
    for row in original:
        parents[row['source_id']].append(row)
    packets = {name: {case_id: value['packet'] for case_id, value in run.items()} for name, run in runs.items()}
    for child_size in (400, 800):
        child = runs[f'target_{child_size}']
        parent_packets = {}
        window_packets = {}
        for case in cases:
            case_id = case['id']
            query = child[case_id]['query']
            parent_candidates = []
            window_candidates = []
            for row in child[case_id]['candidates']:
                parent = best_parent(row, parents)
                if parent is not None:
                    parent_candidates.append(parent)
                window_candidates.append(window_row(row, source_lines))
            parent_packets[case_id] = pack(parent_candidates, query=query)
            window_packets[case_id] = pack(window_candidates, query=query)
        packets[f'child{child_size}_parent1600'] = parent_packets
        packets[f'child{child_size}_window2lines'] = window_packets
    metrics = {}
    details = {}
    for name, packet in packets.items():
        metrics[name], details[name] = score(packet, labels, cases)
    candidate_metrics = {}
    candidate_details = {}
    for name, run in runs.items():
        candidates = {case_id: value['candidates'] for case_id, value in run.items()}
        candidate_metrics[name], candidate_details[name] = score(candidates, labels, cases)
    # Keep case metrics for every variant, but store IDs only where they are
    # needed to audit the baseline and the two observed packing regressions.
    audit_ids = {'baseline_frozen', 'target_400', 'child400_parent1600'}
    for group in (details, candidate_details):
        for name, case_rows in group.items():
            if name not in audit_ids:
                for row in case_rows.values():
                    row.pop('packet_ids', None)
    result = {
        'study': 'E0-E2 offline exploratory', 'split': 'dev', 'model_calls': 0,
        'annotation_status': annotation['annotation_status'], 'labeled_cases': len({x['case_id'] for x in labels}),
        'total_dev_cases': len(cases), 'frozen_corpus_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
        'labels_sha256': hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        'reconstruction': {'sources': len(sources), 'missing_line_slots': missing_line_slots,
                           'baseline_id_match': len(baseline_ids & rebuilt_ids), 'baseline_id_total': len(baseline_ids)},
        'index': {name: {'chunks': len(corpus), 'oversized_blocks': sum(row['oversized_block'] for row in corpus)}
                  for name, corpus in indexed.items()},
        'metrics': metrics, 'details': details,
        'candidate_metrics': candidate_metrics, 'candidate_details': candidate_details,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'reconstruction': result['reconstruction'], 'index': result['index'],
                      'metrics': metrics, 'candidate_metrics': candidate_metrics},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
