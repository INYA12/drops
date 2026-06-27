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
<title>DROPS LAN — Apple Glass Light Mode</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f4f5fa;
  --glass:rgba(255,255,255,0.42);
  --glass-hover:rgba(255,255,255,0.65);
  --glass-active:rgba(255,255,255,0.8);
  --border:rgba(255,255,255,0.7);
  --border-hover:rgba(255,255,255,0.9);
  --border-element:rgba(0,0,0,0.06);
  --border-element-hover:rgba(0,0,0,0.12);
  --accent:#0f1016;
  --text:#0f1016;
  --text-muted:rgba(15,16,22,0.6);
  --text-dim:rgba(15,16,22,0.35);
  --radius-lg:30px;
  --radius-md:18px;
  --radius-sm:12px;
  --transition:all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  --green:#24b33b;
  --red:#ff3b30;
  --shadow:0 30px 70px rgba(31,38,135,0.06), inset 0 1px 0 rgba(255,255,255,0.9), inset 0 -1px 0 rgba(0,0,0,0.02);
}

html,body{
  height:100%;
  font-family:'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  background-color:var(--bg);
  color:var(--text);
  overflow-x:hidden;
  -webkit-font-smoothing:antialiased;
}

/* Light visionOS space background */
.space-bg {
  position: fixed;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
  background: radial-gradient(circle at 50% 50%, #f7f8fc 0%, #e8ecf5 100%);
}

.aurora {
  position: absolute;
  border-radius: 50%;
  filter: blur(130px);
  opacity: 0.55;
  mix-blend-mode: multiply;
  transition: var(--transition);
}

.aurora-1 {
  top: -15%;
  left: -5%;
  width: 65vw;
  height: 65vw;
  background: radial-gradient(circle, #e1e0ff 0%, rgba(225,224,255,0) 70%);
  animation: float-aurora-1 25s infinite alternate ease-in-out;
}

.aurora-2 {
  bottom: -20%;
  right: -10%;
  width: 75vw;
  height: 75vw;
  background: radial-gradient(circle, #fde4ff 0%, rgba(253,228,255,0) 70%);
  animation: float-aurora-2 30s infinite alternate ease-in-out;
}

.aurora-3 {
  top: 25%;
  right: -5%;
  width: 55vw;
  height: 55vw;
  background: radial-gradient(circle, #e0f9ff 0%, rgba(224,249,255,0) 70%);
  animation: float-aurora-3 22s infinite alternate ease-in-out;
}

@keyframes float-aurora-1 {
  0% { transform: translate(0, 0) scale(1) rotate(0deg); }
  50% { transform: translate(10%, 8%) scale(1.1) rotate(60deg); }
  100% { transform: translate(-5%, -5%) scale(0.95) rotate(120deg); }
}

@keyframes float-aurora-2 {
  0% { transform: translate(0, 0) scale(1.05) rotate(0deg); }
  50% { transform: translate(-8%, -12%) scale(0.98) rotate(-90deg); }
  100% { transform: translate(5%, 5%) scale(1.02) rotate(-180deg); }
}

@keyframes float-aurora-3 {
  0% { transform: translate(0, 0) scale(0.95) rotate(0deg); }
  50% { transform: translate(-10%, 10%) scale(1.05) rotate(45deg); }
  100% { transform: translate(5%, -5%) scale(1) rotate(90deg); }
}

/* Subtle grid overlay */
.grid-overlay {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(15,16,22,0.02) 1px, transparent 1px);
  background-size: 32px 32px;
  opacity: 0.8;
}

/* Header */
header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  backdrop-filter: blur(40px) saturate(220%);
  -webkit-backdrop-filter: blur(40px) saturate(220%);
  background: rgba(255, 255, 255, 0.35);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  position: sticky;
  top: 0;
  z-index: 100;
}

.brand {
  display: flex;
  align-items: center;
  gap: 16px;
  cursor: pointer;
}

.logo-icon {
  width: 46px;
  height: 46px;
  background: rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}

.brand:hover .logo-icon {
  transform: scale(1.08);
  background: #0f1016;
  border-color: #0f1016;
}

.brand:hover .logo-icon svg {
  stroke: #ffffff;
}

.logo-icon svg {
  stroke: var(--text);
  width: 24px;
  height: 24px;
  transition: var(--transition);
}

h1 {
  font-family: 'Outfit', sans-serif;
  font-size: 1.9rem;
  font-weight: 700;
  letter-spacing: -0.8px;
}

h1 span {
  font-weight: 300;
  color: var(--text-muted);
}

/* Container */
.container {
  max-width: 820px;
  margin: 0 auto;
  padding: 40px 24px 80px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

/* Premium Light Frosted Glass Card */
.card {
  position: relative;
  background: var(--glass);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 32px;
  backdrop-filter: blur(40px) saturate(220%);
  -webkit-backdrop-filter: blur(40px) saturate(220%);
  box-shadow: var(--shadow);
  transition: var(--transition);
}

.card:hover {
  border-color: var(--border-hover);
  background: rgba(255, 255, 255, 0.55);
  box-shadow: 0 40px 80px rgba(31,38,135,0.09), inset 0 1px 0 rgba(255,255,255,0.95);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--text-muted);
  margin-bottom: 24px;
}

.card-title svg {
  color: var(--text);
  width: 20px;
  height: 20px;
  opacity: 0.8;
}

/* IPs Apple-Style Grid */
.ip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.ip-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.35);
  border: 1px solid var(--border-element);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  transition: var(--transition);
}

.ip-item:hover {
  background: rgba(255, 255, 255, 0.6);
  border-color: rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.ip-addr {
  font-family: 'Outfit', monospace;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text);
}

.copy-btn {
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.05);
  color: var(--text);
  border-radius: 20px;
  padding: 8px 16px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}

.copy-btn:hover {
  background: #0f1016;
  color: #ffffff;
  border-color: #0f1016;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
  transform: scale(1.04);
}

/* Drop Zone */
.drop-zone {
  position: relative;
  border: 2px dashed rgba(0, 0, 0, 0.1);
  text-align: center;
  cursor: pointer;
  transition: var(--transition);
  padding: 64px 24px;
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.2);
}

.drop-zone:hover {
  border-color: rgba(0,0,0,0.3);
  background: rgba(255, 255, 255, 0.45);
}

.drop-zone.drag-over {
  border-color: #000000;
  background: rgba(255, 255, 255, 0.6);
  box-shadow: 0 0 40px rgba(0,0,0,0.05);
  transform: scale(0.99);
}

.drop-icon {
  width: 80px;
  height: 80px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
  transition: var(--transition);
  box-shadow: 0 8px 24px rgba(0,0,0,0.02);
}

.drop-zone:hover .drop-icon {
  background: #0f1016;
  transform: scale(1.08);
  box-shadow: 0 12px 36px rgba(0,0,0,0.15);
}

.drop-zone:hover .drop-icon svg {
  stroke: #ffffff;
}

.drop-icon svg {
  stroke: var(--text);
  width: 32px;
  height: 32px;
  transition: var(--transition);
}

.drop-zone h3 {
  font-size: 1.3rem;
  font-weight: 600;
  margin-bottom: 8px;
  letter-spacing: -0.3px;
}

.drop-zone p {
  font-size: 0.95rem;
  color: var(--text-muted);
}

#file-input {
  display: none;
}

/* Upload Progress */
.upload-status {
  display: none;
  margin-top: 24px;
  background: rgba(255, 255, 255, 0.5);
  padding: 20px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-element);
  text-align: left;
}

.upload-status.show {
  display: block;
  animation: fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.upload-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
  margin-bottom: 12px;
  font-weight: 600;
}

.upload-filename {
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 65%;
}

.upload-stats {
  display: flex;
  gap: 16px;
  color: var(--text-muted);
}

.progress-wrap {
  height: 6px;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 99px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: #0f1016;
  width: 0%;
  transition: width 0.2s linear;
  border-radius: 99px;
  box-shadow: 0 0 12px rgba(0,0,0,0.15);
}

/* File Items */
.files-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 20px;
  background: rgba(255, 255, 255, 0.3);
  border: 1px solid var(--border-element);
  border-radius: var(--radius-md);
  padding: 18px 24px;
  transition: var(--transition);
  animation: slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.file-item:hover {
  background: rgba(255, 255, 255, 0.55);
  border-color: rgba(0, 0, 0, 0.15);
  transform: translateX(4px);
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.file-icon {
  width: 50px;
  height: 50px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(0, 0, 0, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: var(--transition);
}

.file-item:hover .file-icon {
  background: #ffffff;
  border-color: rgba(0, 0, 0, 0.1);
}

.file-icon svg {
  width: 24px;
  height: 24px;
  stroke: var(--text);
  opacity: 0.85;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.file-size {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.file-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: none;
  border-radius: 20px;
  padding: 10px 20px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
  text-decoration: none;
  outline: none;
}

.btn-download {
  background: #0f1016;
  color: #ffffff;
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}

.btn-download:hover {
  background: rgba(15,16,22,0.85);
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 8px 24px rgba(0,0,0,0.18);
}

.btn-remove {
  background: rgba(255, 59, 48, 0.08);
  color: var(--red);
  border: 1px solid rgba(255, 59, 48, 0.15);
  border-radius: 50%;
  padding: 10px;
  width: 40px;
  height: 40px;
}

.btn-remove:hover {
  background: var(--red);
  color: #fff;
  border-color: var(--red);
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 6px 16px rgba(255, 59, 48, 0.25);
}

.empty-text {
  text-align: center;
  color: var(--text-muted);
  font-size: 0.95rem;
  padding: 40px;
  font-weight: 500;
}

/* Notifications */
.notif {
  position: fixed;
  bottom: 40px;
  left: 50%;
  transform: translate(-50%, 100px);
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(0,0,0,0.06);
  color: var(--text);
  border-radius: 40px;
  padding: 14px 28px;
  font-size: 0.9rem;
  font-weight: 600;
  box-shadow: 0 20px 50px rgba(0,0,0,0.08);
  z-index: 1000;
  opacity: 0;
  transition: var(--transition);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  pointer-events: none;
}

.notif.show {
  transform: translate(-50%, 0);
  opacity: 1;
}

.notif.error {
  background: rgba(255, 235, 235, 0.95);
  border-color: rgba(255, 59, 48, 0.3);
  color: var(--red);
}

@media(max-width:600px){
  .container { padding: 24px 16px 60px; }
  .card { padding: 24px; }
  .file-item { flex-direction: column; align-items: stretch; gap: 16px; padding: 20px; }
  .file-actions { width: 100%; justify-content: flex-end; }
  .btn-download { flex: 1; }
}
</style>
</head>
<body>
<div class="space-bg">
  <div class="aurora aurora-1"></div>
  <div class="aurora aurora-2"></div>
  <div class="aurora aurora-3"></div>
  <div class="grid-overlay"></div>
</div>

<header>
  <div class="brand">
    <div class="logo-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    </div>
    <h1>DROPS <span>LAN</span></h1>
  </div>
</header>

<div class="container">
  <!-- Network addresses -->
  <div class="card">
    <div class="card-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
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
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
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
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
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
  n.textContent=msg;
  n.className='notif '+type+' show';
  setTimeout(()=>{
    n.classList.remove('show');
  },3000);
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
      if(dt > 0.5){
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
