#!/usr/bin/env bash
# Task 3: run the service image with 1 CPU / 1 GiB, send 50 sequential requests, record peak memory.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
PORT=${PORT:-8001}
docker rm -f parser-limits >/dev/null 2>&1 || true
docker run -d --name parser-limits --cpus 1 --memory 1g -p "$PORT:8000" \
  -e MODEL_URI=s3://models/v1/ -e MODEL_VERSION=v1 -e S3_ENDPOINT=http://host.docker.internal:8333 \
  -e MAX_NEW_TOKENS=48 -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY ccproj-parser:latest >/dev/null
until curl -sf "localhost:$PORT/readyz" >/dev/null; do sleep 1; done
peak=0
( while docker inspect parser-limits >/dev/null 2>&1; do
    docker stats --no-stream --format '{{.MemUsage}}' parser-limits; sleep 0.5; done ) > results/limits_mem_samples.txt 2>/dev/null &
sampler=$!
ok=0; fail=0
head -50 data/validation.jsonl | while read -r line; do
  text=$(python3 -c 'import json,sys; print(json.dumps({"text": json.loads(sys.argv[1])["text"]}))' "$line")
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "localhost:$PORT/parse" -H 'Content-Type: application/json' -d "$text")
  echo "$code"
done | sort | uniq -c | sed 's/^/HTTP status count: /'
kill $sampler 2>/dev/null || true
echo "OOMKilled: $(docker inspect -f '{{.State.OOMKilled}}' parser-limits)  restarts: $(docker inspect -f '{{.RestartCount}}' parser-limits)"
echo "limits: $(docker inspect -f 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}' parser-limits)"
echo "peak memory sampled: $(sed 's# /.*##' results/limits_mem_samples.txt | sort -h | tail -1)"
docker logs parser-limits 2>&1 | grep -E 'downloaded model|loaded'
docker rm -f parser-limits >/dev/null
