#!/usr/bin/env python3
"""Explicit supplement: high-load transport diagnostics and abrupt primary crash.

The required graceful-stop result is preserved. This run has its own directory
and logs; it does not replace a zero-error graceful election with crash errors.
"""
import json
from pathlib import Path
import shutil
import sys

from run_suite import Run,ROOT,load_level,primary_failure,utc,wait_seconds

def main():
    import fcntl
    lock=(ROOT/'logs/suite.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    main_result=json.loads((ROOT/'logs/results.json').read_text())
    assert main_result['complete']
    run=Run()
    run.summary.update(supplement=True,parent_run_id=main_result['run_id'],
                       control_record=main_result['control_record'])
    run.save()
    run.record('supplement_started',parent_run_id=main_result['run_id'],
               reason='Investigate first transport failures and distinguish graceful handoff from an abrupt crash')
    run.wait_topology()
    run.summary['diagnostic_load']=[load_level(run,1600,30,320)]
    wait_seconds(7)
    primary_failure(run,crash=True)
    run.summary.update(complete=True,completed_utc=utc(),final_members=run.wait_topology())
    run.save()
    for file in run.path.iterdir():
        if file.is_file() and (file.name.startswith('locust_') or file.name.startswith('probe_')):
            shutil.copy2(file,ROOT/'logs'/file.name)
    shutil.copy2(run.path/'events.jsonl',ROOT/'logs/supplement-events.jsonl')
    (ROOT/'logs/supplementary-results.json').write_text(json.dumps(run.summary,indent=2)+'\n')
    run.record('supplement_complete',run_id=run.id)

if __name__=='__main__': main()
