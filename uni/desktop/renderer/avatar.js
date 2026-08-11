// UNI Desktop Companion — avatar.js (Hermes SOLO, 2026-08-11, блок D)
// D-08: state machine аватара (idle / говорит / слушает / думает).
// P3 (D-16..D-18): расширяется на VRM + lip-sync — интерфейс setState сохранён.
(function () {
  const STATES = ["idle", "speaking", "listening", "thinking"];
  let current = "idle";
  let el = null, img = null;

  function init() {
    el = document.getElementById("avatar");
    img = document.getElementById("avatarImg");
    setState("idle");
  }

  // Смена состояния: добавляет класс на контейнер + меняет src (если есть ассет)
  function setState(state) {
    if (!STATES.includes(state)) state = "idle";
    if (el) {
      STATES.forEach((s) => el.classList.remove(s));
      el.classList.add(state);
    }
    if (img) {
      // PNG-заглушки: avatar_idle.svg уже есть; остальные — тот же файл (создатель заменит)
      const map = {
        idle: "../assets/avatar_idle.svg",
        speaking: "../assets/avatar_speak.svg",
        listening: "../assets/avatar_listen.svg",
        thinking: "../assets/avatar_think.svg",
      };
      img.src = map[state] || map.idle;
    }
    current = state;
  }

  function getState() { return current; }

  // D-17 (P3): hook для lip-sync — примет AnalyserNode амплитуду (заготовка)
  function setMouthOpen(amount01) {
    if (img) img.style.setProperty("--mouth", String(amount01));
  }

  window.Avatar = { init, setState, getState, setMouthOpen };
  document.addEventListener("DOMContentLoaded", init);
})();
