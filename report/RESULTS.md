# Measured results (source for report/report.pdf)

All numbers below come from files in `results/`. Assumptions are marked as such.

## Task 1: labelling and cleaning (`results/clean_counts.json`)

| Input | (a) not JSON | (b) wrong keys | (c) bad intent | (d) slot not in command | Duplicates | Kept |
|---|---|---|---|---|---|---|
| 3,000 | 589 | 0 | 4 | 138 | 31 | 2,238 |

3,000 = 589 + 0 + 4 + 138 + 31 + 2,238. `datasets/v1/train.sha256` = `d0f4fc58…752d`, reproduced by
`python worker/clean.py --local datasets/teacher`. Almost all (a) rejects are a valid JSON object followed by an
explanatory note from the teacher.

Sharding: worker k of N takes lines n with n mod N = k (N = 2, Jobs `teacher-shard-0/1` in `pipeline`), so every
line belongs to exactly one shard; each worker writes only `datasets/teacher/shard-k.jsonl`, flushes every 25
records and resumes from what is stored after a restart. Check: 3,000 ids across both shards, 3,000 unique, equal
to the pool. Teacher: Ollama phi3.5 on the laptop (Metal), temperature 0, seed 42, `num_predict` 128.

## Task 2: evaluation on validation.jsonl (100 commands)

| Model | JSON validity | Intent | Date | Time | Place | Full frame |
|---|---|---|---|---|---|---|
| Teacher phi3.5 (`teacher_validation.json`) | 75.0 | 67.0 | 55.0 | 65.0 | 72.0 | 41.0 |
| Pythia-70M untrained (`pythia_base_validation.json`) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Student v1, served (`student_validation.json`) | 100.0 | 88.0 | 76.0 | 85.0 | 85.0 | 48.0 |
| Student v2 (`student_v2_validation.json`) | 100.0 | 83.0 | 74.0 | 85.0 | 81.0 | 40.0 |

v1: 1,500 examples, 8 epochs, lr 3e-4, batch 16, seed 42, max length 96 (`training/loss.csv`: 0.619 → 0.009).
v2: seed 43, 10 epochs (`training/loss_v2.csv`). The student beats the teacher mainly on JSON validity: it was
trained only on replies that passed cleaning, so it never learned to add notes after the JSON.

## Task 3: container under limits (`results/limits_test.txt`)

1 CPU / 1 GiB: 50/50 requests HTTP 200, no OOM kill, peak memory 576 MiB. Image 1.27 GB.
`FAULT_INJECT=1` → HTTP 500 `{"error":"invalid_model_output"}` (`results/fault_inject.txt`).

## Task 4: Kubernetes

| Test | Evidence | Result |
|---|---|---|
| Cold start ×3 | `cold_start.txt` | 2 s, 2 s, 2 s; median 2 s; no ready endpoints for ~2 s while loading; logs show `downloaded model v1 (8 files) from s3://models/v1/` |
| HPA 1→2→1 | `hpa_test.txt` | `SuccessfulRescale New size: 2` under load; back to 1 replica (cpu 0%) after load |
| Rolling update v1→v2 + undo | `rolling_update.txt`, `rolling_stats.csv` | 395 requests, 1 failure (0.25%); after undo all responses `X-Model-Version: v1` |
| Recovery | `recovery.txt` | Pod deleted, ready 1 → 2 in ~7 s; 192 requests, 0 failures |
| Load balancing | `loadtest_headers.json` | 112 / 112 requests (50% each) |

Limitation: single laptop, one k3d server + one agent container on the same Docker VM; no fault tolerance
across machines. metrics-server needs ~1 min before the HPA sees CPU (`FailedGetResourceMetric` at start).

## Task 7: performance, cost, SLO (`loadtest_stats.csv`, `loadtest_top_pods.txt`)

Standard command, 2 Ready replicas: 222 requests (CSV; Locust console 224), 0 failures (0%), p50 2,100 ms,
p95 2,500 ms, 1.87 req/s. Each Pod ~997 m CPU and 464–545 MiB during the run. Cold start median 2 s.

Cost (rate card; billed on limits, 2 replicas × 1 vCPU × 1 GiB):
hourly = 2 × (1 × 3.50 + 1 × 0.45) = 7.90 INR/h; requests/h = 1.8713 × 3,600 = 6,737;
cost per 1,000 requests = 7.90 / 6,737 × 1,000 = **1.17 INR**.

SLO: 99% of `/parse` requests return HTTP 200 within 30 s, window = one standard load-test run.
Error budget = 1% × 222 = 2.22 → 2 failed requests; used 0 (0% of budget).

| Concern | Evidence | Limitation | Improvement |
|---|---|---|---|
| Data and storage | 589/3,000 teacher replies rejected as invalid JSON | 20% of teacher work wasted; single-pod SeaweedFS, OOMKilled at 768 Mi during a 280 MB upload | Stop sequence or JSON mode for the teacher; replicated SeaweedFS with volume servers |
| Model quality | Full frame 48% (teacher 41%) | Slot boundaries learned from a noisy teacher (date 76%) | Better prompt / larger teacher, more cleaned data, slot-span post-check |
| Latency and throughput | p95 2,500 ms, 1.87 req/s | One request at a time per Pod; greedy generation on 1 CPU | Batch requests, ONNX/int8 quantisation, stop at first newline token |
| Resource utilisation | ~997 m CPU, ≤ 545 MiB per Pod | CPU-bound at the 1-core limit; memory only ~50% used | Lower memory limit to 768 Mi; scale on request rate instead of CPU |
| Reliability and recovery | 0.25% failures in rollout, recovery in ~7 s | Single node: a node loss takes everything down | Multi-node cluster, PodDisruptionBudget, anti-affinity |
| Security and cost | 1.17 INR / 1,000 requests; gitleaks: no leaks | Static S3 admin key shared by all namespaces | Per-namespace least-privilege S3 identities; scale to zero when idle |
