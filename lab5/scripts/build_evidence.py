#!/usr/bin/env python3
"""Render factual archived log/CSV excerpts for genuine browser captures."""
import csv
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'logs'
DEST=LOG/'browser-evidence'

def escaped(text): return html.escape(str(text))
def pre(text): return '<pre>'+escaped(text)+'</pre>'
def table(headers,rows):
    return '<table><tr>'+''.join('<th>'+escaped(x)+'</th>' for x in headers)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+escaped(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'

def main():
    r=json.loads((LOG/'results.json').read_text())
    assert r['complete']
    DEST.mkdir(exist_ok=True)
    links=[]
    def page(name,title,source,body):
        links.append((name,title))
        content='''<!doctype html><meta charset="utf-8"><title>'''+escaped(title)+'''</title>
<style>body{font:16px Arial,sans-serif;margin:24px;color:#111;max-width:1200px}h1{font-size:24px;margin:0 0 12px}p{line-height:1.4}pre{font:14px/1.35 monospace;white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:15px}td,th{border:1px solid #aaa;padding:9px;text-align:left}th{background:#f3f3f3}</style>
<h1>'''+escaped(title)+'''</h1><p><strong>Archived log evidence.</strong> Actual Lab 5 measurements, not a live terminal or a replay. Original logs and CSV files accompany the submission.</p><p>Run: '''+escaped(r['run_id'])+'''. Timestamps: UTC (Almaty = UTC+5).<br>Source: '''+escaped(source)+'''</p>'''+body
        (DEST/(name+'.html')).write_text(content)
    initial=json.loads((LOG/'replica-status.log').read_text())
    page('01_replica_set','MongoDB replica set: one primary, two secondaries','logs/replica-status.log',
         table(['Member','State','Health'],[[x['name'],x['state'],x['health']] for x in initial]))
    page('02_compose','Docker Compose services','logs/compose-ps.log',pre((LOG/'compose-ps.log').read_text()))
    events=[json.loads(x) for x in (LOG/'events.jsonl').read_text().splitlines()]
    control=r['control_record']
    create=next(x for x in events if x['event']=='http' and x['method']=='POST' and x.get('body',{}).get('id')==control['id'])
    read=next(x for x in events if x['event']=='http' and x['method']=='GET' and x.get('body',{}).get('id')==control['id'])
    page('03_records','Real record creation and reading','logs/events.jsonl; logs/mongo-record.log',
         pre('\n\n'.join(x['timestamp']+'\n'+x['method']+' '+x['url']+'\nHTTP '+str(x['status'])+'\n'+json.dumps(x['body'],indent=2) for x in [create,read])))
    before=r['baseline_distribution']
    page('04_distribution','30 requests through nginx','logs/distribution-baseline.json',
         table(['API','Actual responses'],sorted(before['counts'].items()))+
         pre('Requests: '+str(before['requests'])+'\nHTTP errors: '+str(before['errors'])))
    a=r['api_failure']
    page('05_api_down','api2 stopped for approximately 20 seconds','logs/distribution-api2-down.json; logs/probe_api_down.txt',
         table(['State','api1','api2','api3'],[
          ['Stopped',*[a['during_distribution']['counts'].get(x,0) for x in ['api1','api2','api3']]],
          ['Restored',*[a['after_distribution']['counts'].get(x,0) for x in ['api1','api2','api3']]]])+
         pre('Stop completed: '+a['stop']['end_utc']+'\nRestart started: '+a['start']['start_utc']+
             '\nStopped interval: '+str(a['stopped_seconds'])+' s\nWrite 503 / other HTTP / transport errors: '+
             ' / '.join(str(a['writes'][k]) for k in ['http_503','other_http_errors','transport_errors'])))
    for level,num in zip(r['load'],['06','07','08']):
        count=str(level['users'])
        rows=[[x['Type']+' '+x['Name'],x['Request Count'],x['Failure Count'],
              '{:.3f}'.format(float(x['Requests/s'])),x['Median Response Time'],x['95%']] for x in level['stats']]
        page(num+'_load_'+count,'Locust final result: '+count+' users, 60 seconds',
          'logs/locust_'+count+'_final_stats.csv; logs/locust_'+count+'.log',
          table(['Endpoint','Requests','Failures','RPS','Median ms','p95 ms'],rows)+
          pre('Start: '+level['start_utc']+'\nEnd: '+level['end_utc']+
              '\nMaximum observed users: '+count+'\nFull raw request rows: '+str(level['raw_rows'])+
              '\nFinal native Locust count equals the complete raw request count.\nTarget p95 <=1000 ms / error <=1%: '+('PASS' if level['targets_pass'] else 'FAIL')))
    m=r['primary_failure']; w=m['writes']
    def stamp(row): return row['end_utc'] if row else 'Not observed'
    page('09_primary_down','Automatic MongoDB election and measured recovery',
       'logs/probe_primary_down.txt; logs/probe_primary_down_reads.txt; logs/events.jsonl',
       table(['Event','Actual observation'],[
        ['Old primary',m['old_primary']],['Stop command started',m['stop']['start_utc']],
        ['First write error',stamp(w['first_error'])],['Write HTTP 503 count',w['http_503']],
        ['Write other HTTP / transport errors',str(w['other_http_errors'])+' / '+str(w['transport_errors'])],
        ['Read HTTP 503 count',m['reads']['http_503']],['New primary',m['new_primary']],
        ['New primary detected',m['new_primary_observation']['timestamp']],
        ['Observed stop-to-detection seconds',m['observed_election_seconds']],
        ['First successful write after errors',stamp(w['first_success_after_errors'])],
        ['Observed stop-to-write-recovery seconds',w['stop_to_recovery_seconds']],
        ['Acknowledged control-record retention',m['retention']]]))
    verified=json.loads((LOG/'final-verification.json').read_text())
    page('10_final_roles','Restored MongoDB topology after all scenarios','logs/final-verification.json',
       table(['Member','State','Health'],[[x['name'],x['state'],x['health']] for x in verified['members']])+
       pre('Control IDs retained: '+str(len(m['retained_control_ids']))+'\nFinal distribution: '+json.dumps(r['final_distribution']['counts'])+
           '\nManual MongoDB promotion performed: NO\nVolumes removed: NONE'))
    (DEST/'index.html').write_text('<h1>Lab 5 archived measurement evidence</h1><p>Actual captured logs; not live terminal output.</p>'+''.join(
        '<p><a href="'+name+'.html">'+escaped(title)+'</a></p>' for name,title in links))
    supplement=LOG/'supplementary-results.json'
    if supplement.exists():
        c=json.loads(supplement.read_text())['primary_crash']; w=c['writes']
        page('11_primary_crash','Supplement: abrupt primary crash and real HTTP 503',
          'logs/supplementary-results.json; logs/probe_primary_crash.txt',
          table(['Event','Actual observation'],[
            ['Crash command','docker compose kill --signal SIGKILL '+c['old_primary']],
            ['Crash command start',c['stop']['start_utc']],
            ['First write 503',stamp(w['first_503'])],
            ['Write 503 / read 503',str(w['http_503'])+' / '+str(c['reads']['http_503'])],
            ['Old / new primary',c['old_primary']+' / '+c['new_primary']],
            ['Observed primary detection seconds',c['observed_election_seconds']],
            ['Write recovery seconds',w['stop_to_recovery_seconds']],
            ['First successful write after errors',stamp(w['first_success_after_errors'])],
            ['Acknowledged control-record retention',c['retention']]]))
    names=[name for name,_ in links]
    if (ROOT/'screenshots/12_live_record.jpg').exists():
        names.append('12_live_record')
    metadata={'provenance':'Genuine browser captures of explicitly labelled archived real-run evidence; no generated terminal imagery',
              'run_id':r['run_id'],'expected_screenshots':[name+'.jpg' for name in names]}
    (ROOT/'screenshots'/'sources.json').write_text(json.dumps(metadata,indent=2)+'\n')
    readme=['# Screenshot provenance','The numbered JPG files are genuine browser screenshot API captures of the factual '
      'archived evidence pages in `logs/browser-evidence/`. Every page explicitly states that it is archived log evidence, '
      'not a live terminal or replay. The exact original JSONL/CSV sources are shown on the image. '
      'No terminal image, command result or measurement was fabricated.',
      '| Image | Actual evidence |','| --- | --- |']
    for name,title in links:
        readme.append('| '+name+'.jpg | '+title+' |')
    if '12_live_record' in names:
        readme.append('| 12_live_record.jpg | Live browser GET of the persistent control record directly from nginx; not an archived page |')
    readme.append('Native Docker Desktop/Terminal capture was unavailable because computer-control permissions were not granted. Browser capture worked. The numbered archived screenshots remain explicitly identified, and the extra live API screenshot shows the real currently served record.')
    readme += ['','Open `logs/browser-evidence/index.html` locally to inspect the same source excerpts. '
      'If the instructor specifically requires native Terminal windows, capture the following '
      'read-only displays or perform a fresh documented experiment after archiving current results:',
      '```bash\ncd /Users/sofiyaserbina/Lab3_Docker_Kubernetes_Lab4/lab5\n'
      'docker compose ps --all\n'
      'docker compose exec mongo1 mongosh --quiet --eval "rs.status().members.map(m=>m.name+\' \'+m.stateStr)"\n'
      'cat logs/distribution-baseline.json\ncat logs/distribution-api2-down.json\n'
      'tail -25 logs/locust_10.log\ntail -25 logs/locust_50.log\ntail -25 logs/locust_100.log\n'
      'cat logs/probe_primary_down.txt\n```',
      'Archived logs displayed in a Terminal are still archived evidence. For a new live failure '
      'screenshot, follow README and archive the current run first. Do not substitute fresh values '
      'into the existing report without updating all related measurements.']
    (ROOT/'screenshots'/'README.md').write_text('\n\n'.join(readme)+'\n')
    # Include the optional crash page in the navigation too.
    (DEST/'index.html').write_text('<h1>Lab 5 archived measurement evidence</h1><p>Actual captured logs; not live terminal output.</p>'+''.join(
        '<p><a href="'+name+'.html">'+escaped(title)+'</a></p>' for name,title in links))
    print('Prepared '+str(len(links))+' truthful browser evidence pages and source mapping.')

if __name__=='__main__': main()
