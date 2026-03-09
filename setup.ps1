# ============================================================================
# OCP Policy Hub — One-command setup (Windows PowerShell)
#
# Usage:
#   .\setup.ps1          # Standard install
#   .\setup.ps1 -Dev     # Include development dependencies (pytest, ruff)
#
# This script:
#   1. Checks for Python 3.11+
#   2. Creates a virtual environment (.venv)
#   3. Installs the project and its dependencies
#   4. Copies config/example.env -> .env (if .env doesn't exist)
#   5. Tells you how to run the agent
#
# Note: If you get "cannot be loaded because running scripts is disabled",
#       run this first (as Administrator):
#           Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
# ============================================================================

param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"

function Write-Info($msg)  { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "[!!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "[X]  $msg" -ForegroundColor Red }

# --------------------------------------------------------------------------
# 1. Find Python 3.11+
# --------------------------------------------------------------------------
$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        $major = & $candidate -c "import sys; print(sys.version_info.major)" 2>$null
        $minor = & $candidate -c "import sys; print(sys.version_info.minor)" 2>$null
        if ([int]$major -ge 3 -and [int]$minor -ge 11) {
            $pythonCmd = $candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Err "Python 3.11+ is required but not found."
    Write-Host "  Install Python from: https://www.python.org/downloads/"
    Write-Host "  Make sure to check 'Add Python to PATH' during installation."
    exit 1
}

Write-Info "Found Python $ver ($pythonCmd)"

# --------------------------------------------------------------------------
# 2. Create virtual environment
# --------------------------------------------------------------------------
$venvDir = ".venv"

if (Test-Path $venvDir) {
    Write-Info "Virtual environment already exists ($venvDir)"
} else {
    Write-Host "Creating virtual environment... " -NoNewline
    & $pythonCmd -m venv $venvDir
    Write-Info "Created $venvDir"
}

# Activate
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Err "Cannot find activation script at $activateScript"
    exit 1
}
. $activateScript
Write-Info "Activated virtual environment"

# --------------------------------------------------------------------------
# 3. Install project
# --------------------------------------------------------------------------
if ($Dev) {
    Write-Host "Installing with development dependencies..."
    pip install -q -e ".[dev]"
} else {
    Write-Host "Installing..."
    pip install -q -e .
}
Write-Info "Installed ocp-policy-hub"

# --------------------------------------------------------------------------
# 4. Copy example.env -> .env
# --------------------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item "config\example.env" ".env"
    Write-Info "Created .env from config\example.env"
    Write-Warn "Edit .env and add your ANTHROPIC_API_KEY before running the agent"
} else {
    Write-Info ".env already exists"
}

# --------------------------------------------------------------------------
# 5. Done!
# --------------------------------------------------------------------------
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor White -BackgroundColor DarkGreen
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "  1. Edit .env and add your Anthropic API key"
Write-Host "     Get one at: https://console.anthropic.com/"
Write-Host ""
Write-Host "  2. Activate the virtual environment (needed each new terminal):"
Write-Host "     .venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "  3. Run the agent:"
Write-Host "     python -m src.agent"
Write-Host ""
