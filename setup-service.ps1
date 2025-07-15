<#
run with this in admin powershell:
.\setup-service.ps1 -ProjectDir "C:\projects\hypercon" -ServiceName "hypercon"
----------------------------------------------------------------------------------
.SYNOPSIS
  Installs and configures your Flask app as a Windows service via NSSM.

.PARAMETER ProjectDir
  Path to your project root (where run.py and config.ini live).

.PARAMETER ServiceName
  The Windows Service name to create (default: "hypercon").
#>

param(
  [string]$ProjectDir   = "C:\projects\hypercon",
  [string]$ServiceName  = "hypercon"
)

Set-StrictMode -Version Latest

# 1. Ensure logs directory exists
$logsDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logsDir)) {
    Write-Host "Creating logs directory at $logsDir"
    New-Item -Path $logsDir -ItemType Directory | Out-Null
}

# 2. Create a virtual environment if missing
$venvDir = Join-Path $ProjectDir "venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "Creating Python virtual environment in $venvDir"
    python -m venv $venvDir
}

# 3. Install Python dependencies
Write-Host "Installing Python dependencies..."
# Activate the venv for this process
& "$venvDir\Scripts\Activate.ps1"
# We won't attempt to upgrade pip here to avoid the "pip install pip" warning
pip install -r (Join-Path $ProjectDir "requirements.txt")
# No explicit Deactivate.ps1 call—once the script exits, the child process ends

# 4. Remove existing service (if any)
Write-Host "Stopping and deleting existing service (if present)..."
sc.exe stop  $ServiceName 2>$null
sc.exe delete $ServiceName 2>$null

# 5. Install the service via NSSM
$nssm   = "nssm"  # adjust if nssm.exe is not in PATH
$python = Join-Path $venvDir "Scripts\python.exe"
$app    = Join-Path $ProjectDir "run.py"

Write-Host "Installing NSSM service '$ServiceName'..."
& $nssm install $ServiceName $python (Join-Path $ProjectDir "run.py")
sc.exe config $ServiceName start= auto

# 6. Configure NSSM settings
Write-Host "Configuring NSSM service parameters..."
& $nssm set $ServiceName AppDirectory      $ProjectDir
& $nssm set $ServiceName AppStdout         (Join-Path $logsDir "stdout.log")
& $nssm set $ServiceName AppStderr         (Join-Path $logsDir "stderr.log")
& $nssm set $ServiceName AppRotateFiles    1

# Optional: environment variables
& $nssm set $ServiceName AppEnvironmentExtra "FLASK_ENV=production;SECRET_KEY=change_me_for_prod"

# 7. Start the new service
Write-Host "Starting service '$ServiceName'..."
sc.exe start $ServiceName

# 8. Wait briefly and show service status
Start-Sleep -Seconds 2
$svc = sc.exe query $ServiceName
Write-Host $svc

# 9. Tail the logs so you can see quickly if it booted
Write-Host "Tailing last 10 lines of stdout.log:"
Get-Content (Join-Path $logsDir "stdout.log") -Tail 10

# ──────────────────────────────────────────────────────
# 10. Set up Nginx itself as a service via NSSM
# ──────────────────────────────────────────────────────

# Path to your nginx install
$nginxDir = "C:\nginx"
$nginxExe = Join-Path $nginxDir "nginx.exe"

if (Test-Path $nginxExe) {
    Write-Host "Configuring Nginx service via NSSM…"

    # remove any old service
    sc.exe stop  nginx 2>$null
    sc.exe delete nginx 2>$null

    # install nginx as a service
    & $nssm install nginx $nginxExe "-p $nginxDir"

    # point it at the correct conf folder
    & $nssm set nginx AppDirectory    $nginxDir

    # (optional) log Nginx stdout/stderr somewhere
    $nginxLogs = Join-Path $nginxDir "logs"
    if (-not (Test-Path $nginxLogs)) {
        New-Item -Path $nginxLogs -ItemType Directory | Out-Null
    }
    & $nssm set nginx AppStdout       (Join-Path $nginxLogs "nginx.out.log")
    & $nssm set nginx AppStderr       (Join-Path $nginxLogs "nginx.err.log")
    & $nssm set nginx AppRotateFiles  1

    # finally, start nginx
    Write-Host "Starting Nginx service…"
    sc.exe start nginx
    sc.exe query nginx | Write-Host
}
else {
    Write-Host "Nginx not found in $nginxDir – skipping Nginx service setup."
}