"""Prueba HTTP de punta a punta con datos simulados. No consulta Google."""
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
import unittest

LINK = "https://www.google.com/maps/@-32.5982971,-62.8343569,143a,68.7y,123.27h,78.76t/data=!3m10!1e1!3m8!1su2W091Q9NSK5C63ZZYxmCw!2e0!6shttps:%2F%2Fstreetviewpixels-pa.clients6.google.com%2Fv1%2Fthumbnail%3Fcb_client%3Dmaps_sv.tactile%26w%3D900%26h%3D600%26pitch%3D11.24473378167609%26panoid%3Du2W091Q9NSK5C63ZZYxmCw%26yaw%3D123.26983611280068!7i16384!8i8192!9m2!1b1!2i35?entry=ttu&g_ep=EgoyMDI2MTEwMS4wIKXMDSoASAFQAw%3D%3D"
PANO = "u2W091Q9NSK5C63ZZYxmCw"
CAPTURE = int(datetime.fromisoformat("2025-07-04T14:16:55+00:00").timestamp())
CENTER = [None, None, -32.5982971, -62.8343569]
INITIAL = [[0], [None, [2, PANO], None, None, None, [[None, [CENTER]]],
                 [None] * 7 + [[2025, 7]]]]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append((self.headers["Content-Type"], request))
        temporal = request[2][0]
        code = 200
        if temporal is None:
            response = INITIAL
        elif self.server.mode == "quota":
            code, response = 429, {}
        elif self.server.mode == "no_timestamp":
            response = [[5]]
        elif self.server.mode == "neighbor":
            response = [[0], [None, [2, "vecino"]]]
        else:
            left, right = temporal[10]
            match = "vecino" if self.server.mode == "neighbor_compatible" else PANO
            response = [[0], [None, [2, match]]] if left <= CAPTURE <= right else [[5]]
        body = json.dumps(response).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Integration(unittest.TestCase):
    def run_cli(self, mode):
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            server.mode = mode
            server.requests = []
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                command = [sys.executable, "-X", "utf8", str(Path(__file__).with_name("GoogleMapsHourFinder.py")),
                           "--zona", "America/Argentina/Cordoba",
                           "--endpoint", f"http://127.0.0.1:{server.server_port}/search"]
                if mode != "neighbor":
                    command.extend(["-v", LINK])
                else:
                    command.append("--verificar-pano")
                result = subprocess.run(command, input=LINK + "\n", capture_output=True,
                                        encoding="utf-8", timeout=20)
            finally:
                server.shutdown()
                worker.join()
        return result, server.requests

    def test_timestamp_from_pasted_link(self):
        result, requests = self.run_cli("ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(
            result.stdout,
            r"\+-+\+\n\| País: [^\n]+\|\n\| +\|\n"
            r"\| Ciudad: [^\n]+\|\n\| +\|\n"
            r"\| Coordenadas: -32\.5982971, -62\.8343569 +\|\n\| +\|\n"
            r"\| Fecha: Viernes 4 de julio de 2025 11:16:55 \(Horario Córdoba, Argentina GMT-3\) +\|\n\+-+\+",
        )
        self.assertNotIn("Pano ID:", result.stdout)
        self.assertNotIn("Intervalo UTC:", result.stdout)
        self.assertNotIn("Buscando día y hora", result.stdout)
        self.assertNotIn("\x1b[", result.stdout)
        self.assertEqual(requests[0][0], "application/json+protobuf")
        self.assertEqual(requests[0][1][4], [2, PANO])
        self.assertEqual(requests[1][1][1], [CENTER, 30])
        self.assertEqual(requests[1][1][2][0][10], [1751241600, 1754092800])
        self.assertLessEqual(len(requests), 31)
        print(result.stdout.strip())

    def test_other_panorama_aborts(self):
        result, requests = self.run_cli("neighbor")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("Copia el link de Google Maps: "))
        self.assertIn("otro fotograma", result.stderr)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1][1][1], [CENTER, 1])

    def test_compatible_mode_displays_neighbor_date_without_label(self):
        result, _ = self.run_cli("neighbor_compatible")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Pano ID de la coincidencia:", result.stdout)
        self.assertNotIn("Aviso:", result.stdout)
        self.assertIn("| Fecha: Viernes 4 de julio de 2025 11:16:55", result.stdout)
        self.assertNotIn("(panorámica cercana)", result.stdout)

    def test_no_timestamp_shows_month_and_suggests_moving(self):
        result, requests = self.run_cli("no_timestamp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Fecha: julio de 2025 (hora sin determinar)", result.stdout)
        self.assertIn("No se puede determinar la hora exacta", result.stderr)
        self.assertIn("pegá el nuevo enlace", result.stderr)
        self.assertEqual(len(requests), 2)

    def test_quota_aborts_without_retry(self):
        result, requests = self.run_cli("quota")
        self.assertEqual(result.returncode, 1)
        self.assertIn("HTTP 429", result.stderr)
        self.assertEqual(len(requests), 2)


if __name__ == "__main__":
    unittest.main()
