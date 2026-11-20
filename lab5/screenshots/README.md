# Screenshot provenance

The numbered JPG files are genuine browser screenshot API captures of the factual archived evidence pages in `logs/browser-evidence/`. Every page explicitly states that it is archived log evidence, not a live terminal or replay. The exact original JSONL/CSV sources are shown on the image. No terminal image, command result or measurement was fabricated.

| Image | Actual evidence |

| --- | --- |

| 01_replica_set.jpg | MongoDB replica set: one primary, two secondaries |

| 02_compose.jpg | Docker Compose services |

| 03_records.jpg | Real record creation and reading |

| 04_distribution.jpg | 30 requests through nginx |

| 05_api_down.jpg | api2 stopped for approximately 20 seconds |

| 06_load_10.jpg | Locust final result: 10 users, 60 seconds |

| 07_load_50.jpg | Locust final result: 50 users, 60 seconds |

| 08_load_100.jpg | Locust final result: 100 users, 60 seconds |

| 09_primary_down.jpg | Automatic MongoDB election and measured recovery |

| 10_final_roles.jpg | Restored MongoDB topology after all scenarios |

| 11_primary_crash.jpg | Supplement: abrupt primary crash and real HTTP 503 |

| 12_live_record.jpg | Live browser GET of the persistent control record directly from nginx; not an archived page |

Native Docker Desktop/Terminal capture was unavailable because computer-control permissions were not granted. Browser capture worked. The numbered archived screenshots remain explicitly identified, and the extra live API screenshot shows the real currently served record.



Open `logs/browser-evidence/index.html` locally to inspect the same source excerpts. If the instructor specifically requires native Terminal windows, capture the following read-only displays or perform a fresh documented experiment after archiving current results:

```bash
cd /Users/sofiyaserbina/Lab3_Docker_Kubernetes_Lab4/lab5
docker compose ps --all
docker compose exec mongo1 mongosh --quiet --eval "rs.status().members.map(m=>m.name+' '+m.stateStr)"
cat logs/distribution-baseline.json
cat logs/distribution-api2-down.json
tail -25 logs/locust_10.log
tail -25 logs/locust_50.log
tail -25 logs/locust_100.log
cat logs/probe_primary_down.txt
```

Archived logs displayed in a Terminal are still archived evidence. For a new live failure screenshot, follow README and archive the current run first. Do not substitute fresh values into the existing report without updating all related measurements.
