# ============================================================================
# OCP CE HR Policy Searcher -- One-command setup (Windows PowerShell)
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
#   5. Prompts for your Anthropic API key
#   6. Prompts for Google Sheets credentials (optional)
#   7. Tells you how to run the agent
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
    pip install -q -e ".[dev,browser]"
} else {
    Write-Host "Installing..."
    pip install -q -e ".[browser]"
}
Write-Info "Installed OCP-CE-HR-Policy-Searcher"

# Install Playwright browser (suppress stderr to prevent deprecation warnings from terminating the script)
Write-Host "Installing Playwright Chromium browser..."
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
playwright install chromium 2>$null
$playwrightExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($playwrightExit -eq 0) {
    Write-Info "Playwright Chromium installed"
} else {
    Write-Warn "Playwright browser install failed -- JS-rendered sites will not work. Run: playwright install chromium"
}

# --------------------------------------------------------------------------
# 4. Copy example.env -> .env and prompt for API key
# --------------------------------------------------------------------------
$envCreated = $false
if (-not (Test-Path ".env")) {
    Copy-Item "config\example.env" ".env"
    Write-Info "Created .env from config\example.env"
    $envCreated = $true
} else {
    Write-Info ".env already exists"
}

# Check if the .env still has the placeholder key
$envContent = Get-Content ".env" -Raw
if ($envContent -match "your-key-here" -or $envContent -match "your-real-key-here") {
    Write-Host ""
    Write-Host "--------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host "  An Anthropic API key is required to run the agent." -ForegroundColor Cyan
    Write-Host "  Get one at: https://console.anthropic.com/" -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    $apiKey = Read-Host "Paste your ANTHROPIC_API_KEY (or press Enter to skip)"
    $apiKey = $apiKey.Trim()

    if ($apiKey -and $apiKey.Length -gt 40) {
        # Replace the placeholder line in .env
        $envContent = $envContent -replace "ANTHROPIC_API_KEY=.*", "ANTHROPIC_API_KEY=$apiKey"
        Set-Content ".env" $envContent -NoNewline
        Write-Info "API key saved to .env"
    } elseif ($apiKey) {
        Write-Warn "That key looks too short. Edit .env manually and paste your full key."
    } else {
        Write-Warn "Skipped. Edit .env and add your ANTHROPIC_API_KEY before running the agent."
    }
}

# --------------------------------------------------------------------------
# 5. Google Sheets setup (optional)
# --------------------------------------------------------------------------
$envContent = Get-Content ".env" -Raw
if ($envContent -notmatch "GOOGLE_CREDENTIALS_FILE=" -and $envContent -notmatch "^GOOGLE_CREDENTIALS=(?!your-)" ) {
    Write-Host ""
    Write-Host "--------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host "  Google Sheets export (optional)" -ForegroundColor Cyan
    Write-Host "  Policies are always saved locally to data/policies.json." -ForegroundColor Cyan
    Write-Host "  To also export to Google Sheets, provide your service" -ForegroundColor Cyan
    Write-Host "  account credentials." -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Enter ONE of:"
    Write-Host "    - Path to your Google service account JSON key file"
    Write-Host "    - Base64-encoded credentials string"
    Write-Host "  (or press Enter to skip and set up later):"
    Write-Host ""
    $credsInput = Read-Host "  Credentials"
    $credsInput = $credsInput.Trim().Trim('"').Trim("'")

    $credsSaved = $false
    if ($credsInput) {
        if (Test-Path $credsInput) {
            # Input is a file path
            $envContent = Get-Content ".env" -Raw
            if ($envContent -match "# GOOGLE_CREDENTIALS_FILE=") {
                $envContent = $envContent -replace "# GOOGLE_CREDENTIALS_FILE=.*", "GOOGLE_CREDENTIALS_FILE=$credsInput"
            } else {
                $envContent = $envContent + "`nGOOGLE_CREDENTIALS_FILE=$credsInput`n"
            }
            Set-Content ".env" $envContent -NoNewline
            Write-Info "Google credentials file path saved to .env"
            $credsSaved = $true
        } elseif ($credsInput.Length -gt 50) {
            # Input is a long string -- treat as base64 or raw JSON
            # (the config loader auto-detects the format at runtime)
            $envContent = Get-Content ".env" -Raw
            if ($envContent -match "# GOOGLE_CREDENTIALS=") {
                $envContent = $envContent -replace "# GOOGLE_CREDENTIALS=.*", "GOOGLE_CREDENTIALS=$credsInput"
            } elseif ($envContent -match "^GOOGLE_CREDENTIALS=") {
                $envContent = $envContent -replace "GOOGLE_CREDENTIALS=.*", "GOOGLE_CREDENTIALS=$credsInput"
            } else {
                $envContent = $envContent + "`nGOOGLE_CREDENTIALS=$credsInput`n"
            }
            Set-Content ".env" $envContent -NoNewline
            Write-Info "Google credentials saved to .env"
            $credsSaved = $true
        } else {
            Write-Warn "Input too short for credentials and not a valid file path."
            Write-Warn "Edit .env and set GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS."
        }

        if ($credsSaved) {
            # Ask for spreadsheet ID
            Write-Host ""
            Write-Host "  Enter your Google Spreadsheet ID"
            Write-Host "  (the part between /d/ and /edit in the URL):"
            Write-Host ""
            $sheetId = Read-Host "  Spreadsheet ID"
            $sheetId = $sheetId.Trim()
            if ($sheetId -and $sheetId.Length -gt 10) {
                $envContent = Get-Content ".env" -Raw
                $envContent = $envContent -replace "# SPREADSHEET_ID=.*", "SPREADSHEET_ID=$sheetId"
                Set-Content ".env" $envContent -NoNewline
                Write-Info "Spreadsheet ID saved to .env"
            } elseif ($sheetId) {
                Write-Warn "That ID looks too short. Edit .env and set SPREADSHEET_ID."
            } else {
                Write-Warn "Skipped. Edit .env and set SPREADSHEET_ID to enable Sheets export."
            }
        }
    } else {
        Write-Info "Skipped Google Sheets setup. Policies will save to data/policies.json."
        Write-Host "  To enable later, edit .env and set GOOGLE_CREDENTIALS_FILE" -ForegroundColor Gray
    }
}

# --------------------------------------------------------------------------
# 6. Done!
# --------------------------------------------------------------------------
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor White -BackgroundColor DarkGreen
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "  1. Activate the virtual environment (needed each new terminal):"
Write-Host "     .venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "  2. Run the agent:"
Write-Host "     python -m src.agent"
Write-Host ""
Write-Host ""
