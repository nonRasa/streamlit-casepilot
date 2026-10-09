"""Read-only-source, local stage snapshots. Never copy credentials/runtime."""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def freeze(stage):
    target = ROOT / 'artifacts/quality_v27' / stage
    if (target / 'manifest.json').exists():
        raise SystemExit('Stage already frozen; choose a new stage name.')
    paths = sorted(p for folder in ('src', 'schemas', 'policies', 'tests', 'scripts')
                   for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths += [ROOT / p for p in ('pyproject.toml', 'requirements.txt', 'docs/QUALITY_V27_PROTOCOL_FA.md')]
    hashes = {}
    for p in paths:
        rel = p.relative_to(ROOT)
        dest = target / 'code' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
        hashes[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    data = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'data').glob('*snapshot*.json')}
    manifest = {'stage': stage, 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'files': hashes, 'snapshot_hashes': data, 'provider_requests': 0}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'stage': stage, 'files': len(hashes), 'commit': manifest['commit']}))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage'); freeze(p.parse_args().stage)
