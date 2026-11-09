#!/usr/bin/env bash
# Task 4.6: under load, delete one Pod and show Kubernetes restores the replica count.
set -uo pipefail
cd "$(dirname "$0")/.."
kubectl -n app patch hpa parser -p '{"spec":{"minReplicas":2}}' >/dev/null
until [ "$(kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}')" = "2" ]; do sleep 2; done
LOADTEST_HEADERS_OUT=results/recovery_headers.json .venv/bin/locust -f tools/locustfile.py --headless --users 4 \
  --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/recovery --only-summary > results/recovery_locust.txt 2>&1 &
lp=$!
sleep 30
victim=$(kubectl -n app get pods -l app=parser -o jsonpath='{.items[0].metadata.name}')
echo "--- $(date -u +%T) deleting $victim"; kubectl -n app get pods -l app=parser
kubectl -n app delete pod "$victim" --wait=false
for i in $(seq 30); do
  echo "$(date -u +%T) desired=$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}') ready=$(kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}')"
  sleep 2
done | awk '!seen[substr($0,10)]++'
echo "--- $(date -u +%T) after recovery"; kubectl -n app get pods -l app=parser
wait $lp
echo "--- locust summary"; grep -E 'Aggregated|POST|HTTP' results/recovery_locust.txt | head -6
kubectl -n app patch hpa parser -p '{"spec":{"minReplicas":1}}' >/dev/null
