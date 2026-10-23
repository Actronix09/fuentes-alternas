<?php
// Añadido en fuentes-alternas. Las páginas originales fijaban credenciales distintas entre sí
// (postgres/postgres, postgres/secreto, localhost); aquí se leen del entorno del contenedor y,
// si no existen, se conservan los valores del repositorio original.
$FA_DB = [
    'host' => getenv('POSTGRES_HOST') ?: 'db',
    'port' => getenv('POSTGRES_PORT') ?: '5432',
    'dbname' => getenv('POSTGRES_DB') ?: 'datawarehouse',
    'user' => getenv('POSTGRES_USER') ?: 'postgres',
    'password' => getenv('POSTGRES_PASSWORD') ?: 'postgres',
];
// Tablero de validación SSN ↔ USGS (servicio web de fuentes-alternas).
$FA_URL_VALIDACION = getenv('URL_VALIDACION') ?: 'http://127.0.0.1:8091';
