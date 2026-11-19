# -*- coding: utf-8 -*-
"""Collect text evidence into docs/evidence/: kubectl get/describe/logs output and checked HTTP tests.

Needs minikube running and the app deployed (deploy.cmd). Run from the repository root: python tools/collect.py
Set KUBECTL to a kubectl path if kubectl is not on PATH. Exits with 1 when a test fails.
"""
import datetime
import http.client
import json
import os
import pathlib
import subprocess
import sys
from urllib.parse import quote

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "evidence"
KUBECTL = os.environ.get("KUBECTL", "kubectl")
NS = ["-n", "id624"]
SEED = (REPO / "apps" / "research" / "research.txt").read_text(encoding="utf-8")
PHOTO = (REPO / "apps" / "about" / "photo.jpg").read_bytes()


def sh(argv):
    shown = " ".join(["kubectl" if a == KUBECTL else a for a in argv])
    r = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace")
    return f"$ {shown}\n{r.stdout}{r.stderr}".rstrip() + "\n"


def k(*args):
    return [KUBECTL, *args]


def save(name, argvs):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (OUT / name).write_text(f"# collected {stamp}\n\n" + "\n".join(sh(a) for a in argvs), encoding="utf-8")


IP = subprocess.run(["minikube", "ip"], capture_output=True, text=True, check=True).stdout.strip()


def req(host, method, path, body=None):
    """One request straight to the ingress IP with a Host header; redirects are not followed."""
    c = http.client.HTTPConnection(IP, 80, timeout=15)
    c.request(method, path, body=body, headers={"Host": host, **({"Content-Type": "application/x-www-form-urlencoded"} if body else {})})
    r = c.getresponse()
    return r.status, r.getheader("Location", ""), r.getheader("Content-Type", ""), r.read()


def pods_seen(host, path, n=24):
    names = set()
    for _ in range(n):
        body = req(host, "GET", path)[3].decode("utf-8")
        names.add(body.split("pod ")[1].split("<")[0].strip())
    return sorted(names)


RESULTS = []


def check(tid, desc, url, expected, got, ok):
    RESULTS.append({"id": tid, "desc": desc, "url": url, "expected": expected, "got": got, "ok": bool(ok)})
    print(("PASS" if ok else "FAIL"), tid, desc, "->", got)


def tests():
    www, adm = "www.id-624.com", "admin.id-624.com"
    s, loc, _, _ = req(www, "GET", "/")
    check("T1", "www root redirects to /about", "http://www.id-624.com/", "302 -> /about", f"{s} -> {loc}", s == 302 and loc.endswith("/about"))
    s, _, t, b = req(www, "GET", "/about")
    check("T2", "/about shows name and ID, app-about", "http://www.id-624.com/about", "200, 68130624, photo",
          f"{s}, {len(b)}B", s == 200 and "68130624".encode() in b and b"/about/photo.jpg" in b and "ปฐมทัศน์ ภูวนกุลชัย".encode() in b)
    s, _, t, b = req(www, "GET", "/about/photo.jpg")
    check("T3", "photo is served unchanged", "http://www.id-624.com/about/photo.jpg", "200 image/jpeg, same bytes as apps/about/photo.jpg",
          f"{s} {t}, {len(b)}B", s == 200 and t == "image/jpeg" and b == PHOTO)
    title = SEED.split("\n", 1)[0]
    s, _, _, b = req(www, "GET", "/research")
    check("T4", "/research shows the summary, app-research", "http://www.id-624.com/research", "200 and the summary title",
          f"{s}, title {'found' if title.encode() in b else 'missing'}", s == 200 and title.encode() in b)
    s, _, _, b = req(www, "GET", "/api/hello")
    check("T5", "/api/<text> shows text big and centred", "http://www.id-624.com/api/hello", '200, <main class="big">hello</main>',
          f"{s}", s == 200 and b'<main class="big">hello</main>' in b)
    thai = "สวัสดี K8s"
    s, _, _, b = req(www, "GET", "/api/" + quote(thai))
    check("T6", "/api handles Thai and spaces", "http://www.id-624.com/api/%E0%B8%AA...%20K8s", "200, Thai text unchanged",
          f"{s}", s == 200 and f'<main class="big">{thai}</main>'.encode() in b)
    s, _, _, b = req(www, "GET", "/api/" + quote("<b>hi</b>", safe=""))
    check("T7", "/api escapes HTML", "http://www.id-624.com/api/%3Cb%3Ehi%3C%2Fb%3E", "200, &lt;b&gt;hi&lt;/b&gt;, no raw <b>",
          f"{s}", s == 200 and b"&lt;b&gt;hi&lt;/b&gt;" in b and b"<b>hi</b>" not in b)
    s, loc, _, _ = req(adm, "GET", "/")
    check("T8", "admin root redirects to /edit", "http://admin.id-624.com/", "302 -> /edit", f"{s} -> {loc}", s == 302 and loc.endswith("/edit"))
    s, _, _, b = req(adm, "GET", "/edit")
    check("T9", "admin /edit shows the editor with the summary", "http://admin.id-624.com/edit", "200, textarea",
          f"{s}", s == 200 and b"<textarea" in b and title.encode() in b)
    s, _, _, _ = req(www, "GET", "/edit")
    check("T10", "editor is not reachable on the www host", "http://www.id-624.com/edit", "404", f"{s}", s == 404)
    s, _, _, _ = req(www, "GET", "/api")
    check("T11", "/api without text gives a hint (404)", "http://www.id-624.com/api", "404", f"{s}", s == 404)
    s, _, _, _ = req(www, "HEAD", "/about")
    check("T12", "HEAD works", "HEAD http://www.id-624.com/about", "200", f"{s}", s == 200)
    marker = "[collect-check] "
    post = lambda text: req(adm, "POST", "/edit", "text=" + quote(text))[:2]
    try:
        s, loc = post(marker + SEED)
        seen = {req(www, "GET", "/research")[3].decode().count(marker) for _ in range(12)}
        check("T13", "saved text is shown at once by every replica", "POST http://admin.id-624.com/edit", "303, then 12 reads all show it",
              f"{s}, reads {sorted(seen)}", s == 303 and seen == {1})
    finally:
        post(SEED)
    s, _, _, b = req(www, "GET", "/research")
    check("T14", "original summary restored after the test", "http://www.id-624.com/research", "title without marker",
          f"{s}", title.encode() in b and marker.encode() not in b)
    for sub, app, host, path in [("a", "app-about", www, "/about"), ("b", "app-api", www, "/api/x"), ("c", "app-research", www, "/research")]:
        names = pods_seen(host, path)
        check("T15" + sub, f"two replicas answer for {app}", f"http://{host}{path} x24", "2 different Pods", f"{len(names)}: {', '.join(names)}", len(names) == 2)
    ready = subprocess.run(k("get", "deploy", *NS, "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.availableReplicas}/{.spec.replicas} {end}"),
                           capture_output=True, text=True).stdout.strip()
    check("T16", "all Deployments are available", "kubectl get deploy -n id624", "2/2 each", ready,
          ready.count("=2/2") == 3)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    save("01-cluster.txt", [["minikube", "version"], ["minikube", "status"], ["minikube", "ip"], k("version"),
                            k("get", "nodes", "-o", "wide"), k("get", "ingressclass"),
                            k("get", "pods,svc", "-n", "ingress-nginx", "-o", "wide")])
    save("02-get.txt", [k("get", "all,ingress,pvc,cm", *NS, "-o", "wide"), k("get", "endpoints", *NS), k("get", "pv")])
    save("03-describe-ingress.txt", [k("describe", "ingress", *NS)])
    save("04-describe-workload.txt", [k("describe", "svc", *NS), k("describe", "pvc", "research-data", *NS),
                                      k("describe", "deploy", "app-research", *NS)])
    tests()
    save("05-logs.txt", [k("logs", "deploy/app-about", *NS, "--tail=5"), k("logs", "deploy/app-api", *NS, "--tail=5"),
                         k("logs", "deploy/app-research", *NS, "--tail=5")])
    (OUT / "results.json").write_text(json.dumps(
        {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ip": IP, "results": RESULTS}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    bad = [r["id"] for r in RESULTS if not r["ok"]]
    print("FAILED:", bad if bad else "none")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
