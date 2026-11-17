# Lab 4 - Service Requirements Specification (Version 3)

**Course:** Distributed & Cloud Computing  
**Laboratory:** Data Storage and Replication  
**Student:** Sofiya Serbina  
**Version:** 3.0 (evolved from Laboratories 2 and 3)

## Version 3 scope and precedence

Sections 1-6 below preserve the Version 2 requirements and their historical deployment context. They continue to describe Lab 2 and Lab 3; their ports, Python 3.12 image, and statements that persistence is out of scope apply to those laboratories only. Lab 4 adds the requirements in Sections 7-10, runs locally on Python 3.9.6 at `127.0.0.1:5002`, and adds shared persistent storage. Lab 3 source files and deployment manifests remain unchanged. The `/time` and `/echo` response contracts are retained. Authentication and public deployment remain out of scope.

The previous specification had no R-numbered requirements (verified before editing). Section 7 assigns identifiers to the retained requirements before continuing with the new requirements.

## 1. Overview (retained Version 2 context)

Laboratory Work 2 implemented two communication approaches:

1. A synchronous REST API with `/time` and `/echo` endpoints.
2. An asynchronous message queue with a separate REST-based broker, producer, and consumer.

Laboratory Work 3 reuses the existing Flask REST API and deploys it as a Docker container, then as multiple Kubernetes pods. The API remains stateless, so separate instances can process requests independently. The `/time` response now identifies the container or pod that handled the request using the `served_by` field.

Only the REST API is included in the Docker image and Kubernetes deployment. The queue components from Lab 2 are **not deployed or tested** in this laboratory.

## 2. REST API (Version 2)

The API uses HTTP and returns JSON responses. Inside the container, Flask listens on `0.0.0.0:5000`. On the macOS host, Docker maps port `5001` to container port `5000`.

### GET /time

- **Method:** `GET`
- **Docker host URL:** `http://127.0.0.1:5001/time`
- **Kubernetes URL:** `<URL returned by minikube service my-api --url>/time`
- **Request body:** none
- **Success status:** `200 OK`

Example response:

```json
{
  "server_time": "2026-10-25 15:06:53.053678",
  "served_by": "6e7f69cd8125"
}
```

Response fields:

- `server_time` — the current server date and time, represented as a string.
- `served_by` — the hostname of the responding instance, obtained using Python's `socket.gethostname()`. It identifies a Docker container when run with Docker and a pod when run with Kubernetes.

The `served_by` field makes it possible to count responses from different pods and demonstrate request distribution through a Kubernetes Service.

### POST /echo

- **Method:** `POST`
- **Docker host URL:** `http://127.0.0.1:5001/echo`
- **Kubernetes URL:** `<URL returned by minikube service my-api --url>/echo`
- **Content-Type:** `application/json`

Example request:

```json
{
  "message": "hello"
}
```

**Success status:** `200 OK`

```json
{
  "message": "hello"
}
```

If the JSON body is missing or the `message` field is absent, the API returns **`400 Bad Request`**:

```json
{
  "error": "field 'message' is required"
}
```

The endpoint does not save requests or responses between calls.

## 3. Containerization and Deployment Requirements

### Docker

- The application code is stored in `app/app.py`.
- `app/requirements.txt` contains `flask`.
- The Dockerfile uses `python:3.12-slim` as its base image.
- The Dockerfile copies and installs dependencies before copying the application code, allowing Docker to reuse cached dependency layers.
- The image is built as `my-api:lab3`.
- Flask listens on `0.0.0.0` and container port `5000`.
- The Docker Compose service is named `api`, builds from `./app`, and maps host port `5001` to container port `5000`.

### Kubernetes

- A Deployment named `my-api` manages **3 replicas** under normal operation.
- All pods use the image `my-api:lab3`, loaded into Minikube.
- The pod labels and Deployment selector use `app: my-api`.
- A Service named `my-api`, of type `NodePort`, uses selector `app: my-api` and forwards Service port `80` to container port `5000`.
- The Service provides access to the pod replicas through one logical endpoint.
- Across **30 requests** to `/time`, the `served_by` field must identify at least **2 different pods**.
- If a pod is deleted, the Deployment should create a replacement to maintain the desired replica count.
- The API should remain accessible through the Service during pod replacement while other healthy replicas are available.
- Scaling to **5 replicas** and back to **3 replicas** must be demonstrated.

## 4. Constraints

- Protocol: HTTP; response format: JSON.
- Runtime: Python 3.12 and Flask in the container.
- The Docker container port is `5000`; the macOS host uses port `5001` because host port `5000` was previously occupied.
- The locally exposed Minikube Service URL and port are provided by `minikube service my-api --url` and may vary between runs.
- The API must not depend on local in-memory session state or on a particular pod to handle consecutive requests.
- Only the API is included in the container; the Lab 2 queue broker, producer, and consumer are out of scope.
- AWS resources, AWS credentials, and other secrets are not required and must not be included in the Docker image.
- Authentication, authorization, HTTPS, and persistent storage are outside the scope of this laboratory.

## 5. Assumptions

1. Docker Desktop, Minikube, and kubectl are installed and running on the local macOS machine.
2. The Docker image is available to the Minikube cluster before the Kubernetes Deployment starts.
3. Clients send correctly formatted JSON for successful `/echo` requests.
4. Each API replica can answer `/time` and `/echo` without shared application state.
5. The Kubernetes Service selects the API pods using matching labels.
6. Healthy replicas are available to handle requests while a deleted pod is being replaced.
7. The laboratory uses a small local workload for request distribution, self-healing, and scaling tests.

## 6. Lab 2 Message Queue (Previous Version - Not Deployed in Lab 3)

The earlier project also included a separate in-memory message queue broker on port `6000`, with one producer and one consumer. The queue functionality is retained as background information only and is **not part of the Lab 3 REST API container**.

### POST /queue/<topic>

Adds a message to a queue identified by its topic. Example: `POST http://127.0.0.1:6000/queue/orders`. A successful request returns `201 Created` with the queue status and topic.

### GET /queue/<topic>

Retrieves and removes the oldest message from the selected queue using FIFO order. It returns `200 OK` with the message if one exists, or `204 No Content` if the queue is empty.

In Lab 2, the producer sent approximately one message per second and the consumer took approximately three seconds to process a message. The broker stored messages only in memory, so restarting it could cause queued messages to be lost. These behaviors are not evaluated in Lab 3.

## 7. Requirement identifiers and verification traceability

The identifiers are stable starting with Version 3. A retained requirement is not claimed as re-executed unless explicitly stated. Container and Kubernetes tests remain Lab 3 evidence.

| ID | Requirement | Verification / evidence |
| --- | --- | --- |
| R1 | GET `/time` returns 200 with string `server_time` and `served_by`. | `tests/test_api.py::test_legacy_contract`; `logs/api-storage.log` |
| R2 | POST `/echo` returns 200 and the submitted `message`. | Same test and live log as R1 |
| R3 | Missing message or malformed/non-object JSON on `/echo` returns JSON 400. | `test_legacy_contract`; live missing-message check |
| R4 | The REST process keeps no per-client session or file state on disk. | Code review of `app.py`; restart persistence check |
| R5 | Retain the Lab 3 Python 3.12 image and dependency-first Docker build. | Historical `app/Dockerfile`, unchanged; not re-run in Lab 4 |
| R6 | Retain Lab 3 container 5000 / host 5001 mapping. | Historical root Compose, unchanged; not re-run in Lab 4 |
| R7 | Retain the three-pod Deployment and matching NodePort Service. | Historical `k8s/`, unchanged; not re-run in Lab 4 |
| R8 | At least two pods serve the 30-request distribution test. | Historical Lab 3 evidence; not re-run in Lab 4 |
| R9 | Deployment replaces deleted pods while remaining pods serve requests. | Historical Lab 3 evidence; not re-run in Lab 4 |
| R10 | Demonstrate scaling 3 to 5 to 3 pods. | Historical Lab 3 evidence; not re-run in Lab 4 |
| R11 | Retain Lab 2 FIFO queue POST 201 / GET 200 or 204 behavior. | Historical broker, unchanged; outside Lab 4 execution scope |
| R12 | Do not embed AWS or RustFS credentials in code, images, or submission. | `.gitignore`; ZIP content and secret audit |
| R13 | POST `/files` stores a UTF-8 text object and returns unique UUID `file_id`, 201, and Location. | `test_upload_and_read`; `logs/api-storage.log` |
| R14 | GET `/files/<file_id>` returns exactly the original text and ID, 200; missing key returns JSON 404. | `test_upload_and_read`, `test_missing_and_invalid_file`; live log |
| R15 | File IDs must be lowercase UUID-shaped strings; invalid IDs return JSON 400 before storage access. | `test_missing_and_invalid_file`; live invalid-ID request |
| R16 | File upload requires a JSON object with non-empty string `text`; malformed JSON, invalid Unicode and wrong types return JSON 400. | `test_invalid_file_json`, `test_malformed_json`, `test_utf8_byte_limit`; live validation |
| R17 | Maximum decoded text is 65,536 UTF-8 bytes inclusive; larger text returns 400. Requests above 512 KiB also return JSON 400. | `test_utf8_byte_limit`; live over-limit checks; `logs/additional-live-checks.log` exact ASCII/Unicode limits and request limit |
| R18 | Use boto3, S3 signature v4 and path-style addressing with RustFS. Create `lab4-files` if absent; handle concurrent creation; permission errors return 503. | `test_bucket_creation_and_race`, `test_bucket_permission_not_hidden`; live S3 HEAD/LIST |
| R19 | Store objects only in RustFS, backed by `lab4_s3-data`. Objects survive Flask restart and RustFS force recreation without volume deletion. | `logs/api-storage.log`: both persistence assertions |
| R20 | S3 connection, timeout, credentials, permission and other service errors return JSON 503 without exposing secrets. | `test_storage_outage`; live stopped-RustFS POST and GET 503 |
| R21 | POST `/counter/increment` executes exactly one Redis INCR on configured primary, returns JSON integer `value`, `source: primary`, 200. | `test_counter_routing`; live E1-E4 |
| R22 | GET `/counter` reads Redis GET from requested source; absent key means 0; default source is primary; invalid/empty/repeated `from` returns JSON 400. | `test_counter_routing`, `test_counter_invalid_source`; live validation |
| R23 | Redis host/port and key are environment configuration; redirect writes by restarting with `REDIS_PRIMARY_PORT=6380`, without code edits. | `test_environment_ports`; `logs/E4-manual-failover.log` |
| R24 | Redis errors, timeouts, read-only primary and invalid stored integer return JSON 503; no automatic write retry or fallback. | `test_redis_outages`, `test_redis_readonly_and_bad_integer`; live E4 primary failure and `logs/additional-live-checks.log` replica failure |
| R25 | Run 100 sequential INCR / primary GET / replica GET iterations and count stale reads. No WAIT is used in the experiment. | `logs/E1-normal.log` contains all 100 iterations |
| R26 | Detach replica, perform 10 API increments, compare values, restore and measure convergence. | `logs/E2-replica-behind.log` |
| R27 | Demonstrate reading own write on primary versus stale detached replica after three writes. | `logs/E3-read-own-write.log` |
| R28 | Stop primary, read replica, observe write 503, promote, redirect, write, restart old primary and record both roles and divergent values. | `logs/E4-manual-failover.log` |
| R29 | After experiments restore one master and one linked replica while preserving the promoted node's newest counter value. Never remove S3 volume. | E4 restoration commands and final replication INFO |
| R30 | Configuration is loaded from environment or `lab4/.env`, relative to `app.py`; explicit environment values override `.env`. Direct launch respects `FLASK_PORT` (default 5002). | Startup provenance log; `test_environment_ports`; E4 restarts |
| R31 | Distinguish isolated mock tests from live infrastructure evidence; retain timestamped raw experiment logs and measured results. | `logs/unit-tests.log`, `logs/results.json`, E1-E4 logs |

## 8. Lab 4 API contract

Base URL: `http://127.0.0.1:5002`. All documented responses are JSON with `Content-Type: application/json`. This is a local educational service. Unknown routes and unsupported methods use Flask's standard 404/405 handling; the JSON error contract concerns the routes below. JSON object fields beyond the required fields are ignored.

| Method and route | Input | Successful response | Error statuses |
| --- | --- | --- | --- |
| GET `/time` | None | 200 `{"server_time":"...","served_by":"..."}` | - |
| POST `/echo` | `{"message":"hello"}`; `message` may have any JSON value, as in Lab 3 | 200 `{"message":"hello"}` | 400 missing field or invalid JSON object |
| POST `/files` | `{"text":"Hello from Lab 4"}`; application/json | 201 `{"file_id":"<lowercase UUID>"}`; `Location: /files/<file_id>` | 400 invalid/oversized input; 503 storage error |
| GET `/files/<file_id>` | Lowercase UUID-shaped ID | 200 `{"file_id":"<id>","text":"Hello from Lab 4"}` | 400 invalid ID; 404 absent object key; 503 storage/bucket or decoding error |
| POST `/counter/increment` | No body required; body is ignored | 200 `{"value":1,"source":"primary"}` | 503 primary unavailable or write fails |
| GET `/counter?from=primary` | `from` absent or exactly `primary` | 200 `{"value":1,"source":"primary"}` | 400 invalid/repeated source; 503 Redis error |
| GET `/counter?from=replica` | Exactly `from=replica` | 200 `{"value":1,"source":"replica"}` | 400 invalid/repeated source; 503 Redis error |

Errors have `{"error":"<human-readable message>"}`. Examples: `{"error":"file not found"}` (404), `{"error":"object storage unavailable"}` (503), `{"error":"redis primary unavailable"}` (503). File payloads are decoded to UTF-8 in memory and streamed to/from S3 without writing user files to the Flask disk. An externally inserted oversized or invalid-UTF-8 object produces 503. A missing bucket or denied access is a storage failure, not a claim that a file key is absent.

## 9. Consistency and failure assumptions

Redis replication is asynchronous. A successful INCR acknowledges execution on the configured primary, not durable acknowledgement by every replica. Reading from the primary after the write provides read-your-writes in these sequential tests while that primary remains authoritative. A replica may return a stale value, including while disconnected. `source` labels the configured client connection; it is not a dynamic Redis ROLE lookup. During E4, both configured clients may temporarily point to the promoted node.

Compose starts `redis-primary` as master at host 6379 and `redis-replica` as its slave at host 6380. Both use Redis 7, AOF, and separate persistent volumes. The API never promotes nodes, redirects itself or writes to the replica client. A stopped primary causes writes to return 503. Recovery requires an operator to promote the replica and restart the API with the new endpoint. Restarting the old primary can produce two masters; Redis does not merge their independent writes. Fence writers before reconciling. The experiment copies the promoted node to the old primary as a replica before returning to the default topology. Runtime REPLICAOF changes do not replace Compose startup configuration.

The Flask development server is bound to loopback with debug/reloader disabled. This deployment is for laboratory use. Redis and S3 ports are bound to loopback. No production high-availability, quorum or zero-data-loss guarantee is asserted.

## 10. Environment and reproduction

| Variable | Default / required meaning |
| --- | --- |
| `FLASK_PORT` | `5002` for `python app.py`; Flask CLI uses `--port` or `FLASK_RUN_PORT` instead |
| `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY` | Required local educational credentials; used by Compose and boto3; no default in source |
| `S3_ENDPOINT_URL` | `http://127.0.0.1:9000` |
| `S3_BUCKET` | `lab4-files` |
| `S3_REGION` | `us-east-1` signing region |
| `REDIS_PRIMARY_HOST`, `REDIS_PRIMARY_PORT` | `127.0.0.1`, `6379` |
| `REDIS_REPLICA_HOST`, `REDIS_REPLICA_PORT` | `127.0.0.1`, `6380` |
| `REDIS_COUNTER_KEY` | `lab4:counter`; database 0 |

The runner uses the standard topology and fixed host ports 5002/6379/6380 for reproducible E1-E4, while the API itself supports configurable Redis ports. See `README.md` for setup, isolated tests, full live experiments, log locations, screenshot provenance and safe restoration. Re-running the experiments increments existing data and replaces experiment logs; archive the previous evidence first.
