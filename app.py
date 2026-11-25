"""LAN/VPN POC server. Exports are built and checked in memory; no STL history."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path
import io, json, logging, os, threading, unicodedata
import trimesh
from generador import generate, preview, audit, ROOT

VERSION = '0.1.0'
COMMIT = os.environ.get('ORNAMENT_COMMIT', 'development')
GEOMETRY_SLOT = threading.BoundedSemaphore(1)
LOG = logging.getLogger('ornament-it')

class Handler(BaseHTTPRequestHandler):
    server_version = 'ornament-it/' + VERSION

    def respond(self, code, body, content_type, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (extra or {}).items(): self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def json_response(self, code, payload):
        self.respond(code, json.dumps(payload, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/healthz':
            self.json_response(200, {'status': 'ok', 'version': VERSION, 'commit': COMMIT})
            return
        if url.path == '/':
            self.respond(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            return
        if url.path not in ('/preview', '/export'):
            self.json_response(404, {'error': 'Ruta no encontrada.'})
            return
        if len(self.path) > 2048:
            self.json_response(414, {'error': 'La solicitud es demasiado larga.'})
            return
        if not GEOMETRY_SLOT.acquire(blocking=False):
            self.json_response(429, {'error': 'Hay otra generación en curso. Vuelve a intentarlo en unos segundos.'})
            return
        try:
            q = parse_qs(url.query)
            args = (q.get('nombre', ['Elisa'])[0], float(q.get('tamano', ['19.5'])[0]), float(q.get('posicion', ['0'])[0]))
            if url.path == '/preview':
                svg, report = preview(*args)
                self.json_response(200, {'svg': svg, 'info': report})
            else:
                mesh, report = generate(*args)
                body = mesh.export(file_type='stl')
                checked = audit(trimesh.load_mesh(io.BytesIO(body), file_type='stl', process=True))
                if checked['piezas'] != 2 or not checked['cerrada'] or checked['bordes_abiertos'] or checked['aristas_non_manifold']:
                    raise ValueError('El archivo exportado no supera la comprobación.')
                normalized = unicodedata.normalize('NFKD', report['nombre']).encode('ascii', 'ignore').decode()
                slug = ''.join(c.lower() for c in normalized if c.isalnum() or c == '-') or 'nombre'
                filename = f'adorno-{slug}.stl'
                self.respond(200, body, 'model/stl', {'Content-Disposition': f'attachment; filename="{filename}"'})
        except ValueError as exc:
            self.json_response(400, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            LOG.info('Cliente desconectado durante la respuesta')
        except Exception:
            LOG.exception('Error al generar el adorno')
            self.json_response(500, {'error': 'No se pudo generar el adorno. Consulta los registros del servicio.'})
        finally:
            GEOMETRY_SLOT.release()

    def log_message(self, fmt, *args):
        # Avoid recording names or request query strings in logs.
        LOG.info('%s request completed', self.command)


def make_server(host=None, port=None):
    return ThreadingHTTPServer((host or os.environ.get('ORNAMENT_HOST', '0.0.0.0'), int(port if port is not None else os.environ.get('ORNAMENT_PORT', '8768'))), Handler)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    server = make_server()
    LOG.info('ornament-it %s listening on %s:%s', VERSION, *server.server_address)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
