# -*- coding: utf-8 -*-
"""Capture evidence screenshots of real windows (Chrome and PowerShell consoles), never the whole screen.

Chrome is driven over the DevTools protocol (typing, clicking). Each step is grabbed with PrintWindow, so
the address bar with www.id-624.com / admin.id-624.com is visible. Chrome maps both names to the minikube
IP with a flag, so the Windows hosts file stays untouched.

Needs: Windows, Chrome, minikube running with the app deployed, `pip install pillow websocket-client`.
Run from the repository root:  python tools/capture.py
Set KUBECTL to a kubectl.exe path if kubectl is not on PATH. Output: docs/screenshots/*.png + shots.json.
"""
import ctypes
import ctypes.wintypes as W
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import quote

import websocket
from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "screenshots"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
KUBECTL = os.environ.get("KUBECTL", "kubectl")
MARK = "[admin-edit-8421] "  # typed in front of the title through the admin page
COLS, LINES = 150, 60

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
dwmapi = ctypes.WinDLL("dwmapi")
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixel sizes
for fn, res, args in [
    (user32.GetWindowDC, ctypes.c_void_p, [W.HWND]),
    (user32.ReleaseDC, ctypes.c_int, [W.HWND, ctypes.c_void_p]),
    (user32.PrintWindow, W.BOOL, [W.HWND, ctypes.c_void_p, W.UINT]),
    (gdi32.CreateCompatibleDC, ctypes.c_void_p, [ctypes.c_void_p]),
    (gdi32.CreateCompatibleBitmap, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
    (gdi32.SelectObject, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p]),
    (gdi32.GetDIBits, ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p, W.UINT, W.UINT, ctypes.c_void_p,
                                     ctypes.c_void_p, W.UINT]),
    (gdi32.DeleteObject, W.BOOL, [ctypes.c_void_p]),
    (gdi32.DeleteDC, W.BOOL, [ctypes.c_void_p]),
]:
    fn.restype, fn.argtypes = res, args


class BIH(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def grab(hwnd):
    """PrintWindow(PW_RENDERFULLCONTENT) of one window, cropped to its visible frame."""
    r, f = W.RECT(), W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(f), ctypes.sizeof(f))  # DWMWA_EXTENDED_FRAME_BOUNDS
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)
    gdi32.SelectObject(mdc, old)
    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    return img.crop((f.left - r.left, f.top - r.top, f.right - r.left, f.bottom - r.top))


def windows(match):
    found = []
    proto = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) and match(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(proto(cb), 0)
    return found


def title_of(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def pid_of(hwnd):
    owner = W.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return owner.value


def kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def trim_bottom(img, top=60, margin=14, scrollbar=40):
    """Drop the empty console rows below the last line of output."""
    body = img.crop((0, top, img.width - scrollbar, img.height)).convert("L").point(lambda v: 255 if v > 70 else 0)
    box = body.getbbox()
    return img if not box else img.crop((0, 0, img.width, min(img.height, top + box[3] + margin)))


PS_HEAD = """$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PATH += ';C:\\Program Files (x86)\\VMware\\VMware Workstation'
{alias}
Set-Location '{here}'
$Host.UI.RawUI.WindowTitle = '{title} | ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
mode con cols={cols} lines={lines}
Clear-Host
function Show([string]$c) {{
  Write-Host ('PS ' + $PWD.Path + '> ') -NoNewline
  Write-Host $c -ForegroundColor Yellow
}}
Write-Host ('# ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' | {label}') -ForegroundColor Cyan
"""


def terminal(name, label, cmds):
    """Run commands in a new console window (conhost + PowerShell) and capture that window only."""
    title = f"evidence-{name}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        marker = tmp / "done"
        alias = f"Set-Alias kubectl '{KUBECTL}'" if KUBECTL != "kubectl" else ""
        body = PS_HEAD.format(alias=alias, here=REPO, title=title, cols=COLS, lines=LINES, label=label)
        # script scope, so variables such as $ip survive between commands
        body += "".join(f"Show @'\n{c}\n'@\nInvoke-Expression @'\n{c}\n'@ | Out-Host\n" for c in cmds)
        body += f"Set-Content -LiteralPath '{marker}' done\n"
        script = tmp / f"{name}.ps1"
        script.write_text(body, encoding="utf-8-sig")
        started = datetime.datetime.now()
        p = subprocess.Popen(["conhost.exe", "powershell.exe", "-NoProfile", "-NoExit", "-ExecutionPolicy",
                              "Bypass", "-File", str(script)], creationflags=subprocess.CREATE_NEW_CONSOLE)
        try:
            deadline = time.time() + 240
            while not marker.exists() and time.time() < deadline:
                time.sleep(0.5)
            time.sleep(1.5)  # let the final prompt render
            found = windows(lambda h: title_of(h).startswith(title + " | "))
            if not found:
                raise RuntimeError(f"window {title} not found")
            img = trim_bottom(grab(found[0]))
        finally:
            kill_tree(p.pid)
    img.save(OUT / f"{name}.png")
    print(f"{name}.png {img.size}")
    return {"file": f"{name}.png", "kind": "terminal", "label": label, "cmds": cmds,
            "time": started.strftime("%Y-%m-%d %H:%M:%S")}


class Chrome:
    """One real Chrome window with its own profile, driven by DevTools, captured by PrintWindow."""

    def __init__(self, ip, port=9333, extra=()):
        rules = f"MAP www.id-624.com {ip}, MAP admin.id-624.com {ip}"
        self.prof = tempfile.mkdtemp()
        # show full URLs: by default Chrome hides "www." and "http://" in the address bar
        (pathlib.Path(self.prof) / "Default").mkdir()
        (pathlib.Path(self.prof) / "Default" / "Preferences").write_text('{"omnibox":{"prevent_url_elisions":true}}')
        self.proc = subprocess.Popen([
            CHROME, *extra, f"--user-data-dir={self.prof}", f"--remote-debugging-port={port}",
            # --test-type hides the "unsupported command-line flag" bar that --host-resolver-rules would show
            f"--host-resolver-rules={rules}", "--test-type", "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--disable-gpu", "--disable-gpu-compositing",
            # keep painting when another window covers Chrome; stop Chrome 154+ from upgrading our http:// URLs to
            # https:// (the ingress has no certificate, so the upgrade ends in ERR_BLOCKED_BY_CLIENT)
            "--disable-features=CalculateNativeWinOcclusion,HttpsUpgrades,HttpsFirstBalancedMode,"
            "HttpsFirstBalancedModeAutoEnable,HttpsFirstModeV2ForTypicallySecureUsers,HttpsFirstModeV2ForEngagedSites,"
            "HttpsFirstModeForEngagedSites,HttpsFirstModeIncognito,HttpsFirstModeWithEngagementHeuristic",
            "--disable-backgrounding-occluded-windows",
            "--window-position=40,40", "--window-size=1280,820", "--new-window", "about:blank"])
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("chrome DevTools did not start")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.n = 0

    def cmd(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        return self.cmd("Runtime.evaluate", expression=expr, returnByValue=True)["result"].get("value")

    def wait_loaded(self, contains):
        time.sleep(0.5)
        for _ in range(60):
            if self.js("document.readyState") == "complete" and contains in self.js("location.href"):
                return
            time.sleep(0.5)
        raise RuntimeError(f"page did not load: {contains}")

    def go(self, url, contains=None):
        self.cmd("Page.navigate", url=url)
        self.wait_loaded(contains or url.split("//", 1)[1])
        for kind in ("mousePressed", "mouseReleased"):  # click the page margin so the address bar is not left selected
            self.cmd("Input.dispatchMouseEvent", type=kind, x=4, y=400, button="left", clickCount=1)

    def shot(self, name, label, url_note="", settle=1.0):
        time.sleep(settle)
        def area(h):
            r = W.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            return (r.right - r.left) * (r.bottom - r.top)
        # the process also owns small helper windows; the browser window is the biggest one
        hwnd = max(windows(lambda h: pid_of(h) == self.proc.pid), key=area)
        for _ in range(20):
            img = grab(hwnd)
            lo, hi = img.crop((0, 160, img.width, img.height)).convert("L").getextrema()
            if hi - lo > 40:  # first frames can be blank under PrintWindow
                break
            time.sleep(1)
        else:
            raise RuntimeError("chrome page stayed blank")
        img.save(OUT / f"{name}.png")
        print(f"{name}.png {img.size}")
        return {"file": f"{name}.png", "kind": "chrome", "label": label, "url": url_note or self.js("location.href"),
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    def close(self):
        self.ws.close()
        kill_tree(self.proc.pid)
        time.sleep(1)


def restore_summary(ip):
    """Put the original summary back through the same POST the admin form sends."""
    text = (REPO / "apps" / "research" / "research.txt").read_text(encoding="utf-8")
    req = urllib.request.Request(f"http://{ip}/edit", headers={"Host": "admin.id-624.com"},
                                 data=("text=" + quote(text)).encode())
    urllib.request.urlopen(req, timeout=15).read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ip = subprocess.run(["minikube", "ip"], capture_output=True, text=True, check=True).stdout.strip()
    ns = "-n id624"
    h = '$ip = minikube ip; $h = "--resolve","www.id-624.com:80:$ip","--resolve","admin.id-624.com:80:$ip"'
    pods = ("1..8 | % {{ curl.exe -s @h {url} }} | sls 'pod (app-[a-z0-9-]+)' | "
            "% {{ $_.Matches[0].Groups[1].Value }} | group -NoElement | ft Count,Name -AutoSize")
    urls = ["http://www.id-624.com/", "http://www.id-624.com/about", "http://www.id-624.com/about/photo.jpg",
            "http://www.id-624.com/research", "http://www.id-624.com/api/hello",
            "http://www.id-624.com/api/%E0%B8%AA%E0%B8%A7%E0%B8%B1%E0%B8%AA%E0%B8%94%E0%B8%B5%20K8s",
            "http://www.id-624.com/api/%3Cb%3Ehi%3C%2Fb%3E", "http://www.id-624.com/api",
            "http://www.id-624.com/edit", "http://admin.id-624.com/", "http://admin.id-624.com/edit"]
    matrix = ("foreach ($u in " + ",".join(f"'{u}'" for u in urls) + ") { curl.exe -s -o NUL -w "
              '"%{http_code}  %{content_type}  %{size_download}B  $u  %{redirect_url}`n" @h $u }')
    only = set(sys.argv[1:])  # e.g. "term-get chrome": redo just these; no argument redoes everything
    meta_path = OUT / "shots.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    shots = [
        ("term-get", "kubectl get: node, Pod, Service, Deployment, Ingress, PVC, ConfigMap", [
            "minikube status", "kubectl get nodes -o wide", f"kubectl get deploy,pods,svc,ingress,pvc {ns} -o wide"]),
        ("term-describe-ingress", "kubectl describe ingress", [f"kubectl describe ingress {ns}"]),
        ("term-describe-svc", "kubectl describe svc, endpoints and PVC", [
            f"kubectl describe svc {ns}", f"kubectl get endpoints {ns}", f"kubectl describe pvc research-data {ns}"]),
        ("term-describe-deploy", "kubectl describe deployment app-research", [
            f"kubectl describe deploy app-research {ns}"]),
        ("term-curl", "curl tests with the host name mapped to the minikube IP", [h, matrix]),
        ("term-curl-security", "HEAD request, security headers, HTML escaping", [
            h, "curl.exe -sI @h http://www.id-624.com/about",
            r"curl.exe -s @h http://www.id-624.com/api/%3Cb%3Ehi%3C%2Fb%3E | sls '<main[^>]*>.*?</main>' | % { $_.Matches.Value }"]),
        ("term-lb", "Load balancing: replies per Pod (8 requests each)", [
            h, pods.format(url="http://www.id-624.com/about"), pods.format(url="http://www.id-624.com/research"),
            pods.format(url="http://www.id-624.com/api/x")]),
    ]
    for name, label, cmds in shots:
        if not only or name in only:
            meta[name] = terminal(name, label, cmds)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if only and "chrome" not in only:
        return

    chrome = Chrome(ip)
    try:
        for name, label, path in [
            ("chrome-about", "www.id-624.com/about : app-about shows the photo, name and ID", "/about"),
            ("chrome-research", "www.id-624.com/research : app-research shows the summary", "/research"),
            ("chrome-api-1", "www.id-624.com/api/สวัสดี K8s : app-api shows the text big and centred", "/api/สวัสดี K8s"),
            ("chrome-api-2", "www.id-624.com/api/<b>hi</b> : HTML is escaped, shown as plain text", "/api/<b>hi</b>"),
        ]:
            chrome.go("http://www.id-624.com" + quote(path, safe="/<>"), "id-624.com/" + path.split("/")[1])
            meta[name] = chrome.shot(name, label)
        chrome.go("http://admin.id-624.com/", "/edit")
        meta["chrome-admin-1"] = chrome.shot("chrome-admin-1", "admin.id-624.com : redirected to /edit, the editor of app-research")
        chrome.cmd("Page.bringToFront")
        chrome.js("var t=document.querySelector('textarea'); t.focus(); t.setSelectionRange(0,0)")
        chrome.cmd("Input.insertText", text=MARK)
        meta["chrome-admin-2"] = chrome.shot("chrome-admin-2", f"typed '{MARK.strip()}' in front of the title (not saved yet)")
        chrome.js("document.querySelector('button').click()")
        chrome.wait_loaded("saved=1")
        meta["chrome-admin-3"] = chrome.shot("chrome-admin-3", "after Save: the editor shows 'บันทึกแล้ว'")
        chrome.go("http://www.id-624.com/research")
        meta["chrome-research-edited"] = chrome.shot("chrome-research-edited", "www.id-624.com/research : the new title appears at once")
        meta["term-persist"] = terminal("term-persist", "Persistence: delete both app-research Pods, the edit stays", [
            h, f"kubectl get pods {ns} -l app=app-research", f"kubectl delete pod {ns} -l app=app-research",
            f"kubectl wait {ns} --for=condition=ready pod -l app=app-research --timeout=120s",
            f"kubectl get pods {ns} -l app=app-research",
            "curl.exe -s @h http://www.id-624.com/research | sls 'admin-edit-\\d+' | % { $_.Matches.Value }"])
        chrome.go("http://www.id-624.com/research")
        meta["chrome-research-restart"] = chrome.shot("chrome-research-restart", "www.id-624.com/research : still edited after the Pods were recreated")
    finally:
        chrome.close()
        restore_summary(ip)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", meta_path)


if __name__ == "__main__":
    main()
