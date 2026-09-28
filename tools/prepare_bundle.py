"""Build an independent Python backend with the official Windows embedded runtime."""
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / '.build' / 'backend'
VERSION = '3.12.10'

def main():
    if sys.version_info[:2] != (3,12):
        raise RuntimeError('Build using the project Python 3.12 environment')
    if DEST.resolve() != ROOT.resolve()/'.build'/'backend':
        raise RuntimeError('Build output must be inside this project')
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True,exist_ok=True)
    # Include application assets from the bundle allowlist.
    for name in ['src','web','images','models']:
        shutil.copytree(ROOT/name,DEST/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.cache'))
    for name in ['app.py','PROVENANCE.md']:
        shutil.copy2(ROOT/name,DEST/name)
    archive=ROOT/'.build'/f'python-{VERSION}-embed-amd64.zip'
    if not archive.exists():
        urllib.request.urlretrieve(f'https://www.python.org/ftp/python/{VERSION}/{archive.name}',archive)
    runtime=DEST/'python'
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(runtime)
    (runtime/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n..\n../src\nimport site\n',encoding='utf8')
    packages=Path(sys.prefix)/'Lib/site-packages'
    excluded=('pip','pytest','_pytest','playwright','pyee','greenlet','ruff','setuptools','wheel')
    def ignore(_directory,names):
        return [n for n in names if n=='__pycache__' or n.endswith('.pyc') or any(n==p or n.startswith(p+'-') for p in excluded)]
    # Keep setuptools: Paddle uses its package metadata and extension helpers.
    excluded=tuple(p for p in excluded if p!='setuptools')
    shutil.copytree(packages,runtime/'Lib/site-packages',dirs_exist_ok=True,ignore=ignore)
    (ROOT/'.build'/'runtime-manifest.json').write_text(json.dumps({'python':VERSION,'source':f'https://www.python.org/ftp/python/{VERSION}/{archive.name}','sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2))
    print('Bundled backend:',DEST)

if __name__=='__main__':
    main()
