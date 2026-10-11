#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
export PATH="$ROOT/.local/bin:$PATH"
export KUBECONFIG="$ROOT/.local/kubeconfig"
CLUSTER=${LAB_CLUSTER:-cloudlab}
PROJECT=${LAB_PROJECT:-cloudlab}
COMPOSE_PORT=${LAB_COMPOSE_PORT:-8090}
KIND_PORT=${LAB_KIND_PORT:-8080}
mkdir -p .local/bin results/tests
compose() { docker compose -p "$PROJECT" --env-file "$ROOT/.env" -f "$ROOT/docker/compose.yaml" "$@"; }
k() { kubectl --kubeconfig "$KUBECONFIG" "$@"; }
wait_http() {
  local url=$1
  for ((i=0;i<90;i++)); do
    if curl --noproxy '*' -fsS --max-time 2 "$url/api/messages?limit=1" >/dev/null 2>&1; then return; fi
    sleep 1
  done
  echo "Public endpoint did not become ready: $url" >&2; return 1
}
bootstrap() {
  for tool in docker curl python3; do command -v "$tool" >/dev/null || { echo "Missing $tool"; return 1; }; done
  docker info >/dev/null
  if ! command -v kubectl >/dev/null; then
    curl -fL --retry 3 https://dl.k8s.io/release/v1.36.1/bin/linux/amd64/kubectl -o .local/bin/kubectl
    curl -fL --retry 3 https://dl.k8s.io/release/v1.36.1/bin/linux/amd64/kubectl.sha256 -o .local/kubectl.sha256
    printf '%s  %s\n' "$(cat .local/kubectl.sha256)" .local/bin/kubectl | sha256sum -c -
    chmod +x .local/bin/kubectl
  fi
  if [[ ! -x .local/bin/kind ]]; then
    curl -fL --retry 3 https://kind.sigs.k8s.io/dl/v0.33.0/kind-linux-amd64 -o .local/bin/kind
    printf '%s  %s\n' aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d .local/bin/kind | sha256sum -c -
    chmod +x .local/bin/kind
  fi
  kind version
  kubectl version --client
  python3 scripts/configure.py
}
build() { compose build; }
compose_up() {
  python3 scripts/configure.py
  compose up -d --scale api="${1:-3}" --wait --wait-timeout 120
  wait_http "http://127.0.0.1:$COMPOSE_PORT"
}
k8s_up() {
  python3 scripts/configure.py
  if ! kind get clusters | grep -qx "$CLUSTER"; then
    python3 -c 'from pathlib import Path; import sys; Path(".local/kind.yaml").write_text(Path("k8s/kind.yaml").read_text().replace("hostPort: 8080", "hostPort: " + sys.argv[1]))' "$KIND_PORT"
    kind create cluster --name "$CLUSTER" --config .local/kind.yaml --kubeconfig "$KUBECONFIG" --wait 120s
  elif [[ ! -f "$KUBECONFIG" ]]; then
    kind export kubeconfig --name "$CLUSTER" --kubeconfig "$KUBECONFIG"
  fi
  kind load docker-image cloudlab-api:1.0 cloudlab-web:1.0 --name "$CLUSTER"
  # Redis is pinned to the same digest in Compose and K8s; loading avoids a second registry download.
  docker pull redis:7.4.5-alpine@sha256:bb186d083732f669da90be8b0f975a37812b15e913465bb14d845db72a4e3e08
  docker image tag redis:7.4.5-alpine@sha256:bb186d083732f669da90be8b0f975a37812b15e913465bb14d845db72a4e3e08 redis:7.4.5-alpine
  docker image save --platform linux/amd64 -o .local/redis-image.tar redis:7.4.5-alpine
  kind load image-archive .local/redis-image.tar --name "$CLUSTER"
  for node in "$CLUSTER-control-plane" "$CLUSTER-worker" "$CLUSTER-worker2"; do
    docker exec "$node" ctr -n k8s.io images tag --force docker.io/library/redis:7.4.5-alpine \
      docker.io/library/redis@sha256:0302cccee2b2043e61b497c8f4075467c5f7ba27a9f38be7e092634f2734baed >/dev/null
  done
  k apply -f k8s/base/namespace.yaml
  k -n cloudlab create secret generic cloudlab-secret --from-env-file=.local/redis.env --dry-run=client -o yaml | k apply -f -
  k apply -k k8s/base
  k -n cloudlab rollout restart statefulset/redis
  k -n cloudlab rollout status statefulset/redis --timeout=180s
  # Refresh existing Pods too: ConfigMap env and subPath files need a rollout on rerun.
  k -n cloudlab rollout restart deployment/api deployment/web
  k -n cloudlab rollout status deployment/api --timeout=180s
  k -n cloudlab rollout status deployment/web --timeout=180s
  python3 scripts/wait_api.py
  wait_http "http://127.0.0.1:$KIND_PORT"
}
tests() {
  docker image inspect cloudlab-api:1.0 >/dev/null 2>&1 || docker build -f docker/api.Dockerfile -t cloudlab-api:1.0 .
  docker build -f docker/test.Dockerfile -t cloudlab-tests:1.0 .
  docker network inspect cloudlab-tests >/dev/null 2>&1 || docker network create cloudlab-tests >/dev/null
  if ! docker container inspect cloudlab-test-redis >/dev/null 2>&1; then
    docker run -d --name cloudlab-test-redis --network cloudlab-tests --network-alias redis redis:7.4.5-alpine >/dev/null
  else
    docker start cloudlab-test-redis >/dev/null
  fi
  docker run --rm --network cloudlab-tests cloudlab-tests:1.0 pytest -q | tee results/tests/green.log
}
metrics() {
  python3 scripts/fetch_metrics.py
  kind load image-archive .local/metrics-image.tar --name "$CLUSTER"
  for node in "$CLUSTER-control-plane" "$CLUSTER-worker" "$CLUSTER-worker2"; do
    docker exec "$node" ctr -n k8s.io images tag --force registry.k8s.io/metrics-server/metrics-server:v0.9.0 \
      registry.k8s.io/metrics-server/metrics-server@sha256:25d291fde59974547bac6f07fa9d6cf6f5bedd1f19d60c893311c5e741e0a42f >/dev/null
  done
  k apply -f k8s/addons/metrics-server.yaml
  k -n kube-system rollout status deployment/metrics-server --timeout=180s
  k wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=90s
  for ((i=0;i<60;i++)); do
    if k get --raw /apis/metrics.k8s.io/v1beta1/nodes 2>/dev/null | python3 -c 'import json,sys; sys.exit(0 if len(json.load(sys.stdin)["items"]) == 3 else 1)' 2>/dev/null; then
      k top nodes
      return
    fi
    sleep 1
  done
  echo 'Metrics API did not report all three nodes.' >&2
  return 1
}
case "${1:-help}" in
  bootstrap) bootstrap;;
  configure) python3 scripts/configure.py;;
  build) build;;
  compose-up) compose_up "${2:-3}";;
  compose-down) compose down;; # Keep the named data volume.
  k8s-up) k8s_up;;
  metrics) metrics;;
  test) tests;;
  check) python3 scripts/check.py --url "http://127.0.0.1:$COMPOSE_PORT"; python3 scripts/check.py --url "http://127.0.0.1:$KIND_PORT";;
  status) compose ps; k get nodes -o wide; k -n cloudlab get deploy,sts,pods,svc,pvc,pdb -o wide;;
  *) echo 'Usage: bash scripts/lab.sh {bootstrap|configure|build|compose-up [replicas]|compose-down|k8s-up|metrics|test|check|status}';;
esac
