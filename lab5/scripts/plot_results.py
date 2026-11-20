from pathlib import Path
import os
import json
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'logs/live/matplotlib-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

lab=ROOT
r=json.loads((lab/'logs/results.json').read_text())
assert r['complete']
supp=json.loads((lab/'logs/supplementary-results.json').read_text()) if (lab/'logs/supplementary-results.json').exists() else {}
rows=r['load']+r.get('exploratory_load',[])+supp.get('diagnostic_load',[])
x=[v['users'] for v in rows]
fig,axes=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
axes[0].plot(x,[v['rps'] for v in rows],'o-',color='#175d92')
axes[0].set(xlabel='Concurrent users',ylabel='Requests per second',title='Measured throughput')
for row in rows:
    axes[0].annotate(str(round(row['rps'])),(row['users'],row['rps']),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
axes[1].plot(x,[v['median_ms'] for v in rows],'o-',label='Median')
axes[1].plot(x,[v['p95_ms'] for v in rows],'s-',label='p95')
axes[1].axhline(1000,ls='--',lw=1,color='#9e302e',label='R48 p95 target')
axes[1].set(xlabel='Concurrent users',ylabel='Response time (ms, log scale)',yscale='log',title='Measured aggregate latency')
axes[1].legend(fontsize=9)
for ax in axes:
    ax.set_xscale('log'); ax.set_xticks(x,labels=[str(n) for n in x]); ax.grid(alpha=.2)
fig.suptitle('Lab 5: 3:1 GET /time and POST /records; fixed think time 0.1-0.5 s',fontsize=12)
fig.savefig(lab/'logs/load-results.png',dpi=180)
print('Saved load-results.png from actual final CSV statistics')
