"""Capture the dirty working baseline once, without credentials or runtime DBs."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'artifacts/quality_v22'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if (DEST/'baseline_manifest.json').exists(): raise SystemExit('نسخهٔ مبنا قبلاً محفوظ است.')
    names=['README.md','report.md','pyproject.toml','CasePilot_project.ipynb']
    for folder in ('src','tests','schemas','workflows','docs','eval','scripts'):
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for name in names:
        target=DEST/'baseline'/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/name,target)
    historical={p.relative_to(ROOT).as_posix():sha(p) for folder in ('artifacts/quality_revision','artifacts/architecture_v2','eval','data') for p in (ROOT/folder).rglob('*') if p.is_file() and 'raw' not in p.parts}
    db=ROOT/'runtime/team_budget.sqlite3'
    import sqlite3
    with sqlite3.connect('file:'+db.as_posix()+'?mode=ro',uri=True) as conn:
        rows=conn.execute('select status, charged from calls').fetchall()
    costs={'confirmed_usd':sum(v for s,v in rows if s=='confirmed'),'reserved_usd':sum(v for s,v in rows if s!='confirmed'),'calls':len(rows),'ledger_sha256':sha(db),'panel_observed':False}
    info={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'status':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
          'baseline_files':{n:sha(ROOT/n) for n in names},'historical_files':historical,'cost_before':costs}
    DEST.mkdir(parents=True,exist_ok=True)
    (DEST/'baseline_manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(names),'historical':len(historical),'costs':costs},indent=2))
if __name__=='__main__': main()
