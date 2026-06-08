#!/usr/bin/env bash
set -euo pipefail

WEBGYM_DIR="${WEBGYM_DIR:-/home/ubuntu/webgym}"
WEBGYM_PYTHON="${WEBGYM_PYTHON:-/home/ubuntu/miniconda3/envs/webgym/bin/python}"
EXPLORER_DIR="${EXPLORER_DIR:-/home/ubuntu/Explorer}"

API_BASE_URL="${API_BASE_URL:-https://api-int.memtensor.cn/v1}"
MODEL_NAME="${MODEL_NAME:-gpt-5.5}"
API_KEY_ENV_VAR="${API_KEY_ENV_VAR:-MEMTENSOR_API_KEY}"

TASK_DATA_DIR="${TASK_DATA_DIR:-${WEBGYM_DIR}/data_official_api}"
TASK_COUNT="${TASK_COUNT:-5}"
MAX_STEPS="${MAX_STEPS:-15}"
VLLM_TIMEOUT="${VLLM_TIMEOUT:-90}"
OPERATION_TIMEOUT="${OPERATION_TIMEOUT:-90}"
MAX_RETRIES="${MAX_RETRIES:-1}"
TASK_TIMEOUT_MINUTES="${TASK_TIMEOUT_MINUTES:-20}"
REMOTE_MAX_IMAGES="${REMOTE_MAX_IMAGES:-2}"
IMAGE_MAX_EDGE="${IMAGE_MAX_EDGE:-768}"
IMAGE_JPEG_QUALITY="${IMAGE_JPEG_QUALITY:-55}"
MASTER_HOST="${MASTER_HOST:-localhost}"
MASTER_PORT="${MASTER_PORT:-17000}"
OMNIBOX_API_KEY="${OMNIBOX_API_KEY:-default_key}"

RUN_ID="${RUN_ID:-webgym_official_$(date +%Y%m%d_%H%M%S)}"
SAVE_PATH="${SAVE_PATH:-${EXPLORER_DIR}/trajectories/${RUN_ID}}"

if [[ ! -d "${WEBGYM_DIR}" ]]; then
  echo "WebGym repo not found: ${WEBGYM_DIR}" >&2
  exit 1
fi

if [[ ! -x "${WEBGYM_PYTHON}" ]]; then
  echo "WebGym Python not found or not executable: ${WEBGYM_PYTHON}" >&2
  exit 1
fi

if [[ -z "${!API_KEY_ENV_VAR:-}" ]]; then
  echo "Missing API key env var: ${API_KEY_ENV_VAR}" >&2
  echo "Example: export ${API_KEY_ENV_VAR}=sk-..." >&2
  exit 1
fi

if [[ ! -f "${TASK_DATA_DIR}/test.jsonl" ]]; then
  echo "Missing WebGym task file: ${TASK_DATA_DIR}/test.jsonl" >&2
  exit 1
fi

if ! curl -fsS -H "x-api-key: ${OMNIBOX_API_KEY}" "http://${MASTER_HOST}:${MASTER_PORT}/info" >/dev/null; then
  echo "OmniBoxes master is not reachable at http://${MASTER_HOST}:${MASTER_PORT}" >&2
  echo "Start WebGym deployment first, then rerun this script." >&2
  exit 1
fi

mkdir -p "${SAVE_PATH}"

echo "Running WebGym official rollout"
echo "  model: ${MODEL_NAME}"
echo "  tasks: ${TASK_COUNT}"
echo "  max steps: ${MAX_STEPS}"
echo "  vLLM timeout: ${VLLM_TIMEOUT}s"
echo "  remote images: last ${REMOTE_MAX_IMAGES}, max edge ${IMAGE_MAX_EDGE}, jpeg quality ${IMAGE_JPEG_QUALITY}"
echo "  save path: ${SAVE_PATH}"

cd "${WEBGYM_DIR}"

WEBGYM_CHROMIUM_EXECUTABLE="${WEBGYM_CHROMIUM_EXECUTABLE:-/usr/bin/google-chrome-stable}" \
WEBGYM_POLICY_API_KEY_ENV_VAR="${API_KEY_ENV_VAR}" \
WEBGYM_REMOTE_MAX_IMAGES="${REMOTE_MAX_IMAGES}" \
WEBGYM_IMAGE_MAX_EDGE="${IMAGE_MAX_EDGE}" \
WEBGYM_IMAGE_JPEG_QUALITY="${IMAGE_JPEG_QUALITY}" \
WEBGYM_FORCE_JPEG_IMAGES="${WEBGYM_FORCE_JPEG_IMAGES:-true}" \
CPU_CLUSTER_TOKEN="${CPU_CLUSTER_TOKEN:-${OMNIBOX_API_KEY}}" \
"${WEBGYM_PYTHON}" scripts/rollout.py --config-name rollout_test \
  "save_path=${SAVE_PATH}" \
  "data_path=${TASK_DATA_DIR}" \
  "policy_config.base_model=${MODEL_NAME}" \
  "policy_config.max_new_tokens=800" \
  "policy_config.temperature=0" \
  "env_config.host_ip=${MASTER_HOST}" \
  "env_config.master_port=${MASTER_PORT}" \
  "env_config.vllm_server_url=${API_BASE_URL%/v1}" \
  "env_config.server_size=1" \
  "env_config.max_vllm_sessions=1" \
  "env_config.test_tasks_rollout_size=${TASK_COUNT}" \
  "env_config.test_difficulty_max_steps.easy=${MAX_STEPS}" \
  "env_config.test_difficulty_max_steps.medium=${MAX_STEPS}" \
  "env_config.test_difficulty_max_steps.hard=${MAX_STEPS}" \
  "env_config.vllm_timeout=${VLLM_TIMEOUT}" \
  "env_config.operation_timeout=${OPERATION_TIMEOUT}" \
  "env_config.max_retries=${MAX_RETRIES}" \
  "env_config.task_timeout_minutes=${TASK_TIMEOUT_MINUTES}" \
  "env_config.completion_threshold=1.0" \
  "env_config.save_traj_progress=false" \
  "env_config.http_pools.navigate=1" \
  "env_config.http_pools.screenshot=1" \
  "env_config.http_pools.ac_tree=0" \
  "env_config.http_pools.metadata=1" \
  "env_config.http_pools.page_metadata=1" \
  "env_config.http_pools.execute=1" \
  "env_config.http_pools.allocate=1" \
  "env_config.http_pools.release=1" \
  "openai_config.model=${MODEL_NAME}" \
  "openai_config.openai_api_key_env_var=${API_KEY_ENV_VAR}" \
  "openai_config.base_url=${API_BASE_URL}" \
  "openai_config.keypoint_detection.model=${MODEL_NAME}" \
  "+openai_config.keypoint_detection.openai_api_key_env_var=${API_KEY_ENV_VAR}" \
  "+openai_config.keypoint_detection.base_url=${API_BASE_URL}" \
  "openai_config.blocking_detection.model=${MODEL_NAME}" \
  "+openai_config.blocking_detection.openai_api_key_env_var=${API_KEY_ENV_VAR}" \
  "+openai_config.blocking_detection.base_url=${API_BASE_URL}" \
  "openai_config.evaluation.model=${MODEL_NAME}" \
  "+openai_config.evaluation.openai_api_key_env_var=${API_KEY_ENV_VAR}" \
  "+openai_config.evaluation.base_url=${API_BASE_URL}"

echo "Done: ${SAVE_PATH}"
