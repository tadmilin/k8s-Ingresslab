# -*- coding: utf-8 -*-
"""Build the two PDFs in docs/ from the repository files and the evidence that collect.py and capture.py saved.

  docs/K8s-Ingress-Report.pdf   steps: manifests, files, kubectl commands, get/describe output
  docs/Test-Evidence.pdf        test results and a screenshot of every service

Needs Chrome and `pip install pymupdf`. Run from the repository root: python tools/build_pdf.py
"""
import html
import json
import pathlib
import subprocess
import tempfile

import fitz

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS, EVID, SHOTS, BUILD = REPO / "docs", REPO / "docs" / "evidence", REPO / "docs" / "screenshots", REPO / "docs" / "build"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
AUTHOR = "Pathomtad Phoovanakulchai"
REPO_URL = "https://github.com/tadmilin/k8s-Ingresslab"

CSS = """
@page { size: A4; margin: 14mm 13mm 16mm }
body { font-family: "Leelawadee UI", Tahoma, "Noto Sans Thai", sans-serif; font-size: 10.5pt; line-height: 1.6; color: #1b1f24 }
h1 { font-size: 21pt; margin: 0 0 4pt } h2 { font-size: 14pt; margin: 18pt 0 6pt; padding-bottom: 2pt; border-bottom: 2px solid #2b6cb0; break-after: avoid }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; break-after: avoid } h4 { font-size: 10pt; margin: 8pt 0 2pt; font-family: Consolas, monospace; break-after: avoid }
p { margin: 4pt 0 } code { font-family: Consolas, monospace; font-size: 9pt; background: #eef2f7; padding: 0 2px }
pre { font-family: Consolas, "Leelawadee UI", monospace; font-size: 7.6pt; line-height: 1.35; background: #f5f7fa; border: 1px solid #d3dae3;
      padding: 5px 8px; margin: 3pt 0 6pt; white-space: pre-wrap; overflow-wrap: anywhere }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 }
td, th { border: 1px solid #c4ccd6; padding: 3px 6px; font-size: 8.8pt; vertical-align: top; text-align: left } th { background: #e6edf5 }
.fig { break-inside: avoid; margin: 8pt 0 10pt } .fig img { display: block; width: 86%; margin: 0 auto; border: 1px solid #aab } .cap { font-size: 9pt; color: #333; margin-top: 2pt }
.ok { color: #0a7a2f; font-weight: 700 } .bad { color: #b00020; font-weight: 700 } .pb { break-before: page }
.meta td:first-child { width: 28%; background: #eef2f7; font-weight: 600 }
"""


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def pre(text):
    return f"<pre>{html.escape(text.rstrip())}</pre>"


def src(rel, note=""):
    return f"<h4>{rel}</h4>" + (f"<p>{note}</p>" if note else "") + pre(read(rel))


def evidence(name):
    return pre((EVID / name).read_text(encoding="utf-8"))


def tree():
    lines = ["k8s-Ingresslab/"]

    def walk(d, prefix):
        items = sorted((p for p in d.iterdir() if p.name not in {".git", "__pycache__", "build"}), key=lambda p: (p.is_file(), p.name))
        for i, p in enumerate(items):
            last = i == len(items) - 1
            lines.append(prefix + ("└── " if last else "├── ") + p.name + ("/" if p.is_dir() else ""))
            if p.is_dir() and p.name not in {"screenshots", "evidence"}:
                walk(p, prefix + ("    " if last else "│   "))
    walk(REPO, "")
    return "\n".join(lines)


def to_pdf(body, title, out):
    BUILD.mkdir(exist_ok=True)
    page = BUILD / (out.stem + ".html")
    page.write_text(f'<!doctype html><html lang="th"><meta charset="utf-8"><title>{html.escape(title)}</title><style>{CSS}</style>{body}</html>',
                    encoding="utf-8")
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                        f"--print-to-pdf={out}", page.as_uri()], capture_output=True, timeout=240)
    doc = fitz.open(out)
    doc.set_metadata({"title": title, "author": AUTHOR, "creator": "", "producer": ""})
    for n, pg in enumerate(doc, 1):
        pg.insert_text((pg.rect.width / 2 - 14, pg.rect.height - 22), f"{n} / {len(doc)}", fontsize=8, color=(0.4, 0.4, 0.4))
    tmp = out.with_suffix(".tmp.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(out)
    print(out.name, f"{out.stat().st_size // 1024} KB")


RES = json.loads((EVID / "results.json").read_text(encoding="utf-8"))
OK = all(r["ok"] for r in RES["results"])
PASSED = sum(r["ok"] for r in RES["results"])
SUMMARY = f"ทดสอบ {len(RES['results'])} ข้อ ผ่าน {PASSED} ข้อ"


def results_table():
    rows = "".join(
        f"<tr><td>{r['id']}</td><td>{html.escape(r['desc'])}</td><td>{html.escape(r['url'])}</td><td>{html.escape(r['expected'])}</td>"
        f"<td>{html.escape(r['got'])}</td><td class=\"{'ok' if r['ok'] else 'bad'}\">{'ผ่าน' if r['ok'] else 'ไม่ผ่าน'}</td></tr>" for r in RES["results"])
    return ("<table><tr><th>ข้อ</th><th>ตรวจอะไร</th><th>URL</th><th>ที่คาดหวัง</th><th>ผลจริง</th><th>ผล</th></tr>" + rows + "</table>")


def report():
    wc = {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in read("docs/evidence/wordcount.txt").splitlines() if ":" in l and not l.startswith("#"))}
    steps = [
        ("เริ่ม cluster", "minikube start -p minikube", "เปิด minikube (VMware driver, Kubernetes v1.35.1). ถ้า cluster ทำงานอยู่แล้วข้ามได้."),
        ("เปิด Ingress controller", "minikube addons enable ingress", "ติดตั้ง ingress-nginx ใน namespace ingress-nginx. ชื่อ addon ของ minikube."),
        ("รอ controller พร้อม", "kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s",
         "ถ้า apply Ingress ก่อน controller พร้อม admission webhook จะปฏิเสธ."),
        ("สร้างทุกอย่าง", "kubectl apply -k .", "kustomize สร้าง ConfigMap จากไฟล์ใน apps/ แล้วสร้าง namespace, PVC, Deployment, Service และ Ingress ใน namespace id624."),
        ("รอ Deployment พร้อม", "kubectl wait --namespace id624 --for=condition=available deployment --all --timeout=180s", "รอให้ Pod ทุกตัว Ready."),
        ("ตรวจ resource", "kubectl get all,ingress,pvc -n id624", "ดูผลในหัวข้อ 8."),
        ("เพิ่มชื่อโดเมนใน hosts", "echo \"$(minikube ip)  www.id-624.com  admin.id-624.com\" | sudo tee -a /etc/hosts",
         "Linux/macOS. บน Windows ใช้ Add-Content กับไฟล์ C:\\Windows\\System32\\drivers\\etc\\hosts ใน PowerShell แบบ Administrator."),
        ("ทดสอบ", "curl --resolve www.id-624.com:80:$(minikube ip) http://www.id-624.com/about", "หรือเปิด URL ในเบราว์เซอร์. ชุดทดสอบเต็ม: python tools/collect.py"),
        ("ลบทั้งหมดเมื่อไม่ใช้", "kubectl delete -k .", "ลบทุก resource ของ lab นี้ รวมถึง PVC และข้อความที่แก้ไว้."),
    ]
    hosts_cmd = f"""$ minikube ssh -- "grep -q id-624 /etc/hosts || echo '{RES['ip']}  www.id-624.com  admin.id-624.com' | sudo tee -a /etc/hosts\""""
    steps_html = "".join(f"<h3>ขั้นที่ {i}. {t}</h3><p>{d}</p>{pre('$ ' + c)}" for i, (t, c, d) in enumerate(steps, 1))
    body = f"""
<h1>รายงานการให้บริการด้วย Kubernetes ผ่าน Ingress</h1>
<p>โดเมน id-624.com บน minikube</p>
<table class="meta">
<tr><td>ผู้จัดทำ</td><td>ปฐมทัศน์ ภูวนกุลชัย ({AUTHOR}) รหัส 68130624</td></tr>
<tr><td>สภาพแวดล้อม</td><td>minikube (VMware driver), Kubernetes v1.35.1, ingress-nginx controller v1.14.3, IP ของ cluster {RES['ip']}</td></tr>
<tr><td>GitHub</td><td>{REPO_URL}</td></tr>
<tr><td>ผลทดสอบ</td><td class="{'ok' if OK else 'bad'}">{SUMMARY}</td></tr>
</table>

<h2>1. สิ่งที่สร้าง</h2>
<p>ระบบมีสามบริการและหนึ่งหน้าแก้ไข. Ingress ส่งคำขอไปยังบริการตามชื่อโดเมนและ path.</p>
<table><tr><th>URL</th><th>Service / Deployment</th><th>ผลลัพธ์</th></tr>
<tr><td>www.id-624.com/about</td><td>app-about</td><td>รูป ชื่อ และรหัส 68130624</td></tr>
<tr><td>www.id-624.com/research</td><td>app-research</td><td>สรุปงานวิจัยที่นำเสนอในวิชาสัมมนา</td></tr>
<tr><td>www.id-624.com/api/&lt;ข้อความ&gt;</td><td>app-api</td><td>แสดงข้อความตัวใหญ่กลางจอ</td></tr>
<tr><td>admin.id-624.com</td><td>app-research (path /edit)</td><td>หน้าแก้ไขสรุปงานวิจัย บันทึกกลับได้</td></tr></table>
<p>www.id-624.com/ ส่งต่อไป /about. admin.id-624.com/ ส่งต่อไป /edit.</p>

<h2>2. การออกแบบ</h2>
{pre('''เบราว์เซอร์ --(hosts: IP ของ minikube = www.id-624.com, admin.id-624.com)--> minikube :80
   Ingress-NGINX controller (namespace ingress-nginx)
     Host www.id-624.com    /about    --> Service app-about    --> 2 Pod  python:3.12-alpine + ConfigMap about-code
                            /research --> Service app-research --> 2 Pod  + PVC research-data (/data/research.txt)
                            /api      --> Service app-api      --> 2 Pod  python:3.12-alpine + ConfigMap api-code
     Host admin.id-624.com  /         --> Service app-research  (annotation app-root: "/" ไปที่ /edit)''')}
<ul>
<li><b>ไม่ต้อง build image.</b> ทุก Pod ใช้ image python:3.12-alpine และอ่านโค้ดจาก ConfigMap. kustomize สร้าง ConfigMap จากไฟล์ใน apps/. เมื่อแก้ไฟล์แล้ว apply ใหม่ ชื่อ ConfigMap เปลี่ยน และ Pod ถูกสร้างใหม่เอง.</li>
<li><b>ข้อความที่แก้ไขเก็บบน PVC.</b> app-research คัดลอกข้อความตั้งต้นจาก ConfigMap research-seed ไปที่ /data/research.txt เฉพาะครั้งแรก. หลังจากนั้นหน้า /edit เขียนทับไฟล์นี้. Pod ถูกลบแล้วข้อมูลยังอยู่.</li>
<li><b>สอง replica ต่อบริการ</b> และมี readiness probe ที่ /healthz. Footer ของทุกหน้าบอกชื่อ Pod ที่ตอบ.</li>
<li><b>ความปลอดภัยเบื้องต้น.</b> Pod ไม่รันเป็น root, root filesystem อ่านอย่างเดียว, ไม่มี Linux capability. ข้อความจาก URL และจากหน้าแก้ไขถูก HTML-escape. ทุกหน้าส่ง Content-Security-Policy.</li></ul>

<h2>3. โครงสร้างไฟล์</h2>
{pre(tree())}

<h2>4. ไฟล์ hosts</h2>
<p>ชื่อ id-624.com ไม่มีใน DNS จริง. ไฟล์ hosts ของเครื่องที่เปิดเบราว์เซอร์ต้องชี้ทั้งสองชื่อไปที่ IP ของ minikube. Ingress เลือก backend จากหัว Host ของคำขอ.</p>
{src('hosts.txt')}
<p>ภาพหน้าจอและผลตรวจในรายงานนี้ไม่ได้แก้ไฟล์ hosts ของ Windows. ผู้จัดทำใช้ <code>curl --resolve</code> และ Chrome ที่ตั้ง <code>--host-resolver-rules</code> ให้สองชื่อชี้ไปที่ {RES['ip']}. ผลเหมือนกับการแก้ไฟล์ hosts เพราะคำขอที่ถึง Ingress เหมือนกันทุกประการ.</p>
<h3>ทดสอบด้วย /etc/hosts ของ Linux จริง</h3>
<p>VM ของ minikube เป็น Linux. ผู้จัดทำเพิ่มบรรทัดจาก hosts.txt ลงใน /etc/hosts ของ VM ด้วย <code>minikube ssh</code> แล้วใช้ curl เรียกด้วยชื่อโดเมนตรง ๆ โดยไม่ใช้ --resolve. ไฟล์ /etc/hosts ของ VM นี้กลับเป็นค่าเดิมเมื่อ VM รีสตาร์ต.</p>
{pre(hosts_cmd)}
{evidence('06-linux-hosts.txt')}

<h2 class="pb">5. Kubernetes manifest</h2>
<p>kustomization.yaml รวมทุกไฟล์และสร้าง ConfigMap สี่ชุด: about-code, research-code, research-seed, api-code.</p>
{src('kustomization.yaml')}{src('k8s/namespace.yaml')}{src('k8s/app-about.yaml')}{src('k8s/app-research.yaml')}{src('k8s/app-api.yaml')}{src('k8s/ingress.yaml')}

<h2 class="pb">6. โค้ดของบริการ</h2>
<p>ใช้ Python standard library อย่างเดียว. common.py ใช้ร่วมกันทั้งสามบริการ และถูกใส่ในทั้งสาม ConfigMap.</p>
{src('apps/common.py')}{src('apps/about/app.py', 'ส่งหน้า /about และไฟล์รูป /about/photo.jpg.')}{src('apps/research/app.py', 'ส่ง /research, ส่งหน้าแก้ไข /edit และรับ POST /edit.')}{src('apps/api/app.py', 'แสดงข้อความหลัง /api/ ตัวใหญ่กลางจอ.')}
{src('deploy.cmd', 'สคริปต์ deploy สำหรับ Windows (ขั้นที่ 2 ถึง 6 ด้านล่าง).')}

<h2 class="pb">7. ขั้นตอนสั่งการ kubectl</h2>
<p>รันที่ root ของ repository. ผลที่ได้จริงของขั้นที่ 2 ถึง 5 อยู่ท้ายหัวข้อนี้.</p>
{steps_html}
<h3>ผลจริงของการรัน deploy.cmd</h3>
{evidence('00-deploy-output.txt')}

<h2 class="pb">8. การตรวจสอบด้วย kubectl get และ describe</h2>
<h3>8.1 Cluster และ Ingress controller</h3>{evidence('01-cluster.txt')}
<h3>8.2 kubectl get</h3>{evidence('02-get.txt')}
<h3>8.3 kubectl describe ingress</h3>{evidence('03-describe-ingress.txt')}
<h3>8.4 kubectl describe service, pvc, deployment</h3>{evidence('04-describe-workload.txt')}
<h3>8.5 Log ของ Pod</h3><p>เวลาใน log ของ Pod เป็นเวลา UTC (เวลาไทยลบ 7 ชั่วโมง).</p>{evidence('05-logs.txt')}

<h2 class="pb">9. ผลการทดสอบ</h2>
<p class="{'ok' if OK else 'bad'}">{SUMMARY}. ภาพหน้าจอของทุกบริการอยู่ในไฟล์ Test-Evidence.pdf.</p>
{results_table()}

<h2>10. เนื้อหาสรุปงานวิจัย</h2>
<p>หน้า /research แสดงสรุปงานวิจัยเรื่อง “การพัฒนาระบบคิวเพื่อจัดการการใช้ Unity Editor ร่วมกันของ AI หลายเอเจนต์” ที่ผู้จัดทำนำเสนอในวิชาสัมมนา. ผู้จัดทำเขียนสรุปจากสไลด์นำเสนอและร่างบทความของงานวิจัยนี้ และคงข้อจำกัดของผลทดลองตามต้นฉบับ.</p>
<p>จำนวนคำ: <b>{wc['words']} คำ</b> (เกณฑ์ 300 ถึง 500 คำ). วิธีนับ: {html.escape(wc['method'])}. ภาษาไทยไม่เว้นวรรคระหว่างคำ ตัวเลขจึงขึ้นกับตัวตัดคำ.</p>
{src('apps/research/research.txt')}
"""
    to_pdf(body, "รายงาน Kubernetes Ingress id-624.com", DOCS / "K8s-Ingress-Report.pdf")


CAP = {
    "chrome-about": ("www.id-624.com/about ทำงานด้วย app-about", "แสดงรูป ชื่อ และรหัส 68130624. Footer บอกชื่อ Pod ที่ตอบ."),
    "chrome-research": ("www.id-624.com/research ทำงานด้วย app-research", "แสดงสรุปงานวิจัย. ข้อความอ่านจากไฟล์บน PVC."),
    "chrome-api-1": ("www.id-624.com/api/สวัสดี K8s ทำงานด้วย app-api", "ข้อความใน URL แสดงตัวใหญ่กลางจอ. ภาษาไทยและช่องว่างแสดงถูกต้อง."),
    "chrome-api-2": ("การทดสอบความปลอดภัย: www.id-624.com/api/&lt;b&gt;hi&lt;/b&gt;",
                     "ภาพนี้ตั้งใจส่งแท็ก HTML ไปใน URL เพื่อทดสอบช่องโหว่ XSS (การฝังโค้ดผ่านลิงก์). "
                     "ผลที่ถูกต้องคือหน้าแสดงข้อความ &lt;b&gt;hi&lt;/b&gt; ตรงตามที่ส่งมา ไม่แปลงเป็นตัวหนา. "
                     "ถ้าระบบแปลงแท็กได้ คนอื่นก็ส่งลิงก์ที่ฝัง &lt;script&gt; ให้รันในเบราว์เซอร์ของผู้เปิดได้. "
                     "ข้อความปกติทุกข้อความแสดงเป็นตัวหนาตัวใหญ่อยู่แล้ว (ดูภาพที่ 3)."),
    "chrome-admin-1": ("admin.id-624.com", "เปิดโดเมน admin แล้วถูกส่งต่อไป /edit. หน้านี้ทำงานด้วย app-research path /edit. กล่องแก้ไขมีข้อความปัจจุบัน."),
    "chrome-admin-2": ("พิมพ์แก้ข้อความ", "พิมพ์ [admin-edit-8421] ไว้หน้าหัวข้อ. ยังไม่กดบันทึก."),
    "chrome-admin-3": ("กดบันทึก", "หน้ากลับมาที่ /edit?saved=1 และแสดงคำว่า “บันทึกแล้ว”. ข้อความในกล่องมีส่วนที่พิมพ์เพิ่ม."),
    "chrome-research-edited": ("ผลที่หน้า /research", "หัวข้อใหม่ที่มี [admin-edit-8421] แสดงทันทีที่ www.id-624.com/research."),
    "term-persist": ("ลบ Pod แล้วข้อมูลยังอยู่", "ลบ Pod app-research ทั้งสองตัว. Deployment สร้าง Pod ใหม่ที่มีชื่อใหม่. คำสั่ง curl ยังพบข้อความที่แก้ เพราะข้อความอยู่บน PVC."),
    "chrome-research-restart": ("หน้า /research หลังสร้าง Pod ใหม่", "Footer แสดงชื่อ Pod ใหม่. หัวข้อที่แก้ยังอยู่."),
    "term-get": ("kubectl get", "สถานะ minikube, node, Deployment, Pod, Service, Ingress และ PVC. Deployment ทั้งสามพร้อม 2/2."),
    "term-describe-ingress": ("kubectl describe ingress", "กฎ host และ path ของ id624-www และ id624-admin พร้อม backend และ annotation app-root."),
    "term-describe-svc": ("kubectl describe svc, endpoints, pvc", "หน้าต่างแสดงส่วนท้ายของ describe svc (Service app-research). kubectl get endpoints แสดงว่าแต่ละ Service มี endpoint สองตัว. PVC research-data อยู่ในสถานะ Bound."),
    "term-describe-deploy": ("kubectl describe deployment app-research", "หน้าต่างแสดงส่วนท้ายของผล: readiness probe, ตัวแปรแวดล้อม, จุด mount, volume สามตัว (ConfigMap สองตัวและ PVC) และ ReplicaSet ใหม่ที่สร้าง Pod ครบ 2/2."),
    "term-curl": ("ผลตอบกลับของทุก URL", "รหัส HTTP, ชนิดเนื้อหา และขนาด. คำขอใช้ --resolve ให้ชื่อโดเมนชี้ไปที่ IP ของ minikube."),
    "term-curl-security": ("HEAD, header ความปลอดภัย, การ escape HTML", "คำขอ HEAD ได้ 200. มี Content-Security-Policy และ X-Content-Type-Options. ข้อความ &lt;b&gt; ถูกแปลงเป็น &amp;lt;b&amp;gt;."),
    "term-linux-hosts": ("/etc/hosts ของ Linux (VM ของ minikube)", "เพิ่มบรรทัด hosts ใน /etc/hosts แล้ว curl ด้วยชื่อ www.id-624.com และ admin.id-624.com ตรง ๆ โดยไม่ใช้ --resolve. ได้ชื่อ Pod ของ app-about และ 302 ไป /edit."),
    "term-lb": ("การกระจายคำขอไปยัง Pod", "ส่งคำขอ 8 ครั้งต่อบริการ. Pod ทั้งสองตัวของทุกบริการได้รับคำขอ. ตัวเลข Count คือจำนวนครั้งที่แต่ละ Pod ตอบ."),
}
GROUPS = [
    ("1. app-about", ["chrome-about"]), ("2. app-research", ["chrome-research"]), ("3. app-api", ["chrome-api-1", "chrome-api-2"]),
    ("4. admin.id-624.com: แก้ไขและบันทึกกลับ", ["chrome-admin-1", "chrome-admin-2", "chrome-admin-3", "chrome-research-edited"]),
    ("5. ข้อมูลอยู่รอดเมื่อ Pod ถูกลบ", ["term-persist", "chrome-research-restart"]),
    ("6. kubectl get และ describe", ["term-get", "term-describe-ingress", "term-describe-svc", "term-describe-deploy"]),
    ("7. curl, /etc/hosts ของ Linux และการกระจายคำขอ", ["term-curl", "term-curl-security", "term-linux-hosts", "term-lb"]),
]


def test_evidence():
    meta = json.loads((SHOTS / "shots.json").read_text(encoding="utf-8"))
    figs, n = "", 0
    for title, names in GROUPS:
        figs += f"<h2>{title}</h2>"
        for name in names:
            n += 1
            head, text = CAP[name]
            figs += (f'<div class="fig"><img src="../screenshots/{meta[name]["file"]}"><div class="cap"><b>ภาพที่ {n}. {head}</b> '
                     f'{text}</div></div>')
    body = f"""
<h1>ไฟล์ตรวจสอบการทดสอบการทำงาน</h1>
<p>ภาพหน้าจอของทุกบริการ: id-624.com บน Kubernetes (Ingress)</p>
<table class="meta">
<tr><td>ผู้จัดทำ</td><td>ปฐมทัศน์ ภูวนกุลชัย ({AUTHOR}) รหัส 68130624</td></tr>
<tr><td>GitHub</td><td>{REPO_URL}</td></tr>
<tr><td>ผลทดสอบ</td><td class="{'ok' if OK else 'bad'}">{SUMMARY}</td></tr>
<tr><td>วิธีถ่ายภาพ</td><td>ภาพเป็นหน้าต่างจริงของ Chrome และ PowerShell ที่ถ่ายด้วย PrintWindow (ไม่ใช่ภาพทั้งหน้าจอ). Chrome ตั้ง host-resolver-rules ให้ www.id-624.com และ admin.id-624.com ชี้ไปที่ {RES['ip']} ซึ่งมีผลเท่ากับไฟล์ hosts. Chrome ถูกควบคุมผ่าน DevTools ตอนพิมพ์และกดบันทึก.</td></tr>
</table>
<h2>ผลการทดสอบอัตโนมัติ</h2>
{results_table()}
<p>หลังทดสอบ ผู้จัดทำใส่ข้อความสรุปงานวิจัยเดิมกลับทุกครั้ง (ภาพที่ 6 ถึง 10 ใช้ข้อความ [admin-edit-8421] ชั่วคราว).</p>
{figs}"""
    to_pdf(body, "ไฟล์ตรวจสอบการทดสอบ id-624.com", DOCS / "Test-Evidence.pdf")


if __name__ == "__main__":
    report()
    test_evidence()
