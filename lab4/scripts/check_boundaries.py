#!/usr/bin/env python3
"""Additional live boundary and replica-outage checks; no counter reset."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone

import redis
import requests

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:5002'
session=requests.Session()
session.trust_env=False
log=(ROOT/'logs/additional-live-checks.log').open('w')


def record(**data):
    row=dict(timestamp=datetime.now(timezone.utc).isoformat(),**data)
    text=json.dumps(row)
    log.write(text+'\n')
    log.flush()
    print(text,flush=True)


def command(*args):
    cmd=['docker','compose',*args]
    p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=40)
    record(command=' '.join(cmd),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
    p.check_returncode()


for name,text in [('ASCII exact limit','x'*65536),('Unicode exact limit','é'*32768)]:
    response=session.post(BASE+'/files',json={'text':text},timeout=10)
    assert response.status_code==201,response.text
    file_id=response.json()['file_id']
    read=session.get(BASE+'/files/'+file_id,timeout=10)
    assert read.status_code==200 and read.json()['text']==text
    record(test=name,file_id=file_id,post_status=response.status_code,get_status=read.status_code,
           utf8_bytes=len(text.encode()),sha256=hashlib.sha256(text.encode()).hexdigest(),status='PASS')

response=session.post(BASE+'/files',data='x'*524289,headers={'Content-Type':'application/json'},timeout=10)
assert response.status_code==400
record(test='JSON request above 512 KiB',http_status=response.status_code,response=response.json(),status='PASS')

before=session.get(BASE+'/counter?from=primary',timeout=5).json()['value']
try:
    command('stop','redis-replica')
    response=session.get(BASE+'/counter?from=replica',timeout=5)
    assert response.status_code==503
    record(test='Replica stopped',http_status=response.status_code,response=response.json(),status='PASS')
    response=session.get(BASE+'/counter?from=primary',timeout=5)
    assert response.status_code==200 and response.json()['value']==before
    record(test='Primary remains readable',http_status=response.status_code,response=response.json(),status='PASS')
finally:
    command('start','redis-replica')
    node=redis.Redis(host='127.0.0.1',port=6380,decode_responses=True,socket_timeout=1)
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            info=node.info('replication')
            response=session.get(BASE+'/counter?from=replica',timeout=3)
            if (info['role']=='slave' and info['master_link_status']=='up' and
                    response.status_code==200 and response.json()['value']==before):
                break
        except (redis.RedisError,requests.RequestException):
            pass
        time.sleep(.05)
    else:
        raise TimeoutError('Replica did not restore')
    record(test='Replica restored',role=info['role'],link=info['master_link_status'],
           value=response.json()['value'],status='PASS')
record(all_checks='PASS',counter_unchanged=before)
