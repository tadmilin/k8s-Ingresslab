"""app-api: /api/<text> shows <text> big, in the middle of the screen."""
import html
from urllib.parse import unquote

from common import Handler, page, serve

CSS = ("main.big{min-height:100vh;display:grid;place-items:center;box-sizing:border-box;max-width:none;"
       "font-size:clamp(2.5rem,12vw,9rem);font-weight:700;line-height:1.2;text-align:center;overflow-wrap:anywhere}")


class Api(Handler):
    def route(self, path):
        if path.startswith("/api/") and len(path) > len("/api/"):
            text = unquote(path[len("/api/"):])  # browsers send UTF-8 percent-encoding
            return self.send(200, page("app-api", text[:80], f'<main class="big">{html.escape(text)}</main>', CSS))
        self.send(404, "use /api/<text>", "text/plain")


serve(Api)
