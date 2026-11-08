#!/usr/bin/env bash
# Task 4.5: under load, roll MODEL_VERSION/MODEL_URI v1 -> v2, then `kubectl rollout undo` back to v1.
set -uo pipefail
cd "$(dirname "$0")/.."
kubectl -n app patch hpa parser -p '{"spec":{"minReplicas":2}}' >/dev/null
until [ "$(kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}')" = "2" ]; do sleep 2; done
LOADTEST_HEADERS_OUT=results/rolling_headers.json .venv/bin/locust -f tools/locustfile.py --headless --users 4 \
  --spawn-rate 4 --run-time 4m --host http://localhost:8080 --csv results/rolling --only-summary > results/rolling_locust.txt 2>&1 &
locust_pid=$!
sleep 30
echo "--- $(date -u +%T) update to v2"
kubectl -n app set env deploy/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2/
kubectl -n app rollout status deploy/parser --timeout=300s
for i in 1 2 3; do curl -s -o /dev/null -D - -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{"text":"what is the weather in london"}' | grep -i x-model-version; done
sleep 45
echo "--- $(date -u +%T) rollout undo"
kubectl -n app rollout undo deploy/parser
kubectl -n app rollout status deploy/parser --timeout=300s
kubectl -n app rollout history deploy/parser
wait $locust_pid
echo "--- after rollback:"
for i in 1 2 3 4; do curl -s -o /dev/null -D - -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{"text":"what is the weather in london"}' | grep -iE 'x-model-version|x-served-by' | tr '\r\n' '  '; echo; done
kubectl -n app get deploy parser -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}'
echo "--- locust summary"; tail -22 results/rolling_locust.txt
kubectl -n app patch hpa parser -p '{"spec":{"minReplicas":1}}' >/dev/null
