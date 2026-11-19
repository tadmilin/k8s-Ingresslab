"""Shared by app-about, app-research and app-api: page template, security headers, HTTP server."""
import html
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POD = os.environ.get("HOSTNAME", socket.gethostname())
STYLE = """
:root{color-scheme:light dark}
body{margin:0;padding-bottom:3rem;font-family:system-ui,"Leelawadee UI","Noto Sans Thai",Tahoma,sans-serif;line-height:1.7}
main,article{max-width:46rem;margin:0 auto;padding:2rem 1.25rem}
footer{position:fixed;left:0;right:0;bottom:0;padding:.5rem;text-align:center;font-size:.75rem;opacity:.7;background:Canvas}
textarea{width:100%;box-sizing:border-box;padding:.75rem;font:inherit}
button{padding:.5rem 1.5rem;font:inherit}
"""


def page(app, title, body, css=""):
    return (f'<!doctype html><html lang="th"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{STYLE}{css}</style>{body}"
            f"<footer>ปฐมทัศน์ ภูวนกุลชัย 68130624 · {app} · pod {POD}</footer></html>")


class Handler(BaseHTTPRequestHandler):
    """Subclasses define route(path); POST is optional."""

    def send(self, status, body, ctype="text/html; charset=utf-8", headers=()):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self'")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def redirect(self, to, status=302):
        self.send(status, "", headers=[("Location", to)])

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self.send(200, "ok", "text/plain")
        self.route(path)

    do_HEAD = do_GET


def serve(handler):
    ThreadingHTTPServer(("", 8080), handler).serve_forever()
