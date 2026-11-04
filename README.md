
<h1 align="center">Street View Timestamp Finder</h1>



<p align="center">
<img alt="Street View Timestamp" src="http://imgfz.com/i/XtH0bsP.png" title="StreetView-Timestamp-Finder">
</p>
<br>





Programa simple de consola en Python que consulta la fecha de captura de panorámicas de Google Street View en cualquier país. Muestra el país, la localidad y las coordenadas. Cuando hay una hora de captura disponible, también muestra el día de la semana y la hora local en formato de 24 horas. Si la ubicación es aproximada, lo indica en el resultado.

<p align="center">
<img alt="Street View Timestamp" src="http://imgfz.com/i/f7z2XcN.png" title="StreetView-Timestamp-Finder">
</p>
<br>

## Instalación y uso

Requiere Python 3.10 o posterior. Abrí PowerShell en la carpeta del proyecto y ejecutá:


```powershell
py -m pip install -r requirements.txt
py .\GoogleMapsHourFinder.py -v "URL_COMPLETA_DE_GOOGLE_MAPS"
```

Si omitís `-v`, el programa te pide que pegues el enlace. Detecta la zona horaria por coordenadas. Podés elegir otra con `--zona Europe/Paris`.

La consulta en vivo predeterminada se hace directamente a Google y no pide clave. Si ya tenés una marca UTC, podés usar `--marca "2025-10-09T12:41:44Z"`. La opción `--metadatos` consulta la fecha publicada con una clave de Street View Static API.

## Ejemplo de salida

<p align="center">
<img alt="Street View Timestamp" src="http://imgfz.com/i/lfN2Sbd.png" title="StreetView-Timestamp-Finder">
</p>
<br>

## Cómo obtiene la hora

El programa extrae el identificador de la panorámica y consulta sus metadatos. Usa el mes de captura como punto de partida para una búsqueda binaria con el filtro `photoAge`. Si encuentra una coincidencia, acota la marca UTC a un intervalo de hasta dos segundos y la convierte a la hora local del lugar.

La búsqueda predeterminada cubre un radio de 30 metros, por lo que el resultado puede corresponder a otro fotograma. Para exigir que coincida el identificador de la panorámica, usá `--verificar-pano`.

La consulta se realiza mediante `SingleImageSearch`, un servicio interno de Google que puede cambiar. Podés configurar otro servicio compatible con `--endpoint`.
