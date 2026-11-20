"""Live sequential write probe. Actual start/end times, not assumed cadence."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import threading
import time

import requests

def run_probe(base,scenario,run_id,path,stop_event,read_id=None):
    session=requests.Session()
    session.trust_env=False
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('w') as stream:
        sequence=0
        while not stop_event.is_set():
            sequence+=1
            started=datetime.now(timezone.utc).isoformat()
            monotonic=time.monotonic()
            row=dict(scenario=scenario,run_id=run_id,sequence=sequence,start_utc=started,
                     start_monotonic=monotonic,method='GET' if read_id else 'POST')
            try:
                if read_id:
                    response=session.get(base+'/records/'+read_id,timeout=12)
                else:
                    response=session.post(base+'/records',json={'text':'probe '+run_id+' '+scenario},timeout=12)
                row['status']=response.status_code
                try:
                    body=response.json()
                    row.update(served_by=body.get('served_by'),record_id=body.get('id'),error=body.get('error'))
                except ValueError:
                    row['error']='Non-JSON response: '+response.text[:100]
            except requests.RequestException as exc:
                row.update(status=None,error=type(exc).__name__)
            row.update(end_utc=datetime.now(timezone.utc).isoformat(),end_monotonic=time.monotonic(),
                       elapsed_ms=round((time.monotonic()-monotonic)*1000,4))
            stream.write(json.dumps(row)+'\n'); stream.flush()
            stop_event.wait(max(0,.5-(time.monotonic()-monotonic)))
    session.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8080')
    parser.add_argument('--output',default='logs/probe-manual.txt')
    parser.add_argument('--scenario',default='manual')
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--read-id')
    args=parser.parse_args()
    stopped=threading.Event()
    timer=threading.Timer(args.seconds,stopped.set)
    timer.start()
    try:
        run_probe(args.base.rstrip('/'),args.scenario,'manual',args.output,stopped,args.read_id)
    except KeyboardInterrupt:
        stopped.set()
    finally:
        timer.cancel()
