// 🤖 DEPRECATED (Hermes, 2026-08-13, G-02): ВТОРАЯ реализация desktop-оверлея.
// КАНОН = uni/desktop/main.js (оно поднято из scripts/launcher.js и содержит
// весь актуальный функционал: single-instance, VRM-аватар, captureStates,
// tray «Стоп/Выход», защищённый renderer v4). Этот каталог (uni/webui/desktop)
// — СТАРАЯ/дублирующая реализация, НЕ используется лаунчером.
// Не развивать; при необходимости — мержить в uni/desktop. Удалять запрещено (инвариант 0.2).
// UNI Desktop Companion — Electron main process (Hermes SOLO, 2026-08-11)
// Прозрачное frameless окно, always-on-top, click-through по альфе, трей, PTT-хоткей.
const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, nativeImage } = require("electron");
const path = require("path");
const http = require("http");

const SERVER = process.env.UNI_SERVER || "http://127.0.0.1:8787";
let win = null;
let tray = null;
let recording = false;

function createWindow() {
  win = new BrowserWindow({
    width: 520,
    height: 720,
    transparent: true,
    frame: false,
    hasShadow: false,
    skipTaskbar: false,
    alwaysOnTop: true,
    resizable: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });
  win.loadFile(path.join(__dirname, "index.html"));
  win.once("ready-to-show", () => win.show());

  // Click-through: рендерер сообщает, есть ли под курсором интерактивный пиксель
  win.setAlwaysOnTop(true, "screen-saver", 1);
  ipcMain.on("hit-test", (event, { x, y, interactive }) => {
    if (!win) return;
    win.setIgnoreMouseEvents(!interactive, { forward: true });
  });

  // SSE: /api/desktop/events -> пересылаем в рендерер
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
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const m = frame.match(/^data: (.+)$/m);
        if (m && win) win.webContents.send("desktop-event", m[1]);
      }
    });
  });
  req.on("error", () => setTimeout(connectEvents, 3000));
}

function setLevel(level) {
  const data = JSON.stringify({ observation_enabled: level !== "off", level });
  const r = http.request(
    SERVER + "/api/desktop/consent",
    { method: "POST", headers: { "Content-Type": "application/json" } },
    () => {}
  );
  r.write(data);
  r.end();
}

app.whenReady().then(() => {
  createWindow();
  // Трей
  const icon = nativeImage.createFromPath(path.join(__dirname, "tray.png"));
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip("UNI Desktop Companion");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Показать", click: () => win && win.show() },
      { label: "Наблюдение: выкл", click: () => setLevel("off") },
      { label: "Наблюдение: observe", click: () => setLevel("observe") },
      { label: "Наблюдение: suggest", click: () => setLevel("suggest") },
      { label: "Наблюдение: act", click: () => setLevel("act") },
      { type: "separator" },
      { label: "Выход", click: () => app.quit() },
    ])
  );
  // Глобальный PTT (push-to-talk): Ctrl+Shift+Space (не конфликтует с AHK Ctrl+Alt+*)
  try {
    globalShortcut.register("CommandOrControl+Shift+Space", () => {
      recording = !recording;
      if (win) win.webContents.send("ptt", recording);
    });
  } catch (e) {}
});

app.on("window-all-closed", () => {/* не выходим, живём в трее */});
app.on("activate", () => win && win.show());
