"""Check common credential shapes in included text and ZIP entries; report paths only."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from package_submission import included

PATTERNS={
    'metis':re.compile(r'(?<![\w-])tpsg-[A-Za-z0-9]{24,}'),
    'github':re.compile(r'(?<![\w-])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})'),
    'api_key':re.compile(r'(?<![\w-])sk-(?:proj-)?[A-Za-z0-9_-]{32,}'),
    'bearer':re.compile(r'Bearer\s+[A-Za-z0-9_-]{24,}')}

def check(data,label):
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:return []
    return [{'path':label,'kind':kind,'count':len(pattern.findall(text))} for kind,pattern in PATTERNS.items() if pattern.search(text)]

def scan(archives=False):
    findings=[]
    for path in ROOT.rglob('*'):
        if path.is_file() and included(path):findings+=check(path.read_bytes(),path.relative_to(ROOT).as_posix())
    archive=ROOT/'streamlit-casepilot_submission.zip'
    if archives and archive.exists():
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():findings+=check(z.read(name),archive.name+'::'+name)
    return findings

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--archives',action='store_true');a=parser.parse_args()
    findings=scan(a.archives);print(json.dumps({'passed':not findings,'findings':findings},indent=2));sys.exit(bool(findings))
