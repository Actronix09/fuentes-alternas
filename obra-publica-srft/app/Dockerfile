# Imagen única para el ETL y para la API web (cambia solo el comando)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /proyecto/app

COPY app/requirements.txt .
RUN pip install -r requirements.txt

COPY app /proyecto/app
COPY original /proyecto/original
COPY db /proyecto/db

# El usuario se fija en compose.yml (por defecto 1000:1000) para que los
# archivos descargados en ./datos pertenezcan al usuario del equipo.
CMD ["python", "etl.py"]
