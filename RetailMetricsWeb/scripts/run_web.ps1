$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $appRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

function Get-LanIPv4Address {
    try {
        $address = Get-NetIPConfiguration -ErrorAction Stop |
            Where-Object {
                $_.NetAdapter.Status -eq "Up" -and
                $_.IPv4DefaultGateway -and
                $_.IPv4Address
            } |
            ForEach-Object { $_.IPv4Address.IPAddress } |
            Where-Object { $_ -ne "127.0.0.1" -and $_ -notlike "169.254.*" } |
            Select-Object -First 1
        if ($address) {
            return $address
        }
    } catch {
        # Fall through to the adapter-only lookup for older Windows installations.
    }

    try {
        $address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.InterfaceAlias -notmatch "Loopback"
            } |
            Sort-Object -Property InterfaceMetric |
            Select-Object -ExpandProperty IPAddress -First 1
        if ($address) {
            return $address
        }
    } catch {
        # A clear error is raised below.
    }

    throw "No LAN IPv4 address was detected. Connect to the LAN, or set API_BASE_URL=http://HOST_IP:8000 before running this launcher."
}

function Get-DotEnvApiBaseUrl {
    $envFile = Join-Path $appRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) {
        return $null
    }
    $line = Get-Content -LiteralPath $envFile |
        Where-Object { $_ -match '^\s*API_BASE_URL\s*=' } |
        Select-Object -Last 1
    if (-not $line) {
        return $null
    }
    return (($line -replace '^\s*API_BASE_URL\s*=\s*', '').Trim().Trim('"').Trim("'"))
}

function Test-IsLoopbackOrPlaceholder([string] $url) {
    if ([string]::IsNullOrWhiteSpace($url) -or $url -match 'HOST_IP') {
        return $true
    }
    try {
        $uri = [Uri]$url
        if (-not $uri.IsAbsoluteUri -or $uri.Scheme -notin @("http", "https") -or -not $uri.Host) {
            throw "invalid URL"
        }
        return $uri.Host -in @("127.0.0.1", "localhost", "::1")
    } catch {
        throw "API_BASE_URL must be an absolute HTTP URL such as http://192.168.1.25:8000."
    }
}

$lanIPv4 = Get-LanIPv4Address
$configuredApiBaseUrl = if ($env:API_BASE_URL) { $env:API_BASE_URL } else { Get-DotEnvApiBaseUrl }
$env:API_BASE_URL = if (Test-IsLoopbackOrPlaceholder $configuredApiBaseUrl) {
    "http://${lanIPv4}:8000"
} else {
    $configuredApiBaseUrl.TrimEnd("/")
}
$localHealthUrl = "http://127.0.0.1:8000/health"

$api = Start-Process -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000") `
    -WorkingDirectory $appRoot `
    -WindowStyle Hidden `
    -PassThru

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($api.HasExited) {
            throw "FastAPI stopped before becoming ready (exit code $($api.ExitCode))."
        }
        try {
            $response = Invoke-WebRequest -Uri $localHealthUrl -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "FastAPI did not become ready at $localHealthUrl."
    }

    Write-Host "FastAPI:   $($env:API_BASE_URL)/docs"
    Write-Host "Streamlit: http://${lanIPv4}:8501"
    Write-Host "LAN access is limited by your Windows Firewall and network profile."
    & $python -m streamlit run frontend\app.py --server.address 0.0.0.0 --server.port 8501
} finally {
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id
        $api.WaitForExit()
    }
}
