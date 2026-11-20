#!/usr/bin/env python3
"""Read-only final live verification and protection of earlier laboratories."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

import requests

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent

def command(cmd,cwd=ROOT):
    p=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=60)
    p.check_returncode()
    return p.stdout

def main():
    result=json.loads((ROOT/'logs/results.json').read_text())
    assert result['complete']
    branch=command(['git','branch','--show-current'],REPO).strip()
    assert branch=='lab5-nosql-fault-tolerance'
    base=command(['git','rev-parse','lab4-storage-replication'],REPO).strip()
    assert base=='462db1db5f91648f101cc3dc52412df39d681a85'
    preserved={}
    names=command(['git','ls-tree','-r','--name-only',base],REPO).splitlines()
    for name in names:
        old=subprocess.check_output(['git','show',base+':'+name],cwd=REPO)
        current=(REPO/name).read_bytes()
        if name=='.gitignore':
            assert current.startswith(old), 'Only safe append to original gitignore is permitted'
        else:
            assert current==old, 'Earlier laboratory modified: '+name
            preserved[name]=hashlib.sha256(current).hexdigest()
    compose=['docker','compose','--project-name','lab5','--file',str(ROOT/'docker-compose.yml')]
    roles=json.loads(command(compose+['exec','-T','mongo1','mongosh','--quiet','--eval',
        'JSON.stringify(rs.status().members.map(m=>({name:m.name,state:m.stateStr,health:m.health})))']).strip())
    assert len(roles)==3 and sum(x['state']=='PRIMARY' for x in roles)==1 and sum(x['state']=='SECONDARY' for x in roles)==2
    assert all(x['health']==1 for x in roles)
    configs=[]
    for service in ['mongo1','mongo2','mongo3','api1','api2','api3','nginx']:
        data=json.loads(command(['docker','inspect','lab5-'+service+'-1']))[0]
        assert data['State']['Running'] and not data['State'].get('OOMKilled',False)
        ports=data['HostConfig'].get('PortBindings') or {}
        if service!='nginx': assert not ports, (service,ports)
        else:
            assert ports['80/tcp'][0]['HostIp']=='127.0.0.1'
        configs.append({'service':service,'id':data['Id'],'image_id':data['Image'],
                        'hostname':data['Config']['Hostname'],'ports':ports,'mounts':data['Mounts'],
                        'state':data['State']['Status'],'started_at':data['State']['StartedAt']})
    assert len({x['image_id'] for x in configs if x['service'].startswith('api')})==1
    assert command(['docker','network','inspect','lab5_database','--format','{{.Internal}}']).strip()=='true'
    session=requests.Session(); session.trust_env=False
    observed=[]
    base_url=result['base_url']
    for path in ['/time','/records/'+result['control_record']['id']]:
        r=session.get(base_url+path,timeout=12)
        assert r.status_code==200
        if path.startswith('/records/'):
            assert r.json()['text']==result['control_record']['text']
        observed.append({'url':r.url,'status':r.status_code,'body':r.json()})
    nginx=command(compose+['exec','-T','nginx','nginx','-t'])
    versions={}
    for service,args in [('mongo1',['mongod','--version']),('nginx',['nginx','-v']),
                         ('api1',['python','-c','import platform,importlib.metadata as m; print(platform.python_version()); print({x:m.version(x) for x in ["Flask","pymongo","gunicorn"]})'])]:
        p=subprocess.run(compose+['exec','-T',service,*args],cwd=ROOT,text=True,capture_output=True,check=True,timeout=20)
        versions[service]=p.stdout+p.stderr
    data={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS','branch':branch,
          'protected_lab4_head':base,'original_files_preserved':len(preserved),'original_sha256':preserved,
          'members':roles,'containers':configs,'http':observed,'versions':versions,
          'mongo_network_internal':True,'mongo_api_ports_not_published':True,
          'no_lab5_OOM_killed':True,'acknowledged_control_record_retained':True}
    (ROOT/'logs/final-verification.json').write_text(json.dumps(data,indent=2)+'\n')
    # Freeze a snapshot; never follow/append live Docker output into tracked files.
    for service in ['nginx','api1','api2','api3','mongo1','mongo2','mongo3']:
        p=subprocess.run(compose+['logs','--no-color','--timestamps',service],cwd=ROOT,
                          text=True,capture_output=True,timeout=60,check=True)
        (ROOT/'logs'/('container-'+service+'.log')).write_text(p.stdout+p.stderr)
    print('PASS: topology, all seven core services, persistence, no exposed database/API, earlier files unchanged.')

if __name__=='__main__': main()
