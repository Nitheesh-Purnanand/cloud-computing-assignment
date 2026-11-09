#!/usr/bin/env bash
# Task 3: with FAULT_INJECT=1 the service must answer HTTP 500 {"error": "invalid_model_output"}.
set -uo pipefail
cd "$(dirname "$0")/.."
ask() { curl -si -m 30 -X POST localhost:8080/parse -H 'Content-Type: application/json' \
          -d '{"text":"what is the weather in london"}' | grep -E '^HTTP|^X-|^\{'; }
roll() {  # change FAULT_INJECT and wait until only new Pods remain
  old=$(kubectl -n app get pods -l app=parser -o name)
  kubectl -n app set env deploy/parser FAULT_INJECT="$1" >/dev/null
  sleep 3
  kubectl -n app rollout status deploy/parser --timeout=300s >/dev/null
  [ -n "$old" ] && kubectl -n app wait --for=delete $old --timeout=120s >/dev/null 2>&1
}
roll 1
echo "--- FAULT_INJECT=1 on $(kubectl -n app get pods -l app=parser -o name)"; ask; ask
roll 0
echo "--- FAULT_INJECT=0 on $(kubectl -n app get pods -l app=parser -o name)"; ask
echo "--- probes:"
for p in healthz readyz; do
  kubectl -n app exec deploy/parser -- python -c "import urllib.request as u; r=u.urlopen('http://localhost:8000/$p'); print('$p', r.status, r.read().decode())"
done
