"""app-research: /research shows the summary, /edit changes it. The text lives on a PVC at /data."""
import html
import os
from urllib.parse import parse_qs

from common import POD, Handler, page, serve

DATA, SEED = "/data/research.txt", "/seed/research.txt"
MAX_BODY = 200_000  # bytes; Thai text grows 9x when URL-encoded by the form

if not os.path.exists(DATA):  # first start only; replicas copy the same content, so a race is harmless
    with open(SEED, "rb") as src, open(DATA, "wb") as dst:
        dst.write(src.read())


def current():
    with open(DATA, encoding="utf-8") as f:
        return f.read()


def article(text):
    title, _, rest = text.strip().partition("\n")
    paragraphs = "".join(f"<p>{html.escape(p.strip())}</p>" for p in rest.split("\n\n") if p.strip())
    return f"<article><h1>{html.escape(title)}</h1>{paragraphs}</article>"


def editor(saved):
    note = '<p style="color:green"><b>บันทึกแล้ว</b></p>' if saved else ""
    return page("app-research /edit", "แก้ไขสรุปงานวิจัย", f"""<main><h1>แก้ไขสรุปงานวิจัย</h1>{note}
<form method="post" action="/edit"><textarea name="text" rows="16">{html.escape(current())}</textarea>
<p>บรรทัดแรกคือหัวข้อ เว้นบรรทัดว่างหนึ่งบรรทัดเพื่อขึ้นย่อหน้าใหม่</p><button>บันทึก</button></form></main>""")


class Research(Handler):
    def route(self, path):
        if path.rstrip("/") == "/research":
            return self.send(200, page("app-research", "Research", article(current())))
        if path.rstrip("/") == "/edit":
            return self.send(200, editor("saved=1" in self.path))
        self.send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path.split("?", 1)[0].rstrip("/") != "/edit":
            return self.send(404, "not found", "text/plain")
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            return self.send(413, "too large", "text/plain")
        text = parse_qs(self.rfile.read(size).decode("utf-8")).get("text", [""])[0].replace("\r\n", "\n").strip()
        if not text:
            return self.send(400, "empty text", "text/plain")
        tmp = f"{DATA}.{POD}.tmp"  # pod name: replicas share the volume, so pid 1 would collide
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        os.replace(tmp, DATA)
        self.redirect("/edit?saved=1", 303)


serve(Research)
