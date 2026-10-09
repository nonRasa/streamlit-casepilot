"""Read original run or separately preserved completion of missing operational plans."""
from pathlib import Path
import hashlib,json

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))

def result_paths(folder):
    folder=Path(folder);completion=folder/'completion_manifest.json'
    if not completion.exists():return folder/'manifest.json',folder/'multi_turn_results.json'
    data=read(completion)
    for name,sha in data['completion_provenance']['source_sha256'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('Original/completion source changed: '+name)
    return completion,folder/'completed_multi_turn_results.json'
