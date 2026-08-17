// GPU profile detection for llama-server (P-15, 2026-08-17).
//
// Запуск:
//   node scripts/gpu_detect.js
//
// Выводит JSON-объект:
//   { "profile": "cpu" | "cuda" | "rocm",
//     "args": ["--n-gpu-layers", "99"],
//     "honest_fallback": true | false,
//     "reason": "...",
//     "devices": [...] }
//
// Используется launcher.js при запуске llama-server. Честный fallback:
// если GPU запрошен, но недоступен — НЕ silent degradation, а явный
// reason + honest_fallback:true (caller логирует это).

'use strict';
const { execSync } = require('child_process');

function safe(cmd, timeoutMs = 3000) {
  try {
    return execSync(cmd, {
      stdio: ['ignore', 'pipe', 'ignore'],
      windowsHide: true,
      encoding: 'utf8',
      timeout: timeoutMs,
    });
  } catch (e) {
    return null;
  }
}

function detectNvidia() {
  const out = safe('nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader');
  if (!out) return null;
  const devices = out.trim().split(/\r?\n/).filter(Boolean).map(line => {
    const parts = line.split(',').map(s => s.trim());
    return { idx: parts[0], name: parts[1], memory_mb: parts[2] || null };
  });
  return devices.length ? devices : null;
}

function detectRocm() {
  const out = safe('rocm-smi --showproductname');
  if (!out || !/GPU\[\d+\]/.test(out)) return null;
  const lines = out.split(/\r?\n/).filter(l => /GPU\[\d+\]/.test(l));
  return lines.map(l => l.trim());
}

function detectFromEnv() {
  const force = (process.env.UNI_GPU_PROFILE || '').toLowerCase();
  if (force === 'cpu') return { profile: 'cpu', forced: true };
  if (force === 'cuda') return { profile: 'cuda', forced: true };
  if (force === 'rocm') return { profile: 'rocm', forced: true };
  return null;
}

function main() {
  const forced = detectFromEnv();
  if (forced) {
    const args = forced.profile === 'cpu'
      ? ['--n-gpu-layers', '0']
      : ['--n-gpu-layers', '99'];
    console.log(JSON.stringify({
      profile: forced.profile, args,
      honest_fallback: false, reason: `forced by UNI_GPU_PROFILE=${forced.profile}`,
      devices: [],
    }));
    return;
  }

  const nvidia = detectNvidia();
  if (nvidia) {
    console.log(JSON.stringify({
      profile: 'cuda',
      args: ['--n-gpu-layers', '99'],
      honest_fallback: false,
      reason: 'nvidia-smi detected',
      devices: nvidia,
    }));
    return;
  }

  const rocm = detectRocm();
  if (rocm) {
    console.log(JSON.stringify({
      profile: 'rocm',
      args: ['--n-gpu-layers', '99'],
      honest_fallback: false,
      reason: 'rocm-smi detected',
      devices: rocm,
    }));
    return;
  }

  // No GPU — honest CPU fallback
  console.log(JSON.stringify({
    profile: 'cpu',
    args: ['--n-gpu-layers', '0'],
    honest_fallback: true,
    reason: 'no GPU detected (nvidia-smi and rocm-smi absent); using CPU',
    devices: [],
  }));
}

main();
