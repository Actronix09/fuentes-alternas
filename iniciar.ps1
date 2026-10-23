param([switch]$Recargar, [switch]$SoloDatos)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot '.runtime'
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'evidencia/logs') | Out-Null

function Ejecutar-Python {
    param([string[]]$Argumentos)
    & python @Argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falló Python: $Argumentos" }
}

& python -c 'import flask, psycopg, psycopg2, sqlalchemy, flask_sqlalchemy, flask_cors, boto3, dotenv, cryptography, tzdata, rdflib' 2>$null
if ($LASTEXITCODE -ne 0) {
    Ejecutar-Python -Argumentos @('-m', 'pip', 'install', '--target', '.runtime', '-r', 'requirements-local.txt')
}
& docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Abre Docker Desktop y vuelve a ejecutar este script.' }
& docker compose -f agua-reportes-sacmex/compose.yml -f agua-reportes-sacmex/compose.windows.yml up -d db
if ($LASTEXITCODE -ne 0) { throw 'No arrancó PostgreSQL de agua.' }
& docker compose -f obra-publica-srft/compose.yml up -d db
if ($LASTEXITCODE -ne 0) { throw 'No arrancó PostgreSQL de obras.' }
& docker compose -f sismos-usgs/compose.yml -f sismos-usgs/compose.windows.yml up -d db
if ($LASTEXITCODE -ne 0) { throw 'No arrancó PostgreSQL de sismos.' }
$env:FORZAR_ETL = if ($Recargar) { '1' } else { '0' }

$servicios = @(
    @{Nombre='agua';Carpeta='agua-reportes-sacmex';Puerto=8092;Dsn='postgresql://agua:agua_local@localhost:5442/agua_dw'},
    @{Nombre='obras';Carpeta='obra-publica-srft';Puerto=8093;Dsn='postgresql://obras:obras_local@localhost:5443/obras_publicas'},
    @{Nombre='sismos';Carpeta='sismos-usgs';Puerto=8091;Dsn='postgresql://sismos:sismos_local@localhost:5441/sismos_dw'}
)
foreach ($servicio in $servicios) {
    $env:DATABASE_URL = $servicio.Dsn
    $env:DIR_DATOS = Join-Path $PSScriptRoot ($servicio.Carpeta + '/datos')
    Write-Host "Ejecutando ETL de $($servicio.Nombre)..."
    Ejecutar-Python -Argumentos @((Join-Path $PSScriptRoot ($servicio.Carpeta + '/app/etl.py')))
    if ($SoloDatos) { continue }
    $url = "http://127.0.0.1:$($servicio.Puerto)"
    $activo = $false
    try { $activo = (Invoke-RestMethod "$url/api/salud" -TimeoutSec 3).ok -eq $true } catch {}
    if (-not $activo) {
        $appPath = Join-Path $PSScriptRoot ($servicio.Carpeta + '/app/web.py')
        $stdoutPath = Join-Path $PSScriptRoot "evidencia/logs/$($servicio.Nombre)-web.log"
        $stderrPath = Join-Path $PSScriptRoot "evidencia/logs/$($servicio.Nombre)-error.log"
        $argumentos = '-m flask --app "' + $appPath + '" run --host 127.0.0.1 --port ' + $servicio.Puerto
        Start-Process -FilePath (Get-Command python).Source -ArgumentList $argumentos -WorkingDirectory $PSScriptRoot `
            -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath | Out-Null
        $listo = $false
        for ($intento=0; $intento -lt 20; $intento++) {
            Start-Sleep -Milliseconds 500
            try { if ((Invoke-RestMethod "$url/api/salud" -TimeoutSec 2).ok) { $listo=$true; break } } catch {}
        }
        if (-not $listo) { throw "No arrancó $url. Revisa $stderrPath" }
    }
    Write-Host "LISTO: $url"
}
if (-not $SoloDatos) {
    # El frontend original de sismos es PHP: se sirve en Docker sobre la misma base.
    & docker compose -f sismos-usgs/compose.yml -f sismos-usgs/compose.windows.yml up -d --build --no-deps original
    if ($LASTEXITCODE -ne 0) { throw 'No arrancó la interfaz original de sismos.' }
    Write-Host 'LISTO: http://127.0.0.1:8094'
}
Write-Host 'Datos cargados.'
