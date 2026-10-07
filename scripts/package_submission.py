"""Build a source/data submission archive and optionally copy it to an explicit folder.

Never includes secrets, a virtualenv, runtime databases, raw acquisition responses,
or Git metadata. Existing unrelated destination files are preserved.
"""
import argparse, hashlib, json, shutil, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import utcnow, write_json
from check_mapbox_tokens import scan

ARCHIVE='streamlit-casepilot_submission.zip'
MANIFEST='submission_manifest.json'

def included(path):
    rel=path.relative_to(ROOT); parts=rel.parts
    if any(x in {'.git','.venv','__pycache__','.ipynb_checkpoints','runtime','dist','build'} or x.endswith('.egg-info') for x in parts): return False
    if parts[:2] in {('data','raw'),('artifacts','live_cache'),('artifacts','pilot_smoke')}: return False
    if rel.as_posix()=='data/fresh_holdout_raw.json': return False
    if path.name in {ARCHIVE,MANIFEST}: return False
    if path.name.startswith('.env') and path.name!='.env.example': return False
    return path.suffix not in {'.pyc','.pyo','.sqlite3','.db'}

def main(destination=None):
    if scan(ROOT,include_archives=False): raise RuntimeError('Mapbox-shaped credentials remain in submission files.')
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and included(p))
    required=['CasePilot_project.ipynb','report.md','README.md','artifacts/notebook_execution.json','artifacts/offline/test/evaluation_metrics.json']
    for name in required:
        if not (ROOT/name).is_file(): raise RuntimeError('Missing required deliverable: '+name)
    verified=json.loads((ROOT/'artifacts/package_verification.json').read_text(encoding='utf-8'))
    if not verified['passed']: raise RuntimeError('Package verification must pass first.')
    manifest={'at':utcnow(),'files':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'excluded':'Git metadata, secrets, environments, runtime DBs, live cache, raw acquisition and retired pilot outputs'}
    write_json(ROOT/MANIFEST,manifest); files.append(ROOT/MANIFEST)
    with zipfile.ZipFile(ROOT/ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files: archive.write(path,'streamlit-casepilot/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(ROOT/ARCHIVE) as archive:
        if archive.testzip() is not None: raise RuntimeError('Archive verification failed.')
    if scan(ROOT): raise RuntimeError('Mapbox-shaped credentials remain in archive contents.')
    if destination:
        dest=Path(destination).resolve()
        if dest==ROOT or ROOT.is_relative_to(dest) or dest.is_relative_to(ROOT): raise ValueError('Destination must be separate from source.')
        if dest.name!='streamlit-casepilot': raise ValueError('Destination must be the explicitly named project folder.')
        files.append(ROOT/ARCHIVE)
        # Check ALL conflicts before any copy. Never overwrite user changes.
        for source in files:
            target=dest/source.relative_to(ROOT)
            if target.exists() and target.read_bytes()!=source.read_bytes(): raise RuntimeError('Conflicting destination file: '+str(target))
        dest.mkdir(parents=True,exist_ok=True)
        for source in files:
            target=(dest/source.relative_to(ROOT)).resolve()
            if not target.is_relative_to(dest): raise ValueError('Unsafe destination path.')
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
            if target.read_bytes()!=source.read_bytes(): raise RuntimeError('Copy verification failed: '+str(target))
    print(json.dumps({'files':len(files),'archive_bytes':(ROOT/ARCHIVE).stat().st_size,'copy_verified':bool(destination)},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--destination'); main(parser.parse_args().destination)
