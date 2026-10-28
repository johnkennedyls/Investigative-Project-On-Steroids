# preparar_space_app.ps1 - arma la carpeta que se sube al Space de la app
#
# Junta en un solo directorio lo que el Space necesita en su raiz:
#   app.py, llm_client.py, conversacion.py, templates/index.html
#   + Dockerfile, start.sh, requirements.txt, descargar_artefactos.py, README.md
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File deploy\preparar_space_app.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\preparar_space_app.ps1 -Destino C:\ruta\space
#
# Nota: este archivo se mantiene en ASCII a proposito para que Windows
# PowerShell 5.1 (que lee sin BOM como ANSI) no se rompa con acentos ni emojis.
param(
    [string]$Destino = ""
)

$ErrorActionPreference = "Stop"

$DeployDir = $PSScriptRoot
$RepoDir   = Split-Path -Parent $DeployDir
if (-not $Destino) { $Destino = Join-Path $RepoDir "build\hf_space_app" }
$AgenteDir = Join-Path $RepoDir "echopulse_llm_orquestator"
$SpaceSrc  = Join-Path $DeployDir "hf_space_app"

$archivosAgente = @("app.py", "llm_client.py", "conversacion.py")
$archivosSpace  = @("Dockerfile", "start.sh", "requirements.txt", "descargar_artefactos.py", "README.md", ".dockerignore")

Write-Host "[1/3] Preparando el Space de EchoPulse" -ForegroundColor Cyan
Write-Host "      proyecto: $RepoDir"
Write-Host "      destino : $Destino"

foreach ($f in $archivosAgente) {
    if (-not (Test-Path (Join-Path $AgenteDir $f))) { throw "Falta $f en $AgenteDir" }
}
foreach ($f in $archivosSpace) {
    if (-not (Test-Path (Join-Path $SpaceSrc $f))) { throw "Falta $f en $SpaceSrc" }
}
if (-not (Test-Path (Join-Path $AgenteDir "templates\index.html"))) { throw "Falta templates/index.html" }

if (Test-Path $Destino) { Remove-Item $Destino -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $Destino "templates") -Force | Out-Null

foreach ($f in $archivosAgente) { Copy-Item (Join-Path $AgenteDir $f) $Destino }
Copy-Item (Join-Path $AgenteDir "templates\index.html") (Join-Path $Destino "templates")
foreach ($f in $archivosSpace) { Copy-Item (Join-Path $SpaceSrc $f) $Destino -Force }

Write-Host ""
Write-Host "[2/3] Carpeta lista:" -ForegroundColor Green
Get-ChildItem -Path $Destino -Recurse -File |
    ForEach-Object { "      {0,8:N1} KB  {1}" -f ($_.Length / 1KB), $_.FullName.Substring($Destino.Length + 1) }

Write-Host ""
Write-Host "[3/3] Siguiente paso:" -ForegroundColor Yellow
Write-Host "      1. Crea el Space (Docker) en https://huggingface.co/new-space"
Write-Host "      2. Clonalo:  git clone https://huggingface.co/spaces/<usuario>/<space>"
Write-Host "      3. Copia el contenido de $Destino dentro del clon"
Write-Host "      4. git add . ; git commit -m 'EchoPulse AI' ; git push"
