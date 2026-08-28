#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
#  OpenCHAI GUI — Start Script  (v3)
#
#  Fix vs v2: CHAI_VERIFY_SSL and OPENCHAI_VAULT_NETWORK_URL were exported
#  AFTER the exec call so they were never seen by the backend process.
#  They are now set at the top with all other env vars.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"

# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight: System dependencies + JWT setup (RHEL-based safe bootstrap)
# ─────────────────────────────────────────────────────────────────────────────

# Detect OS (RHEL vs Debian)
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=$ID
else
    OS_ID=""
fi

# ── Install PAM dev headers (required for python-pam) ─────────────────────────
install_pam_dev() {
    if command -v dnf &>/dev/null; then
        if ! rpm -q pam-devel &>/dev/null; then
            echo "[openchai] Installing pam-devel..."
            dnf install -y pam-devel
        fi
    elif command -v apt &>/dev/null; then
        if ! dpkg -l | grep -q libpam0g-dev; then
            echo "[openchai] Installing libpam0g-dev..."
            apt update -y && apt install -y libpam0g-dev
        fi
    else
        echo "[openchai] WARN: Could not detect package manager for PAM dev install"
    fi
}

install_pam_dev

# ── Ensure persistent JWT secret ──────────────────────────────────────────────
if [ -z "${JWT_SECRET_KEY:-}" ]; then
    echo "[openchai] Generating persistent JWT secret..."
    export JWT_SECRET_KEY="$(openssl rand -hex 64)"
fi

# ── Default admin groups (only if not already set) ────────────────────────────
# Portal access is restricted to openchai-admins ONLY — wheel/sudo membership
# does NOT grant GUI access. root logs in via the OPENCHAI_ALLOW_ROOT bypass
# below, independent of group membership.
export OPENCHAI_ADMIN_GROUPS="${OPENCHAI_ADMIN_GROUPS:-openchai-admins}"
export OPENCHAI_ALLOW_ROOT="${OPENCHAI_ALLOW_ROOT:-true}"

# ── Optional: create admin group if missing (non-fatal) ───────────────────────
if ! getent group openchai-admins >/dev/null 2>&1; then
    echo "[openchai] Creating group: openchai-admins"
    groupadd openchai-admins || true
fi

# ── Registry / SSL ────────────────────────────────────────────────────────────
export OPENCHAI_VAULT_NETWORK_URL="${OPENCHAI_VAULT_NETWORK_URL:-https://hpcsangrah-test.pune.cdac.in/vault/OpenCHAI/hpcsuite_registry/}"
export CHAI_VERIFY_SSL="${CHAI_VERIFY_SSL:-false}"

# ── Paths ─────────────────────────────────────────────────────────────────────
export OPENCHAI_ROOT="${OPENCHAI_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
export ANSIBLE_DIR="${ANSIBLE_DIR:-${OPENCHAI_ROOT}/automation/ansible}"
export INVENTORY_PATH="${INVENTORY_PATH:-${ANSIBLE_DIR}/inventory/hosts.ini}"
export GROUP_VARS_DIR="${GROUP_VARS_DIR:-${ANSIBLE_DIR}/group_vars}"
export PLAYBOOK_LIBRARY="${PLAYBOOK_LIBRARY:-${ANSIBLE_DIR}/playbook_library}"
export ANSIBLE_CFG="${ANSIBLE_CFG:-${ANSIBLE_DIR}/ansible.cfg}"

# ── Cluster Setup Wizard ───────────────────────────────────────────────────────
# Points to $OPENCHAI_ROOT/cluster_setup/ which contains:
#   ha_server_setup/  →  headnode/  hpc_master/  hpc_management/  hpc_login/  bmcnode/
#   single_server/    →  single-master-node.yml
export CLUSTER_SETUP_DIR="${CLUSTER_SETUP_DIR:-${OPENCHAI_ROOT}/cluster_setup}"

# ── Authentication ───────────────────────────────────────────────────────────
# JWT_SECRET_KEY: MUST be set to a stable secret for persistent sessions.
# Generate one: openssl rand -hex 64
# If unset, a new random key is generated each restart (invalidates all tokens).
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"
export ACCESS_TOKEN_EXPIRE_MINUTES="${ACCESS_TOKEN_EXPIRE_MINUTES:-480}"
# Linux group that grants admin role in the GUI (comma-separated; default
# restricts to openchai-admins only — wheel/sudo do NOT count)
export OPENCHAI_ADMIN_GROUPS="${OPENCHAI_ADMIN_GROUPS:-openchai-admins}"
# root always allowed in regardless of group membership (set false to disable)
export OPENCHAI_ALLOW_ROOT="${OPENCHAI_ALLOW_ROOT:-true}"

# ── SSH ───────────────────────────────────────────────────────────────────────
export ANSIBLE_USER="${ANSIBLE_USER:-root}"
export ANSIBLE_PRIVATE_KEY="${ANSIBLE_PRIVATE_KEY:-${HOME}/.ssh/id_rsa}"

# ── Server ────────────────────────────────────────────────────────────────────
export OPENCHAI_HOST="${OPENCHAI_HOST:-0.0.0.0}"
export OPENCHAI_PORT="${OPENCHAI_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
MODE="${1:-dev}"

# =============================================================================
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[openchai]${NC} $*"; }
warn()    { echo -e "${YELLOW}[openchai]${NC} $*"; }
error()   { echo -e "${RED}[openchai]${NC} $*" >&2; }
section() { echo -e "\n${CYAN}── $* ──${NC}"; }
check_cmd() { command -v "$1" &>/dev/null || { error "$1 not found."; exit 1; }; }
free_port() {
    if lsof -i :"$1" &>/dev/null 2>&1; then
        warn "Port $1 in use — killing existing process"
        lsof -ti :"$1" | xargs -r kill -9; sleep 1
    fi
}

section "Configuration"
echo "  OPENCHAI_ROOT      = ${OPENCHAI_ROOT}"
echo "  ANSIBLE_DIR        = ${ANSIBLE_DIR}"
echo "  CLUSTER_SETUP_DIR  = ${CLUSTER_SETUP_DIR}
  PLAYBOOK_LIBRARY   = ${PLAYBOOK_LIBRARY}"
echo "  CHAI_VERIFY_SSL    = ${CHAI_VERIFY_SSL}"
echo "  BACKEND            = ${OPENCHAI_HOST}:${OPENCHAI_PORT}"
echo "  AUTH               = PAM (Linux system credentials)"
echo "  ADMIN_GROUPS       = ${OPENCHAI_ADMIN_GROUPS}"
echo "  ALLOW_ROOT         = ${OPENCHAI_ALLOW_ROOT}"
echo "  JWT_KEY_SET        = $([ -n "${JWT_SECRET_KEY}" ] && echo 'YES (persistent)' || echo 'NO (auto-generated, sessions lost on restart)')"
echo "  FRONTEND PORT      = ${FRONTEND_PORT}"
echo "  MODE               = ${MODE}"

section "Validation"
[[ -d "${BACKEND_DIR}" ]] || { error "Backend dir missing: ${BACKEND_DIR}"; exit 1; }
[[ -d "${FRONTEND_DIR}" ]] || warn "Frontend dir missing — UI will not start"

section "Backend Setup"
check_cmd python3
VENV="${BACKEND_DIR}/.venv"
[[ ! -d "${VENV}" ]] && { warn "Creating virtualenv…"; python3 -m venv "${VENV}"; }
# shellcheck source=/dev/null
source "${VENV}/bin/activate"
pip install --upgrade pip -q
pip install -r "${BACKEND_DIR}/requirements.txt" -q
UVICORN="${VENV}/bin/uvicorn"

if [[ "${MODE}" == "dev" ]]; then
    section "Frontend Setup"
    check_cmd node; check_cmd npm
    [[ ! -d "${FRONTEND_DIR}/node_modules" ]] && \
        { warn "Installing npm dependencies…"; (cd "${FRONTEND_DIR}" && npm install); }
    VITE_CMD="npx vite"
    command -v vite &>/dev/null && VITE_CMD="vite"
    free_port "${FRONTEND_PORT}"
    info "Starting frontend dev server on port ${FRONTEND_PORT}…"
    (cd "${FRONTEND_DIR}" && ${VITE_CMD} --host "${OPENCHAI_HOST}" --port "${FRONTEND_PORT}") &
    VITE_PID=$!
    info "Frontend PID: ${VITE_PID}"
    trap "info 'Stopping frontend…'; kill ${VITE_PID} 2>/dev/null || true" EXIT
fi

section "Backend Start"
free_port "${OPENCHAI_PORT}"
cd "${BACKEND_DIR}"
RELOAD_FLAG=""; [[ "${MODE}" == "dev" ]] && RELOAD_FLAG="--reload"
LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
info "Backend  → http://${LOCAL_IP}:${OPENCHAI_PORT}"
info "API docs → http://${LOCAL_IP}:${OPENCHAI_PORT}/docs"
[[ "${MODE}" == "dev" ]] && info "Frontend → http://${LOCAL_IP}:${FRONTEND_PORT}"

exec "${UVICORN}" app:app \
    --host "${OPENCHAI_HOST}" \
    --port "${OPENCHAI_PORT}" \
    --log-level "$(echo "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')" \
    ${RELOAD_FLAG}
