#!/bin/bash

set -e

########################################
# Logging Functions
########################################
info()    { echo -e "\e[34m[INFO]\e[0m $1"; }
warn()    { echo -e "\e[33m[WARN]\e[0m $1"; }
notice()  { echo -e "\e[32m[SUCCESS]\e[0m $1"; }
error_exit() { echo -e "\e[31m[ERROR]\e[0m $1"; exit 1; }

echo "========== OpenCHAI GUI Setup Starting =========="

# Detect project root dynamically
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

info "Project Root: $PROJECT_ROOT"

########################################
# Ansible Installation Check
########################################
info "Checking for Ansible installation..."

if ! command -v ansible >/dev/null 2>&1; then
    warn "Ansible not found. Installing..."

    PKG_MGR=$(command -v dnf || command -v yum || true)
    [[ -z "$PKG_MGR" ]] && error_exit "No supported package manager found."

    sudo $PKG_MGR -y install epel-release || true
    sudo $PKG_MGR -y install ansible-core ansible || error_exit "Failed to install Ansible."

    notice "Ansible installed successfully."
else
    notice "Ansible is already installed."
fi

########################################
# Backend Setup (Python Virtual Env)
########################################
info "Setting up Backend..."

cd "$BACKEND_DIR" || error_exit "Backend directory not found!"

# Remove broken venv (fix for moved directories)
if [ -d ".venv" ]; then
    warn "Removing existing virtual environment..."
    rm -rf .venv
fi

info "Creating virtual environment..."
python3 -m venv .venv

info "Activating virtual environment..."
source .venv/bin/activate

info "Upgrading pip..."
pip install --upgrade pip

info "Installing Python dependencies..."
pip install -r requirements.txt

########################################
# Frontend Setup (Node.js)
########################################
info "Setting up Frontend..."

if ! command -v node >/dev/null 2>&1; then
    warn "Node.js not found. Installing..."
    sudo dnf install -y nodejs || error_exit "Failed to install Node.js"
else
    notice "Node.js already installed: $(node -v)"
fi

cd "$FRONTEND_DIR" || error_exit "Frontend directory not found!"

info "Installing frontend dependencies..."
npm install

########################################
# Additional Markdown Rendering Packages
########################################
info "Installing Markdown rendering packages..."

npm install -D @tailwindcss/typography
npm install react-markdown remark-gfm

########################################
# Start Frontend (Dev Mode)
########################################
#info "Starting frontend (dev mode)..."
#npm run dev &

########################################
# Final Output
########################################
echo "========================================="
notice "Setup Completed Successfully!"
echo ""
echo "To activate backend later:"
echo "source backend/.venv/bin/activate"
echo ""
echo "Frontend running on: http://localhost:5173 (or similar)"
echo "========================================="
