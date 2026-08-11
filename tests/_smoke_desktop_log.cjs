// Smoke-тест F-02: desktop.log создаётся и пишется (мок electron, без GUI).
// Запуск: node tests/_smoke_desktop_log.cjs  (из корня проекта uni/desktop)
const fs = require("fs");
const path = require("path");
const Module = require("module");

const DESKTOP_DIR = path.join(__dirname, "..", "uni", "desktop");
const LOG_PATH = path.join(DESKTOP_DIR, "desktop.log");

// Фейковый electron
const fakeElectron = {
  app: {
    whenReady: () => Promise.resolve(),
    on: () => {},
    quit: () => {},
    requestSingleInstanceLock: () => true,
    setLoginItemSettings: () => {},
    getPath: () => DESKTOP_DIR,
  },
  BrowserWindow: class { constructor() { this.webContents = { on: () => {}, send: () => {} }; }
    loadFile() {} on() {} once() {} show() {} focus() {} hide() {} setIgnoreMouseEvents() {}
    setOpacity() {} getBounds() { return { x: 0, y: 0, width: 380, height: 640 }; }
    isVisible() { return true; } isDestroyed() { return false; } setPosition() {} },
  Tray: class { constructor() {} setToolTip() {} setContextMenu() {} },
  Menu: { buildFromTemplate: () => ({}) },
  globalShortcut: { register: () => {} },
  ipcMain: { on: () => {}, handle: () => {} },
  nativeImage: { createFromPath: () => ({ isEmpty: () => true }), createEmpty: () => ({}) },
};

// перехват require("electron")
const origResolve = Module._resolveFilename;
const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === "electron") return fakeElectron;
  return origLoad.apply(this, arguments);
};

(async () => {
  // чистим старый лог
  try { fs.unlinkSync(LOG_PATH); } catch {}
  // подгружаем main.js (он сам вызовет app.whenReady().then(...))
  require(path.join(DESKTOP_DIR, "main.js"));
  // даём микротаскам отработать
  await new Promise((r) => setTimeout(r, 300));
  const exists = fs.existsSync(LOG_PATH);
  const content = exists ? fs.readFileSync(LOG_PATH, "utf-8") : "";
  console.log("LOG_EXISTS:", exists);
  console.log("LOG_HAS_READY:", content.includes("app ready"));
  console.log("LOG_SNIPPET:", content.split("\n").slice(0, 5).join(" | "));
  if (!exists || !content.includes("app ready")) {
    console.error("SMOKE FAIL"); process.exit(1);
  }
  console.log("SMOKE_OK");
  process.exit(0);
})();
