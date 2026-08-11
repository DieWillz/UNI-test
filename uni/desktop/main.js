// UNI Desktop Companion — main.js (Hermes SOLO, 2026-08-11, блок D)
// D-02: прозрачное frameless, alwaysOnTop, трей, автозапуск.
// D-03: click-through по альфе (hit-test от renderer).
// D-04: позиция у нижней кромки + учёт DPI (state.json).
const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, nativeImage } = require("electron");
const path = require("path");
const http = require("http");
const fs = require("fs");

const SERVER = process.env.UNI_SERVER || "http://127.0.0.1:8787";
const STATE_PATH = path.join(__dirname, "state.json");
let win = null;
let tray = null;
let recording = false;

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_PATH, "utf-8")); }
  catch { return {}; }
}
function saveState(obj) {
  const s = Object.assign(loadState(), obj);
  try { fs.writeFileSync(STATE_PATH, JSON.stringify(s, null, 2)); } catch {}
  return s;
}

function placeAtBottomRight(w) {
  const { screen } = require("electron");
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const b = w.getBounds();
  // D-04: у нижней кромки, справа; учёт DPI через workAreaSize (уже в физических пикселях)
  const x = width - b.width - 12;
  const y = height - b.height - 8;
  w.setPosition(Math.max(0, x), Math.max(0, y));
}

function createWindow() {
  win = new BrowserWindow({
    width: 520, height: 720,
    transparent: true, frame: false, hasShadow: false,
    skipTaskbar: false, alwaysOnTop: true, resizable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true, nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.once("ready-to-show", () => { win.show(); placeAtBottomRight(win); });

  // D-02: принудительно поверх всех (включая полноэкранные, где возможно)
  win.setAlwaysOnTop(true, "screen-saver", 1);
  placeAtBottomRight(win);

  // D-03: click-through по hit-test от renderer
  ipcMain.on("hit-test", (_e, interactive) => {
    if (win) win.setIgnoreMouseEvents(!interactive, { forward: true });
  });
  ipcMain.on("hide", () => win && win.hide());
  ipcMain.on("show", () => win && win.show());
  ipcMain.on("set-opacity", (_e, v) => { if (win) win.setOpacity(Number(v) || 1); });
  ipcMain.handle("save-state", (_e, obj) => saveState(obj));
  ipcMain.handle("load-state", () => loadState());
  // D-12: observe-тик — делает скриншот рабочего стола и отправляет в /api/vision/capture
  ipcMain.handle("observe-tick", async () => {
    try {
      const { desktopCapturer } = require("electron");
      const sources = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 320, height: 180 } });
      const src = sources[0];
      if (!src) return { ok: false, error: "no screen source" };
      const dataUrl = src.thumbnail.toDataURL();
      const b64 = dataUrl.split(",")[1];
      const r = await fetch(SERVER + "/api/vision/capture", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_b64: b64 }),
      });
      const d = await r.json().catch(() => ({}));
      return { ok: true, caption: d.caption || null };
    } catch (e) {
      return { ok: false, error: String(e && e.message || e) };
    }
  });
  connectEvents();
}

function connectEvents() {
  const req = http.get(SERVER + "/api/desktop/events", (res) => {
    res.setEncoding("utf8");
    let buf = "";
    res.on("data", (chunk) => {
      buf += chunk;
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
        const m = frame.match(/^data: (.+)$/m);
        if (m && win) win.webContents.send("desktop-event", m[1]);
      }
    });
  });
  req.on("error", () => setTimeout(connectEvents, 3000));
}

function setConsent(level) {
  const data = JSON.stringify({ observation_enabled: level !== "off", level });
  const r = http.request(SERVER + "/api/desktop/consent",
    { method: "POST", headers: { "Content-Type": "application/json" } }, () => {});
  r.write(data); r.end();
}

app.whenReady().then(() => {
  createWindow();
  // D-02: автозапуск (только если явно включено в state)
  const st = loadState();
  if (st.autostart) app.setLoginItemSettings({ openAtLogin: true });

  // Трей
  const icon = nativeImage.createFromPath(path.join(__dirname, "assets", "tray.png"));
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip("UNI Desktop Companion");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Показать", click: () => win && win.show() },
    { label: "Наблюдение: выкл", click: () => setConsent("off") },
    { label: "Наблюдение: observe", click: () => setConsent("observe") },
    { label: "Наблюдение: suggest", click: () => setConsent("suggest") },
    { label: "Наблюдение: act", click: () => setConsent("act") },
    { type: "separator" },
    { label: "Выход", click: () => app.quit() },
  ]));

  // D-10/P0: PTT хоткей (свободен от AHK Ctrl+Alt+*)
  try {
    globalShortcut.register("CommandOrControl+Shift+Space", () => {
      recording = !recording;
      if (win) win.webContents.send("ptt", recording);
    });
  } catch (e) {}
});

app.on("window-all-closed", () => {/* живём в трее */});
app.on("activate", () => win && win.show());
