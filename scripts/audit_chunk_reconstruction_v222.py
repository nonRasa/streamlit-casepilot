"""Check whether the frozen chunk index can reproduce its source text exactly."""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from casepilot.chunking import chunks


def reconstruct(rows):
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row['source_id']].append(row)
    sources = []
    gaps = 0
    for source_id, group in grouped.items():
        lines = {}
        for row in group:
            start, end = row['lines']
            part = row['text'].split('\n')
            if len(part) != end - start + 1:
                raise ValueError(f'line count mismatch: {row["id"]}')
            for line_no, text in enumerate(part, start):
                if line_no in lines and lines[line_no] != text:
                    raise ValueError(f'overlap disagreement: {row["id"]}:{line_no}')
                lines[line_no] = text
        gaps += max(lines) - len(lines)
        source = {key: group[0].get(key) for key in ('kind', 'title', 'url', 'revision', 'product_version', 'issue_number')}
        source.update(id=source_id, text='\n'.join(lines.get(i, '') for i in range(1, max(lines) + 1)))
        sources.append(source)
    return sources, gaps


if __name__ == '__main__':
    original = json.loads((ROOT / 'data/corpus_v2.json').read_text(encoding='utf-8'))
    sources, gaps = reconstruct(original)
    rebuilt = [row for source in sources for row in chunks(source)]
    old = {x['id']: x for x in original}
    new = {x['id']: x for x in rebuilt}
    examples = [{'source_id': x['source_id'], 'old_lines': x['lines'], 'old_text': x['text'][:70]}
                for x in original if x['id'] not in new][:5]
    print(json.dumps({'sources': len(sources), 'original_chunks': len(original), 'rebuilt_chunks': len(rebuilt),
                      'same_ids': set(old) == set(new), 'matched_ids': len(set(old) & set(new)),
                      'missing_line_slots': gaps, 'examples': examples}, indent=2))
