param([switch]$Recargar)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:FORZAR_ETL = if ($Recargar) { '1' } else { '0' }
& docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Abre Docker Desktop antes de ejecutar este script.' }
& docker compose -f agua-reportes-sacmex/compose.yml -f agua-reportes-sacmex/compose.windows.yml up -d --build
if ($LASTEXITCODE -ne 0) { throw 'No termino correctamente el arranque de agua. Consulta docker compose logs.' }
& docker compose -f obra-publica-srft/compose.yml up -d --build
if ($LASTEXITCODE -ne 0) { throw 'No termino correctamente el arranque de obras. Consulta docker compose logs.' }
& docker compose -f sismos-usgs/compose.yml -f sismos-usgs/compose.windows.yml up -d --build
if ($LASTEXITCODE -ne 0) { throw 'No termino correctamente el arranque de sismos. Consulta docker compose logs.' }
foreach ($puerto in @(8091,8092,8093)) {
    $url = "http://127.0.0.1:$puerto"
    $listo = $false
    for ($i=0; $i -lt 20; $i++) {
        try { if ((Invoke-RestMethod "$url/api/salud" -TimeoutSec 3).ok) { $listo=$true; break } } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $listo) { throw "No responde $url. Revisa los registros de Docker." }
    Write-Host "LISTO: $url"
}
try { Invoke-WebRequest 'http://127.0.0.1:8094/vista.html' -UseBasicParsing -TimeoutSec 10 | Out-Null } catch { throw 'No responde la interfaz original de sismos en http://127.0.0.1:8094.' }
Write-Host 'LISTO: http://127.0.0.1:8094'
Write-Host 'Todo funciona en Docker.'
