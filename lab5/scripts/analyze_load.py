#!/usr/bin/env python3
"""Keep transport failures distinct from real HTTP statuses and compare capacity."""
from collections import Counter
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'logs'

def main():
    main=json.loads((LOG/'results.json').read_text())
    supplement=json.loads((LOG/'supplementary-results.json').read_text())
    assert main['complete'] and supplement['complete']
    levels=main['load']+main['exploratory_load']+supplement['diagnostic_load']
    rows=[]
    for level in levels:
        records=list(csv.DictReader((LOG/('locust_'+str(level['users'])+'_requests.csv')).open()))
        bad=[x for x in records if x['error']]
        assert len(records)==level['request_count'] and len(bad)==level['failures']
        transport=[x for x in bad if x['status'] in ('','0')]
        rows.append({'users':level['users'],'request_count':len(records),'failures':len(bad),
          'transport_failures':len(transport),'http_failures':len(bad)-len(transport),
          'underlying_errors':dict(Counter(x.get('transport_error','') or x['error'] for x in bad)),
          'rps':level['rps'],'p95_ms':level['p95_ms'],'error_percent':level['error_percent']})
    nginx=(LOG/'container-nginx.log').read_text()
    related=[line for line in nginx.splitlines() if 'worker_connections' in line]
    eight=next(x for x in rows if x['users']==800)
    sixteen=next(x for x in rows if x['users']==1600)
    result={'levels':rows,'nginx_worker_connection_limit_messages':len(related),
      'nginx_worker_connection_limit_examples':related[:5],
      'throughput_change_800_to_1600_percent':100*(sixteen['rps']/eight['rps']-1),
      'capacity_observation':'End-to-end saturation/degradation in the tested 800-1600 user range; not an isolated database-capacity claim',
      'cause_assessment':('nginx explicitly logged its worker-connection limit' if related else
        'No nginx worker-connection-limit message was logged. Remote disconnect/reset errors establish an ingress/connection-path failure; shared generator/host/VM contention remains a hypothesis requiring isolation.'),
      'instrumentation_note':'The original 800-user run kept generic expected-status failure labels; status 0 is Locust no-response, not HTTP 0. The supplement preserved underlying transport exceptions.'}
    (LOG/'bottleneck-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='levels'},indent=2))

if __name__=='__main__': main()
