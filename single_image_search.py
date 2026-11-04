"""Adaptador para un servicio autorizado con el formato SingleImageSearch."""
import json
import math
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def encode_request(*, pano=None, location=None, radius=None, photo_age=None):
    # JSON+protobuf representa los números de campo como índices a partir de 1.
    lat, lng = map(float, location.split(",")) if location else (0, 0)
    center = [None, None, lat, lng]
    filters = None
    if photo_age is not None:
        filters = [None] * 10 + [[photo_age["startSeconds"], photo_age["endSeconds"]]]
    options = [filters] + [None] * 7 + [[2], None, [[[2, True, 2]]]]
    request = [["apiv3"], [center, radius or (50 if location else 30)], options, [[2, 6]]]
    if pano:
        request.append([2, pano])
    return request


def decode_response(payload, *, temporal):
    try:
        code = payload[0][0]
        if code == 5:
            return {"status": "NO_RESULTS"}
        if code != 0 or type(code) is not int:
            raise ValueError("El servicio devolvió un estado de error.")
        metadata = payload[1]
        pano_id = metadata[1][1]
        if not isinstance(pano_id, str) or not pano_id:
            raise ValueError("La respuesta no contiene un pano ID válido.")
        result = {"status": "OK", "pano_id": pano_id}
        if not temporal:
            year, month, *_ = metadata[6][7]
            lat, lng = metadata[5][0][1][0][2:4]
            if type(year) is not int or type(month) is not int or not 1 <= month <= 12:
                raise ValueError("La respuesta no contiene un mes y año válidos.")
            if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("La respuesta no contiene coordenadas válidas.")
            result.update(year=year, month=month, location=f"{lat},{lng}")
        return result
    except (IndexError, KeyError, TypeError):
        raise ValueError("Respuesta incompatible con SingleImageSearch.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SingleImageSearch:
    def __init__(self, endpoint, token=None):
        url = urlsplit(endpoint)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not url.hostname or url.username or url.password or url.fragment
                or not (url.scheme == "https" or local and url.scheme == "http")):
            raise ValueError("Configurá una URL HTTPS. HTTP solo se admite para pruebas locales.")
        self.endpoint = endpoint
        self.opener = build_opener(NoRedirect())
        self.headers = {"Content-Type": "application/json+protobuf"}
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.delay = 0 if local else 0.25
        self.last_request = 0.0

    def __call__(self, **query):
        pause = self.delay - (monotonic() - self.last_request)
        if pause > 0:
            sleep(pause)
        request = Request(self.endpoint, data=json.dumps(encode_request(**query)).encode(),
                          headers=self.headers, method="POST")
        self.last_request = monotonic()
        try:
            with self.opener.open(request, timeout=10) as response:
                data = response.read(1_048_577)
        except HTTPError as error:
            if error.code == 429:
                raise ValueError("El servicio limitó las consultas (HTTP 429). Búsqueda detenida.") from None
            raise ValueError(f"El servicio respondió HTTP {error.code}. Búsqueda detenida.") from None
        except (URLError, OSError):
            raise ValueError("No se pudo conectar con el servicio o se agotó el tiempo de espera.") from None
        if len(data) > 1_048_576:
            raise ValueError("La respuesta superó el tamaño permitido.")
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeError):
            raise ValueError("El servicio no devolvió JSON válido.") from None
        return decode_response(payload, temporal="photo_age" in query)
