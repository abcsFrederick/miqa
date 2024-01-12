<?php
echo 'Authentication code : ' . htmlspecialchars($_GET["code"]);
$url = 'https://fsivgl-rms01p.ncifcrf.gov/rms2/accounts/itrust/login/callback/?code=' . htmlspecialchars($_GET["code"]);
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($curl, CURLOPT_RETURNTRANSFER, 1);
$result = curl_exec($ch);
curl_close($curl);
echo $result;
?>