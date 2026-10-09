"""Reject Mapbox-shaped credentials in deliverable text and archive contents.

Only paths/counts are reported; matched credential values are never logged.
This is a targeted guard, not a replacement for GitHub secret scanning.
"""
import argparse, io, json, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import MAPBOX_TOKEN_RE

def strings(value):
    if isinstance(value,str): yield value
    elif isinstance(value,list):
        for item in value: yield from strings(item)
    elif isinstance(value,dict):
        for key,item in value.items():
            yield str(key); yield from strings(item)

def hits(data):
    try: text=data.decode('utf-8-sig')
    except UnicodeDecodeError: return 0
    raw=len(MAPBOX_TOKEN_RE.findall(text))
    try: decoded=sum(len(MAPBOX_TOKEN_RE.findall(s)) for s in strings(json.loads(text)))
    except (ValueError,TypeError): decoded=0
    return max(raw,decoded)

def scan(root,include_archives=True):
    findings=[]
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root)
        if any(x in {'.git','.venv','__pycache__','runtime','.ipynb_checkpoints'} for x in rel.parts): continue
        if rel.parts[:2] in {('data','raw'),('artifacts','live_cache')}: continue
        if not path.is_file(): continue
        if path.suffix=='.zip':
            if include_archives:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        count=hits(archive.read(name))
                        if count: findings.append({'path':rel.as_posix()+'::'+name,'count':count})
        else:
            count=hits(path.read_bytes())
            if count: findings.append({'path':rel.as_posix(),'count':count})
    return findings

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--skip-archives',action='store_true'); args=parser.parse_args()
    findings=scan(ROOT,not args.skip_archives)
    print(json.dumps({'passed':not findings,'findings':findings},indent=2))
    sys.exit(1 if findings else 0)
