// UNI Desktop Companion — preload.js (Hermes SOLO, 2026-08-11)
// Безопасный мост между renderer и main process (contextIsolation: true).
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("uni", {
  // hit-test для click-through: renderer сообщает, интерактивен ли пиксель
  hitTest: (interactive) => ipcRenderer.send("hit-test", interactive),
  // push-to-talk состояние
  onPTT: (cb) => ipcRenderer.on("ptt", (_e, on) => cb(on)),
  // события оверлея от main (SSE /api/desktop/events)
  onEvent: (cb) => ipcRenderer.on("desktop-event", (_e, data) => cb(data)),
  // скрыть в трей
  hide: () => ipcRenderer.send("hide"),
  show: () => ipcRenderer.send("show"),
  // обновить прозрачность окна
  setOpacity: (v) => ipcRenderer.send("set-opacity", v),
  // D-12: observe-тик — скриншот экрана (main делает capture)
  observeTick: () => ipcRenderer.invoke("observe-tick"),
  // сохранить состояние (позиция и т.п.)
  saveState: (obj) => ipcRenderer.invoke("save-state", obj),
  loadState: () => ipcRenderer.invoke("load-state"),
});
