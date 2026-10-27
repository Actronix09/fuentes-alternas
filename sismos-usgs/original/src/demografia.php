<?php
// Contexto demográfico oficial añadido en fuentes-alternas.
require_once __DIR__ . '/config_local.php';
header('Location: ' . rtrim($FA_URL_VALIDACION, '/') . '/demografia/');
