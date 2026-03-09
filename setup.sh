#!/usr/bin/env bash
# ============================================================================
# OCP Policy Hub — One-command setup
#
# Usage:
#   ./setup.sh          # Standard install
#   ./setup.sh --dev    # Include development dependencies (pytest, ruff)
#
# This script:
#   1. Checks for Python 3.11+
#   2. Creates a virtual environment (.venv)
#   3. Installs the project and its dependencies
#   4. Copies config/example.env → .env (if .env doesn't exist)
#   5. Tells you how to run the agent
# ============================================================================

set -e

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BOLD='' NC=''
fi

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

# --------------------------------------------------------------------------
# 1. Find Python 3.11+
# --------------------------------------------------------------------------
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        minor=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ] 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.11+ is required but not found."
    echo "  Install Python from: https://www.python.org/downloads/"
    exit 1
fi

info "Found Python $version ($PYTHON)"

# --------------------------------------------------------------------------
# 2. Create virtual environment
# --------------------------------------------------------------------------
VENV_DIR=".venv"

if [ -d "$VENV_DIR" ]; then
    info "Virtual environment already exists ($VENV_DIR)"
else
    echo -n "Creating virtual environment... "
    "$PYTHON" -m venv "$VENV_DIR"
    info "Created $VENV_DIR"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Activated virtual environment"

# --------------------------------------------------------------------------
# 3. Install project
# --------------------------------------------------------------------------
INSTALL_FLAG=""
if [ "$1" = "--dev" ]; then
    INSTALL_FLAG=".[dev]"
    echo "Installing with development dependencies..."
else
    INSTALL_FLAG="."
    echo "Installing..."
fi

pip install -q -e "$INSTALL_FLAG"
info "Installed ocp-policy-hub"

# --------------------------------------------------------------------------
# 4. Copy example.env → .env
# --------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    cp config/example.env .env
    info "Created .env from config/example.env"
    warn "Edit .env and add your ANTHROPIC_API_KEY before running the agent"
else
    info ".env already exists"
fi

# --------------------------------------------------------------------------
# 5. Done!
# --------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit .env and add your Anthropic API key"
echo "     Get one at: https://console.anthropic.com/"
echo ""
echo "  2. Activate the virtual environment (needed each new terminal):"
echo "     source .venv/bin/activate"
echo ""
echo "  3. Run the agent:"
echo "     python -m src.agent"
echo ""
