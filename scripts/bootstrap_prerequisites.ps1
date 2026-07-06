# Auto-download and install Python 3.12 + optional ODBC Driver (Windows).
param(
    [switch]$PythonOnly,
    [switch]$OdbcOnly
)

$ErrorActionPreference = "Continue"

function Write-Step([string]$Msg) {
    Write-Host ""
    Write-Host $Msg
    [Console]::Out.Flush()
}

function Test-PythonInstalled {
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $true }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("-3.12", "-3.11", "-3")) {
            & py $v -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
    }
    return $false
}

function Download-FileWithProgress([string]$Url, [string]$Dest) {
    Write-Host "  URL: $Url"
    try {
        if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
            Start-BitsTransfer -Source $Url -Destination $Dest -DisplayName "Download" -Description "Downloading..."
            Write-Host "  Download complete."
            return $true
        }
    } catch {
        Write-Host "  BITS failed, using WebRequest..."
    }

    $wc = New-Object System.Net.WebClient
    $wc.DownloadFile($Url, $Dest)
    Write-Host "  Download complete."
    return $true
}

function Install-PythonDirect {
    $version = "3.12.7"
    $url = "https://www.python.org/ftp/python/$version/python-$version-amd64.exe"
    $dest = Join-Path $env:TEMP "python-$version-amd64.exe"

    Write-Step "  Downloading Python $version..."
    try {
        Download-FileWithProgress -Url $url -Dest $dest | Out-Null
    } catch {
        Write-Host "  ERROR: Download failed: $_"
        return $false
    }

    if (-not (Test-Path $dest)) {
        Write-Host "  ERROR: Download file missing."
        return $false
    }

    Write-Host "  Running installer - wait 1-3 minutes..."
    $proc = Start-Process -FilePath $dest -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_launcher=1"
    ) -Wait -PassThru
    Remove-Item $dest -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -ne 0) {
        Write-Host "  ERROR: Python installer exit code $($proc.ExitCode)"
        return $false
    }

    Start-Sleep -Seconds 3
    if (Test-PythonInstalled) {
        Write-Host "  OK  Python installed."
        return $true
    }

    Write-Host "  ERROR: Installer finished but python.exe was not found."
    return $false
}

function Install-PythonWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }

    Write-Host "  Trying winget (timeout 4 min)..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "winget"
    $psi.Arguments = "install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements --disable-interactivity"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($psi)

    $exited = $proc.WaitForExit(240000)
    if (-not $exited) {
        try { $proc.Kill() } catch {}
        Write-Host "  winget timed out."
        return $false
    }

    $out = $proc.StandardOutput.ReadToEnd()
    if ($out) { $out.Trim().Split("`n") | ForEach-Object { Write-Host "  $_" } }
    Start-Sleep -Seconds 2
    return (Test-PythonInstalled)
}

function Install-Python {
    Write-Step "[bootstrap] Installing Python 3.12..."

    if (Install-PythonDirect) { return $true }

    Write-Host "  Direct install failed, trying winget..."
    if (Install-PythonWinget) {
        Write-Host "  OK  Python installed via winget."
        return $true
    }

    return $false
}

function Install-Odbc {
    Write-Step "[bootstrap] Installing ODBC Driver 17..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Trying winget (timeout 4 min)..."
        $proc = Start-Process winget -ArgumentList @(
            "install", "--id", "Microsoft.MicrosoftODBCDriver17ForSQLServer", "-e",
            "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"
        ) -PassThru -NoNewWindow -Wait
        if ($proc.ExitCode -eq 0) {
            Write-Host "  OK  ODBC Driver 17 installed."
            return $true
        }
        Write-Host "  winget ODBC 17 failed, trying ODBC 18..."
        $proc = Start-Process winget -ArgumentList @(
            "install", "--id", "Microsoft.MicrosoftODBCDriver18ForSQLServer", "-e",
            "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"
        ) -PassThru -NoNewWindow -Wait
        if ($proc.ExitCode -eq 0) { return $true }
    }

    $msiUrl = "https://go.microsoft.com/fwlink/?linkid=2249004"
    $msiDest = Join-Path $env:TEMP "msodbcsql17.msi"
    Write-Host "  Downloading ODBC MSI..."
    try {
        Download-FileWithProgress -Url $msiUrl -Dest $msiDest | Out-Null
    } catch {
        Write-Host "  ERROR: ODBC download failed: $_"
        return $false
    }

    Write-Host "  Running MSI installer..."
    $proc = Start-Process msiexec.exe -ArgumentList "/i", "`"$msiDest`"", "/qn", "IACCEPTMSODBCSQLLICENSETERMS=YES" -Wait -PassThru
    Remove-Item $msiDest -Force -ErrorAction SilentlyContinue
    return ($proc.ExitCode -eq 0)
}

Write-Host "============================================================"
Write-Host "  Auto-install prerequisites"
Write-Host "============================================================"
[Console]::Out.Flush()

$ok = $true

if (-not $OdbcOnly) {
    if (Test-PythonInstalled) {
        Write-Step "[bootstrap] Python already installed - skipped."
    } elseif (-not (Install-Python)) {
        $ok = $false
    }
}

if (-not $PythonOnly -and $ok -and -not $OdbcOnly) {
    Install-Odbc | Out-Null
}

if ($OdbcOnly) {
    Install-Odbc | Out-Null
}

Write-Host ""
if ($ok) {
    Write-Host "Bootstrap finished."
    exit 0
}

Write-Host "Bootstrap failed. See errors above."
exit 1
