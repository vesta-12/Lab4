#!/usr/bin/env python3
"""Standard-library-only ZIP packer; also usable after filling report metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.venv','.git','__pycache__','.pytest_cache','live'}

def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            result.update(chunk)
    return result.hexdigest()

def selected():
    files=[]
    for path in ROOT.rglob('*'):
        rel=path.relative_to(ROOT)
        if not path.is_file() or any(part in EXCLUDED for part in rel.parts): continue
        if path.name.startswith('.env') or path.name=='.DS_Store': continue
        if path.suffix in {'.pyc','.pid','.lock','.zip'}: continue
        files.append(path)
    return sorted(files)

def package(output):
    for required in ['docker-compose.yml','nginx.conf','init-replica.js','app/app.py','app/Dockerfile',
                     'tests/test_api.py','tests/locustfile.py','tests/probe.py','spec.md','test_report.md']:
        assert (ROOT/required).is_file(),required
    assert json.loads((ROOT/'logs/results.json').read_text())['complete']
    for source in ['logs/supplementary-results.json']:
        if (ROOT/source).exists(): assert json.loads((ROOT/source).read_text())['complete']
    sources=json.loads((ROOT/'screenshots/sources.json').read_text())
    for name in sources['expected_screenshots']:
        assert (ROOT/'screenshots'/name).is_file(),'Missing required screenshot: '+name
    assert '**Version:** 4.0' in (ROOT/'spec.md').read_text()
    files=[p for p in selected() if p.name!='MANIFEST.sha256']
    # AWS key-shaped values are forbidden; this project needs no credentials.
    for path in files:
        data=path.read_bytes()
        assert not re.search(rb'(?:AKIA|ASIA)[A-Z0-9]{16}',data),'Credential pattern: '+str(path)
    (ROOT/'MANIFEST.sha256').write_text(''.join(digest(p)+'  '+str(p.relative_to(ROOT))+'\n' for p in files))
    files=selected()
    output=Path(output).resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:
            archive.write(path,str(Path('lab5')/path.relative_to(ROOT)))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(files)
    audit={'archive':str(output),'files':len(files),'bytes':output.stat().st_size,
           'sha256':digest(output),'integrity':'PASS','screenshots':len(sources['expected_screenshots']),
           'group_missing':'Group: Not provided' in (ROOT/'test_report.md').read_text()}
    print(json.dumps(audit,indent=2))
    return audit

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,help='Absolute ZIP destination, preferably outside lab5/')
    args=parser.parse_args()
    package(args.output)
