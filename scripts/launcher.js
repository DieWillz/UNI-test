#!/usr/bin/env node
/*
 * UNI — единый лаунчер (родитель процессов).
 * Hermes 2026-08-13, по директиве «Единый лаунчер».
 *
 * Поднимает: llama-server (:1235) + WebUI (:8787) + Electron-оверлей,
 * все СКРЫТО кроме оверлея. Держит runtime/pids.json для дедупа и чистого
 * завершения. При выходе любого дочернего или по сигналу — убивает детей
 * в порядке electron -> webui -> llama и удаляет pids.json.
 *
 * Запуск: node scripts/launcher.js [--restart]
 *   --restart : если найден живой stale-инстанс, убить его перед подъёмом.
 */
'use strict';
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const ROOT = path.resolve(__dirname, '..');            // C:\LLM\UNI
const PYTHON = 'C:\\LLM\\python312\\python.exe';
const PIDS_FILE = path.join(ROOT, 'runtime', 'pids.json');
const LOGS_DIR = path.join(ROOT, 'runtime', 'logs');
const PORT_LLAMA = 1235;
const PORT_WEBUI = 8787;
const ARGS = process.argv.slice(2);
const RESTART = ARGS.includes('--restart');

fs.mkdirSync(LOGS_DIR, { recursive: true });

function log(...a) { console.log('[launcher]', ...a); }
function pidAlive(pid) {
  if (!pid) return false;
  try { process.kill(pid, 0); return true; } catch { return false; }
}
function killPid(pid, label) {
  if (!pid || !pidAlive(pid)) return;
  try {
    execSync(`taskkill /F /PID ${pid} /T`, { stdio: 'ignore', windowsHide: true });
    log('killed', label, pid);
  } catch (e) { log('kill failed', label, pid, e.message); }
}
function readPids() {
  try { return JSON.parse(fs.readFileSync(PIDS_FILE, 'utf8')); } catch { return null; }
}
function writePids(obj) { fs.writeFileSync(PIDS_FILE, JSON.stringify(obj, null, 2)); }
function clearPids() { try { fs.unlinkSync(PIDS_FILE); } catch {} }

// --- дедуп: живой stale-инстанс на наших портах? ---
const prev = readPids();
if (prev) {
  const live = [prev.llama && pidAlive(prev.llama.pid), prev.webui && pidAlive(prev.webui.pid), prev.electron && pidAlive(prev.electron.pid)];
  const anyLive = live.some(Boolean);
  if (anyLive && !RESTART) {
    log('обнаружен живой инстанс Юни (pids.json), НЕ запускаю второй. Выход.');
    log('  llama=' + (prev.llama && prev.llama.pid) + ' webui=' + (prev.webui && prev.webui.pid) + ' electron=' + (prev.electron && prev.electron.pid));
    process.exit(0);
  }
  if (anyLive && RESTART) {
    log('--restart: убиваю stale-инстанс...');
    killPid(prev.electron && prev.electron.pid, 'electron');
    killPid(prev.webui && prev.webui.pid, 'webui');
    killPid(prev.llama && prev.llama.pid, 'llama');
    clearPids();
    // дать портам освободиться
    try { execSync('ping -n 2 127.0.0.1', { stdio: 'ignore', windowsHide: true }); } catch {}
  }
}

// --- spawn детей ---
const children = {};

function launchLlama() {
  const bin = path.join(ROOT, 'runtime', 'llama', 'llama-server.exe');
  if (!fs.existsSync(bin)) { log('ПРОПУСК llama: нет', bin); return null; }
  const model = path.join(ROOT, 'downloads', 'Qwen3-8B-Q4_K_M.gguf');
  const args = ['--model', model, '--host', '127.0.0.1', '--port', String(PORT_LLAMA),
    '--n-gpu-layers', '99', '--api-key', 'uni-local'];
  const p = spawn(bin, args, {
    cwd: ROOT, windowsHide: true,
    stdio: ['ignore', fs.openSync(path.join(LOGS_DIR, 'llama-server.log'), 'a'), fs.openSync(path.join(LOGS_DIR, 'llama-server.log'), 'a')],
  });
  log('llama pid', p.pid);
  return p;
}

function launchWebui() {
  const p = spawn(PYTHON, ['-m', 'uni.webui.server'], {
    cwd: ROOT, env: Object.assign({}, process.env, { PYTHONPATH: ROOT }),
    windowsHide: true,
    stdio: ['ignore', fs.openSync(path.join(LOGS_DIR, 'webui.log'), 'a'), fs.openSync(path.join(LOGS_DIR, 'webui.log'), 'a')],
  });
  log('webui pid', p.pid);
  return p;
}

function launchElectron() {
  const electron = path.join(ROOT, 'uni', 'desktop', 'node_modules', '.bin', 'electron.cmd');
  const electronJs = path.join(ROOT, 'uni', 'desktop', 'node_modules', 'electron', 'cli.js');
  const cwd = path.join(ROOT, 'uni', 'desktop');
  // Запускаем electron через node cli.js напрямую (без .cmd и без shell — надёжнее на Windows)
  const p = spawn(process.execPath, [electronJs, '.'], {
    cwd, windowsHide: false, stdio: ['ignore', 'ignore', 'ignore'],
  });
  log('electron pid', p.pid);
  return p;
}

// порядок: сначала серверы, затем оверлей
children.llama = launchLlama();
children.webui = launchWebui();
children.electron = launchElectron();

writePids({
  llama: { pid: children.llama ? children.llama.pid : null, port: PORT_LLAMA },
  webui: { pid: children.webui ? children.webui.pid : null, port: PORT_WEBUI },
  electron: { pid: children.electron ? children.electron.pid : null },
  started_at: Date.now(),
});

// --- завершение: убить детей electron -> webui -> llama ---
let shuttingDown = false;
function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  log('завершение: убиваю детей...');
  if (children.electron) killPid(children.electron.pid, 'electron');
  if (children.webui) killPid(children.webui.pid, 'webui');
  if (children.llama) killPid(children.llama.pid, 'llama');
  clearPids();
  log('готово.');
  process.exit(code);
}

// выход оверлея (electron) => убить остальное
if (children.electron) {
  children.electron.on('exit', (c, s) => {
    log('electron завершился (code=' + c + ', signal=' + s + ') -> глушим всё');
    shutdown(0);
  });
  children.electron.on('error', (e) => { log('electron error', e.message); shutdown(1); });
}
// если упал llama или webui — тоже глушим, чтобы не висели осиротевшие
if (children.webui) children.webui.on('exit', (c) => { if (c !== 0 && !shuttingDown) { log('webui упал, глушим'); shutdown(1); } });
if (children.llama) children.llama.on('exit', (c) => { if (c !== 0 && !shuttingDown) { log('llama упал, глушим'); shutdown(1); } });

process.on('SIGINT', () => { log('SIGINT'); shutdown(0); });
process.on('SIGTERM', () => { log('SIGTERM'); shutdown(0); });
process.on('uncaughtException', (e) => { log('uncaught', e.message); shutdown(1); });

log('Юни запущена. Оверлей видим; серверы скрыты. pids.json записан.');
