// UNI Desktop Companion — avatar.js (Hermes, финальная директива 2026-08-12 F-05 D-16/17/18)
// D-16: three-vrm аватар из ../assets/UNI.vrm; SVG — fallback при сбое загрузки.
// D-17: lip-sync от громкости TTS (AnalyserNode -> рот).
// D-18: лимит 30 fps, low-power, настройка «качество аватара».
(function () {
  const STATES = ["idle", "speaking", "listening", "thinking"];
  let current = "idle";
  let el = null, img = null, canvas = null;

  // VRM runtime state
  let vrmMode = false;
  let three = null, vrm = null, renderer = null, scene = null, camera = null;
  let clock = null, mixer = null, analyser = null, audioCtx = null;
  let rafId = null;
  let quality = "high"; // high | low (D-18)
  let fpsLimit = 30;
  let lastFrame = 0;

  const SVG_MAP = {
    idle: "../assets/avatar_idle.svg",
    speaking: "../assets/avatar_speak.svg",
    listening: "../assets/avatar_listen.svg",
    thinking: "../assets/avatar_think.svg",
  };

  function log(...a) { if (window.uni && window.uni.log) window.uni.log("[avatar]", ...a); }

  function init() {
    el = document.getElementById("avatar");
    img = document.getElementById("avatarImg");
    canvas = document.getElementById("vrmCanvas");
    setState("idle");
    loadVRM();
  }

  // D-16: загрузка VRM. Импорты идут через importmap (см. index.html), т.к. Electron
  // renderer не имеет bundler'а и не резолвит bare-спецификаторы внутри зависимостей
  // (GLTFLoader / three-vrm сами делают `import 'three'`).
  async function loadVRM() {
    try {
      const vrmUrl = "../assets/UNI.vrm";
      const modThree = await import("three");
      const modVrm = await import("@pixiv/three-vrm");
      const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
      three = modThree;
      const loader = new GLTFLoader();
      loader.register((parser) => new modVrm.VRMLoaderPlugin(parser));
      loader.load(vrmUrl, (gltf) => {
        // @pixiv/three-vrm 2.x кладёт VRM либо в gltf.userData.vrm, либо в gltf.vrm
        vrm = gltf.userData.vrm || gltf.vrm;
        log("VRM gltf: vrm?", typeof vrm, "scene?", vrm && typeof vrm.scene,
            "three.Scene?", typeof three.Scene);
        if (!vrm || !vrm.scene) { fallback("no vrm.scene in gltf"); return; }
        try { modVrm.VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch (e) {}
        setupThree();
        if (!scene) { fallback("scene not created"); return; }
        scene.add(vrm.scene);
        vrmMode = true;
        img.classList.add("hidden");
        canvas.classList.remove("hidden");
        log("VRM loaded");
        animate();
      }, undefined, (err) => fallback("VRM load error: " + (err && err.message)));
    } catch (e) {
      fallback("three/@pixiv/three-vrm import error: " + (e && e.message));
    }
  }

  function setupThree() {
    const w = 180, h = 320;
    canvas.width = w; canvas.height = h;
    renderer = new three.WebGLRenderer({ canvas, alpha: true, antialias: quality === "high" });
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(quality === "high" ? 2 : 1);
    scene = new three.Scene();
    camera = new three.PerspectiveCamera(30, w / h, 0.1, 100);
    camera.position.set(0, 1.2, 3);
    clock = new three.Clock();
  }

  function fallback(reason) {
    vrmMode = false;
    if (canvas) canvas.classList.add("hidden");
    if (img) { img.classList.remove("hidden"); img.src = SVG_MAP[current] || SVG_MAP.idle; }
    log("SVG fallback:", reason);
  }

  // D-18: лимит 30 fps цикл
  function animate() {
    if (!vrmMode) return;
    rafId = requestAnimationFrame(animate);
    const now = performance.now();
    if (now - lastFrame < 1000 / fpsLimit) return;
    lastFrame = now;

    const delta = clock.getDelta();
    if (mixer) mixer.update(delta);
    // D-17: lip-sync — громкость из analyser -> открытие рта
    if (analyser && vrm.expressionManager) {
      const data = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += Math.abs(data[i] - 128);
      const amp = Math.min(1, sum / data.length / 40);
      try {
        vrm.expressionManager.setValue("aa", current === "speaking" ? amp : amp * 0.1);
      } catch (e) {}
    }
    renderer.render(scene, camera);
  }

  function setState(state) {
    if (!STATES.includes(state)) state = "idle";
    if (el) { STATES.forEach((s) => el.classList.remove(s)); el.classList.add(state); }
    if (!vrmMode && img) img.src = SVG_MAP[state] || SVG_MAP.idle;
    current = state;
  }

  function getState() { return current; }

  // D-17: подключить AnalyserNode к аудио-источнику (вызывается из app.js при TTS)
  function attachAudio(sourceNode) {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      sourceNode.connect(analyser);
      log("audio analyser attached");
    } catch (e) { log("attachAudio error: " + (e && e.message)); }
  }

  // D-18: настройка качества аватара
  function setQuality(q) {
    quality = q === "low" ? "low" : "high";
    fpsLimit = quality === "low" ? 15 : 30;
    if (renderer) { renderer.setPixelRatio(quality === "high" ? 2 : 1); }
    log("avatar quality ->", quality, "fps", fpsLimit);
  }

  window.Avatar = { init, setState, getState, attachAudio, setQuality, loadVRM, fallback };
  document.addEventListener("DOMContentLoaded", init);
})();
