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

  // 🤖 P2 (2026-08-13): 2D-состояния отрисованы ИЗ VRM offscreen -> ../assets/states/*.png
  // (цветные, а не «слишком простые» SVG). SVG оставлены как last-resort fallback.
  const STATES_DIR = "../assets/states/";
  const SVG_MAP = {
    idle: STATES_DIR + "idle.png",
    speaking: STATES_DIR + "speak.png",
    listening: STATES_DIR + "listen.png",
    thinking: STATES_DIR + "think.png",
    stop: STATES_DIR + "stop.png",
  };
  const SVG_FALLBACK = {
    idle: "../assets/avatar_idle.svg",
    speaking: "../assets/avatar_speak.svg",
    listening: "../assets/avatar_listen.svg",
    thinking: "../assets/avatar_think.svg",
    stop: "../assets/avatar_idle.svg",
  };

  function log(...a) { if (window.uni && window.uni.log) window.uni.log("[avatar]", ...a); }

  // 🤖 P2 (2026-08-13): режим аватара.
  //   "auto" -> пробуем 3D VRM, fallback 2D PNG-состояния (из VRM offscreen).
  //   "2d"   -> сразу 2D PNG-состояния (цветные, отрендерены из VRM). ДЕФОЛТ по Фазе-3 P2.2.
  //   "3d"   -> только 3D VRM.
  const AVATAR_MODE = "2d";

  function init() {
    el = document.getElementById("avatar");
    img = document.getElementById("avatarImg");
    canvas = document.getElementById("vrmCanvas");
    setState("idle");
    if (AVATAR_MODE === "2d") {
      // 2D: сразу показываем цветные PNG-состояния, VRM не грузим
      if (img) { img.classList.remove("hidden"); img.src = SVG_MAP.idle; }
      if (canvas) canvas.classList.add("hidden");
      log("avatar mode = 2d (PNG states)");
    } else {
      loadVRM(); // "3d" или "auto"
    }
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
    // 🤖 P2 (2026-08-13): корректная цветопередача + прозрачный фон окна
    renderer.outputColorSpace = three.SRGBColorSpace;
    renderer.toneMapping = three.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    scene = new three.Scene();
    // 🤖 P2: СВЕТ — без него MToon-материалы VRM рендерятся почти чёрным силуэтом.
    const ambient = new three.AmbientLight(0xffffff, 1.4);          // мягкая заливка
    const hemi = new three.HemisphereLight(0xffffff, 0x444466, 0.9); // небо/земля
    const key = new three.DirectionalLight(0xffffff, 2.2);          // ключевой спереди-сверху
    key.position.set(0.6, 2.2, 2.4);
    const fill = new three.DirectionalLight(0xffffff, 0.7);         // контр-свет
    fill.position.set(-1.2, 1.0, 1.5);
    scene.add(ambient, hemi, key, fill);
    // лёгкая среда для отражений MToon (без файла — процедурно)
    try {
      const pmrem = new three.PMREMGenerator(renderer);
      const envScene = new three.Scene();
      envScene.add(new three.AmbientLight(0xffffff, 1));
      const d = new three.DirectionalLight(0xffffff, 1); d.position.set(0, 1, 1);
      envScene.add(d);
      scene.environment = pmrem.fromScene(envScene, 0.04).texture;
    } catch (e) { log("env gen skipped:", e && e.message); }

    camera = new three.PerspectiveCamera(30, w / h, 0.1, 100);
    camera.position.set(0, 1.2, 3);
    camera.lookAt(0, 1.0, 0); // 🤖 P2: смотреть на торс/лицо аватара
    clock = new three.Clock();
  }

  function fallback(reason) {
    vrmMode = false;
    if (canvas) canvas.classList.add("hidden");
    if (img) {
      img.classList.remove("hidden");
      img.onerror = () => { img.onerror = null; img.src = SVG_FALLBACK[current] || SVG_FALLBACK.idle; };
      img.src = SVG_MAP[current] || SVG_MAP.idle;
    }
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
    if (!vrmMode && img) {
      img.onerror = () => { img.onerror = null; img.src = SVG_FALLBACK[state] || SVG_FALLBACK.idle; };
      img.src = SVG_MAP[state] || SVG_MAP.idle;
    }
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

  // 🤖 P2 (2026-08-13): отрисовать PNG-состояния ИЗ САМОЙ VRM offscreen.
  // Возвращает [{name, dataURL}] для сохранения в uni/desktop/assets/states/.
  async function captureStates() {
    if (!vrmMode || !vrm || !vrm.expressionManager) return [];
    const names = ["idle", "listening", "speaking", "thinking", "stop"];
    const exprFor = {
      idle: {}, listening: { "aa": 0.0, "blink": 0.0 }, speaking: { "aa": 0.6 },
      thinking: { "blink": 0.0, "gaze": 0.3 }, stop: { "aa": 0.0, "blink": 0.0 },
    };
    const out = [];
    for (const n of names) {
      try {
        const ex = exprFor[n] || {};
        for (const k of Object.keys(ex)) vrm.expressionManager.setValue(k, ex[k]);
        vrm.expressionManager.update();
        renderer.render(scene, camera);
        const url = canvas.toDataURL("image/png");
        out.push({ name: n, dataURL: url });
      } catch (e) { log("captureStates " + n + " error:", e && e.message); }
    }
    return out;
  }

  window.Avatar = { init, setState, getState, attachAudio, setQuality, loadVRM, fallback, captureStates };
  document.addEventListener("DOMContentLoaded", init);
})();
