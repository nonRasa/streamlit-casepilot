"""Create a blank two-reviewer sheet for the E0 development cases."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cases = [c for c in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8')) if c['split'] == 'dev']
labels = json.loads((ROOT / 'eval/e0_span_seed_v222.json').read_text(encoding='utf-8'))['labels']
by_case = {label['case_id']: label for label in labels}
path = ROOT / 'eval/e0_reviewer_sheet_v222.csv'
with path.open('w', newline='', encoding='utf-8-sig') as handle:
    writer = csv.DictWriter(handle, fieldnames=[
        'case_id', 'category', 'proposed_source_id', 'proposed_exact_span', 'provisional_exclusion_reason',
        'reviewer_1_relevant', 'reviewer_1_version_fit', 'reviewer_1_missing_span',
        'reviewer_2_relevant', 'reviewer_2_version_fit', 'reviewer_2_missing_span',
        'adjudicated_relevant', 'adjudicated_version_fit', 'adjudicated_span', 'notes'])
    writer.writeheader()
    for case in cases:
        label = by_case.get(case['id'], {})
        writer.writerow({'case_id': case['id'], 'category': case['category'],
                         'proposed_source_id': label.get('source_id', ''),
                         'proposed_exact_span': label.get('needle', ''),
                         'provisional_exclusion_reason': label.get('exclusion_reason', '')})
print(path)
