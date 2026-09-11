#!/usr/bin/env bash
set -euo pipefail

readonly CLUSTER_NAME="${ARGUS_KIND_CLUSTER:-argus-learning}"
readonly CONTEXT_NAME="kind-${CLUSTER_NAME}"
readonly NAMESPACE="argus"
readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OVERLAY_DIR="${ROOT_DIR}/infra/k8s/overlays/kind"

require_tool() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required tool is missing: $1" >&2
    exit 1
  }
}

require_context() {
  local current_context
  current_context="$(kubectl config current-context)"
  if [[ "${current_context}" != "${CONTEXT_NAME}" ]]; then
    echo "Refusing to continue: kubectl context is ${current_context}, expected ${CONTEXT_NAME}." >&2
    exit 1
  fi
}

ensure_cluster() {
  if ! kind get clusters 2>/dev/null | grep -Fxq "${CLUSTER_NAME}"; then
    kind create cluster --name "${CLUSTER_NAME}" --wait 120s
  fi
  kubectl config use-context "${CONTEXT_NAME}" >/dev/null
  require_context
}

image_tag() {
  printf '%s-kind' "$(git -C "${ROOT_DIR}" rev-parse --short=12 HEAD)"
}

build_and_load_images() {
  local tag
  tag="$(image_tag)"
  if [[ "${ARGUS_KIND_SKIP_BUILD:-false}" != "true" ]]; then
    docker build \
      --platform linux/arm64 \
      --tag "argus-backend:${tag}" \
      "${ROOT_DIR}"
    docker build \
      --platform linux/arm64 \
      --file "${ROOT_DIR}/frontend/Dockerfile.prod" \
      --tag "argus-frontend:${tag}" \
      "${ROOT_DIR}/frontend"
  fi
  docker image inspect "argus-backend:${tag}" >/dev/null
  docker image inspect "argus-frontend:${tag}" >/dev/null
  kind load docker-image \
    "argus-backend:${tag}" \
    "argus-frontend:${tag}" \
    --name "${CLUSTER_NAME}"
}

ensure_runtime_secrets() {
  local password database_url
  kubectl apply -f "${ROOT_DIR}/infra/k8s/base/namespace.yaml" >/dev/null
  if ! kubectl -n "${NAMESPACE}" get secret argus-local-infra >/dev/null 2>&1; then
    password="$(openssl rand -hex 24)"
    kubectl -n "${NAMESPACE}" create secret generic argus-local-infra \
      --from-literal="POSTGRES_PASSWORD=${password}" \
      --dry-run=client \
      -o yaml | kubectl apply -f - >/dev/null
  fi
  password="$(
    kubectl -n "${NAMESPACE}" get secret argus-local-infra \
      -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 --decode
  )"
  database_url="postgresql+psycopg://argus:${password}@argus-postgres:5432/argus"
  kubectl -n "${NAMESPACE}" create secret generic argus-secrets \
    --from-literal="ARGUS_DATABASE_URL=${database_url}" \
    --dry-run=client \
    -o yaml | kubectl apply -f - >/dev/null
  unset password database_url
}

render_overlay() {
  local tag
  tag="$(image_tag)"
  kubectl kustomize "${OVERLAY_DIR}" | sed "s/KIND_IMAGE_TAG/${tag}/g"
}

deploy() {
  ensure_cluster
  build_and_load_images
  ensure_runtime_secrets
  kubectl -n "${NAMESPACE}" apply -f "${OVERLAY_DIR}/local-infra.yaml"
  kubectl -n "${NAMESPACE}" wait \
    --for=condition=available \
    deployment/argus-postgres \
    deployment/argus-redis \
    deployment/argus-kafka \
    --timeout=240s
  kubectl -n "${NAMESPACE}" delete job argus-kafka-topic-bootstrap \
    --ignore-not-found \
    --wait=true >/dev/null
  render_overlay | kubectl apply -f -
  kubectl -n "${NAMESPACE}" wait \
    --for=condition=complete \
    job/argus-kafka-topic-bootstrap \
    --timeout=180s
  kubectl -n "${NAMESPACE}" rollout status deployment/argus-api --timeout=240s
  kubectl -n "${NAMESPACE}" rollout status deployment/argus-frontend --timeout=180s
  kubectl -n "${NAMESPACE}" rollout status deployment/argus-worker --timeout=180s
  kubectl -n "${NAMESPACE}" rollout status deployment/argus-event-consumer --timeout=180s
}

accept() {
  require_context
  kubectl -n "${NAMESPACE}" exec deployment/argus-api -c api -- \
    argus-verify-migration
  kubectl -n "${NAMESPACE}" exec deployment/argus-api -c api -- \
    python /app/scripts/kafka_local_acceptance.py \
      --bootstrap argus-kafka:9092 \
      --api-base http://localhost:8000
  kubectl -n "${NAMESPACE}" exec deployment/argus-kafka -c kafka -- \
    /opt/kafka/bin/kafka-consumer-groups.sh \
      --bootstrap-server localhost:9092 \
      --describe \
      --group argus-audit-metrics-v1
}

status() {
  require_context
  kubectl -n "${NAMESPACE}" get deployments
  kubectl -n "${NAMESPACE}" get pods
  kubectl -n "${NAMESPACE}" get jobs
  kubectl -n "${NAMESPACE}" get services
}

destroy() {
  if kind get clusters 2>/dev/null | grep -Fxq "${CLUSTER_NAME}"; then
    kind delete cluster --name "${CLUSTER_NAME}"
  else
    echo "Cluster ${CLUSTER_NAME} does not exist; nothing to delete."
  fi
}

usage() {
  echo "Usage: $0 {deploy|accept|status|destroy}" >&2
  exit 2
}

main() {
  require_tool docker
  require_tool kind
  require_tool kubectl
  require_tool openssl
  require_tool grep
  require_tool sed
  case "${1:-}" in
    deploy) deploy ;;
    accept) accept ;;
    status) status ;;
    destroy) destroy ;;
    *) usage ;;
  esac
}

main "$@"
