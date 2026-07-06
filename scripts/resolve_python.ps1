# Fast Python resolver - never calls Windows Store python.exe alias.
# Output: EXE|C:\path\python.exe   OR   PY|-3.12
$paths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "${env:ProgramFiles}\Python312\python.exe",
    "${env:ProgramFiles}\Python311\python.exe"
)

foreach ($p in $paths) {
    if (-not (Test-Path $p)) { continue }
    try {
        & $p -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Output "EXE|$p"
            exit 0
        }
    } catch {}
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("-3.12", "-3.11", "-3.10", "-3.9", "-3")) {
        try {
            & py $v -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Output "PY|$v"
                exit 0
            }
        } catch {}
    }
}

exit 1
