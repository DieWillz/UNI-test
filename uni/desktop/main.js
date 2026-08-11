// UNI Desktop Companion — main.js (Hermes, финальная директива 2026-08-12 F-01..F-05)
// F-02: логирование в desktop.log + перехват uncaughtException/unhandledRejection.
// F-03: окно создаётся и показывается ДАЖЕ если сервер недоступен; «Показать» пересоздаёт.
// F-04: single-instance lock; автозапуск дефолт false.
// F-05: VRM-аватар (three-vrm) подхватывается из assets/UNI.vrm; SVG — fallback.
const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");

const SERVER = process.env.UNI_SERVER || "http://127.0.0.1:8787";
const STATE_PATH = path.join(__dirname, "state.json");
const LOG_PATH = path.join(__dirname, "desktop.log");
const VRM_PATH = path.join(__dirname, "assets", "UNI.vrm");

let win = null;
let tray = null;
let recording = false;
let sseReq = null;

// ── F-02: логирование ───────────────────────────────────────────────
function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.map(String).join(" ")}`;
  try { fs.appendFileSync(LOG_PATH, line + "\n"); } catch {}
  console.log(line);
}
// F-02: перехват необработанных ошибок — в лог, НЕ краш-диалог
process.on("uncaughtException", (err) => {
  log("UNCAUGHT:", err && err.stack || err);
  if (tray) tray.setToolTip("UNI: ошибка, см. desktop.log");
});
process.on("unhandledRejection", (reason) => {
  log("UNHANDLED_REJECTION:", reason && reason.stack || reason);
});

// ── состояние ───────────────────────────────────────────────────────
function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_PATH, "utf-8")); }
  catch { return {}; }
}
function saveState(obj) {
  const s = Object.assign(loadState(), obj);
  try { fs.writeFileSync(STATE_PATH, JSON.stringify(s, null, 2)); } catch {}
  return s;
}

// ── F-05: позиция у нижней кромки ──────────────────────────────────
function placeAtBottomRight(w) {
  try {
    const { screen } = require("electron");
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    const b = w.getBounds();
    const x = Math.max(0, width - b.width - 12);
    const y = Math.max(0, height - b.height - 8);
    w.setPosition(x, y);
    log("setBounds", JSON.stringify(b), "->", x, y);
  } catch (e) { log("placeAtBottomRight error", e.message); }
}

// ── HTTP через fetch (F-01: уходит от Parse Error http.* к серверу) ─
async function httpPost(urlPath, body, headers) {
  try {
    log("HTTP POST", SERVER + urlPath);
    const r = await fetch(SERVER + urlPath, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, headers || {}),
      body: JSON.stringify(body),
    });
    log("HTTP POST", urlPath, "status", r.status);
    return r;
  } catch (e) {
    log("HTTP POST", urlPath, "ERROR", e.message);
    return null;
  }
}
async function httpGetJSON(urlPath) {
  try {
    log("HTTP GET", SERVER + urlPath);
    const r = await fetch(SERVER + urlPath);
    const d = await r.json().catch(() => ({}));
    log("HTTP GET", urlPath, "status", r.status);
    return d;
  } catch (e) {
    log("HTTP GET", urlPath, "ERROR", e.message);
    return null;
  }
}

// ── F-03: создание/пересоздание окна ───────────────────────────────
function createWindow() {
  if (win && !win.isDestroyed()) { win.show(); win.focus(); return; }
  log("createWindow");
  win = new BrowserWindow({
    width: 380, height: 640,
    transparent: true, frame: false, hasShadow: false,
    skipTaskbar: false, alwaysOnTop: true, resizable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true, nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.once("ready-to-show", () => {
    win.show(); placeAtBottomRight(win);
    log("ready-to-show -> show, visible=", win.isVisible());
  });
  win.on("closed", () => { win = null; log("window closed"); });

  // F-02: ошибки renderer прилетают сюда
  win.webContents.on("render-process-gone", (_e, details) => log("renderer gone:", details.reason));
  win.webContents.on("console-message", (_e, level, msg) => log("renderer console:", msg));

  // F-02: лог из renderer -> desktop.log
  ipcMain.on("log", (_e, msg) => log("[renderer]", msg));
  // D-03: click-through по hit-test от renderer
  ipcMain.on("hit-test", (_e, interactive) => {
    if (win && !win.isDestroyed()) win.setIgnoreMouseEvents(!interactive, { forward: true });
  });
  ipcMain.on("hide", () => { if (win && !win.isDestroyed()) win.hide(); });
  ipcMain.on("show", () => { if (win && !win.isDestroyed()) win.show(); });
  ipcMain.on("set-opacity", (_e, v) => { if (win && !win.isDestroyed()) win.setOpacity(Number(v) || 1); });
  ipcMain.handle("save-state", (_e, obj) => saveState(obj));
  ipcMain.handle("load-state", () => loadState());
  ipcMain.handle("get-bounds", () => (win && !win.isDestroyed()) ? win.getBounds() : null);
  ipcMain.handle("is-visible", () => (win && !win.isDestroyed()) ? win.isVisible() : false);

  // D-12: observe-тик — скриншот экрана -> /api/vision/capture
  ipcMain.handle("observe-tick", async () => {
    try {
      const { desktopCapturer } = require("electron");
      const sources = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 320, height: 180 } });
      const src = sources[0];
      if (!src) return { ok: false, error: "no screen source" };
      const b64 = src.thumbnail.toDataURL().split(",")[1];
      const r = await httpPost("/api/vision/capture", { image_b64: b64 });
      const d = r ? await r.json().catch(() => ({})) : {};
      return { ok: true, caption: d.caption || null };
    } catch (e) {
      log("observe-tick error", e.message);
      return { ok: false, error: String(e && e.message || e) };
    }
  });

  connectEvents();
  log("createWindow done");
}

// F-01/F-02: SSE через fetch (streaming) — без http.get/Parse Error
async function connectEvents() {
  try {
    log("SSE connect", SERVER + "/api/desktop/events");
    const r = await fetch(SERVER + "/api/desktop/events");
    if (!r.ok || !r.body) { setTimeout(connectEvents, 3000); return; }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i); buf = buf.slice(i + 2);
        const m = frame.match(/^data: (.+)$/m);
        if (m && win && !win.isDestroyed()) {
          try { win.webContents.send("desktop-event", m[1]); } catch (e) { log("send event error", e.message); }
        }
      }
    }
  } catch (e) {
    log("SSE error", e.message);
  }
  setTimeout(connectEvents, 3000);
}

function setConsent(level) {
  httpPost("/api/desktop/consent", { observation_enabled: level !== "off", level });
  log("tray consent ->", level);
}

// ── F-04: single-instance ──────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) { app.quit(); }
app.on("second-instance", () => { createWindow(); }); // второй экземпляр -> показать окно

app.whenReady().then(() => {
  log("app ready");
  createWindow();

  // F-04: автозапуск дефолт false
  const st = loadState();
  if (st.autostart) app.setLoginItemSettings({ openAtLogin: true });
  else app.setLoginItemSettings({ openAtLogin: false });

  // F-03: трей
  const icon = nativeImage.createFromPath(path.join(__dirname, "assets", "tray.png"));
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip("UNI Desktop Companion");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Показать", click: () => { log("tray: Показать"); createWindow(); } },
    { label: "Наблюдение: выкл", click: () => setConsent("off") },
    { label: "Наблюдение: observe", click: () => setConsent("observe") },
    { label: "Наблюдение: suggest", click: () => setConsent("suggest") },
    { label: "Наблюдение: act", click: () => setConsent("act") },
    { type: "separator" },
    { label: "Выход", click: () => { log("tray: Выход"); app.quit(); } },
  ]));

  // D-10: PTT хоткей
  try {
    globalShortcut.register("CommandOrControl+Shift+Space", () => {
      recording = !recording;
      if (win && !win.isDestroyed()) win.webContents.send("ptt", recording);
    });
  } catch (e) { log("PTT register error", e.message); }

  log("whenReady done");
});

app.on("window-all-closed", () => { /* живём в трее */ });
app.on("activate", () => createWindow());
