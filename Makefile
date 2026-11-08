# Fresh clone:  git clone <repo> && cd cloud-computing-assignment && make up
# Needs: docker, k3d, kubectl, python3.11 (and ollama + phi3.5 only for `make label` / teacher eval).
SHELL := /bin/bash
PY ?= python3.11
VENV := .venv
BIN := $(VENV)/bin
CLUSTER := ccproj
IMAGE := ccproj-parser:latest
REPO ?= Nitheesh-Purnanand/cloud-computing-assignment
RELEASE_TAG ?= model-v1
SUBSET ?= 0
CONFIG ?= training/config.yaml
VERSION ?= v1
S3ENV = set -a; . ./.env; set +a; export S3_ENDPOINT=http://localhost:8333;

.PHONY: up down venv cluster storage label clean-data train publish-model models image deploy \
        test lint eval loadtest release

up: venv cluster storage image models deploy   ## build and deploy everything
	@echo "Ready: curl -s -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{\"text\":\"wake me at six am\"}'"

down:
	k3d cluster delete $(CLUSTER)

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements-train.txt
venv: $(BIN)/python

cluster:
	k3d cluster list $(CLUSTER) >/dev/null 2>&1 || k3d cluster create --config cluster/k3d.yaml
	kubectl apply -f k8s/00-namespaces.yaml

storage: venv
	./scripts/secrets.sh
	kubectl apply -f k8s/10-seaweedfs.yaml
	kubectl -n data rollout status deploy/seaweedfs --timeout=300s
	until $(S3ENV) $(BIN)/python scripts/s3_setup.py; do sleep 3; done

# Task 1: parallel teacher labelling in the cluster, then cleaning (hours on CPU; Ollama runs on the host).
label: storage
	docker build -t ccproj-worker:v1 -f worker/Dockerfile .
	k3d image import ccproj-worker:v1 -c $(CLUSTER)
	kubectl apply -f k8s/20-workers.yaml
	kubectl -n pipeline wait --for=condition=complete job --all --timeout=24h
	$(MAKE) clean-data

clean-data:
	$(S3ENV) $(BIN)/python worker/clean.py
	$(S3ENV) $(BIN)/python -c "import sys; sys.path.insert(0,'worker'); from common import s3; c=s3(); \
	  [c.download_file('datasets', k, 'datasets/'+k) for k in ('v1/train.jsonl','v1/train.sha256','teacher/shard-0.jsonl','teacher/shard-1.jsonl')]"

# Task 2: `make train` or `make train SUBSET=50`; reads only $(CONFIG).
train: venv
	$(BIN)/python training/train.py --config $(CONFIG) $(if $(filter-out 0,$(SUBSET)),--subset $(SUBSET))

publish-model: venv
	$(S3ENV) $(BIN)/python scripts/publish_model.py $(VERSION)

# Put v1 and v2 into object storage: from local artifacts if present, else from the GitHub Release.
models: venv
	for v in v1 v2; do \
	  if [ -f artifacts/$$v/model.safetensors ]; then $(MAKE) publish-model VERSION=$$v; \
	  else mkdir -p artifacts && curl -fsSL -o artifacts/model-$$v.tar.gz \
	    https://github.com/$(REPO)/releases/download/model-$$v/model-$$v.tar.gz && \
	    ($(S3ENV) $(BIN)/python scripts/publish_model.py $$v --from-tar artifacts/model-$$v.tar.gz); fi; \
	done

image:
	docker build -t $(IMAGE) -f service/Dockerfile .
	k3d image import $(IMAGE) -c $(CLUSTER)

deploy:
	kubectl apply -f k8s/30-app.yaml
	kubectl -n app rollout status deploy/parser --timeout=600s

test: venv
	SCHEMA_FILE=data/schema.json $(BIN)/python -m pytest -q tests

lint: venv
	$(BIN)/ruff check worker service training tests scripts

eval: venv   ## score a local model dir: make eval MODEL=artifacts/v1 NAME=student
	$(BIN)/python training/predict.py $(MODEL) data/validation.jsonl results/$(NAME)_predictions.jsonl
	$(BIN)/python tools/score.py results/$(NAME)_predictions.jsonl data/validation.jsonl --out results/$(NAME)_validation.json

loadtest: venv
	$(BIN)/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
	  --host http://localhost:8080 --csv results/loadtest

release:   ## publish model tarballs as GitHub Release assets (needs gh auth and a pushed repo)
	for v in v1 v2; do gh release create model-$$v artifacts/model-$$v.tar.gz artifacts/model-$$v.sha256 \
	  --repo $(REPO) --title "Model $$v" --notes "Pythia-70M student $$v; sha256 in model-$$v.sha256"; done
