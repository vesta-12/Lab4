# Screenshot provenance and optional native Terminal replacements

All JPG files are original captures from the browser screenshot API, made after the real run. No image was drawn to resemble a terminal. The Console capture is the live RustFS UI. The other views explicitly identify themselves as excerpts of previously recorded evidence. Full source logs accompany them.

| Screenshot | Evidence |
| --- | --- |
| `01_file_created.jpg` | Actual POST `/files`, status 201, UUID; `logs/api-storage.log` |
| `02_file_read.jpg` | Actual GET of the same UUID, status 200 and original text |
| `03_file_missing.jpg` | Actual absent UUID request, status 404 |
| `04_file_persistence.jpg` | Real restart/recreation PASS events and subsequent GET 200 |
| `05_rustfs_console.jpg` | Live authenticated RustFS Console > Browser > lab4-files; same UUID, 45 bytes |
| `06_redis-primary.jpg` | Original INFO replication: role master, connected_slaves 1 |
| `07_redis-replica.jpg` | Original INFO replication: role slave, master_link_status up |
| `08_E1.jpg` | Six representative original iteration rows and full 100-iteration result, zero stale |
| `09_E2.jpg` | Original detach/restore commands, 110 versus 100, measured 0.077514 seconds |
| `10_E3.jpg` | Original triples 111/111/110, 112/112/110, 113/113/110 and restoration |
| `11_E4.jpg` | Original HTTP responses, two-master observation, divergent 113/114, restored 114 |

If native Terminal captures are specifically required by your instructor, open a terminal in `~/Lab3_Docker_Kubernetes_Lab4/lab4` and capture the following. This is optional replacement of presentation, not missing measurements. Do not label archived logs as a currently occurring failure.

1. For storage 201/200/404: `curl -i -H 'Content-Type: application/json' -d '{"text":"Defense example"}' http://127.0.0.1:5002/files`; copy the new ID, then `curl -i http://127.0.0.1:5002/files/<new_id>`; finally request `/files/00000000-0000-4000-8000-000000000000`. The status line and JSON must be visible. This creates one additional object.
2. For persistence already measured: `.venv/bin/python -m json.tool logs/results.json` displays both PASS fields, and `curl -i http://127.0.0.1:5002/files/b536f0e7-46e0-42b2-8b89-2d1e093d0c85` shows the still-persisted original text. A new live restart demonstration can use the README steps and the same ID, preserving the volume.
3. For current roles: `docker compose exec redis-primary redis-cli INFO replication` and the replica equivalent. Show master/connected_slaves 1 and slave/link up respectively.
4. For archived E1-E4 in a real Terminal, display the relevant original log with `cat logs/E1-normal.log`, `cat logs/E2-replica-behind.log`, `cat logs/E3-read-own-write.log`, `cat logs/E4-manual-failover.log`. Use `tail -n 1` on each for its result record. These are truthful recorded outputs, not a replay. For readable multiline command output, use the HTML evidence pages or parse the JSONL's `stdout` field.
5. For a new live E1-E4 capture, archive the current logs/screenshots first and run the full suite from the README. It requires port 5002 free and changes the counter. Do not mix new measurements with the old report table unless updating the report.

No new measurements need to be transferred into the existing report. Current topology after the recorded run: one primary on 6379 and one linked replica on 6380, counter 114 on both.
