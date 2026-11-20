"""Fixed 3:1 workload, raw per-request CSV, 0.1-0.5 s think time."""
import csv
from datetime import datetime,timezone
import os
from pathlib import Path

from locust import HttpUser,task,between,events
from locust.stats import StatsCSV, PERCENTILES_TO_REPORT

stream=None
writer=None
runtime=None
@events.test_start.add_listener
def start_raw(environment,**kwargs):
    global stream,writer,runtime
    runtime=environment
    name=os.getenv('LAB5_RAW_CSV')
    if name:
        Path(name).parent.mkdir(parents=True,exist_ok=True)
        stream=open(name,'w',newline='')
        writer=csv.writer(stream)
        writer.writerow(['start_utc','end_utc','method','endpoint','milliseconds','status','bytes',
                         'error','served_by','record_id','users','transport_error'])

@events.request.add_listener
def measured(request_type,name,response_time,response_length,response=None,exception=None,
             start_time=None,**kwargs):
    if writer is None:
        return
    try:
        body=response.json() if response is not None else {}
    except ValueError:
        body={}
    writer.writerow([datetime.fromtimestamp(start_time,timezone.utc).isoformat() if start_time else '',
        datetime.now(timezone.utc).isoformat(),request_type,name,response_time,
        response.status_code if response is not None and response.status_code else '',response_length,
        str(exception) if exception else '',body.get('served_by',''),body.get('id',''),
        runtime.runner.user_count,
        repr(getattr(response,'error',None)) if getattr(response,'error',None) else ''])

@events.test_stop.add_listener
def stop_raw(environment,**kwargs):
    global stream,writer
    if stream:
        stream.flush(); stream.close()
    stream=None; writer=None

@events.quit.add_listener
def export_final(exit_code,**kwargs):
    # The periodic built-in CSV may precede the last request. Export the actual
    # final Locust statistics only AFTER runner.quit and in-flight completion.
    path=os.getenv('LAB5_FINAL_CSV')
    if path and runtime is not None:
        with open(path,'w',newline='') as final:
            StatsCSV(runtime,PERCENTILES_TO_REPORT).requests_csv(csv.writer(final))

class ApiUser(HttpUser):
    wait_time=between(.1,.5)

    @task(3)
    def get_time(self):
        with self.client.get('/time',timeout=12,catch_response=True) as response:
            if response.status_code and response.status_code!=200:
                response.failure('Expected HTTP 200')
            elif response.status_code==200:
                try:
                    if response.json().get('served_by') not in {'api1','api2','api3'}:
                        response.failure('Invalid served_by')
                except ValueError:
                    response.failure('Invalid JSON')

    @task(1)
    def create_record(self):
        with self.client.post('/records',json={'text':'load '+os.getenv('LAB5_RUN_ID','manual')},
                              timeout=12,catch_response=True) as response:
            if response.status_code and response.status_code!=201:
                response.failure('Expected HTTP 201')
