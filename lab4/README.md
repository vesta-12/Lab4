# Laboratory Work 4 - Data Storage and Replication

Student: Sofiya Serbina. Course: Distributed & Cloud Computing.

Lab 4 is isolated in this directory on `lab4-storage-replication`. The original Lab 2 and Lab 3 code, root Compose and Kubernetes files are unchanged. `spec.md` is Version 3 and retains the Version 2 material with its historical scope.

## Verified result

The live run completed on **17 November 2026 at 14:00 Almaty time (09:00 UTC)** using Python **3.9.6**, Flask on **5002**, RustFS **1.0.0**, and two real Redis 7 containers. These measurements come from `logs/results.json`, not from mocks.

| Experiment | Actual observations |
| --- | --- |
| E1 | 100 sequential increments and two reads per increment; primary 0 to 100; **0 stale replica reads**. All 100 rows are retained. |
| E2 | Detached replica stayed at **100**; primary reached **110** after 10 API increments. Reconnection and equal-value/link-up check completed in **0.077514 s**. |
| E3 | Write/primary/replica triples: **111/111/110**, **112/112/110**, **113/113/110**. Replication was then restored. |
| E4 | With primary stopped, replica read **113** (200), writes returned **503**. Promotion plus API restart with primary port **6380** allowed increment to **114** (200). Old primary returned as another master at **113**, while the promoted master had **114**. Both were observed as master. Restoration preserved **114** on both nodes. |

E2 timing uses `time.monotonic()` from immediately before the restoring REPLICAOF command until role/link/value checks succeed. It includes Docker command overhead. Checks poll every 50 ms; this is an observed local recovery duration, not an intrinsic network latency or a durability guarantee.

Storage evidence: file ID **`b536f0e7-46e0-42b2-8b89-2d1e093d0c85`**, text `Hello from Lab 4 - persistent RustFS evidence`. POST 201, GET 200, absent key 404, invalid inputs and oversized text 400, stopped RustFS POST/GET 503. The same object remained readable after Flask restart and RustFS `--force-recreate` using the existing **`lab4_s3-data`** volume. S3 HEAD/LIST and the Console confirmed the object. Redis data also uses separate AOF-backed volumes.

**23 isolated contract tests passed.** Their dependency mocks are intentionally separate from the live tests above; see `logs/unit-tests.log`.

Additional live checks (`logs/additional-live-checks.log`) uploaded and read exactly 65,536 UTF-8 bytes in both ASCII and Unicode, rejected a JSON request above 512 KiB with 400, and verified replica GET 503 during a controlled replica stop while primary GET stayed 200. The replica was restarted and rejoined at counter 114. These boundary objects are also retained; the earlier Console screenshot shows the original object before these extra uploads.

## Setup and normal launch

Use this directory, not `~/PycharmProjects/Lab2_REST_Queues`:

```bash
cd ~/Lab3_Docker_Kubernetes_Lab4/lab4
git branch --show-current
# Must print lab4-storage-replication.
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# On a fresh checkout only: copy .env.example to .env and choose LOCAL keys.
# Keep an existing .env: changing keys could prevent access to an existing volume.
docker compose up -d
.venv/bin/python app.py
```

The existing local `.env` is intentionally absent from Git and the ZIP. On this machine it is already configured; it must not be overwritten. On a different machine use a fresh `.env` with your own educational credentials matching the RustFS deployment. No AWS account is used.

`app.py` loads `.env` beside itself regardless of the working directory. Explicit environment values take precedence. A direct Python launch uses `FLASK_PORT` (default 5002). An alternative Flask CLI launch is `.venv/bin/python -m flask --app app run --host 127.0.0.1 --port 5002`; Flask CLI uses `--port` / `FLASK_RUN_PORT`, not `FLASK_PORT`. Run one server at a time.

Configuration is listed in `.env.example` and spec Section 10. Redis ports can be changed without editing source. The API binds to loopback and has debug/reloader disabled.

## Initial Flask problem and resolution

The correct repository's original `lab4/app.py` contained only `/time` and `/echo`, and `app.run(..., port=5000)`. The file API was in the other repository, so changing `FLASK_PORT` could not change the hardcoded port or register missing routes. At diagnosis time, macOS Control Center owned port 5000, port 5002 was free, and no Python/Flask server was running. The earlier reported 5002 HTML 404 cannot be retrospectively assigned to a particular process.

The corrected absolute module path, route inventory, listener ownership and real HTTP responses are recorded in `logs/startup-diagnosis.log`, `logs/api-storage.log` and `logs/flask-server.log`. No system service or unrelated process was stopped.

## API demonstration

In another terminal, while Flask is running:

```bash
curl -i http://127.0.0.1:5002/time
curl -i -H 'Content-Type: application/json' -d '{"message":"hello"}' http://127.0.0.1:5002/echo
curl -i -H 'Content-Type: application/json' -d '{"text":"Hello from Lab 4"}' http://127.0.0.1:5002/files
# Replace <file_id> with the returned UUID.
curl -i http://127.0.0.1:5002/files/<file_id>
curl -i http://127.0.0.1:5002/files/00000000-0000-4000-8000-000000000000
curl -i -X POST http://127.0.0.1:5002/counter/increment
curl -i 'http://127.0.0.1:5002/counter?from=primary'
curl -i 'http://127.0.0.1:5002/counter?from=replica'
docker compose exec redis-primary redis-cli INFO replication
docker compose exec redis-replica redis-cli INFO replication
```

`source` identifies the configured client connection. It does not dynamically check ROLE. All increments use the primary client; replica reads may be stale. Missing counter keys read as 0 without a write. File limits are 65,536 decoded UTF-8 bytes and 512 KiB total JSON request size; over-limit requests return 400.

RustFS Console: `http://127.0.0.1:9001`, sign in with the existing local `.env` credentials, open Browser > `lab4-files`. S3 API endpoint: `http://127.0.0.1:9000`.

## Reproduce tests and E1-E4

Isolated contract tests (no container manipulation):

```bash
.venv/bin/python -m pytest tests -v
```

Full live suite, from this directory, **with port 5002 initially free**:

```bash
docker compose up -d
.venv/bin/python scripts/run_experiments.py
```

The suite owns its Flask child, performs real HTTP requests, recreates RustFS without deleting its volume, temporarily stops only Lab 4 services, changes Redis roles, and restores the standard topology. It never kills a foreign listener, resets the counter or deletes volumes. It leaves its Flask process on port 5002; its PID is in ignored `logs/flask.pid`. To stop that server, inspect the PID and process path before sending it TERM, or stop your own foreground server with Ctrl+C. Do not kill a process based on port alone.

With that API running, `.venv/bin/python scripts/check_boundaries.py` reproduces the additional size-limit and stopped-replica checks. It creates two boundary objects, briefly stops the replica, restores it, and leaves the counter unchanged.

Re-running **adds increments to the existing counter and replaces experiment logs**. Copy the current `logs/` and `screenshots/` first if preserving this submission's evidence. Logs are timestamped JSON Lines with original command stdout and HTTP responses. `logs/integration-run.log` contains the combined full run. `logs/replication-status.log` has the initial roles; the end of E4 contains the restored roles. No Redis WAIT is inserted between E1 writes and reads.

## Manual failover procedure

These commands intentionally alter Lab 4 service roles. Use a single controlled writer and retain evidence before changing topology:

```bash
docker compose stop redis-primary
# Replica GET works; API POST increment returns 503.
docker compose exec redis-replica redis-cli REPLICAOF NO ONE
# Stop YOUR Flask process, then redirect it without source edits:
REDIS_PRIMARY_PORT=6380 .venv/bin/python app.py
# POST increment and GET from=primary now use the promoted node.
docker compose start redis-primary
docker compose exec redis-primary redis-cli INFO replication
docker compose exec redis-replica redis-cli INFO replication
# Both may be master; inspect their GET lab4:counter values.
```

To reconcile after observing split-brain, first stop API writers. Preserve the promoted node's newer data by making the old primary follow it:

```bash
docker compose exec redis-primary redis-cli REPLICAOF redis-replica 6379
# Wait for the OLD primary's master_link_status:up and identical counter values.
# Only then return to the normal service names:
docker compose exec redis-primary redis-cli REPLICAOF NO ONE
docker compose exec redis-replica redis-cli REPLICAOF redis-primary 6379
# Wait for replica link up and equal values, then restart Flask normally:
REDIS_PRIMARY_PORT=6379 REDIS_REPLICA_PORT=6380 .venv/bin/python app.py
```

The experiment script checks these conditions automatically. Never attach the newer promoted node to the stale old primary before copying the new data, and never run `docker compose down -v`. REPLICAOF changes are runtime configuration; Compose defines the original topology on container recreation.

## Screenshots and report

`screenshots/` contains **11 genuine browser captures**. `05_rustfs_console.jpg` captures the actual authenticated RustFS Console and object. Other images capture a browser displaying clearly labelled, factual excerpts from this run's original logs; they are **archived evidence views, not native Terminal screenshots or live replays**. The original JSONL remains authoritative. No outputs or screenshots were fabricated. The screenshot tool could not control the macOS Terminal app.

`logs/browser-evidence/index.html` opens those source excerpts locally. `scripts/build_evidence_pages.py` regenerates excerpts from the logs; regenerating pages does not recapture images. `screenshots/README.md` maps each image to its original evidence. If your instructor specifically requires native Terminal windows, take replacement screenshots using the commands there; no experiment data is missing from the report.

`report.pdf` is a visually checked two-page report in English, using the existing Lab 3 report's Times New Roman typography, right-aligned student block, centered title and page geometry. `report-source.txt` provides editable report text. The available reference was `Lab3_Report_Serbina_Sofiya.docx` in the repository.

## Interpretation for the defense

RustFS keeps files outside the Flask process and uses a persistent volume. Redis INCR is atomic on one primary. Asynchronous replication explains why an ordinary local E1 run can have zero stale reads yet a deliberately disconnected replica in E2/E3 is stale. The E2 catch-up shows eventual consistency after communication resumes.

Manual failover required promotion, application redirection and reconciliation of the returning node. This two-node Compose setup has no Sentinel/Cluster and no election service. Redis Sentinel adds monitoring and coordinated failover with client discovery; MongoDB replica sets elect a primary using voting members and a majority, and compatible drivers discover the new primary. Automatic failover requires suitable topology/configuration and does not imply that every acknowledged write is preserved.

Primary sources: [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/), [Redis Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/), [MongoDB elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/).
