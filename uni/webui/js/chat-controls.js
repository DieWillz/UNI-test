/* Chat boundary: roles, explicit media input, passive telemetry and TTS. */
(() => {
  'use strict';
  const el = id => document.getElementById(id), base = location.origin;
  let busy = false, roleEpoch = 0, cameraOn = false, cameraBusy = false, cameraTimer, lastFrame = '', audio;
  let dialogListening = false, micListening = false, micEpoch = 0, lastDorchStatus = null;
  const sessionMessages = new Set();
  function onEvent(event) {
    if (event.type !== 'assistant_message' || event.source !== 'dorch' || !event.text) return;
    const key = JSON.stringify([event.ts, event.text]);
    if (sessionMessages.has(key)) return;
    sessionMessages.add(key);
    if (sessionMessages.size > 200) sessionMessages.delete(sessionMessages.values().next().value);
    addMsg('uni', event.text); // Session already speaks this line. Do not call TTS twice.
  }
  async function request(path, body, timeout = 15000) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(base + path, {signal: controller.signal,
        ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})});
      const raw = await response.text();
      let data;
      try { data = JSON.parse(raw); }
      catch (_) { throw new Error(`Сервер вернул не JSON (HTTP ${response.status}). Повторите запрос после переподключения.`); }
      if (!response.ok || data.error) throw new Error(data.error || data.text || `HTTP ${response.status}`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Истекло время ожидания ответа');
      throw error;
    } finally { clearTimeout(timer); }
  }
  async function loadRoles() {
    const epoch = ++roleEpoch, data = await request('/api/roles');
    if (epoch !== roleEpoch) return data;
    if (!Array.isArray(data.roles) || !data.current) throw new Error('Сервер не сообщил текущую роль');
    for (const id of ['roleSel', 'setRole']) {
      const select = el(id); if (!select) continue;
      select.replaceChildren(...data.roles.map(role => new Option(role.name || role.id || role, role.id || role)));
      select.value = data.current;
    }
    el('roleNow').textContent = data.current;
    return data;
  }
  window.applyRole = async (name = el('roleSel').value) => {
    const button = el('roleApply'); if (button.disabled) return;
    button.disabled = true;
    try {
      await request('/api/role/switch', {role: name});
      const data = await loadRoles();
      if (data.current !== name) throw new Error('Сервер не подтвердил выбранную роль');
      toast('Роль применена: ' + data.current);
    } catch (error) { toast('Роль не изменена: ' + error.message); }
    finally { button.disabled = false; }
  };
  async function telemetry() {
    if (document.hidden) return;
    if (!document.querySelector('.page[data-page="chat"].act, .page[data-page="dorch"].act, #drawer.open')) return;
    el('dorchBadge').style.display = '';
    try {
      // /xtoys/session/status lazily starts the agent. Merely viewing the UI
      // must not start models, autonomy or device connections.
      const readiness = await request('/api/safety', undefined, 4000);
      if (readiness.agent_ready !== true) {
        lastDorchStatus = null;
        el('dorchVal').textContent = 'Агент не запущен';
        el('chatDeviceStatus').textContent = 'Фоновый запуск отключён. Состояние устройства не проверено.';
        const autoBtn = el('dorchAutoBtn');
        if (autoBtn) { autoBtn.textContent = 'Авто Dorch: нет данных'; autoBtn.classList.remove('active'); }
        renderQueue({});
        return;
      }
      const data = await request('/api/xtoys/session/status', undefined, 4000), value = data.current_intensity;
      lastDorchStatus = data;
      const autoBtn = el('dorchAutoBtn');
      if (autoBtn) {
        autoBtn.textContent = data.autonomous_running ? '\u0410\u0432\u0442\u043e Dorch: \u0412\u041a\u041b' : '\u0410\u0432\u0442\u043e Dorch: \u0412\u042b\u041a\u041b';
        autoBtn.classList.toggle('active', !!data.autonomous_running);
      }
      el('dorchVal').textContent = data.emergency_stop ? 'STOP' : !data.intiface_connected ? 'Intiface не подключён' :
        !data.device_connected ? 'Intiface ✓ · устройство не найдено' :
        `${value == null ? 'нет данных' : value + '%'} · фаза ${data.phase || '—'}`;
      el('chatDeviceStatus').textContent = [data.emergency_stop ? 'Аварийный СТОП.' : '', data.status,
        'Проценты — последняя команда Intiface. Физическое движение не подтверждено.', data.last_error ? 'Причина: ' + data.last_error : '',
        'Обновлено: ' + new Date().toLocaleTimeString()].filter(Boolean).join(' ');
      renderQueue(data);
    } catch (error) {
      lastDorchStatus = null;
      renderQueue({});
      el('dorchVal').textContent = 'нет данных';
      el('chatDeviceStatus').textContent = 'Статус недоступен: ' + error.message + '. Предыдущие значения устарели.';
    }
  }
  window.resetDorchStop = async () => {
    if (!window.confirm('Снять аварийный STOP? Новую сессию затем запускайте явно.')) return;
    try { await request('/api/xtoys/emergency-reset', {}); toast('STOP снят. Устройство не запущено.'); }
    catch (error) { toast(error.message); }
    finally { void telemetry(); }
  };
  window.toggleDorchAuto = async () => {
    const running = !!lastDorchStatus?.autonomous_running;
    const button = el('dorchAutoBtn'); if (button) button.disabled = true;
    try {
      if (running) {
        await request('/api/xtoys/autonomous/stop', {}, 15000);
        toast('\u0410\u0432\u0442\u043e\u043d\u043e\u043c\u043d\u044b\u0439 Dorch \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d. STOP \u043d\u0435 \u0437\u0430\u0449\u0451\u043b\u043a\u043d\u0443\u0442.');
      } else {
        await request('/api/xtoys/session/start', {}, 15000);
        toast('\u0410\u0432\u0442\u043e\u043d\u043e\u043c\u043d\u044b\u0439 Dorch \u0432\u043a\u043b\u044e\u0447\u0451\u043d. \u042e\u043d\u0438 \u043f\u043b\u0430\u043d\u0438\u0440\u0443\u0435\u0442 \u0448\u0430\u0433\u0438 \u0441\u0430\u043c\u0430.');
      }
    } catch (error) { toast('Dorch: ' + error.message); }
    finally { if (button) button.disabled = false; void telemetry(); }
  };

  async function playSpeech(text, url) {
    try {
      let settings = {}; try { settings = JSON.parse(localStorage.getItem('uni_tts') || '{}'); } catch (_) { /* defaults */ }
      const data = url ? {audio_url: url} : await request('/api/tts', {...settings, text}, 90000);
      if (data.browser) {
        if (!window.speechSynthesis) throw new Error('\u0413\u043e\u043b\u043e\u0441 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d');
        await new Promise(resolve => {
          const utterance = new SpeechSynthesisUtterance(text); utterance.lang = 'ru-RU';
          utterance.onend = resolve;
          utterance.onerror = () => { addMsg('sys', '\u041e\u0437\u0432\u0443\u0447\u043a\u0430: \u0431\u0440\u0430\u0443\u0437\u0435\u0440 \u043d\u0435 \u0441\u043c\u043e\u0433 \u0432\u043e\u0441\u043f\u0440\u043e\u0438\u0437\u0432\u0435\u0441\u0442\u0438 \u0440\u0435\u0447\u044c'); resolve(); };
          speechSynthesis.cancel(); speechSynthesis.speak(utterance);
        });
      } else {
        if (!data.audio_url) throw new Error('\u0421\u0435\u0440\u0432\u0435\u0440 \u043d\u0435 \u0432\u0435\u0440\u043d\u0443\u043b \u0430\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b');
        const target = new URL(data.audio_url, base);
        if (target.origin !== base) throw new Error('\u0410\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u043d\u0430 \u0441\u0435\u0440\u0432\u0435\u0440\u0435 \u042e\u043d\u0438');
        if (audio) audio.pause(); audio = new Audio(target.href);
        await new Promise(async resolve => {
          audio.onended = resolve;
          audio.onerror = () => { addMsg('sys', '\u041e\u0437\u0432\u0443\u0447\u043a\u0430: \u0430\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b \u043d\u0435 \u0432\u043e\u0441\u043f\u0440\u043e\u0438\u0437\u0432\u043e\u0434\u0438\u0442\u0441\u044f'); resolve(); };
          try { await audio.play(); } catch (_) { resolve(); }
        });
      }
    } catch (error) { addMsg('sys', '\u041e\u0437\u0432\u0443\u0447\u043a\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430: ' + error.message); }
  }
  async function send(text, image) {
    text = String(text || '').trim(); if (!text && !image) return false;
    // A stop must bypass a chat request waiting for the model/TTS.
    if (!image && /(^|\s)(стоп|красный|остановись)(?=\s|[.!?,]|$)|останови\s+(сессию|дорч)/i.test(text)) {
      addMsg('user', text);
      try {
        await request('/api/xtoys/emergency-stop', {}, 10000);
        addMsg('sys', 'STOP отправлен через Intiface. Проверьте физическую остановку.');
      } catch (error) { addMsg('sys', 'STOP не подтверждён: ' + error.message + '. Используйте физический пульт!'); }
      finally { void telemetry(); }
      return true;
    }
    if (busy) { toast('Дождитесь ответа Юни'); return false; }
    let receivedReply = false;
    busy = true; el('chatSend').disabled = true;
    if (el('dwSendBtn')) el('dwSendBtn').disabled = true;
    el('chatRequestState').textContent = image ? 'Анализирую изображение…' : 'Юни отвечает…';
    if (el('dwRequestState')) el('dwRequestState').textContent = el('chatRequestState').textContent;
    const voice = el('speakChk').checked; text ||= 'Что на изображении?'; addMsg('user', text, image);
    try {
      // Browser owns playback; the task-local server gate prevents duplicate speech.
      const data = await request('/api/chat', {text, image, use_voice: false}, 100000);
      const reply = data.text || data.reply || data.response;
      if (!reply) throw new Error('Сервер не вернул текст ответа');
      addMsg('uni', reply);
      receivedReply = true;
      // Ordinary dialogue/image descriptions are not executed real-world tasks.
      // Keep the fail-closed label with actual actions, not as a repeated chat message.
      if (data.outcome?.actions?.length && data.status !== 'verified' && !data.transport_acknowledged) addMsg('sys', 'Действие: результат пока не подтверждён независимой проверкой.');
      if (voice && el('speakChk').checked) { const spoken = playSpeech(reply, data.audio_url); if (dialogListening) await spoken; else void spoken; }
    } catch (error) { addMsg('sys', 'Запрос не подтверждён: ' + error.message); }
    finally {
      busy = false; el('chatSend').disabled = false;
      if (el('dwSendBtn')) el('dwSendBtn').disabled = false;
      const message = receivedReply ? '' : 'Ответ не получен. Текст сохранён в поле ввода.';
      el('chatRequestState').textContent = message;
      if (el('dwRequestState')) el('dwRequestState').textContent = message;
      void telemetry();
    }
    return receivedReply;
  }
  window.pickImage = () => el('imgInput').click();
  window.sendImageFile = async input => {
    const file = input.files?.[0]; if (!file) return;
    try {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 1048576) throw new Error('Выберите JPEG/PNG/WebP до 1 МБ');
      const image = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('Файл не читается')); reader.readAsDataURL(file);
      });
      const text = el('chatIn').value;
      if (await send(text, image) && el('chatIn').value === text) el('chatIn').value = '';
    } catch (error) { toast(error.message); } finally { input.value = ''; }
  };
  function setMicState(active, text = '') {
    for (const id of ['micBtn', 'dwMic']) {
      const button = el(id); if (!button) continue;
      button.classList.toggle('rec', active); button.classList.toggle('active', active);
      button.title = text || '\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0439 Whisper';
    }
    const state = el('chatRequestState');
    if (state && active) state.textContent = text;
    else if (state && !busy) state.textContent = '';
  }
  async function listenLocalOnce(epoch) {
    micListening = true; setMicState(true, '\u0421\u043b\u0443\u0448\u0430\u044e\u2026');
    try {
      const data = await request('/api/stt/listen', {wait_seconds: 8}, 45000);
      if (epoch !== micEpoch) return '';
      return String(data.text || '').trim();
    } catch (error) {
      if (epoch === micEpoch) toast('STT: ' + error.message);
      return '';
    } finally {
      micListening = false;
      if (!dialogListening || epoch !== micEpoch) setMicState(false);
    }
  }
  async function handleMicText(text, mode) {
    if (!text) return;
    if (mode === 'input') {
      if (el('chatIn')) el('chatIn').value = text;
      if (el('dwIn')) el('dwIn').value = text;
      setMicState(false, '\u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e');
      return;
    }
    await send(text);
  }
  async function dialogLoop(epoch) {
    while (dialogListening && epoch === micEpoch) {
      const text = await listenLocalOnce(epoch);
      if (!dialogListening || epoch !== micEpoch) break;
      if (text) await handleMicText(text, 'chat');
    }
    if (epoch === micEpoch) { dialogListening = false; setMicState(false); }
  }
  async function toggleMicrophone() {
    if (dialogListening || micListening) {
      dialogListening = false; micEpoch += 1; setMicState(false);
      return;
    }
    const mode = el('micMode')?.value || 'input';
    const epoch = ++micEpoch;
    if (mode === 'dialog') {
      dialogListening = true; setMicState(true, '\u0414\u0438\u0430\u043b\u043e\u0433: \u0441\u043b\u0443\u0448\u0430\u044e\u2026');
      void dialogLoop(epoch); return;
    }
    const text = await listenLocalOnce(epoch);
    if (epoch === micEpoch) await handleMicText(text, mode);
  }

  async function frame() {
    if (!cameraOn) return;
    try {
      const data = await request('/api/camera/frame', {}); if (!cameraOn) return;
      if (!/^data:image\/(jpeg|png|webp);base64,/.test(data.image_b64 || '')) throw new Error('Кадр не получен');
      lastFrame = data.image_b64; el('chatCameraPreview').src = lastFrame; el('chatCameraSend').disabled = false;
      el('cameraBadge').textContent = 'Камера: включена';
      el('chatCameraState').textContent = 'Камера включена. Модель получит кадр только по кнопке «Отправить кадр».';
    } catch (error) {
      lastFrame = ''; el('chatCameraPreview').removeAttribute('src'); el('chatCameraSend').disabled = true;
      el('chatCameraState').textContent = 'Кадр недоступен: ' + error.message;
      el('cameraBadge').textContent = 'Камера: кадр недоступен';
    } finally { if (cameraOn) cameraTimer = setTimeout(frame, 1500); }
  }
  window.toggleCam = async () => {
    if (cameraBusy) return; cameraBusy = true; el('camBtn').disabled = true;
    el('cameraBadge').textContent = cameraOn ? 'Камера: выключение…' : 'Камера: запуск…';
    try {
      if (cameraOn) {
        await request('/api/camera/stop', {}); cameraOn = false; clearTimeout(cameraTimer); lastFrame = '';
        el('chatCameraPanel').hidden = true; el('chatCameraPreview').removeAttribute('src'); el('camBtn').textContent = '📷 Камера';
        el('chatCameraSend').disabled = true; el('cameraBadge').textContent = 'Камера: выключена';
      } else {
        await request('/api/camera/start', {notice_ack: true}, 30000); cameraOn = true;
        el('chatCameraPanel').hidden = false; el('camBtn').textContent = '📷 Выключить камеру'; void frame();
        el('cameraBadge').textContent = 'Камера: ожидание кадра';
      }
    } catch (error) { el('cameraBadge').textContent = 'Камера: ошибка переключения'; toast('Камера: ' + error.message); }
    finally { cameraBusy = false; el('camBtn').disabled = false; }
  };
  window.sendCameraFrame = async () => {
    if (!lastFrame || !cameraOn) { toast('Свежий кадр недоступен'); return; }
    const text = el('chatIn').value;
    if (await send(text, lastFrame) && el('chatIn').value === text) el('chatIn').value = '';
  };
  // 🤖 Единый виджет очереди: показывает серверное состояние (один источник).
  function renderQueue(data) {
    const box = el('dorchQueue');
    if (!box) return;
    const active = data && !data.emergency_stop && data.mode && data.mode !== 'stopped';
    box.style.display = active ? '' : 'none';
    if (!active) return;
    const cur = data.current_step;
    el('dorchQueueNow').innerHTML = '<b>Сейчас:</b> ' + (cur
      ? `${cur.pattern_id || cur.kind || 'hold'} · ${cur.intensity_percent}% · осталось ${Math.round(cur.remaining_seconds)} с${cur.speech ? ' · «' + cur.speech + '»' : ''}`
      : '—');
    const nxt = (data.pending_steps || []).slice(0, 3);
    el('dorchQueueNext').innerHTML = '<b>Далее:</b> ' + (nxt.length
      ? nxt.map(s => `${s.pattern_id || s.kind || 'hold'} ${s.intensity_percent}% (${Math.round(s.duration_seconds)} с)${s.speech ? ' · «' + s.speech + '»' : ''}`).join(' → ')
      : '—');
    el('dorchQueueTotal').innerHTML = '<b>Всего:</b> ' + (data.total_remaining_seconds != null ? Math.round(data.total_remaining_seconds) + ' с' : '—');
  }
  window.dqClearPending = async () => {
    try { await request('/api/xtoys/queue/clear', {}, 8000); toast('Будущие шаги очищены'); }
    catch (e) { toast('Очистка: ' + e.message); }
  };
  window.dqStop = async () => {
    try { await request('/api/xtoys/emergency-stop', {}, 10000); toast('STOP отправлен'); }
    catch (e) { toast('STOP: ' + e.message); }
  };
  window.ChatControls = {loadRoles, send, playSpeech, onEvent, toggleMicrophone};
  document.addEventListener('DOMContentLoaded', () => {
    el('micBtn')?.addEventListener('click', toggleMicrophone);
    el('dwMic')?.addEventListener('click', toggleMicrophone);
    el('speakChk').addEventListener('change', () => { if (!el('speakChk').checked) { if (audio) audio.pause(); window.speechSynthesis?.cancel(); } });
    const poll = async () => { await telemetry(); setTimeout(poll, 2000); }; void poll();
  });
  window.addEventListener('pagehide', () => { if (cameraOn) navigator.sendBeacon(base + '/api/camera/stop', '{}'); });
})();
