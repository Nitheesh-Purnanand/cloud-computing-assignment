#!/usr/bin/env bash
# Create S3 credentials once (stored in .env, which is git-ignored) and load them into
# Kubernetes Secrets. Nothing secret is ever written to the repository.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo "AWS_ACCESS_KEY_ID=$(openssl rand -hex 10)" > .env
  echo "AWS_SECRET_ACCESS_KEY=$(openssl rand -hex 20)" >> .env
  chmod 600 .env
fi
set -a; . ./.env; set +a
cfg=$(printf '{"identities":[{"name":"admin","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}' \
      "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY")
kubectl -n data create secret generic seaweedfs-s3-config --from-literal=s3.json="$cfg" \
  --dry-run=client -o yaml | kubectl apply -f -
for ns in pipeline app; do
  kubectl -n "$ns" create secret generic s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -
done
