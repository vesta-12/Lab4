#!/usr/bin/env python3
"""Real HTTP/Docker suite. Stops only named services of Compose project lab5.

Each run gets a unique directory. No counter reset, volume removal, manual
MongoDB promotion or modification of any previous laboratory is performed.
"""
import argparse
import csv
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

import psutil
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from probe import run_probe
BASE=os.getenv('BASE_URL','http://127.0.0.1:8080').rstrip('/')
COMPOSE=['docker','compose','--project-name','lab5','--file',str(ROOT/'docker-compose.yml')]
SESSION=requests.Session()
SESSION.trust_env=False

def utc():
    return datetime.now(timezone.utc).isoformat()

def validate_location():
    assert (ROOT/'docker-compose.yml').is_file()
    assert (ROOT/'docker-compose.yml').read_text().startswith('name: lab5')
    # Preserve branch protection in the real checkout, but a submission ZIP
    # intentionally has no .git directory and must remain executable.
    checkout=(ROOT.parent/'.git').exists()
    branch=None
    if checkout:
        branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
        assert branch=='lab5-nosql-fault-tolerance',branch
    return {'root':str(ROOT),'compose_project':'lab5','git_checkout':checkout,'branch':branch}

class Run:
    def __init__(self):
        self.id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6]
        self.path=ROOT/'logs'/'runs'/self.id
        self.path.mkdir(parents=True)
        self.summary={'run_id':self.id,'started_utc':utc(),'base_url':BASE,'complete':False,
                      'evidence_type':'Live HTTP through nginx and Docker containers; no mocks',
                      'targets_declared_in_spec':{'p95_ms':1000,'error_percent':1}}
        self.save()

    def record(self,event,**data):
        row=dict(timestamp=utc(),monotonic=time.monotonic(),event=event,**data)
        line=json.dumps(row,ensure_ascii=True)
        with (self.path/'events.jsonl').open('a') as stream:
            stream.write(line+'\n')
        print(line,flush=True)
        return row

    def save(self):
        (self.path/'summary.json').write_text(json.dumps(self.summary,indent=2)+'\n')

    def command(self,*args,timeout=90,allow_failure=False,compose=True):
        cmd=(COMPOSE if compose else [])+list(args)
        start=time.monotonic(); started=utc()
        result=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
        row=self.record('command',command=cmd,start_utc=started,end_utc=utc(),
                        start_monotonic=start,end_monotonic=time.monotonic(),
                        returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        if not allow_failure:
            result.check_returncode()
        return result,row

    def http(self,method,path,expected=200,**kwargs):
        start=time.monotonic()
        r=SESSION.request(method,BASE+path,timeout=12,**kwargs)
        try: body=r.json()
        except ValueError: body={'non_json':r.text[:150]}
        self.record('http',method=method,url=BASE+path,status=r.status_code,body=body,
                    milliseconds=round((time.monotonic()-start)*1000,4))
        assert r.status_code==expected,(r.status_code,body)
        return body

    def roles(self,node='mongo1'):
        result,_=self.command('exec','-T',node,'mongosh','--quiet','--eval',
          'JSON.stringify(rs.status().members.map(m=>({name:m.name,state:m.stateStr,health:m.health})))',timeout=12)
        return json.loads(result.stdout.strip())

    def wait_topology(self,timeout=120):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            try:
                roles=self.roles()
                if (len(roles)==3 and sum(x['state']=='PRIMARY' for x in roles)==1 and
                        sum(x['state']=='SECONDARY' for x in roles)==2 and all(x['health']==1 for x in roles)):
                    self.record('topology_ready',members=roles)
                    return roles
            except (subprocess.SubprocessError,ValueError):
                pass
            time.sleep(.5)
        raise TimeoutError('Replica set did not restore 1 PRIMARY + 2 SECONDARY')

    def distribution(self,label,forbidden=None):
        counts={}; rows=[]
        for i in range(30):
            r=SESSION.get(BASE+'/time',timeout=12)
            row=dict(index=i+1,status=r.status_code,body=r.json(),timestamp=utc())
            rows.append(row)
            assert r.status_code==200
            host=row['body']['served_by']; counts[host]=counts.get(host,0)+1
            assert host!=forbidden,(label,host)
        assert len(counts)>=2,counts
        result=dict(label=label,requests=30,counts=counts,errors=0,rows=rows)
        (self.path/('distribution-'+label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        self.record('distribution',label=label,counts=counts,requests=30)
        return result

class ProbePair:
    def __init__(self,run,name,read_id):
        self.stop_event=threading.Event()
        self.paths={method:run.path/('probe_'+name+('_reads' if method=='GET' else '')+'.txt')
                    for method in ['POST','GET']}
        self.threads=[]
        for method in ['POST','GET']:
            thread=threading.Thread(target=run_probe,args=(BASE,name,run.id,self.paths[method],
                   self.stop_event,read_id if method=='GET' else None),daemon=True)
            thread.start(); self.threads.append(thread)
    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(15)
            assert not thread.is_alive(),'Probe did not stop after its HTTP timeout'
    def rows(self,method='POST'):
        return [json.loads(x) for x in self.paths[method].read_text().splitlines()]

def wait_seconds(seconds):
    # Kept short enough for an external caller to report progress while running.
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        time.sleep(min(.2,max(0,deadline-time.monotonic())))

def error_summary(rows,stop_start):
    after=[r for r in rows if r['start_monotonic']>=stop_start]
    errors=[r for r in after if r.get('status') not in (200,201)]
    first_error=errors[0] if errors else None
    last_error=max((x['end_monotonic'] for x in errors),default=None)
    recovered=next((r for r in after if r.get('status') in (200,201) and
                    last_error is not None and r['start_monotonic']>=last_error),None)
    return dict(samples=len(rows),post_stop_samples=len(after),
        http_503=sum(r.get('status')==503 for r in after),
        other_http_errors=sum(r.get('status') is not None and r['status'] not in (200,201,503) for r in after),
        transport_errors=sum(r.get('status') is None for r in after),
        first_error=first_error,first_503=next((r for r in after if r.get('status')==503),None),
        first_success_after_errors=recovered,
        stop_to_recovery_seconds=round(recovered['end_monotonic']-stop_start,6) if recovered else None,
        error_to_recovery_seconds=round(recovered['end_monotonic']-first_error['end_monotonic'],6) if recovered else None,
        first_post_stop_success=next((r for r in after if r.get('status') in (200,201)),None))

def functional(run):
    run.wait_topology()
    result,_=run.command('exec','-T','mongo1','mongosh','--quiet','/scripts/init-replica.js')
    (run.path/'init-idempotency.log').write_text(result.stdout+result.stderr)
    config,_=run.command('config')
    (run.path/'compose-config.yml').write_text(config.stdout)
    ps,_=run.command('ps','--all')
    (run.path/'compose-ps.log').write_text(ps.stdout)
    ng,_=run.command('exec','-T','nginx','nginx','-t')
    (run.path/'nginx-config-test.log').write_text(ng.stdout+ng.stderr)
    roles=run.roles()
    (run.path/'replica-status.log').write_text(json.dumps(roles,indent=2)+'\n')
    config,_=run.command('exec','-T','api1','python','-c',
        'from app import app; c=app.extensions["records"]; print(c.write_concern.document); print(c.read_concern.document); print(c.read_preference)')
    (run.path/'mongo-client-config.log').write_text(config.stdout)
    run.summary['baseline_distribution']=run.distribution('baseline')
    env=dict(os.environ,BASE_URL=BASE,LAB5_RUN_DIR=str(run.path))
    args=[sys.executable,'-m','pytest','tests/test_api.py','-v','--junitxml='+str(run.path/'pytest.xml')]
    with (run.path/'pytest.log').open('w') as stream:
        p=subprocess.run(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    run.record('pytest',command=args,returncode=p.returncode)
    cases=[json.loads(x) for x in (run.path/'functional-results.jsonl').read_text().splitlines()]
    run.summary['functional']={'passed':sum(x['outcome']=='passed' for x in cases),
                               'failed':sum(x['outcome']=='failed' for x in cases),'cases':cases}
    run.save()
    assert p.returncode==0,(run.path/'pytest.log').read_text()
    control=run.http('POST','/records',201,json={'text':'Persistent control '+run.id})
    run.summary['control_record']=control
    inspected,_=run.command('exec','-T','mongo1','mongosh','--quiet','--eval',
        'JSON.stringify(db.getSiblingDB("lab5").records.findOne({_id:'+json.dumps(control['id'])+'}))')
    doc=json.loads(inspected.stdout.strip())
    assert doc['_id']==control['id'] and doc['text']==control['text']
    (run.path/'mongo-record.log').write_text(inspected.stdout)
    try:
        run.command('stop','api1')
        assert run.http('GET','/records/'+control['id'])['text']==control['text']
    finally:
        run.command('start','api1')
    wait_seconds(6)
    assert run.http('GET','/records/'+control['id'])['text']==control['text']
    run.summary['api_restart_persistence']='PASS'
    run.save()

def full_outage(run):
    control=run.summary['control_record']
    try:
        run.command('stop','mongo1','mongo2','mongo3')
        start=time.monotonic()
        run.http('POST','/records',503,json={'text':'Full outage '+run.id})
        write_duration=time.monotonic()-start
        start=time.monotonic()
        run.http('GET','/records/'+control['id'],503)
        read_duration=time.monotonic()-start
        run.http('GET','/time')
        assert write_duration<12 and read_duration<12
        run.summary['full_database_outage']={'write_status':503,'read_status':503,
            'write_seconds':round(write_duration,6),'read_seconds':round(read_duration,6)}
    finally:
        run.command('start','mongo1','mongo2','mongo3')
        run.wait_topology()
    assert run.http('GET','/records/'+control['id'])['text']==control['text']
    run.save()

def api_failure(run):
    control=run.summary['control_record']
    pair=ProbePair(run,'api_down',control['id'])
    restored=False
    try:
        wait_seconds(5)
        _,stopped=run.command('stop','api2')
        down_until=time.monotonic()+20
        during=run.distribution('api2-down',forbidden='api2')
        wait_seconds(max(0,down_until-time.monotonic()))
        _,started=run.command('start','api2')
        restored=True
        wait_seconds(7)
        after=run.distribution('api2-restored')
        assert 'api2' in after['counts']
    finally:
        if not restored: run.command('start','api2')
        pair.stop()
    assert run.http('GET','/records/'+control['id'])['text']==control['text']
    run.summary['api_failure']={'stop':stopped,'start':started,
        'stopped_seconds':round(started['start_monotonic']-stopped['end_monotonic'],6),
        'during_distribution':during,'after_distribution':after,
        'writes':error_summary(pair.rows(),stopped['start_monotonic']),
        'reads':error_summary(pair.rows('GET'),stopped['start_monotonic'])}
    run.record('api_failure_result',result=run.summary['api_failure'])
    run.save()

def primary_failure(run,crash=False):
    roles=run.wait_topology()
    old=next(x['name'].split(':')[0] for x in roles if x['state']=='PRIMARY')
    survivor=next(x['name'].split(':')[0] for x in roles if x['name'].split(':')[0]!=old)
    controls=[run.summary['control_record']]+[run.http('POST','/records',201,
        json={'text':'Majority-acknowledged pre-failure '+str(i)+' '+run.id}) for i in range(3)]
    key='primary_crash' if crash else 'primary_failure'
    pair=ProbePair(run,'primary_crash' if crash else 'primary_down',controls[0]['id'])
    restored=False
    try:
        wait_seconds(5)
        _,stopped=run.command(*(['kill','--signal','SIGKILL',old] if crash else ['stop',old]))
        deadline=time.monotonic()+90
        election=None
        while time.monotonic()<deadline:
            current=run.roles(survivor)
            new=next((x['name'].split(':')[0] for x in current if x['state']=='PRIMARY' and x['health']==1),None)
            if new and new!=old:
                election=run.record('new_primary_detected',old_primary=old,new_primary=new,members=current)
                break
            wait_seconds(.5)
        assert election is not None,'No new primary was observed while the old one was stopped'
        # Prove successful writes before returning the old primary.
        created=run.http('POST','/records',201,json={'text':'After automatic election '+run.id})
        for control in controls:
            assert run.http('GET','/records/'+control['id'])['text']==control['text']
        wait_seconds(6)
        _,started=run.command('start',old)
        restored=True
        final=run.wait_topology()
        wait_seconds(5)
    finally:
        if not restored:
            run.command('start',old)
            run.wait_topology()
        pair.stop()
    for control in controls+[created]:
        assert run.http('GET','/records/'+control['id'])['text']==control['text']
    run.summary[key]={'old_primary':old,'new_primary':new,'stop':stopped,
        'start':started,'new_primary_observation':election,
        'observed_election_seconds':round(election['monotonic']-stopped['start_monotonic'],6),
        'writes':error_summary(pair.rows(),stopped['start_monotonic']),
        'reads':error_summary(pair.rows('GET'),stopped['start_monotonic']),
        'retained_control_ids':[x['id'] for x in controls], 'retention':'PASS','final_members':final}
    run.record(key+'_result',result=run.summary[key])
    run.save()

def memory_bytes(text):
    import re
    match=re.match(r'([\d.]+)\s*([a-zA-Z]+)',text)
    if not match: return 0
    units={'B':1,'kB':1000,'KB':1000,'KiB':1024,'MB':1000**2,'MiB':1024**2,'GB':1000**3,'GiB':1024**3}
    return float(match[1])*units.get(match[2],1)

def sample_resources(path,stopped,process):
    sampler=psutil.Process(process.pid)
    sampler.cpu_percent()
    with path.open('w') as stream:
        while not stopped.is_set():
            try:
                p=subprocess.run(['docker','stats','--no-stream','--format','{{json .}}'],
                                  text=True,capture_output=True,timeout=10)
                stats=[json.loads(x) for x in p.stdout.splitlines() if x.startswith('{')]
                row=dict(timestamp=utc(),docker=stats,host_memory_percent=psutil.virtual_memory().percent,
                    host_available_bytes=psutil.virtual_memory().available,host_swap_used_bytes=psutil.swap_memory().used,
                    generator_cpu_percent=sampler.cpu_percent(),generator_rss=sampler.memory_info().rss)
                stream.write(json.dumps(row)+'\n'); stream.flush()
            except (psutil.Error,subprocess.SubprocessError,ValueError):
                break
            stopped.wait(3)

def load_level(run,users,duration,spawn):
    # Warm-up is outside Locust CSVs and the declared measured interval.
    for _ in range(10):
        SESSION.get(BASE+'/time',timeout=12).raise_for_status()
        r=SESSION.post(BASE+'/records',json={'text':'Warm-up '+run.id},timeout=12)
        assert r.status_code==201
    prefix=run.path/('locust_'+str(users))
    raw=run.path/('locust_'+str(users)+'_requests.csv')
    cmd=[sys.executable,'-m','locust','-f','tests/locustfile.py','--headless','-u',str(users),
         '-r',str(spawn),'-t',str(duration)+'s','--host',BASE,'--csv',str(prefix),
         '--csv-full-history','--stop-timeout','12','--only-summary']
    env=dict(os.environ,LAB5_RAW_CSV=str(raw),LAB5_RUN_ID=run.id,
             LAB5_FINAL_CSV=str(prefix)+'_final_stats.csv')
    start=time.monotonic(); started=utc()
    with (run.path/('locust_'+str(users)+'.log')).open('w') as stream:
        process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        stopped=threading.Event()
        sampler=threading.Thread(target=sample_resources,
            args=(run.path/('locust_'+str(users)+'_resources.jsonl'),stopped,process),daemon=True)
        sampler.start()
        try:
            returncode=process.wait(timeout=duration+60)
        except subprocess.TimeoutExpired:
            process.terminate(); process.wait(timeout=15)
            raise
        finally:
            stopped.set(); sampler.join(12)
    stats=list(csv.DictReader(Path(str(prefix)+'_final_stats.csv').open()))
    aggregate=next(x for x in stats if x['Name']=='Aggregated')
    raw_rows=list(csv.DictReader(raw.open()))
    assert len(raw_rows)==int(aggregate['Request Count']),(len(raw_rows),aggregate)
    assert max(int(x['users']) for x in raw_rows)==users
    endpoint_targets=[]
    for row in stats:
        count=int(row['Request Count']); failure=int(row['Failure Count'])
        endpoint_targets.append(float(row['95%'])<=1000 and (100*failure/count if count else 100)<=1)
    result=dict(users=users,duration_configured_seconds=duration,elapsed_seconds=round(time.monotonic()-start,6),
       spawn_rate=spawn,start_utc=started,end_utc=utc(),command=cmd,returncode=returncode,
       request_count=int(aggregate['Request Count']),failures=int(aggregate['Failure Count']),
       rps=float(aggregate['Requests/s']),median_ms=float(aggregate['Median Response Time']),
       p95_ms=float(aggregate['95%']),error_percent=100*int(aggregate['Failure Count'])/int(aggregate['Request Count']),
       targets_pass=all(endpoint_targets),maximum_observed_users=users,raw_rows=len(raw_rows),stats=stats)
    run.record('load_result',result=result)
    return result

def load_tests(run,extended):
    run.summary['load']=[]
    for users,spawn in [(10,5),(50,10),(100,20)]:
        run.summary['load'].append(load_level(run,users,60,spawn)); run.save()
    run.summary['exploratory_load']=[]
    if extended:
        for users in [200,400,800,1600]:
            result=load_level(run,users,30,users//5)
            run.summary['exploratory_load'].append(result); run.save()
            # End the bounded exploration at the first observed target breach.
            if not result['targets_pass']:
                break

def publish_selected(run):
    # Originals remain under runs/<id>; copy the selected run to required filenames.
    for p in run.path.iterdir():
        if p.is_file(): shutil.copy2(p,ROOT/'logs'/p.name)
    (ROOT/'logs'/'results.json').write_text(json.dumps(run.summary,indent=2)+'\n')
    (ROOT/'logs'/'latest-run.txt').write_text(run.id+'\n')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--extended',action='store_true',help='Bounded additional saturation runs up to 1600 users')
    parser.add_argument('--check-location',action='store_true',help='Validate checkout/standalone ZIP without starting tests')
    args=parser.parse_args()
    location=validate_location()
    if args.check_location:
        print(json.dumps(location))
        return
    import fcntl
    lock=(ROOT/'logs'/'suite.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    run=Run()
    try:
        functional(run)
        full_outage(run)
        load_tests(run,args.extended)
        api_failure(run)
        primary_failure(run)
        final=run.wait_topology()
        run.summary['final_members']=final
        run.summary['final_distribution']=run.distribution('final')
        run.summary.update(complete=True,completed_utc=utc())
        run.save(); publish_selected(run)
        run.record('suite_complete',run_id=run.id,summary=str(run.path/'summary.json'))
    except BaseException as exc:
        run.summary.update(error=type(exc).__name__+': '+str(exc),failed_at_utc=utc())
        run.save()
        raise

if __name__=='__main__':
    main()
