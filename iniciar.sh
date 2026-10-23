#!/usr/bin/env bash
# Arranque completo en Docker para Linux y macOS (equivalente a iniciar-docker.ps1).
#   ./iniciar.sh              construye, carga lo que falte y comprueba las páginas
#   ./iniciar.sh --recargar   vuelve a ejecutar los ETL desde los archivos conservados
set -euo pipefail
cd "$(dirname "$0")"

export FORZAR_ETL=0
case "${1:-}" in
  --recargar) export FORZAR_ETL=1 ;;
  "") ;;
  *) echo "Uso: $0 [--recargar]" >&2; exit 2 ;;
esac
export HOST_UID="${HOST_UID:-$(id -u)}" HOST_GID="${HOST_GID:-$(id -g)}"

docker info --format '{{.ServerVersion}}' >/dev/null || { echo 'Inicia Docker antes de ejecutar este script.' >&2; exit 1; }

for proyecto in agua-reportes-sacmex obra-publica-srft sismos-usgs; do
  echo "Levantando $proyecto..."
  # En una recarga se repite el ETL aunque su contenedor ya haya terminado antes.
  [ "$FORZAR_ETL" = 1 ] && docker compose -f "$proyecto/compose.yml" rm -fsv etl >/dev/null 2>&1 || true
  docker compose -f "$proyecto/compose.yml" up -d --build --quiet-pull \
    || { echo "No terminó correctamente el arranque de $proyecto. Consulta: docker compose -f $proyecto/compose.yml logs" >&2; exit 1; }
done

esperar() {
  local url=$1
  for _ in $(seq 1 60); do
    curl -fsS --max-time 3 "$url" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "No responde $url. Revisa los registros de Docker." >&2
  exit 1
}

for puerto in 8091 8092 8093; do
  esperar "http://127.0.0.1:$puerto/api/salud"
  echo "LISTO: http://127.0.0.1:$puerto"
done
esperar "http://127.0.0.1:8094/vista.html"
echo "LISTO: http://127.0.0.1:8094"
echo 'Todo funciona en Docker.'
