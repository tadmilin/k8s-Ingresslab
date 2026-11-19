"""app-about: serves /about with the photo and name."""
from common import Handler, page, serve

PHOTO = open("/app/photo.jpg", "rb").read()
BODY = """<main style="text-align:center">
<img src="/about/photo.jpg" alt="ปฐมทัศน์ ภูวนกุลชัย" style="width:min(320px,80vw);border-radius:16px">
<h1 style="margin-bottom:0">ปฐมทัศน์ ภูวนกุลชัย</h1>
<p style="margin-top:0">Pathomtad Phoovanakulchai</p>
<p style="font-size:1.5rem;font-weight:700">68130624</p>
</main>"""


class About(Handler):
    def route(self, path):
        path = path.rstrip("/") or "/"
        if path == "/":
            return self.redirect("/about")
        if path == "/about":
            return self.send(200, page("app-about", "About 68130624", BODY))
        if path == "/about/photo.jpg":
            return self.send(200, PHOTO, "image/jpeg")
        self.send(404, "not found", "text/plain")


serve(About)
