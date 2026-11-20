"""Live HTTP observations and pytest outcomes; no dependency mocks."""
import hashlib
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

import pytest
import requests

RUN = Path(os.getenv("LAB5_RUN_DIR", Path(__file__).resolve().parents[1]/"logs"/"manual-tests"))
RUN.mkdir(parents=True,exist_ok=True)

def append(name,data):
    with (RUN/name).open('a') as stream:
        stream.write(json.dumps(data,ensure_ascii=True)+'\n')

def concise(value):
    if isinstance(value,dict):
        return {k:concise(v) for k,v in value.items()}
    if isinstance(value,str) and len(value)>200:
        return {'utf8_bytes':len(value.encode()),'sha256':hashlib.sha256(value.encode()).hexdigest()}
    return value

@pytest.fixture
def api(request):
    session=requests.Session()
    session.trust_env=False
    base=os.getenv('BASE_URL','http://127.0.0.1:8080').rstrip('/')
    def call(method,path,**kwargs):
        start=time.perf_counter()
        response=session.request(method,base+path,timeout=12,**kwargs)
        try:
            body=response.json()
        except ValueError:
            body=response.text[:200]
        append('functional-http.jsonl',dict(timestamp=datetime.now(timezone.utc).isoformat(),
               test=request.node.nodeid,method=method,url=base+path,status=response.status_code,
               milliseconds=round((time.perf_counter()-start)*1000,4),body=concise(body)))
        return response
    yield call
    session.close()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    if report.when=='call' or (report.when=='setup' and report.failed):
        append('functional-results.jsonl',dict(test=item.nodeid,outcome=report.outcome,
               seconds=report.duration,error=str(report.longrepr) if report.failed else None))
