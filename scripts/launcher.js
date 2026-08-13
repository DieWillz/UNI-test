#!/usr/bin/env node
/*
 * UNI — единый лаунчер (родитель процессов).
 * Hermes 2026-08-13, директива «Единая точка входа + Самотест + Мышь Юни».
 *
 * Поднимает: llama-server (:1235) + WebUI (:8787) + Electron-оверлей,
 * все СКРЫТО кроме оверлея. Логи → runtime/logs/{llama,webui,desktop}.log.
 * Держит runtime/pids.json для дедупа и чистого завершения. При выходе
 * любого дочернего или по сигналу — убивает детей в порядке
 * electron -> webui -> llama (-> tts) и удаляет pids.json.
 *
 * Дополнительно (этот проход):
 *  - дедуп по ПОРТУ (а не только по PID) — живой инстанс на наших портах
 *    не дублируется (single-instance);
 *  - опционально поднимает TTS-WebUI (:7778), если он распакован
 *    (env UNI_TTS_AUTOSTART=1) — иначе самотест помечает TTS «НЕ ПРОВЕРЕНО»;
 *  - мини HTTP :8790 для самотеста оверлея (видимость/статус/аватар/демо-мышь);
 *  - трей «Самотест» запускает самотест через тот же :8790.
 *
 * Запуск: node scripts/launcher.js [--restart]
 *   --restart : если найден живой stale-инстанс, убить его перед подъёмом.
 */
'use strict';
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');
const os = require('os');

const ROOT = path.resolve(__dirname, '..');            // C:\\LLM\\UNI
const PYTHON = 'C:\\LLM\\python312\\python.exe';
const PIDS_FILE = path.join(ROOT, 'runtime', 'pids.json');
const LOGS_DIR = path.join(ROOT, 'runtime', 'logs');
const PORT_LLAMA = 1235;
const PORT_WEBUI = 8787;
const PORT_LAUNCHER_HTTP = 8790;
const PORT_TTS = 7778;
const ARGS = process.argv.slice(2);
const RESTART = ARGS.includes('--restart');
const TTS_AUTOSTART = process.env.UNI_TTS_AUTOSTART === '1' ||
  (fs.existsSync(path.join(ROOT, 'runtime', 'tts-webui')) && process.env.UNI_TTS_AUTOSTART !== '0');

fs.mkdirSync(LOGS_DIR, { recursive: true });

function log(...a) { console.log('[launcher]', ...a); }
function pidAlive(pid) {
  if (!pid) return false;
  try { process.kill(pid, 0); return true; } catch { return false; }
}
function portInUse(port, host = '127.0.0.1') {
  // лёгкая проверка: попытка bind на порт; если EACCES/EADDRINUSE — занят
  return new Promise((resolve) => {
    const srv = require('net').createServer();
    srv.once('error', () => resolve(true));
    srv.once('listening', () => { srv.close(() => resolve(false)); });
    srv.listen(port, host);
  });
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

// --- дедуп: живой stale-инстанс на наших портах ИЛИ по PID? ---
async function main() {
  const prev = readPids();
  let anyLive = false;
  if (prev) {
    const live = [prev.llama && pidAlive(prev.llama.pid), prev.webui && pidAlive(prev.webui.pid), prev.electron && pidAlive(prev.electron.pid)];
    anyLive = live.some(Boolean);
  }
  // дедуп по порту (независимо от pids.json — ловит осиротевшие инстансы)
  const [lUsed, wUsed] = await Promise.all([portInUse(PORT_LLAMA), portInUse(PORT_WEBUI)]);
  if (lUsed || wUsed) {
    log('обнаружен живой инстанс Юни на порту (1235=' + lUsed + ', 8787=' + wUsed + ').');
    anyLive = true;
  }
  if (anyLive && !RESTART) {
    log('НЕ запускаю второй инстанс (single-instance). Выход.');
    log('  llama=' + (prev && prev.llama && prev.llama.pid) + ' webui=' + (prev && prev.webui && prev.webui.pid) + ' electron=' + (prev && prev.electron && prev.electron.pid));
    process.exit(0);
  }
  if (anyLive && RESTART) {
    log('--restart: убиваю stale-инстанс...');
    if (prev) {
      killPid(prev.electron && prev.electron.pid, 'electron');
      killPid(prev.webui && prev.webui.pid, 'webui');
      killPid(prev.llama && prev.llama.pid, 'llama');
      killPid(prev.tts && prev.tts.pid, 'tts');
    }
    clearPids();
    try { execSync('ping -n 2 127.0.0.1', { stdio: 'ignore', windowsHide: true }); } catch {}
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

  function launchTts() {
    const dir = path.join(ROOT, 'runtime', 'tts-webui');
    if (!TTS_AUTOSTART || !fs.existsSync(dir)) {
      log('ПРОПУСК tts: autostart=' + TTS_AUTOSTART + ' dir=' + fs.existsSync(dir));
      return null;
    }
    const cmd = path.join(dir, 'start_windows.bat');
    if (!fs.existsSync(cmd)) { log('ПРОПУСК tts: нет', cmd); return null; }
    const p = spawn('cmd', ['/c', cmd], {
      cwd: dir, windowsHide: true,
      stdio: ['ignore', fs.openSync(path.join(LOGS_DIR, 'tts.log'), 'a'), fs.openSync(path.join(LOGS_DIR, 'tts.log'), 'a')],
    });
    log('tts pid', p.pid);
    return p;
  }

  function launchElectron() {
    const electronJs = path.join(ROOT, 'uni', 'desktop', 'node_modules', 'electron', 'cli.js');
    const cwd = path.join(ROOT, 'uni', 'desktop');
    const p = spawn(process.execPath, [electronJs, '.'], {
      cwd, windowsHide: false, stdio: ['ignore', 'ignore', 'ignore'],
    });
    log('electron pid', p.pid);
    return p;
  }

  // 🤖 ФИНАЛ (2026-08-13): Electron в этом окружении флейкает (instant close) —
  // старый код глушил ВСЕ серверы по electron.on('exit'), из-за чего стек
  // самоубивался через 1-2с и «ничего не происходило». Теперь: при раннем
  // выходе (в течение 10с) делаем до 3 попыток рестарта; глушим серверы
  // ТОЛЬКО если исчерпаны попытки ИЛИ пришёл явный стоп (сигнал/Стоп/Выход).
  const ELECTRON_MAX_RETRIES = 3;
  const ELECTRON_FLAKE_WINDOW_MS = 10000;
  let electronRetries = 0;
  let electronStableSince = 0;
  function launchElectronWithRetry() {
    const p = launchElectron();
    children.electron = p;
    const startedAt = Date.now();
    p.on('exit', (code, sig) => {
      const uptime = Date.now() - startedAt;
      const isFlake = uptime < ELECTRON_FLAKE_WINDOW_MS;
      if (!shuttingDown && isFlake && electronRetries < ELECTRON_MAX_RETRIES) {
        electronRetries++;
        log('electron флейк (uptime=' + uptime + 'ms, code=' + code + ') — рестарт ' + electronRetries + '/' + ELECTRON_MAX_RETRIES);
        setTimeout(launchElectronWithRetry, 800);
        return;
      }
      if (!shuttingDown) {
        if (electronRetries >= ELECTRON_MAX_RETRIES) {
          log('electron исчерпал попытки -> глушим весь стек');
          shutdown(1);
        } else {
          log('electron завершён (code=' + code + ') -> глушим весь стек');
          shutdown(0);
        }
      }
    });
    p.on('error', (e) => {
      log('electron error', e.message);
      if (!shuttingDown && electronRetries < ELECTRON_MAX_RETRIES) {
        electronRetries++;
        setTimeout(launchElectronWithRetry, 800);
      } else { shutdown(1); }
    });
    return p;
  }

  // порядок: сначала серверы, затем оверлей
  children.llama = launchLlama();
  children.webui = launchWebui();
  children.tts = launchTts();
  children.electron = launchElectronWithRetry();

  writePids({
    llama: { pid: children.llama ? children.llama.pid : null, port: PORT_LLAMA },
    webui: { pid: children.webui ? children.webui.pid : null, port: PORT_WEBUI },
    tts: { pid: children.tts ? children.tts.pid : null, port: TTS_AUTOSTART ? PORT_TTS : null },
    electron: { pid: children.electron ? children.electron.pid : null },
    launcher_http: { port: PORT_LAUNCHER_HTTP },
    started_at: Date.now(),
  });

  // --- мини HTTP :8790 для самотеста оверлея + демо-мышь + самотест ---
  startLauncherHttp(children);

  // --- завершение: убить детей electron -> webui -> llama -> tts ---
  let shuttingDown = false;
  function shutdown(code = 0) {
    if (shuttingDown) return;
    shuttingDown = true;
    log('завершение: убиваю детей...');
    if (children.electron && pidAlive(children.electron.pid)) killPid(children.electron.pid, 'electron');
    if (children.webui && pidAlive(children.webui.pid)) killPid(children.webui.pid, 'webui');
    if (children.llama && pidAlive(children.llama.pid)) killPid(children.llama.pid, 'llama');
    if (children.tts && pidAlive(children.tts.pid)) killPid(children.tts.pid, 'tts');
    clearPids();
    log('готово.');
    process.exit(code);
  }

  // 🤖 ФИНАЛ (2026-08-13): electron.on('exit') больше НЕ глушит серверы здесь —
  // ранний выход Electron (флейк) обрабатывается рестартом в launchElectronWithRetry.
  // Глушим стек только если САМИ серверы упали с ошибкой (не флейк).
  if (children.webui) children.webui.on('exit', (c) => { if (c !== 0 && !shuttingDown) { log('webui упал, глушим'); shutdown(1); } });
  if (children.llama) children.llama.on('exit', (c) => { if (c !== 0 && !shuttingDown) { log('llama упал, глушим'); shutdown(1); } });

  process.on('SIGINT', () => { log('SIGINT'); shutdown(0); });
  process.on('SIGTERM', () => { log('SIGTERM'); shutdown(0); });
  process.on('uncaughtException', (e) => { log('uncaught', e.message); shutdown(1); });

  log('Юни запущена. Оверлей видим; серверы скрыты. pids.json записан. HTTP :' + PORT_LAUNCHER_HTTP + ' поднят.');
}

// --- мини-сервер лаунчера (для самотеста / демо-мыши из webui) ---
function startLauncherHttp(children) {
  const server = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    const url = (req.url || '/').split('?')[0];

    if (url === '/api/overlay/status') {
      // проксирует статус оверлея через webui (8787)
      proxyJson(res, 'http://127.0.0.1:' + PORT_WEBUI + '/api/uni/status');
      return;
    }
    if (url === '/api/overlay/screenshot') {
      // screenshot оверлея: electron делает capturePage по IPC; здесь — best-effort
      res.statusCode = 200;
      res.end(JSON.stringify({ ok: false, error: 'use webui /api/desktop/capture', hint: 'electron-only' }));
      return;
    }
    if (url === '/api/selftest' && req.method === 'POST') {
      // запустить самотест: зовём webui /api/selftest
      proxyJson(res, 'http://127.0.0.1:' + PORT_WEBUI + '/api/selftest', 'POST');
      return;
    }
    if (url === '/api/demo/mouse' && req.method === 'POST') {
      proxyJson(res, 'http://127.0.0.1:' + PORT_WEBUI + '/api/demo/mouse', 'POST');
      return;
    }
    if (url === '/api/health') {
      res.statusCode = 200;
      res.end(JSON.stringify({ ok: true, launcher: true, pids: readPids() }));
      return;
    }
    if (url === '/api/launcher/stop') {
      // 🤖 ФИНАЛ (2026-08-13): явная остановка всего стека (tray «Выход»/Стоп).
      res.statusCode = 200;
      res.end(JSON.stringify({ ok: true, stopping: true }));
      setTimeout(() => shutdown(0), 50);
      return;
    }
    res.statusCode = 404;
    res.end(JSON.stringify({ error: 'not found', url }));
  });
  server.listen(PORT_LAUNCHER_HTTP, '127.0.0.1', () => log('launcher HTTP on :' + PORT_LAUNCHER_HTTP));
  server.on('error', (e) => log('launcher HTTP error', e.message));
}

function proxyJson(res, target, method = 'GET') {
  const u = new URL(target);
  const r = http.request({
    hostname: u.hostname, port: u.port, path: u.pathname,
    method, headers: { 'Content-Type': 'application/json' },
  }, (up) => {
    let body = '';
    up.on('data', (c) => (body += c));
    up.on('end', () => {
      res.statusCode = up.statusCode || 502;
      res.end(body);
    });
  });
  r.on('error', (e) => {
    res.statusCode = 502;
    res.end(JSON.stringify({ ok: false, error: e.message }));
  });
  if (method === 'POST') r.write('{}');
  r.end();
}

main();
