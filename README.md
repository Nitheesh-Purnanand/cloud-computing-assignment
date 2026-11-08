# Command parser: knowledge distillation + local cloud deployment

Phi-3.5-mini (teacher, via Ollama) labels 3,000 voice commands; Pythia-70M (student) is fine-tuned on
the cleaned teacher replies (sequence-level distillation) and served by a FastAPI service on a local
k3d (k3s) cluster, with model weights in SeaweedFS object storage.

## Prerequisites

Docker (Docker Desktop or Colima, ≥ 6 CPU / 8 GB), `k3d`, `kubectl`, `python3.11`, `make`.
Only for re-labelling or teacher evaluation: Ollama with `ollama pull phi3.5`.

## Build, deploy, test, tear down

```bash
git clone https://github.com/Nitheesh-Purnanand/cloud-computing-assignment.git
cd cloud-computing-assignment
make up          # venv, k3d cluster, SeaweedFS + buckets, image, models v1/v2 into S3, deploy
```

```bash
curl -si -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{"text":"wake me at six am tomorrow"}'
make test        # unit tests
make lint
make loadtest    # standard Locust command against http://localhost:8080
make down        # delete the cluster
```

`make up` takes the model from `artifacts/` if you trained it locally, otherwise from the GitHub Release
(`model-v1`, `model-v2`). S3 credentials are generated into `.env` (git-ignored) and loaded into
Kubernetes Secrets by `scripts/secrets.sh`; nothing secret is in the repository.

## Pipeline

| Step | Command | Output |
|---|---|---|
| Teacher labelling (2 shard workers in `pipeline`) | `make label` | `s3://datasets/teacher/shard-{0,1}.jsonl` |
| Cleaning | `make clean-data` (or `python worker/clean.py --local datasets/teacher`) | `datasets/v1/train.jsonl`, `train.sha256`, `results/clean_counts.json` |
| Training | `make train` / `make train SUBSET=50` / `make train CONFIG=training/config_v2.yaml` | `artifacts/v1/`, `training/loss.csv` |
| Publish model | `make publish-model VERSION=v1` | `s3://models/v1/` + `model.sha256` |
| Evaluate | `make eval MODEL=artifacts/v1 NAME=student` | `results/student_validation.json` |
| Release assets | `make release` (needs `gh auth login` and a pushed repo) | GitHub Releases `model-v1`, `model-v2` |

## Layout

```
cluster/k3d.yaml          k3d cluster (1 server, 1 agent; :8080 -> ingress, :8333 -> S3)
k8s/                      namespaces, SeaweedFS, labelling Jobs, app (Deployment/Service/Ingress/HPA)
prompts/teacher_prompt.txt
worker/                   worker.py (sharded labelling), clean.py, Dockerfile
training/                 config.yaml, config_v2.yaml, train.py, predict.py, loss.csv
service/                  app.py, Dockerfile, requirements.txt (fully pinned)
network/                  subnets.md, nacl.json
tests/                    unit tests (pytest)
results/                  score reports, raw outputs, logs, load-test files
tools/, data/             course kit (unchanged)
```
