#!/usr/bin/env python3
"""Real HTTP/Docker evidence. Changes only lab4 services; never deletes volumes.

Run from an idle Lab 4 API port. The runner owns/restarts only its own Flask
child. It leaves that child and the original single-primary topology running.
Counter values are never reset. E4 preserves the promoted node's newer data
before restoring service names to their original roles.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv
import redis
import requests

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)
BASE = 'http://127.0.0.1:5002'
SESSION = requests.Session()
SESSION.trust_env = False
PROCESS = None
LOG = None
SUMMARY = {}
NODES = {name:redis.Redis(host='127.0.0.1', port=port, decode_responses=True,
                         socket_timeout=1, socket_connect_timeout=1)
         for name,port in [('redis-primary',6379),('redis-replica',6380)]}
KEY = os.getenv('REDIS_COUNTER_KEY','lab4:counter')


def record(event, **data):
    item = dict(timestamp=datetime.now(timezone.utc).isoformat(), event=event, **data)
    line = json.dumps(item, ensure_ascii=True)
    print(line, flush=True)
    if LOG:
        LOG.write(line+'\n')
        LOG.flush()
    return item


def section(name):
    global LOG
    if LOG:
        LOG.close()
    LOG = (ROOT/'logs'/name).open('w')
    record('section', title=name, evidence='LIVE HTTP and Docker; no mocks', counter_key=KEY)


def command(*args):
    cmd = ['docker','compose',*args]
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    record('command', command=' '.join(cmd), returncode=result.returncode,
           stdout=result.stdout, stderr=result.stderr, seconds=round(time.monotonic()-start,6))
    result.check_returncode()
    return result.stdout


def cli(service, *args):
    return command('exec','-T',service,'redis-cli',*args)


def api(method, path, expected=200, **kwargs):
    response = SESSION.request(method, BASE+path, timeout=10, **kwargs)
    data = response.json()
    record('http', method=method, url=BASE+path, status=response.status_code, body=data)
    assert response.status_code == expected, (response.status_code,data)
    return data


def wait_for(predicate, timeout=40):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (requests.RequestException, redis.RedisError):
            pass
        time.sleep(.05)
    raise TimeoutError('Condition not met within {} seconds'.format(timeout))


def start_api(port=6379, replica_port=6380, live=False):
    global PROCESS
    if PROCESS is not None:
        PROCESS.terminate()
        PROCESS.wait(timeout=10)
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1',5002)) != 0, 'Port 5002 occupied; no foreign process will be killed'
    env = dict(os.environ, FLASK_PORT='5002', REDIS_PRIMARY_PORT=str(port),
               REDIS_REPLICA_PORT=str(replica_port), PYTHONUNBUFFERED='1')
    # Keep captured experiment evidence immutable after the run completes.
    stream = (ROOT/'logs'/('flask-live.log' if live else 'flask-server.log')).open('a')
    PROCESS = subprocess.Popen([sys.executable,str(ROOT/'app.py')], cwd=ROOT,
                               env=env, stdout=stream, stderr=subprocess.STDOUT,
                               start_new_session=True)
    stream.close()
    (ROOT/'logs'/'flask.pid').write_text(str(PROCESS.pid)+'\n')
    def ready():
        if PROCESS.poll() is not None:
            raise RuntimeError('Flask child exited; inspect flask-server.log')
        return SESSION.get(BASE+'/time',timeout=1).status_code == 200
    wait_for(ready,20)
    record('application_started', pid=PROCESS.pid, interpreter=sys.executable,
           script=str(ROOT/'app.py'), port=5002, redis_primary_port=port,
           redis_replica_port=replica_port)


def value(name):
    raw = NODES[name].get(KEY)
    return int(raw) if raw is not None else 0


def sync(primary='redis-primary', replica='redis-replica'):
    def synchronized():
        p = NODES[primary].info('replication')
        r = NODES[replica].info('replication')
        return (p['role']=='master' and p['connected_slaves']==1 and
                r['role']=='slave' and r['master_link_status']=='up' and
                not r['master_sync_in_progress'] and value(primary)==value(replica))
    wait_for(synchronized)
    record('synchronized', primary=primary, replica=replica,
           primary_value=value(primary), replica_value=value(replica))


def statuses():
    for name in NODES:
        cli(name,'INFO','replication')
        cli(name,'GET',KEY)


def part_a():
    section('api-storage.log')
    start_api()
    # Import provenance and route inventory are obtained from the actual module.
    result = subprocess.run([sys.executable,'-c',
        'import app,sys; print(sys.executable); print(app.__file__); print(app.app.url_map)'],
        cwd=ROOT, text=True, capture_output=True, check=True)
    record('module_provenance', stdout=result.stdout)
    api('GET','/time')
    api('POST','/echo',json={'message':'Lab 3 contract preserved'})
    api('POST','/echo',400,json={})
    text = 'Hello from Lab 4 - persistent RustFS evidence'
    created = api('POST','/files',201,json={'text':text})
    file_id = created['file_id']
    path = '/files/'+file_id
    assert api('GET',path)['text']==text
    api('GET','/files/00000000-0000-4000-8000-000000000000',404)
    api('GET','/files/invalid-id',400)
    for body in [{},[],{'text':1},{'text':''}]:
        api('POST','/files',400,json=body)
    api('POST','/files',400,data='{',headers={'Content-Type':'application/json'})
    api('POST','/files',400,json={'text':'x'*65537})
    api('POST','/files',400,json={'text':'é'*32769})
    client = boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT_URL','http://127.0.0.1:9000'),
                          aws_access_key_id=os.environ['RUSTFS_ACCESS_KEY'],
                          aws_secret_access_key=os.environ['RUSTFS_SECRET_KEY'],
                          region_name='us-east-1')
    bucket = os.getenv('S3_BUCKET','lab4-files')
    head = client.head_object(Bucket=bucket,Key=file_id)
    record('s3_head_object', bucket=bucket,key=file_id,bytes=head['ContentLength'],etag=head['ETag'])
    objects = client.list_objects_v2(Bucket=bucket)
    record('s3_list_objects', bucket=bucket,keys=[x['Key'] for x in objects.get('Contents',[])])
    start_api()
    assert api('GET',path)['text']==text
    record('flask_restart_persistence', file_id=file_id, status='PASS')
    command('up','-d','--force-recreate','s3')
    def storage_ready():
        try:
            return SESSION.get('http://127.0.0.1:9000/health',timeout=1).status_code==200
        except requests.RequestException:
            return False
    wait_for(storage_ready)
    assert api('GET',path)['text']==text
    record('rustfs_recreation_persistence', file_id=file_id, volume='lab4_s3-data',status='PASS')
    try:
        command('stop','s3')
        api('POST','/files',503,json={'text':'outage probe'})
        api('GET',path,503)
    finally:
        command('start','s3')
        wait_for(storage_ready)
    assert api('GET',path)['text']==text
    SUMMARY['storage'] = {'file_id':file_id,'text':text,'s3_volume':'lab4_s3-data',
                          'create':201,'read':200,'missing':404,'invalid':400,'outage':503,
                          'flask_restart':'PASS','rustfs_force_recreate':'PASS'}


def experiments():
    section('replication-status.log')
    sync()
    statuses()
    api('GET','/counter?from=invalid',400)
    api('GET','/counter?from=primary&from=replica',400)
    section('E1-normal.log')
    baseline = api('GET','/counter?from=primary')['value']
    rows = []
    for i in range(1,101):
        written = api('POST','/counter/increment')['value']
        p = api('GET','/counter?from=primary')['value']
        r = api('GET','/counter?from=replica')['value']
        assert p == written
        assert r <= p
        rows.append({'iteration':i,'write':written,'primary':p,'replica':r,'stale':r<p})
        record('iteration',**rows[-1])
    SUMMARY['E1'] = {'iterations':100,'baseline':baseline,'final':rows[-1]['primary'],
                     'stale_reads':sum(row['stale'] for row in rows),
                     'mismatches':[row for row in rows if row['stale']]}
    record('result', **SUMMARY['E1'])
    section('E2-replica-behind.log')
    sync()
    before = value('redis-primary')
    try:
        cli('redis-replica','REPLICAOF','127.0.0.1','1')
        for _ in range(10):
            api('POST','/counter/increment')
        p = api('GET','/counter?from=primary')['value']
        r = api('GET','/counter?from=replica')['value']
        assert p == before+10 and r == before
        record('detached_values',primary=p,replica=r,difference=p-r)
    finally:
        start = time.monotonic()
        cli('redis-replica','REPLICAOF','redis-primary','6379')
        sync()
        elapsed = time.monotonic()-start
    SUMMARY['E2'] = {'baseline':before,'primary_detached':p,'replica_detached':r,
                     'difference':p-r,'recovery_seconds':round(elapsed,6),
                     'poll_interval_seconds':.05,'recovered_value':value('redis-replica')}
    record('result',**SUMMARY['E2'])
    section('E3-read-own-write.log')
    sync()
    before = value('redis-primary')
    rows = []
    try:
        cli('redis-replica','REPLICAOF','127.0.0.1','1')
        for i in range(1,4):
            w = api('POST','/counter/increment')['value']
            p = api('GET','/counter?from=primary')['value']
            r = api('GET','/counter?from=replica')['value']
            assert w == p == before+i and r == before
            rows.append(dict(write=w,primary=p,replica=r))
            record('read_your_write',**rows[-1])
    finally:
        cli('redis-replica','REPLICAOF','redis-primary','6379')
        sync()
    SUMMARY['E3'] = {'baseline':before,'operations':rows,'restored':True}
    record('result',**SUMMARY['E3'])
    section('E4-manual-failover.log')
    sync()
    old_value = value('redis-primary')
    promoted = False
    try:
        command('stop','redis-primary')
        replica_read = api('GET','/counter?from=replica')['value']
        api('GET','/counter?from=primary',503)
        api('POST','/counter/increment',503)
        cli('redis-replica','REPLICAOF','NO','ONE')
        promoted = True
        assert NODES['redis-replica'].info('replication')['role']=='master'
        cli('redis-replica','INFO','replication')
        start_api(port=6380)
        new_value = api('POST','/counter/increment')['value']
        assert api('GET','/counter?from=primary')['value']==new_value
        command('start','redis-primary')
        wait_for(lambda:NODES['redis-primary'].ping())
        statuses()
        roles = {name:NODES[name].info('replication')['role'] for name in NODES}
        values = {name:value(name) for name in NODES}
        masters = sum(role=='master' for role in roles.values())
        assert masters == 2
        assert values == {'redis-primary':old_value,'redis-replica':new_value}
        assert new_value == old_value+1
        SUMMARY['E4'] = {'replica_read_during_failure':replica_read,'write_during_failure':503,
                         'redirected_primary_port':6380,'write_after_redirect':200,
                         'master_count_on_return':masters,'roles_on_return':roles,
                         'values_on_return':values}
        record('split_brain_observed',**SUMMARY['E4'])
    finally:
        command('start','redis-primary')
        wait_for(lambda:NODES['redis-primary'].ping())
        if promoted:
            # Keep the promoted node authoritative until its newer value is copied.
            cli('redis-primary','REPLICAOF','redis-replica','6379')
            sync(primary='redis-replica',replica='redis-primary')
            cli('redis-primary','INFO','replication')
            cli('redis-primary','REPLICAOF','NO','ONE')
        cli('redis-replica','REPLICAOF','redis-primary','6379')
        sync()
        start_api(live=True)
    statuses()
    final = api('GET','/counter?from=primary')['value']
    assert api('GET','/counter?from=replica')['value'] == final
    SUMMARY['E4']['restored_value'] = final
    SUMMARY['E4']['restored_topology'] = 'redis-primary master; redis-replica slave; link up'
    record('result',**SUMMARY['E4'])


def main():
    (ROOT/'logs').mkdir(exist_ok=True)
    branch = subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    assert branch=='lab4-storage-replication', 'Wrong branch'
    # Exclusive process lock prevents overlapping destructive experiments.
    import fcntl
    lock = (ROOT/'logs'/'experiments.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    section('run-environment.log')
    record('environment',branch=branch,python=sys.version,interpreter=sys.executable,
           working_directory=str(ROOT),base_url=BASE)
    command('ps')
    part_a()
    experiments()
    SUMMARY['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    SUMMARY['evidence_type'] = 'Live Docker containers and Flask HTTP API; no mocks'
    (ROOT/'logs'/'results.json').write_text(json.dumps(SUMMARY,indent=2)+'\n')
    record('all_real_checks_passed', summary_file='logs/results.json')


if __name__ == '__main__':
    main()
