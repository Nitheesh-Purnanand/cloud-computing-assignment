#!/usr/bin/env bash
# Tasks 4.8 + 7: standard load test through the Ingress with exactly two Ready replicas,
# sampling `kubectl top pods` during the run. HPA minReplicas is pinned to 2 for the run, then restored.
set -uo pipefail
cd "$(dirname "$0")/.."
kubectl -n app patch hpa parser -p '{"spec":{"minReplicas":2}}' >/dev/null
kubectl -n app scale deploy/parser --replicas=2 >/dev/null
until [ "$(kubectl -n app get deploy parser -o jsonpath='{.status.readyReplicas}')" = "2" ]; do sleep 2; done
echo "--- Ready replicas before the run:"; kubectl -n app get pods -l app=parser -o wide
( sleep 20; for i in 1 2 3 4 5 6 7 8 9; do echo "--- kubectl top pods $(date -u +%T)"; kubectl -n app top pods; sleep 10; done ) > results/loadtest_top_pods.txt 2>&1 &
.venv/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
  --host http://localhost:8080 --csv results/loadtest 2>&1 | tail -25
wait
kubectl -n app patch hpa parser -p '{"spec":{"minReplicas":1}}' >/dev/null
