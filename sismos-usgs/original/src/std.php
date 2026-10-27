<?php
// fuentes-alternas: mapa ampliado. Original conservado en std_mexico_legacy.php.
require_once __DIR__ . '/config_local.php';
$parametros = [];
foreach (['anio', 'magnitud', 'pais'] as $clave) {
    if (isset($_GET[$clave]) && is_string($_GET[$clave]) && $_GET[$clave] !== '') {
        $parametros[$clave] = $_GET[$clave];
    }
}
$url = rtrim($FA_URL_VALIDACION, '/') . '/norteamerica/';
if ($parametros) { $url .= '?' . http_build_query($parametros); }
header('Location: ' . $url);
exit;
