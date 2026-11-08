#!/usr/bin/env bash
# Task 4.4: start at 1 replica, apply load, show the HPA scaling 1 -> 2 and back to 1.
set -uo pipefail
cd "$(dirname "$0")/.."
kubectl -n app scale deploy/parser --replicas=1 >/dev/null
kubectl -n app wait --for=condition=Ready pod -l app=parser --timeout=120s >/dev/null
( while true; do echo "$(date -u +%T) cpu=$(kubectl -n app get hpa parser -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')% desired=$(kubectl -n app get hpa parser -o jsonpath='{.status.desiredReplicas}') ready=$(kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}')"; sleep 10; done ) &
watcher=$!
echo "--- load start $(date -u +%T)"
LOADTEST_HEADERS_OUT=results/hpa_headers.json .venv/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 \
  --run-time 4m --host http://localhost:8080 --csv results/hpa --only-summary 2>&1 | tail -6
echo "--- load stop $(date -u +%T); waiting for scale-down"
for i in $(seq 60); do
  [ "$(kubectl -n app get deploy parser -o jsonpath='{.spec.replicas}')" = "1" ] && break; sleep 10
done
sleep 10; kill $watcher
echo "--- HPA events"; kubectl -n app describe hpa parser | sed -n '/Events:/,$p'
