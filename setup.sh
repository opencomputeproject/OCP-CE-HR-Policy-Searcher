#!/usr/bin/env bash
# ============================================================================
# OCP CE HR Policy Searcher -- One-command setup
#
# Usage:
#   ./setup.sh          # Standard install
#   ./setup.sh --dev    # Include development dependencies (pytest, ruff)
#
# This script:
#   1. Checks for Python 3.11+
#   2. Creates a virtual environment (.venv)
#   3. Installs the project and its dependencies
#   4. Copies config/example.env -> .env (if .env doesn't exist)
#   5. Prompts for your Anthropic API key
#   6. Prompts for Google Sheets credentials (optional)
#   7. Tells you how to run the agent
# ============================================================================

set -e

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' CYAN='' BOLD='' NC=''
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
    INSTALL_FLAG=".[dev,browser]"
    echo "Installing with development dependencies..."
else
    INSTALL_FLAG=".[browser]"
    echo "Installing..."
fi

pip install -q -e "$INSTALL_FLAG"
info "Installed OCP-CE-HR-Policy-Searcher"

# Install Playwright browser
echo "Installing Playwright Chromium browser..."
if playwright install chromium 2>/dev/null; then
    info "Playwright Chromium installed"
else
    warn "Playwright browser install failed -- JS-rendered sites won't work. Run: playwright install chromium"
fi

# --------------------------------------------------------------------------
# 4. Copy example.env -> .env and prompt for API key
# --------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    cp config/example.env .env
    info "Created .env from config/example.env"
else
    info ".env already exists"
fi

# Check if the .env still has the placeholder key
if grep -q "your-key-here\|your-real-key-here" .env 2>/dev/null; then
    echo ""
    echo -e "${CYAN}--------------------------------------------------------------${NC}"
    echo -e "${CYAN}  An Anthropic API key is required to run the agent.${NC}"
    echo -e "${CYAN}  Get one at: https://console.anthropic.com/${NC}"
    echo -e "${CYAN}--------------------------------------------------------------${NC}"
    echo ""
    echo -n "Paste your ANTHROPIC_API_KEY (or press Enter to skip): "
    read -r api_key

    # Trim whitespace
    api_key=$(echo "$api_key" | xargs)

    if [ -n "$api_key" ] && [ ${#api_key} -gt 40 ]; then
        # Replace the placeholder line in .env
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
        else
            sed -i "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
        fi
        info "API key saved to .env"
    elif [ -n "$api_key" ]; then
        warn "That key looks too short. Edit .env manually and paste your full key."
    else
        warn "Skipped. Edit .env and add your ANTHROPIC_API_KEY before running the agent."
    fi
fi

# --------------------------------------------------------------------------
# 5. Google Sheets setup (optional)
# --------------------------------------------------------------------------
# Check for UNCOMMENTED credential lines (lines NOT starting with #).
# The example.env has commented-out examples like "# GOOGLE_CREDENTIALS_FILE=..."
# which must NOT count as "already configured".
has_creds_file=$(grep -c "^GOOGLE_CREDENTIALS_FILE=" .env 2>/dev/null || true)
has_creds_value=$(grep "^GOOGLE_CREDENTIALS=" .env 2>/dev/null | grep -cv "^GOOGLE_CREDENTIALS=your-" 2>/dev/null || true)
if [ "$has_creds_file" -eq 0 ] && [ "$has_creds_value" -eq 0 ]; then
    echo ""
    echo -e "${CYAN}--------------------------------------------------------------${NC}"
    echo -e "${CYAN}  Google Sheets export (optional)${NC}"
    echo -e "${CYAN}  Policies are always saved locally to data/policies.json.${NC}"
    echo -e "${CYAN}  To also export to Google Sheets, provide your service${NC}"
    echo -e "${CYAN}  account credentials.${NC}"
    echo -e "${CYAN}--------------------------------------------------------------${NC}"
    echo ""
    echo "  Enter ONE of:"
    echo "    - Path to your Google service account JSON key file"
    echo "    - Base64-encoded credentials string"
    echo "  (or press Enter to skip and set up later):"
    echo ""
    echo -n "  Credentials: "
    read -r creds_input

    # Trim whitespace and quotes
    creds_input=$(echo "$creds_input" | xargs | tr -d "\"'")

    if [ -n "$creds_input" ]; then
        creds_saved=false

        if [ -f "$creds_input" ]; then
            # Input is a file path
            if grep -q "# GOOGLE_CREDENTIALS_FILE=" .env 2>/dev/null; then
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    sed -i '' "s|# GOOGLE_CREDENTIALS_FILE=.*|GOOGLE_CREDENTIALS_FILE=$creds_input|" .env
                else
                    sed -i "s|# GOOGLE_CREDENTIALS_FILE=.*|GOOGLE_CREDENTIALS_FILE=$creds_input|" .env
                fi
            else
                echo "GOOGLE_CREDENTIALS_FILE=$creds_input" >> .env
            fi
            info "Google credentials file path saved to .env"
            creds_saved=true
        elif [ ${#creds_input} -gt 50 ]; then
            # Input is a long string -- treat as base64 or raw JSON
            # (the config loader auto-detects the format at runtime)
            if grep -q "# GOOGLE_CREDENTIALS=" .env 2>/dev/null; then
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    sed -i '' "s|# GOOGLE_CREDENTIALS=.*|GOOGLE_CREDENTIALS=$creds_input|" .env
                else
                    sed -i "s|# GOOGLE_CREDENTIALS=.*|GOOGLE_CREDENTIALS=$creds_input|" .env
                fi
            elif grep -q "^GOOGLE_CREDENTIALS=" .env 2>/dev/null; then
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    sed -i '' "s|GOOGLE_CREDENTIALS=.*|GOOGLE_CREDENTIALS=$creds_input|" .env
                else
                    sed -i "s|GOOGLE_CREDENTIALS=.*|GOOGLE_CREDENTIALS=$creds_input|" .env
                fi
            else
                echo "GOOGLE_CREDENTIALS=$creds_input" >> .env
            fi
            info "Google credentials saved to .env"
            creds_saved=true
        else
            warn "Input too short for credentials and not a valid file path."
            warn "Edit .env and set GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS."
        fi

        if [ "$creds_saved" = true ]; then
            # Ask for spreadsheet ID
            echo ""
            echo "  Enter your Google Spreadsheet ID"
            echo "  (the part between /d/ and /edit in the URL):"
            echo ""
            echo -n "  Spreadsheet ID: "
            read -r sheet_id
            sheet_id=$(echo "$sheet_id" | xargs)

            if [ -n "$sheet_id" ] && [ ${#sheet_id} -gt 10 ]; then
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    sed -i '' "s|# SPREADSHEET_ID=.*|SPREADSHEET_ID=$sheet_id|" .env
                else
                    sed -i "s|# SPREADSHEET_ID=.*|SPREADSHEET_ID=$sheet_id|" .env
                fi
                info "Spreadsheet ID saved to .env"
            elif [ -n "$sheet_id" ]; then
                warn "That ID looks too short. Edit .env and set SPREADSHEET_ID."
            else
                warn "Skipped. Edit .env and set SPREADSHEET_ID to enable Sheets export."
            fi
        fi
    else
        info "Skipped Google Sheets setup. Policies will save to data/policies.json."
        echo "  To enable later, edit .env and set GOOGLE_CREDENTIALS_FILE"
    fi
fi

# --------------------------------------------------------------------------
# 6. Done!
# --------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Activate the virtual environment (needed each new terminal):"
echo "     source .venv/bin/activate"
echo ""
echo "  2. Run the agent:"
echo "     python -m src.agent"
echo ""
echo ""
