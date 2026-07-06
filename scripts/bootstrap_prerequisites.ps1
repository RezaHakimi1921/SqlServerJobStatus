# Auto-download and install Python 3.12 + ODBC Driver for SQL Server (Windows).
# Requires internet. Run from setup.bat when prerequisites are missing.

$ErrorActionPreference = "Continue"

function Test-PythonInstalled {
    $candidates = @(
        @("py", "-3"),
        @("py"),
        @("python3"),
        @("python")
    )
    foreach ($args in $candidates) {
        try {
            & $args[0] @($args[1..($args.Length - 1)]) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch {}
    }
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $true }
    }
    return $false
}

function Install-Python {
    Write-Host ""
    Write-Host "[1/2] Installing Python 3.12..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Trying winget..."
        winget install --id Python.Python.3.12 -e `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -eq 0 -and (Test-PythonInstalled)) {
            Write-Host "  OK  Python installed via winget."
            return $true
        }
        Write-Host "  winget install did not complete successfully."
    } else {
        Write-Host "  winget not found, using direct download..."
    }

    $version = "3.12.7"
    $url = "https://www.python.org/ftp/python/$version/python-$version-amd64.exe"
    $dest = Join-Path $env:TEMP "python-$version-amd64.exe"

    Write-Host "  Downloading Python $version..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    } catch {
        Write-Host "  ERROR: Download failed: $_"
        return $false
    }

    Write-Host "  Running installer (quiet, add to PATH)..."
    $proc = Start-Process -FilePath $dest -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_launcher=1"
    ) -Wait -PassThru
    Remove-Item $dest -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -ne 0) {
        Write-Host "  ERROR: Python installer exit code $($proc.ExitCode)"
        return $false
    }

    if (Test-PythonInstalled) {
        Write-Host "  OK  Python installed."
        return $true
    }

    Write-Host "  ERROR: Python installer finished but python.exe was not found."
    Write-Host "  Disable Store aliases: Settings > Apps > App execution aliases > OFF python.exe"
    return $false
}

function Test-OdbcInstalled {
    try {
        $py = $null
        foreach ($args in @(@("py", "-3"), @("py"), @("python"))) {
            & $args[0] @($args[1..($args.Length - 1)]) -c "import pyodbc; d=[x for x in pyodbc.drivers() if 'SQL Server' in x]; raise SystemExit(0 if d else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
    } catch {}
    return $false
}

function Install-Odbc {
    Write-Host ""
    Write-Host "[2/2] Installing ODBC Driver for SQL Server..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Trying winget ODBC Driver 17..."
        winget install --id Microsoft.MicrosoftODBCDriver17ForSQLServer -e `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK  ODBC Driver 17 installed via winget."
            return $true
        }

        Write-Host "  Trying winget ODBC Driver 18..."
        winget install --id Microsoft.MicrosoftODBCDriver18ForSQLServer -e `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK  ODBC Driver 18 installed via winget."
            return $true
        }
    }

    $msiUrl = "https://go.microsoft.com/fwlink/?linkid=2249004"
    $msiDest = Join-Path $env:TEMP "msodbcsql17.msi"
    Write-Host "  Downloading ODBC Driver 17 MSI..."
    try {
        Invoke-WebRequest -Uri $msiUrl -OutFile $msiDest -UseBasicParsing
    } catch {
        Write-Host "  ERROR: ODBC download failed: $_"
        return $false
    }

    Write-Host "  Running MSI installer..."
    $proc = Start-Process msiexec.exe -ArgumentList "/i", "`"$msiDest`"", "/qn", "IACCEPTMSODBCSQLLICENSETERMS=YES" -Wait -PassThru
    Remove-Item $msiDest -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -eq 0) {
        Write-Host "  OK  ODBC Driver 17 installed."
        return $true
    }

    Write-Host "  WARNING: ODBC MSI exit code $($proc.ExitCode). You may install manually later."
    return $false
}

Write-Host "============================================================"
Write-Host "  Auto-install prerequisites (Python + ODBC)"
Write-Host "============================================================"

$ok = $true
if (-not (Test-PythonInstalled)) {
    if (-not (Install-Python)) { $ok = $false }
} else {
    Write-Host ""
    Write-Host "[1/2] Python already installed - skipped."
}

if (-not (Test-OdbcInstalled)) {
    Install-Odbc | Out-Null
} else {
    Write-Host ""
    Write-Host "[2/2] ODBC driver already present - skipped."
}

Write-Host ""
if ($ok) {
    Write-Host "Bootstrap finished. Continuing setup..."
    exit 0
}

Write-Host "Bootstrap failed. Fix errors above and run setup.bat again."
exit 1
