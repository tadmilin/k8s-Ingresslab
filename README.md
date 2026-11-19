# k8s-Ingresslab

Kubernetes lab: เว็บไซต์ `id-624.com` ที่แยกบริการด้วย Ingress บน minikube
ผู้จัดทำ: ปฐมทัศน์ ภูวนกุลชัย (Pathomtad Phoovanakulchai) รหัส 68130624

## บริการที่ให้

| URL | ทำงานด้วย | ผลลัพธ์ |
|---|---|---|
| `www.id-624.com/about` | `app-about` | รูป ชื่อ และรหัสนักศึกษา |
| `www.id-624.com/research` | `app-research` | สรุปงานวิจัยที่นำเสนอในวิชาสัมมนา (435 คำ นับด้วย PyThaiNLP newmm) |
| `www.id-624.com/api/<ข้อความ>` | `app-api` | แสดง `<ข้อความ>` ตัวใหญ่กลางจอ |
| `admin.id-624.com` | `app-research` path `/edit` | หน้าแก้ไขสรุปงานวิจัย กดบันทึกแล้วหน้า `/research` เปลี่ยนทันที |

`www.id-624.com/` ส่งต่อไป `/about`. `admin.id-624.com/` ส่งต่อไป `/edit`.

## โครงสร้างไฟล์

```
k8s-Ingresslab/
├── README.md
├── deploy.cmd              สคริปต์ deploy (Windows)
├── hosts.txt               บรรทัดที่ต้องเพิ่มใน /etc/hosts
├── kustomization.yaml      สร้าง ConfigMap จากไฟล์ใน apps/ และรวม manifest ทั้งหมด
├── k8s/
│   ├── namespace.yaml      namespace id624
│   ├── app-about.yaml      Deployment + Service
│   ├── app-research.yaml   PVC + Deployment + Service
│   ├── app-api.yaml        Deployment + Service
│   └── ingress.yaml        Ingress www.id-624.com และ admin.id-624.com
├── apps/                   โค้ด Python (stdlib อย่างเดียว) ของแต่ละบริการ
│   ├── common.py           หน้าเว็บ, header ความปลอดภัย, HTTP server ที่ใช้ร่วมกัน
│   ├── about/              app.py, photo.jpg
│   ├── research/           app.py, research.txt (ข้อความตั้งต้น)
│   └── api/                app.py
├── tools/                  สคริปต์เก็บหลักฐาน (collect.py, capture.py, build_pdf.py)
└── docs/                   รายงาน PDF, ภาพหน้าจอ, ผลตรวจ
```

## Deploy

ต้องมี minikube ที่ start แล้ว และ kubectl.

```
minikube start
minikube addons enable ingress
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s
kubectl apply -k .
kubectl wait --namespace id624 --for=condition=available deployment --all --timeout=180s
kubectl get all,ingress,pvc -n id624
```

บน Windows รัน `deploy.cmd` แทนคำสั่งตั้งแต่ `minikube addons enable ingress` ลงมาได้เลย. จากนั้นเพิ่มชื่อโดเมนในไฟล์ hosts ของเครื่องที่เปิดเบราว์เซอร์:

```
# Linux / macOS
echo "$(minikube ip)  www.id-624.com  admin.id-624.com" | sudo tee -a /etc/hosts
# Windows: เปิด PowerShell แบบ Administrator
Add-Content C:\Windows\System32\drivers\etc\hosts "$(minikube ip)  www.id-624.com  admin.id-624.com"
```

หมายเหตุ: ถ้า minikube ใช้ไดรเวอร์ docker บน Windows หรือ macOS ให้รัน `minikube tunnel` ค้างไว้ และใช้ `127.0.0.1` แทน `minikube ip`.

## ตรวจสอบ

เปิด `http://www.id-624.com/about` ฯลฯ ในเบราว์เซอร์ หรือไม่ต้องแก้ hosts ก็ทดสอบด้วย curl ได้:

```
IP=$(minikube ip)
curl --resolve www.id-624.com:80:$IP http://www.id-624.com/about
curl --resolve www.id-624.com:80:$IP "http://www.id-624.com/api/สวัสดี"
curl --resolve admin.id-624.com:80:$IP -i http://admin.id-624.com/
kubectl describe ingress -n id624
```

`python tools/collect.py` รันชุดทดสอบ 18 ข้อ (T1-T16, T15 แยกเป็น a/b/c ตามบริการ) และเก็บผล `kubectl get/describe` ไว้ใน `docs/evidence/`. ผลและภาพหน้าจอของ service ทุกตัวอยู่ใน `docs/Test-Evidence.pdf`. ขั้นตอนทั้งหมดอยู่ใน `docs/K8s-Ingress-Report.pdf`.

## การออกแบบ

- **ไม่ต้อง build image.** ทุก Pod ใช้ `python:3.12-alpine` และ mount โค้ดจาก ConfigMap. `kustomization.yaml` สร้าง ConfigMap จากไฟล์ใน `apps/`. แก้ไฟล์แล้ว `kubectl apply -k .` Pod จะถูกสร้างใหม่เอง เพราะชื่อ ConfigMap เปลี่ยนตามเนื้อหา.
- **ข้อความที่แก้จากหน้า admin อยู่บน PVC** (`research-data`, ไฟล์ `/data/research.txt`). Pod ถูกลบแล้วข้อมูลยังอยู่. ข้อความตั้งต้นมาจาก ConfigMap `research-seed` และถูกคัดลอกเฉพาะครั้งแรกที่ไม่มีไฟล์.
- **ทุก Deployment มี 2 replica** และมี readiness probe (`/healthz`). ชื่อ Pod ที่ตอบอยู่ที่ footer ของทุกหน้า.
- **ความปลอดภัยเบื้องต้น:** Pod ไม่รันเป็น root, root filesystem อ่านอย่างเดียว, ไม่มี capability. ข้อความจาก URL และจากหน้าแก้ไขถูก HTML-escape ก่อนแสดง. ทุกหน้าส่ง `Content-Security-Policy`.

## ข้อจำกัด

- หน้า `admin.id-624.com` **ไม่มีการล็อกอิน** ใครเข้าถึงโดเมนนี้ได้ก็แก้สรุปได้. ใช้ในเครือข่ายทดลองเท่านั้น. ถ้าต้องเปิดจริง ให้เพิ่ม basic auth ที่ Ingress.
- ไม่มี TLS (HTTP เท่านั้น) และ `id-624.com` ไม่ได้จดทะเบียน DNS ต้องใช้ไฟล์ hosts.
- PVC ใช้ storage class `standard` ของ minikube (hostPath) ซึ่งทำงานได้กับ node เดียว.
- รูปใน `apps/about/photo.jpg` เป็นรูปของผู้จัดทำ และเปิดเผยต่อสาธารณะผ่าน repository นี้.
