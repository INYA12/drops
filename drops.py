#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import io
import json
import socket
import threading
import time
import mimetypes
import urllib.parse
import hashlib
import shutil
import queue
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import webbrowser

# Fix Windows console encoding safely
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except AttributeError:
        pass

PORT = 8888
SHARED_FILES = {}
LOCK = threading.Lock()
SSE_CLIENTS = []
CHUNK_SIZE = 64 * 1024  # 64 KB chunks for efficient streaming

def get_local_ips():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ':' not in ip and not ip.startswith('127.'):
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips = [s.getsockname()[0]]
            s.close()
        except Exception:
            ips = ["127.0.0.1"]
    return ips

def fmt_size(n: int) -> str:
    for unit in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ПБ"

def push_event(data: dict):
    msg = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    with LOCK:
        for q in SSE_CLIENTS:
            q.put(msg)

def broadcast_files():
    files_data = [{'id': k, 'name': v['name'], 'size': fmt_size(v['size'])} for k, v in SHARED_FILES.items()]
    # Sort by added time descending
    files_data.sort(key=lambda x: SHARED_FILES[x['id']]['added'], reverse=True)
    push_event({'type': 'files', 'files': files_data})

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DROPS LAN — Сверхбыстрая передача файлов</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0b10;
  --surface:rgba(18,20,29,0.55);
  --surface2:rgba(26,29,43,0.7);
  --border:rgba(255,255,255,0.08);
  --border-focus:rgba(108,99,255,0.4);
  --accent:#6c63ff;
  --accent2:#a78bfa;
  --accent-gradient:linear-gradient(135deg, #6c63ff, #a78bfa, #ec4899);
  --accent-glow:rgba(108,99,255,0.25);
  --green:#22d3a8;
  --red:#ff5555;
  --text:#e8eaf6;
  --text-muted:#8b8fa8;
  --radius:24px;
  --transition:0.3s cubic-bezier(0.4,0,0.2,1);
}
html,body{height:100%;font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);overflow-x:hidden}

/* Animated Background */
.bg-glow {
  position: fixed;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
  background-color: var(--bg);
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.3;
  mix-blend-mode: screen;
  transition: all 0.3s ease;
}

.blob-1 {
  top: -10%;
  left: -10%;
  width: 50vw;
  height: 50vw;
  background: radial-gradient(circle, var(--accent) 0%, rgba(108,99,255,0) 70%);
  animation: float-blob-1 25s infinite alternate ease-in-out;
}

.blob-2 {
  bottom: -20%;
  right: -10%;
  width: 55vw;
  height: 55vw;
  background: radial-gradient(circle, var(--accent2) 0%, rgba(167,139,250,0) 70%);
  animation: float-blob-2 28s infinite alternate ease-in-out;
}

.blob-3 {
  top: 30%;
  left: 50%;
  width: 40vw;
  height: 40vw;
  background: radial-gradient(circle, #ec4899 0%, rgba(236,72,153,0) 70%);
  animation: float-blob-3 20s infinite alternate ease-in-out;
}

@keyframes float-blob-1 {
  0% { transform: translate(0, 0) scale(1) rotate(0deg); }
  50% { transform: translate(10%, 15%) scale(1.1) rotate(120deg); }
  100% { transform: translate(-5%, -5%) scale(0.9) rotate(240deg); }
}

@keyframes float-blob-2 {
  0% { transform: translate(0, 0) scale(1.1) rotate(0deg); }
  50% { transform: translate(-15%, -10%) scale(0.9) rotate(-180deg); }
  100% { transform: translate(5%, 10%) scale(1) rotate(-360deg); }
}

@keyframes float-blob-3 {
  0% { transform: translate(0, 0) scale(0.9) rotate(0deg); }
  50% { transform: translate(-10%, 15%) scale(1.1) rotate(90deg); }
  100% { transform: translate(10%, -10%) scale(1) rotate(180deg); }
}

/* Glassmorphism Dot Grid Overlay */
.grid-overlay {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(var(--border) 1px, transparent 1px);
  background-size: 24px 24px;
  opacity: 0.3;
  mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 60%, rgba(0,0,0,0.3) 100%);
  -webkit-mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 60%, rgba(0,0,0,0.3) 100%);
}

/* Header */
header{display:flex;align-items:center;justify-content:center;padding:20px 24px;border-bottom:1px solid var(--border);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);background:rgba(10,11,16,0.6);position:sticky;top:0;z-index:10}
.brand{display:flex;align-items:center;gap:14px}
.logo-icon{width:42px;height:42px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:14px;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px var(--accent-glow);transition:transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)}
.brand:hover .logo-icon{transform:rotate(15deg) scale(1.05)}
.logo-icon svg{stroke:#fff;width:24px;height:24px}
h1{font-family:'Outfit',sans-serif;font-size:1.8rem;letter-spacing:-0.5px}
h1 span{background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}

/* Main Container */
.container{max-width:800px;margin:0 auto;padding:32px 20px;display:flex;flex-direction:column;gap:24px}

/* Glass Cards */
.card{
  position:relative;
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:var(--radius);
  padding:28px;
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  box-shadow:0 8px 32px rgba(0,0,0,0.3), inset 0 1px 1px rgba(255,255,255,0.05);
  transition:border-color 0.2s, box-shadow 0.3s, transform 0.2s;
  overflow:hidden;
}
.card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0) 100%);
  border-radius: var(--radius);
  pointer-events: none;
  z-index: 1;
}
.card:hover{
  border-color:var(--border-focus);
  transform:translateY(-2px);
  box-shadow:0 12px 40px rgba(0,0,0,0.4), 0 0 15px var(--accent-glow);
}
.card-title{display:flex;align-items:center;gap:10px;font-size:0.95rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text-muted);margin-bottom:18px}
.card-title svg{color:var(--accent);width:20px;height:20px}

/* IPs */
.ip-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.ip-item{display:flex;align-items:center;justify-content:space-between;background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:12px 16px;transition:var(--transition)}
.ip-item:hover{border-color:rgba(108,99,255,0.4);transform:translateY(-2px)}
.ip-addr{font-family:'Outfit',monospace;font-size:1.05rem;font-weight:600;color:var(--accent2)}
.copy-btn{background:rgba(255,255,255,0.05);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 12px;font-size:0.8rem;font-weight:600;cursor:pointer;transition:var(--transition)}
.copy-btn:hover{background:var(--accent);border-color:var(--accent);box-shadow:0 4px 12px var(--accent-glow);color:#fff}

/* Drop Zone */
.drop-zone{
  position:relative;
  border:2px dashed var(--border);
  text-align:center;
  cursor:pointer;
  transition:all 0.3s;
  padding:54px 20px;
  border-radius:var(--radius);
  background:linear-gradient(180deg, rgba(108,99,255,0.02) 0%, rgba(0,0,0,0) 100%);
  overflow:hidden;
}
.drop-zone::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at center, var(--accent-glow) 0%, transparent 70%);
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}
.drop-zone:hover{border-color:var(--accent2)}
.drop-zone.drag-over{
  border-color:var(--accent);
  background:rgba(108,99,255,0.08);
  box-shadow:0 0 30px var(--accent-glow), inset 0 0 15px var(--accent-glow);
  transform:scale(0.995);
}
.drop-zone.drag-over::after {
  opacity: 1;
}
.drop-icon{
  width:76px;
  height:76px;
  background:var(--surface2);
  border:1px solid var(--border);
  border-radius:20px;
  display:flex;
  align-items:center;
  justify-content:center;
  margin:0 auto 20px;
  transition:all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  box-shadow:0 4px 15px rgba(0,0,0,0.15);
}
.drop-zone:hover .drop-icon{
  transform:translateY(-8px) rotate(5deg) scale(1.05);
  border-color:var(--accent2);
  color:#fff;
  background:var(--accent-gradient);
  box-shadow:0 8px 25px var(--accent-glow);
}
.drop-zone:hover .drop-icon svg{stroke:#fff}
.drop-icon svg{stroke:var(--accent2);width:36px;height:36px;transition:stroke 0.2s}
.drop-zone h3{font-size:1.25rem;margin-bottom:8px}
.drop-zone p{font-size:0.9rem;color:var(--text-muted)}
#file-input{display:none}

/* Upload Progress */
.upload-status{display:none;margin-top:20px;background:var(--surface2);padding:16px;border-radius:12px;border:1px solid var(--border)}
.upload-status.show{display:block;animation:fadeIn 0.3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.upload-header{display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:10px;font-weight:600}
.upload-filename{color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%}
.upload-stats{color:var(--accent2);display:flex;gap:12px}
.progress-wrap{height:8px;background:var(--bg);border-radius:99px;overflow:hidden;border:1px solid var(--border)}
.progress-bar{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));width:0%;transition:width 0.2s linear;border-radius:99px;box-shadow:0 0 10px var(--accent-glow)}

/* Files List */
.files-list{display:flex;flex-direction:column;gap:12px}
.file-item{display:flex;align-items:center;gap:16px;background:var(--surface2);border:1px solid var(--border);border-radius:16px;padding:16px;transition:var(--transition);animation:slide-in-py 0.3s cubic-bezier(0.4,0,0.2,1) forwards}
.file-item:hover{border-color:rgba(108,99,255,0.3);transform:translateX(4px)}
@keyframes slide-in-py {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.file-icon{width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,rgba(108,99,255,0.2),rgba(167,139,250,0.1));display:flex;align-items:center;justify-content:center;flex-shrink:0}
.file-icon svg{width:24px;height:24px;stroke:var(--accent2)}
.file-info{flex:1;min-width:0}
.file-name{font-size:1rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
.file-size{font-size:0.8rem;color:var(--text-muted)}
.file-actions{display:flex;gap:8px;flex-shrink:0}
.btn{display:inline-flex;align-items:center;gap:6px;border:none;border-radius:12px;padding:10px 16px;font-size:0.85rem;font-weight:600;cursor:pointer;transition:var(--transition);text-decoration:none;outline:none}
.btn-download{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;box-shadow:0 4px 16px rgba(108,99,255,0.3)}
.btn-download:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(108,99,255,0.5)}
.btn-remove{background:rgba(255,85,85,0.08);color:var(--red);border:1px solid rgba(255,85,85,0.2);padding:10px}
.btn-remove:hover{background:var(--red);color:#fff;border-color:var(--red);transform:translateY(-2px);box-shadow:0 6px 15px rgba(255,85,85,0.3)}
.empty-text{text-align:center;color:var(--text-muted);font-size:0.95rem;padding:32px;font-weight:500}

/* Notifications */
.notif{position:fixed;bottom:30px;right:30px;background:var(--surface2);border:1px solid var(--green);color:var(--green);border-radius:12px;padding:16px 24px;font-size:0.95rem;font-weight:600;box-shadow:0 8px 32px rgba(0,0,0,0.4);z-index:1000;transform:translateY(100px);opacity:0;transition:var(--transition);backdrop-filter:blur(10px)}
.notif.show{transform:translateY(0);opacity:1}
.notif.error{border-color:var(--red);color:var(--red)}

@media(max-width:600px){
  .container{padding:16px}
  .card{padding:16px}
  .file-item{flex-direction:column;align-items:flex-start}
  .file-actions{width:100%}
  .btn{flex:1;justify-content:center}
}
</style>
</head>
<body>
<div class="bg-glow">
  <div class="blob blob-1"></div>
  <div class="blob blob-2"></div>
  <div class="blob blob-3"></div>
  <div class="grid-overlay"></div>
</div>

<header>
  <div class="brand">
    <div class="logo-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    </div>
    <h1>DROPS <span>LAN</span></h1>
  </div>
</header>

<div class="container">
  <!-- Network addresses -->
  <div class="card">
    <div class="card-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
      Адреса для подключения
    </div>
    <div class="ip-grid" id="ip-grid">
      <div class="empty-text">Загрузка...</div>
    </div>
  </div>

  <!-- Drop zone -->
  <div class="card drop-zone" id="drop-zone">
    <input type="file" id="file-input" multiple>
    <div class="drop-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
    </div>
    <h3>Перетащите файлы сюда</h3>
    <p>или нажмите для выбора на устройстве</p>
    
    <div class="upload-status" id="upload-status">
      <div class="upload-header">
        <span class="upload-filename" id="upload-filename">Загрузка...</span>
        <div class="upload-stats">
          <span id="upload-speed">0 МБ/с</span>
          <span id="upload-pct">0%</span>
        </div>
      </div>
      <div class="progress-wrap"><div class="progress-bar" id="upload-bar"></div></div>
    </div>
  </div>

  <!-- Shared files -->
  <div class="card">
    <div class="card-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
      Доступные файлы
    </div>
    <div class="files-list" id="files-list">
      <div class="empty-text">Нет загруженных файлов</div>
    </div>
  </div>
</div>

<div class="notif" id="notif"></div>

<script>
function notify(msg, type='success'){
  const n=document.getElementById('notif');
  n.textContent=msg; n.className='notif '+type+' show';
  setTimeout(()=>n.className='notif',3000);
}

// SSE for realtime files updates
const sse = new EventSource('/events');
sse.onmessage = e => {
  const d = JSON.parse(e.data);
  if(d.type === 'files') renderFiles(d.files);
};

// Load addresses
fetch('/api/info').then(r=>r.json()).then(d=>{
  const grid=document.getElementById('ip-grid');
  grid.innerHTML='';
  d.ips.forEach(ip=>{
    const url=`http://${ip}:${d.port}`;
    const el=document.createElement('div');
    el.className='ip-item';
    el.innerHTML=`<span class="ip-addr">${url}</span><button class="copy-btn" onclick="copyUrl('${url}')">Копировать</button>`;
    grid.appendChild(el);
  });
});

function copyUrl(url){
  navigator.clipboard.writeText(url).then(()=>notify('Ссылка скопирована! ✓'));
}

// Drop zone
const dz=document.getElementById('drop-zone');
const fi=document.getElementById('file-input');
dz.addEventListener('click',()=>fi.click());
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag-over')});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag-over'));
dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('drag-over');uploadFiles(e.dataTransfer.files)});
fi.addEventListener('change',e=>uploadFiles(e.target.files));

// Sequential upload queue
let uploadQueue = [];
let isUploading = false;

function uploadFiles(files){
  [...files].forEach(file => uploadQueue.push(file));
  processQueue();
}

function processQueue(){
  if(isUploading || uploadQueue.length === 0) return;
  isUploading = true;
  const file = uploadQueue.shift();
  
  const status=document.getElementById('upload-status');
  const bar=document.getElementById('upload-bar');
  const fn=document.getElementById('upload-filename');
  const pct=document.getElementById('upload-pct');
  const speedEl=document.getElementById('upload-speed');
  
  status.classList.add('show');
  fn.textContent = file.name;
  bar.style.width = '0%';
  pct.textContent = '0%';
  speedEl.textContent = '...';

  const xhr = new XMLHttpRequest();
  // Pass filename in query string, send RAW binary in body
  xhr.open('POST', '/upload?name=' + encodeURIComponent(file.name));
  xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
  
  let startTime = Date.now();
  
  xhr.upload.onprogress=e=>{
    if(e.lengthComputable){
      const p=Math.round(e.loaded/e.total*100);
      bar.style.width=p+'%';
      pct.textContent=p+'%';
      
      const now = Date.now();
      const dt = (now - startTime) / 1000;
      if(dt > 0.5){ // Update speed every 0.5s for stability
        const speed = e.loaded / dt / 1024 / 1024;
        speedEl.textContent = speed.toFixed(1) + ' МБ/с';
      }
    }
  };
  
  xhr.onload=()=>{
    if(xhr.status===200){
      notify(`✓ Файл "${file.name}" загружен`);
    } else {
      notify('Ошибка загрузки', 'error');
    }
    finishUpload();
  };
  xhr.onerror=()=>{
    notify('Ошибка сети', 'error');
    finishUpload();
  };
  
  function finishUpload(){
    setTimeout(()=>{
      status.classList.remove('show');
      isUploading = false;
      fi.value='';
      processQueue();
    }, 1000);
  }
  
  // Send the raw file object!
  xhr.send(file);
}

function renderFiles(files){
  const list=document.getElementById('files-list');
  if(!files.length){
    list.innerHTML='<div class="empty-text">Пока нет файлов. Перетащите их в область выше!</div>';
    return;
  }
  list.innerHTML='';
  files.forEach(f=>{
    const el=document.createElement('div');
    el.className='file-item';
    el.innerHTML=`
      <div class="file-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
      <div class="file-info">
        <div class="file-name" title="${f.name}">${f.name}</div>
        <div class="file-size">${f.size}</div>
      </div>
      <div class="file-actions">
        <a class="btn btn-download" href="/download/${f.id}" download="${f.name}">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Скачать
        </a>
        <button class="btn btn-remove" onclick="removeFile('${f.id}')" title="Удалить">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>`;
    list.appendChild(el);
  });
}

function removeFile(id){
  fetch('/remove/'+id,{method:'DELETE'}).then(()=>notify('Файл удалён'));
}
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Only log errors
        if args and (str(args[1]) if len(args) > 1 else '') not in ('200', '206'):
            super().log_message(fmt, *args)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            body = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)

        elif path == '/api/info':
            self.send_json({'ips': get_local_ips(), 'port': PORT})

        elif path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()

            q = queue.Queue()
            with LOCK:
                SSE_CLIENTS.append(q)
            
            # Send initial files list
            files_data = [{'id': k, 'name': v['name'], 'size': fmt_size(v['size'])} for k, v in SHARED_FILES.items()]
            files_data.sort(key=lambda x: SHARED_FILES[x['id']]['added'], reverse=True)
            initial_msg = f"data: {json.dumps({'type':'files','files':files_data}, ensure_ascii=False)}\n\n"
            
            try:
                self.wfile.write(initial_msg.encode())
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=5.0)
                        self.wfile.write(msg.encode())
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with LOCK:
                    if q in SSE_CLIENTS:
                        SSE_CLIENTS.remove(q)

        elif path.startswith('/download/'):
            fid = path.split('/download/', 1)[1]
            with LOCK:
                info = SHARED_FILES.get(fid)
            if not info:
                self.send_response(404)
                self.end_headers()
                return

            fname = info['name']
            fpath = info['path']
            fsize = info['size']
            mime = info.get('mime', 'application/octet-stream')

            try:
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', fsize)
                safe_name = urllib.parse.quote(fname)
                self.send_header('Content-Disposition', f'attachment; filename="{fname}"; filename*=UTF-8\'\'{safe_name}')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()

                with open(fpath, 'rb') as f:
                    shutil.copyfileobj(f, self.wfile, length=CHUNK_SIZE)
                
                print(f"[DOWNLOAD] {fname} ({fmt_size(fsize)}) ✓")
            except (BrokenPipeError, ConnectionResetError):
                print(f"[DOWNLOAD] {fname} — прервано")
            except Exception as e:
                print(f"[DOWNLOAD ERROR] {e}")

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/upload':
            qs = urllib.parse.parse_qs(parsed.query)
            fname = qs.get('name', ['uploaded_file'])[0]
            length = int(self.headers.get('Content-Length', 0))

            if length == 0:
                self.send_json({'error': 'Empty file'}, 400)
                return

            os.makedirs('shared_files', exist_ok=True)
            fid = hashlib.md5(f"{fname}{time.time()}".encode()).hexdigest()[:12]
            safe = "".join(c for c in fname if c.isalnum() or c in ' ._-()[]').strip() or 'file'
            fpath = os.path.join('shared_files', f"{fid}_{safe}")

            bytes_written = 0
            try:
                with open(fpath, 'wb') as f:
                    # Stream read and write to avoid loading whole file into memory
                    while bytes_written < length:
                        to_read = min(CHUNK_SIZE, length - bytes_written)
                        chunk = self.rfile.read(to_read)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_written += len(chunk)
            except Exception as e:
                print(f"[UPLOAD ERROR] {e}")
                self.send_json({'error': 'Upload failed'}, 500)
                return

            mime, _ = mimetypes.guess_type(fname)
            mime = mime or 'application/octet-stream'

            with LOCK:
                SHARED_FILES[fid] = {'path': fpath, 'name': fname, 'size': bytes_written, 'mime': mime, 'added': time.time()}

            print(f"[UPLOAD] {fname} ({fmt_size(bytes_written)}) → {fpath}")

            # Broadcast update
            broadcast_files()

            self.send_json({'ok': True, 'id': fid, 'size': fmt_size(bytes_written)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/remove/'):
            fid = path.split('/remove/', 1)[1]
            with LOCK:
                info = SHARED_FILES.pop(fid, None)
            if info:
                try:
                    os.remove(info['path'])
                except Exception:
                    pass
                broadcast_files()
                self.send_json({'ok': True})
            else:
                self.send_json({'error': 'not found'}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def main():
    global PORT
    os.makedirs('shared_files', exist_ok=True)
    ips = get_local_ips()
    
    server = None
    for p in range(8888, 8900):
        try:
            server = ThreadingHTTPServer(('0.0.0.0', p), Handler)
            PORT = p
            break
        except OSError as e:
            if getattr(e, 'errno', None) in (98, 10048) or "already in use" in str(e).lower():
                continue
            raise e

    if not server:
        try:
            server = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
            PORT = server.server_address[1]
        except Exception as e:
            print(f"Ошибка запуска сервера: {e}")
            sys.exit(1)

    server.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    sep = "=" * 52
    print("\n" + sep)
    print("  DROPS LAN -- Сверхбыстрая передача файлов")
    print(sep)
    print(f"\n  Открой в браузере на ЭТОМ устройстве:")
    print(f"  -> http://localhost:{PORT}")
    print(f"\n  Скинь другу ссылку (он в той же WiFi/LAN):")
    for ip in ips:
        print(f"  -> http://{ip}:{PORT}")
    print("\n  Нажми Ctrl+C для остановки\n")
    print(sep + "\n")

    def open_browser():
        time.sleep(0.5)
        try:
            webbrowser.open(f"http://localhost:{PORT}")
        except Exception:
            pass
    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nСервер остановлен.")
        server.shutdown()


if __name__ == '__main__':
    main()
