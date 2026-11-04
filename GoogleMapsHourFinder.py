# ==========================================
# StreetView-Timestamp-Finder
# Created by FacuSecX
# https://github.com/FacuSecX/StreetView-Timestamp-Finder
# ==========================================

"""GoogleMapsHourFinder. Consultá la fecha de una panorámica de Street View."""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
import os
import re
import sys
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from single_image_search import SingleImageSearch


ENDPOINT = "https://maps.googleapis.com/maps/api/streetview/metadata"
PANO = r"[A-Za-z0-9_-]{22}"
STREET_VIEW_SEARCH = (
    "https://maps.googleapis.com/$rpc/"
    "google.internal.maps.mapsjs.v1.MapsJsInternalService/SingleImageSearch"
)
WEEKDAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
ZONE_LABELS = {"Europe/Paris": "Francia", "America/Argentina/Cordoba": "Córdoba, Argentina"}


def format_local_capture(capture, zone):
    local = capture.astimezone(zone)
    day = WEEKDAYS[local.weekday()]
    month = MONTHS[local.month - 1]
    offset = int(local.utcoffset().total_seconds())
    hours, remainder = divmod(abs(offset), 3600)
    minutes, seconds = divmod(remainder, 60)
    gmt = f"GMT{'+' if offset >= 0 else '-'}{hours}"
    if remainder:
        gmt += f":{minutes:02d}"
    if seconds:
        gmt += f":{seconds:02d}"
    label = ZONE_LABELS.get(zone.key, zone.key)
    return f"{day} {local.day} de {month} de {local.year} {local:%H:%M:%S} (Horario {label} {gmt})"


def supports_color():
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        return False
    if os.name != "nt":
        return os.environ.get("TERM") != "dumb"
    import ctypes
    import msvcrt
    from ctypes import wintypes

    console = ctypes.WinDLL("kernel32", use_last_error=True)
    console.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    console.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    handle = msvcrt.get_osfhandle(sys.stdout.fileno())
    mode = wintypes.DWORD()
    return bool(console.GetConsoleMode(handle, ctypes.byref(mode))
                and console.SetConsoleMode(handle, mode.value | 0x0004))


def clear_console():
    if not sys.stdout.isatty():
        return
    if os.name == "nt":
        os.system("cls")
    elif os.environ.get("TERM") != "dumb":
        print("\033[2J\033[H", end="", flush=True)


def show_banner():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    color = supports_color()
    if color:
        print("\033[96m", end="")
    for letter in "Street View Timestamp Finder":
        print(letter, end="", flush=True)
        sleep(0.025)
    print("\033[0m" if color else "")
    print("for Google Street View")
    print("Creado por FacuSecX")
    print("https://github.com/FacuSecX\n")


def show_fields(location, date_value):
    country, city, coordinates = location_fields(location)
    color = supports_color()
    fields = (("País", country), ("Ciudad", city), ("Coordenadas", coordinates), ("Fecha", date_value))
    width = max(len(label) + 2 + len(value) for label, value in fields)
    border = "+" + "-" * (width + 2) + "+"
    blank = "|" + " " * (width + 2) + "|"
    print(f"\n{border}")
    for index, (label, value) in enumerate(fields):
        if index:
            print(blank)
        padding = " " * (width - len(label) - 2 - len(value))
        row = f"{label}: {value}"
        if color:
            row = f"\033[92m{label}:\033[0m \033[96m{value}\033[0m"
        print(f"| {row}{padding} |")
    print(border)


def parse_target(raw):
    raw = raw.strip()
    if re.fullmatch(PANO, raw):
        return {"pano": raw}

    coords = raw
    if "://" in raw:
        url = urlsplit(raw)
        if url.hostname in {"maps.app.goo.gl", "goo.gl"}:
            raise ValueError("Abrí el enlace corto y pegá la URL completa de Street View.")
        if (url.scheme != "https"
                or not re.fullmatch(r"(?:(?:www|maps)\.)?google\.(?:com|com\.ar)", url.hostname or "")):
            raise ValueError("Ingresá una URL de Google Maps o un pano ID.")
        query = parse_qs(url.query)
        for name in ("pano", "panoid"):
            if name in query:
                pano = query[name][0]
                if not re.fullmatch(PANO, pano):
                    raise ValueError("El pano ID del enlace tiene un formato no compatible.")
                return {"pano": pano}
        pano = re.search(r"!1s(" + PANO + r")(?=[!/?&#]|$)", unquote(url.path + "?" + url.query))
        if pano:
            return {"pano": pano[1]}
        if "data=" in raw and "!1s" in unquote(raw):
            raise ValueError("No pude leer el pano ID del enlace. Pegá el ID directamente.")
        coords = query.get("viewpoint", [""])[0]
        if not coords:
            position = re.search(r"@([^,/]+,[^,/]+)", url.path)
            coords = position[1] if position else ""
    try:
        lat, lng = map(float, coords.split(","))
    except ValueError:
        raise ValueError("Pegá una URL larga, un pano ID de 22 caracteres o latitud,longitud.") from None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Coordenadas fuera de rango.")
    return {"location": f"{lat},{lng}"}


def metadata(target, key, signature=None):
    params = {**target, "key": key}
    if signature:
        params["signature"] = signature
    try:
        with urlopen(ENDPOINT + "?" + urlencode(params), timeout=10) as response:
            data = json.load(response)
    except HTTPError as error:
        raise ValueError(f"Google respondió HTTP {error.code}. Consultá el estado de la clave o el servicio.") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Falló la conexión HTTPS con Google o se agotó el tiempo de espera.") from None
    except ValueError:
        raise ValueError("Google devolvió una respuesta que no pude leer.") from None
    if not isinstance(data, dict):
        raise ValueError("Formato de metadatos inesperado.")
    status = data.get("status")
    if status != "OK":
        messages = {
            "ZERO_RESULTS": "Google no encontró ese panorama. El ID puede haber cambiado.",
            "NOT_FOUND": "Google no encontró esa ubicación.",
            "REQUEST_DENIED": "Google rechazó la solicitud. Revisá la clave, API habilitada y firma si corresponde.",
            "OVER_QUERY_LIMIT": "Google indicó un límite de uso.",
            "OVER_DAILY_LIMIT": "Google indicó un límite diario o un problema con la cuenta.",
            "INVALID_REQUEST": "Google rechazó los parámetros de la consulta.",
            "UNKNOWN_ERROR": "Google indicó un error temporal.",
        }
        raise ValueError(messages.get(status, "Google devolvió un estado desconocido."))
    if not isinstance(data.get("pano_id"), str):
        raise ValueError("La respuesta de Google no incluyó un pano ID.")
    if "pano" in target and data["pano_id"] != target["pano"]:
        raise ValueError("Google devolvió otro pano ID. No se puede atribuir la fecha al solicitado.")
    return data


def show_metadata(target, data, zone_name):
    location = data.get("location") or {}
    coords = f"{location['lat']},{location['lng']}" if {"lat", "lng"} <= location.keys() else None
    captured = data.get("date")
    date_value = "No informada por Google"
    if captured:
        precision = {4: "año", 7: "mes", 10: "día"}.get(len(captured), "sin especificar")
        date_value = f"{captured} (precisión: {precision}, sin hora)"
    show_fields(coords, date_value)
    if data.get("copyright"):
        print(f"\n{data['copyright']}")
    if "location" in target:
        print("\nBúsqueda por proximidad. Puede ser otro fotograma.")
    if zone_name:
        print(f"Zona horaria: {zone_name}")


def link_location(raw, target):
    if "location" in target:
        return target["location"]
    position = re.search(r"@(-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?)(?=,|/|$)", urlsplit(raw).path)
    return position[1] if position else None


def read_location_json(endpoint, params):
    try:
        with urlopen(f"{endpoint}?{urlencode(params)}", timeout=4) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def french_commune(lat, lng):
    communes = read_location_json("https://geo.api.gouv.fr/communes",
                                  {"lat": lat, "lon": lng, "fields": "nom,code"})
    if isinstance(communes, list) and len(communes) == 1 and isinstance(communes[0], dict):
        commune = communes[0]
        name = commune.get("nom")
        if isinstance(name, str) and name:
            return "París" if commune.get("code") == "75056" else name
    return None


def argentine_municipality(lat, lng):
    data = read_location_json("https://apis.datos.gob.ar/georef/api/v2.0/ubicacion",
                              {"lat": lat, "lon": lng})
    if not isinstance(data, dict) or not isinstance(data.get("ubicacion"), dict):
        return False, None
    location = data["ubicacion"]
    province = location.get("provincia")
    country_confirmed = isinstance(province, dict) and bool(province.get("id"))
    municipality = location.get("gobierno_local") or location.get("municipio")
    name = municipality.get("nombre") if isinstance(municipality, dict) else None
    return country_confirmed, name if isinstance(name, str) and name else None


def location_fields(location):
    country = city = "Sin determinar"
    if location:
        try:
            import reverse_geocode
            from babel import Locale
        except ImportError:
            print("Para detectar país y ciudad, ejecutá py -m pip install -r requirements.txt.")
        else:
            lat, lng = map(float, location.split(","))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                place = reverse_geocode.get((lat, lng))
                country_code = place["country_code"]
                country = Locale.parse("es").territories.get(country_code, place["country"])
                confirmed, municipality = False, None
                if country_code == "FR":
                    municipality = french_commune(lat, lng)
                    confirmed = bool(municipality)
                elif country_code == "AR":
                    confirmed, municipality = argentine_municipality(lat, lng)
                if not confirmed:
                    country += " (aproximado)"
                city = municipality or f"{place['city']} (localidad cercana)"
    coordinates = location.replace(",", ", ") if location else "Sin determinar"
    return country, city, coordinates


def resolve_zone(zone_name, location):
    if zone_name:
        return ZoneInfo(zone_name)
    if location:
        try:
            from timezonefinder import TimezoneFinder
        except ImportError:
            print("Para detectar la zona automáticamente, instalá las dependencias con py -m pip install -r requirements.txt.")
            return None
        try:
            lat, lng = map(float, location.split(","))
        except ValueError:
            lat, lng = float("nan"), float("nan")
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            detected = TimezoneFinder().timezone_at(lng=lng, lat=lat)
            if detected:
                return ZoneInfo(detected)
    print("Zona local sin determinar. Usá una URL con coordenadas o indicá --zona.")
    return None


def bracket(start, end, query, limit=28):
    """query devuelve True si el objetivo aparece en el intervalo, False si está ausente."""
    if not query(start, end):
        return None
    steps = 0
    while end - start > 2 and steps < limit:
        middle = (start + end + 1) // 2
        if query(start, middle):
            end = middle
        else:
            start = middle
        steps += 1
    if end - start > 2:
        raise ValueError("Se agotó el límite de consultas sin alcanzar la resolución buscada.")
    return start, end, steps


class CaptureTimeUnavailable(Exception):
    def __init__(self, month, location):
        self.month = month
        self.location = location


def infer_capture(target, search, *, verify_pano=False):
    """search(**query) devuelve un dict normalizado de SingleImageSearch."""
    initial = search(**target)
    if initial["status"] != "OK":
        raise ValueError("No se encontró el panorama inicial.")
    pano_id = initial["pano_id"]
    if target.get("pano", pano_id) != pano_id:
        raise ValueError("La consulta inicial devolvió otro panorama.")
    month = datetime(initial["year"], initial["month"], 1, tzinfo=timezone.utc)
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    start = int((month - timedelta(days=1)).timestamp())
    end = int((next_month + timedelta(days=1)).timestamp())

    def matching_pano(left, right):
        result = search(
            location=initial["location"],
            radius=1 if verify_pano else 30,
            photo_age={"startSeconds": left, "endSeconds": right},
        )
        if result["status"] == "NO_RESULTS":
            return None
        if result["status"] != "OK":
            raise ValueError("La consulta temporal falló. El intervalo no se puede confirmar.")
        match = result["pano_id"]
        if verify_pano and match != pano_id:
            raise ValueError("La consulta temporal devolvió otro fotograma. Hora sin confirmar.")
        return match

    window = bracket(start, end, lambda left, right: matching_pano(left, right) is not None)
    if window is None:
        raise CaptureTimeUnavailable(month, initial["location"])
    low, high, steps = window
    if high >= end - 10:
        raise CaptureTimeUnavailable(month, initial["location"])
    # Identifica la coincidencia en el intervalo final.
    match = matching_pano(low, high)
    if match is None:
        raise CaptureTimeUnavailable(month, initial["location"])
    return pano_id, low, high, steps + 3, initial["location"], match


def simulate(target, capture):
    """Servidor en memoria con un solo panorama y un reloj conocido."""
    instant = capture.timestamp()
    pano = {
        "status": "OK",
        "pano_id": target.get("pano", "morrison_demo_local_01"),
        "location": target.get("location", "-32.5846056,-62.8327147"),
        "year": capture.year,
        "month": capture.month,
    }

    def search(**query):
        age = query.get("photo_age")
        if age is None or age["startSeconds"] <= instant <= age["endSeconds"]:
            return pano
        return {"status": "NO_RESULTS"}

    return infer_capture(target, search)


def show_estimate(result, zone, location, note=None):
    _, low, high, _, _, _ = result
    midpoint = datetime.fromtimestamp((low + high + 1) // 2, timezone.utc)
    date_value = format_local_capture(midpoint, zone) if zone else midpoint.strftime("%Y-%m-%d %H:%M:%S UTC")
    show_fields(location, date_value)
    if note:
        print(f"\n{note}")


def demo():
    reference = datetime.fromisoformat("2025-07-04T10:47:47-03:00")
    location = "-32.5846056,-62.8327147"
    show_estimate(simulate(parse_target(location), reference),
                  ZoneInfo("America/Argentina/Cordoba"),
                  location, "Demo de Morrison con una hora simulada.")


def show_supplied_capture(raw, target, zone_name, supplied, simulated=False):
    capture = datetime.fromisoformat(supplied.strip().replace("Z", "+00:00"))
    if capture.tzinfo is None:
        raise ValueError("La marca necesita Z o un desplazamiento como -03:00.")
    location = link_location(raw, target)
    zone = resolve_zone(zone_name, location)
    if simulated:
        simulation_target = {**target, "location": location} if location else target
        show_estimate(simulate(simulation_target, capture), zone, location, "Hora simulada para esta prueba.")
        return
    utc = capture.astimezone(timezone.utc)
    date_value = format_local_capture(capture, zone) if zone else utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    show_fields(location, date_value)
    print("\nHora ingresada manualmente. Su asociación con la panorámica queda sin verificar.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Ejemplo: py .\\GoogleMapsHourFinder.py -v "URL_COMPLETA_DE_GOOGLE_MAPS". '
               'Ejecutalo sin URL para pegarla cuando te la pida. Usá --demo para probar sin conexión.',
    )
    parser.add_argument("entrada", nargs="?", help="URL larga, pano ID de 22 caracteres o latitud,longitud")
    parser.add_argument("-v", "--url", metavar="LINK", help="URL de Street View entre comillas")
    parser.add_argument("--zona", help="Zona IANA opcional. Por defecto se detecta por coordenadas.")
    parser.add_argument("--verificar-pano", action="store_true",
                        help="busca en 1 metro y exige que coincida el pano ID")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--marca", help="Marca ISO 8601 obtenida por separado, con Z o desplazamiento UTC")
    mode.add_argument("--demo", action="store_true", help="simulación sin red del caso Morrison")
    mode.add_argument("--simular", metavar="MARCA", help="busca una marca de prueba sin hacer consultas en vivo")
    mode.add_argument("--endpoint", metavar="URL", help="servicio autorizado que implemente SingleImageSearch")
    mode.add_argument("--metadatos", action="store_true", help="consulta oficial de fecha con clave de Google")
    args = parser.parse_args()
    if args.url is not None and args.entrada is not None:
        parser.error("Pasá la URL con -v o como argumento directo, una sola vez.")
    clear_console()
    try:
        if args.demo:
            demo()
            return 0
        show_banner()
        raw = args.url if args.url is not None else args.entrada
        if raw is None:
            prompt = "Copia el link de Google Maps:"
            if supports_color():
                prompt = f"\033[92m{prompt}\033[0m"
            raw = input(f"{prompt} ")
        target = parse_target(raw)
        zone_name = args.zona or os.environ.get("STREETVIEW_ZONA")
        supplied = args.simular or args.marca
        if supplied:
            show_supplied_capture(raw, target, zone_name, supplied, simulated=bool(args.simular))
            return 0
        endpoint = args.endpoint or os.environ.get("STREETVIEW_ENDPOINT")
        if not args.metadatos:
            token = os.environ.get("STREETVIEW_TOKEN") if endpoint else None
            search = SingleImageSearch(endpoint or STREET_VIEW_SEARCH, token)
            result = infer_capture(target, search, verify_pano=args.verificar_pano)
            zone = resolve_zone(zone_name, result[4])
            show_estimate(result, zone, result[4])
            return 0
        print("Modo de metadatos oficiales. Google devuelve la fecha disponible, sin hora.")
        key = (os.environ.get("GOOGLE_MAPS_API_KEY") or getpass.getpass("Clave de Google Maps Platform: ")).strip()
        if not key:
            raise ValueError("Se necesita una clave habilitada para Street View Static API.")
        data = metadata(target, key, os.environ.get("GOOGLE_MAPS_SIGNATURE"))
        location = data.get("location") or {}
        coords = f"{location['lat']},{location['lng']}" if {"lat", "lng"} <= location.keys() else None
        zone = resolve_zone(zone_name, coords)
        show_metadata(target, data, zone.key if zone else None)
        return 0
    except CaptureTimeUnavailable as error:
        month = error.month
        show_fields(error.location, f"{MONTHS[month.month - 1]} de {month.year} (hora sin determinar)")
        sys.stdout.flush()
        parser.exit(1, "\nNo se puede determinar la hora exacta. "
                    "Desplazate hacia un costado o avanzá unos metros en Street View y pegá el nuevo enlace.\n")
    except ZoneInfoNotFoundError:
        parser.exit(1, "Error: zona IANA desconocida o base ausente. Revisá --zona e instalá las dependencias.\n")
    except (ValueError, EOFError, KeyboardInterrupt) as error:
        parser.exit(1, f"Error: {error or 'consulta interrumpida'}\n")


if __name__ == "__main__":
    raise SystemExit(main())
