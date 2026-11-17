"""Publish truthful excerpts of captured logs for browser screenshots.

These pages explicitly identify recorded evidence; they never impersonate a
terminal or execute/replay experiments. Original JSONL stays authoritative.
"""
from pathlib import Path
import json
import html
import shutil

lab = Path(__file__).resolve().parents[1]
dest = lab/'logs'/'browser-evidence'
dest.mkdir(exist_ok=True)
results = json.loads((lab/'logs/results.json').read_text())
def rows(name):
    return [json.loads(x) for x in (lab/'logs'/name).read_text().splitlines()]
def pretty(row):
    stamp = row['timestamp']
    if row['event']=='http':
        return '{}  {} {}\nHTTP {}\n{}'.format(stamp,row['method'],row['url'],row['status'],json.dumps(row['body'],indent=2))
    if row['event']=='command':
        return '{}\n{}\n{}'.format(stamp,row['command'],row['stdout'].rstrip())
    return stamp+'\n'+json.dumps({k:v for k,v in row.items() if k not in ('timestamp',)},indent=2)
links = []
def page(name,title,source,text):
    links.append((name,title))
    content = ('<!doctype html><meta charset="utf-8"><title>'+html.escape(title)+'</title>'
               '<style>body{font:16px Arial,sans-serif;margin:24px;color:#111;max-width:1200px}'
               'h1{font-size:23px;margin:0 0 10px}p{margin:7px 0 14px}pre{font:14px/1.32 monospace;white-space:pre-wrap;overflow-wrap:anywhere}</style>'
               '<h1>'+html.escape(title)+'</h1><p>Recorded evidence from the real Flask/Docker run on 17 November 2026. This is an archived log excerpt, not a live terminal.</p>'
               '<p>Original source: '+html.escape(source)+'. Timestamps below are UTC (Almaty = UTC+5).</p><pre>'+html.escape(text)+'</pre>')
    (dest/(name+'.html')).write_text(content)

a = rows('api-storage.log')
fid = results['storage']['file_id']
created = next(x for x in a if x['event']=='http' and x['status']==201)
read = next(x for x in a if x['event']=='http' and x['url'].endswith(fid) and x['status']==200)
missing = next(x for x in a if x['event']=='http' and x['status']==404)
page('01_file_created','File stored - HTTP 201','logs/api-storage.log',pretty(created))
page('02_file_read','Original text read - HTTP 200','logs/api-storage.log',pretty(read))
page('03_file_missing','Missing object - HTTP 404','logs/api-storage.log',pretty(missing))
persistence = [x for x in a if x['event'] in ('flask_restart_persistence','rustfs_recreation_persistence')]
page('04_file_persistence','File survived both restarts','logs/api-storage.log',
     '\n\n'.join(pretty(x) for x in persistence+[next(x for x in reversed(a) if x['event']=='http' and x['status']==200)]))
r = rows('replication-status.log')
for name,num in [('redis-primary','06'),('redis-replica','07')]:
    found = next(x for x in r if x['event']=='command' and name+' redis-cli INFO' in x['command'])
    page(num+'_'+name,'Replication status - '+name,'logs/replication-status.log',pretty(found))
e1 = rows('E1-normal.log')
iterations = [x for x in e1 if x['event']=='iteration']
text = 'iteration   write   primary   replica   stale\n'
for x in iterations[:3]+iterations[-3:]:
    text += '{:9d} {:7d} {:9d} {:9d}   {}\n'.format(x['iteration'],x['write'],x['primary'],x['replica'],x['stale'])
text += '\nRows 4-97 are in the full original log (all 100 iterations).\n\n'+pretty(e1[-1])
page('08_E1','E1 - 100 sequential writes and reads','logs/E1-normal.log',text)
e2 = rows('E2-replica-behind.log')
select = [x for x in e2 if x['event']=='command' or x['event'] in ('detached_values','result')]
page('09_E2','E2 - replica falls behind and catches up','logs/E2-replica-behind.log','\n\n'.join(pretty(x) for x in select))
e3 = rows('E3-read-own-write.log')
commands = [x for x in e3 if x['event']=='command']
text = '\n\n'.join(pretty(x) for x in commands[:1])+'\n\nwrite   primary   replica\n'
for x in [x for x in e3 if x['event']=='read_your_write']:
    text += '{}     {}       {}\n'.format(x['write'],x['primary'],x['replica'])
text += '\n'+pretty(commands[-1])+'\n\n'+pretty(next(x for x in reversed(e3) if x['event']=='synchronized'))
page('10_E3','E3 - reading your own write','logs/E3-read-own-write.log',text)
e4 = rows('E4-manual-failover.log')
selected = [x for x in e4 if x['event']=='http']
text = '\n'.join('{} {} -> HTTP {} {}'.format(x['method'],x['url'],x['status'],json.dumps(x['body'])) for x in selected[:6])
text += '\n\n'+pretty(next(x for x in e4 if x['event']=='split_brain_observed'))
text += '\n\nFinal recovery: '+results['E4']['restored_topology']+'; both counter values = '+str(results['E4']['restored_value'])
page('11_E4','E4 - manual failover and split-brain','logs/E4-manual-failover.log',text)
(dest/'index.html').write_text('<h1>Lab 4 recorded evidence</h1><p>Real log excerpts for screenshot review. Full original logs are in the submission.</p>'+''.join('<p><a href="'+name+'.html">'+title+'</a></p>' for name,title in links))
print('Prepared {} factual log excerpt pages'.format(len(links)))
