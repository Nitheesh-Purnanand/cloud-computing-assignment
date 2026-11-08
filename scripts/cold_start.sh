#!/usr/bin/env bash
# Task 4.7: delete all parser Pods three times; report creation -> Ready time of the NEW Pods,
# the model-download log lines, and the Service endpoints while the model is loading.
set -uo pipefail
cd "$(dirname "$0")/.."
times=()
for run in 1 2 3; do
  old=$(kubectl -n app get pods -l app=parser -o jsonpath='{.items[*].metadata.name}')
  echo "=== run $run: deleting all Pods ($old) at $(date -u +%T)"
  kubectl -n app delete pod -l app=parser --wait=false >/dev/null
  # poll ready endpoint addresses until a NEW Pod is listed
  new=""
  for i in $(seq 600); do
    ready=$(kubectl -n app get endpointslices -l kubernetes.io/service-name=parser \
      -o jsonpath='{range .items[*].endpoints[?(@.conditions.ready==true)]}{.targetRef.name} {end}')
    echo "$(date -u +%T.%N | cut -c1-12) ready endpoints: ${ready:-<none>}"
    new=$(for p in $ready; do [[ " $old " == *" $p "* ]] || echo "$p"; done)
    [ -n "$new" ] && break
    sleep 0.2
  done | awk '{ if ($0 != prev_body) print; prev_body=$0; sub(/^[^ ]+ /,"",prev_body) }'
  kubectl -n app wait --for=condition=Ready pod -l app=parser --timeout=300s >/dev/null 2>&1
  for p in $(kubectl -n app get pods -l app=parser -o jsonpath='{.items[*].metadata.name}'); do
    [[ " $old " == *" $p "* ]] && continue
    c=$(kubectl -n app get pod "$p" -o jsonpath='{.metadata.creationTimestamp}')
    r=$(kubectl -n app get pod "$p" -o jsonpath='{.status.conditions[?(@.type=="Ready")].lastTransitionTime}')
    s=$(( $(date -juf %Y-%m-%dT%H:%M:%SZ "$r" +%s) - $(date -juf %Y-%m-%dT%H:%M:%SZ "$c" +%s) ))
    echo "$p created $c ready $r -> ${s}s"
    kubectl -n app logs "$p" | grep -E 'downloaded model|loaded, ready'
    times+=("$s")
  done
  kubectl -n app wait --for=delete pod $old --timeout=120s >/dev/null 2>&1
done
echo "cold-start times (s): $(printf '%s\n' "${times[@]}" | sort -n | tr '\n' ' ')"
echo "median (s): $(printf '%s\n' "${times[@]}" | sort -n | awk '{a[NR]=$1} END {print (NR%2 ? a[(NR+1)/2] : (a[NR/2]+a[NR/2+1])/2)}')"
echo "note: Kubernetes timestamps have 1 s resolution."
