<?php
$p=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);
if(in_array($p,['/app.js','/style.css'],true))return false;
require __DIR__.'/index.php';
