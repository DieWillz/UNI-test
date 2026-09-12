(() => {
  'use strict';

  const state = { snapshot: null, baseline: new Map(), loaded: false, busy: false, loading: false };
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function notify(message, kind = '') {
    const el = $('#configSettingsStatus');
    if (el) {
      el.textContent = message;
      el.className = `settings-notice ${kind}`.trim();
    }
    if (typeof window.toast === 'function' && kind === 'error') window.toast(message);
  }

  async function jsonFetch(url, options) {
    const response = await fetch(url, {signal: AbortSignal.timeout(15000), ...options});
    let body;
    try { body = await response.json(); } catch (_) {
      throw new Error(`Сервер вернул не JSON (HTTP ${response.status}). Перезагрузите страницу или проверьте журнал сервера.`);
    }
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  }

  function encodeBaseline(value) { return JSON.stringify(value); }

  function fieldValue(field, input) {
    if (field.kind === 'boolean') return !!input.checked;
    if (field.kind === 'number') return input.value === '' ? null : Number(input.value);
    if (field.kind === 'list') return input.value.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
    return input.value;
  }

  function inputHtml(field) {
    const id = `cfg_${field.path.replace(/[^a-z0-9]+/gi, '_')}`;
    const attrs = [
      `id="${id}"`, `data-config-path="${esc(field.path)}"`,
      field.readonly ? 'disabled' : '',
      field.min !== undefined ? `min="${field.min}"` : '',
      field.max !== undefined ? `max="${field.max}"` : '',
      field.step !== undefined ? `step="${field.step}"` : '',
    ].filter(Boolean).join(' ');
    if (field.kind === 'boolean') return `<input type="checkbox" ${attrs} ${field.value ? 'checked' : ''}>`;
    if (field.kind === 'select') {
      const options = [...(field.options || [])];
      const current = field.value ?? '';
      if (!options.includes(current)) options.unshift(current);
      return `<select ${attrs}>${options.map(v => `<option value="${esc(v)}" ${v === current ? 'selected' : ''}>${esc(v || 'Не задано')}</option>`).join('')}</select>`;
    }
    if (field.kind === 'list') return `<textarea rows="3" ${attrs}>${esc((field.value || []).join('\n'))}</textarea>`;
    const type = field.kind === 'password' ? 'password' : field.kind === 'number' ? 'number' : 'text';
    const value = field.secret ? '' : field.value ?? '';
    const placeholder = field.secret && field.secret_set ? 'Задано — введите новое значение для замены' : '';
    return `<input type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${attrs}>`;
  }

  function renderField(field) {
    const badges = [
      field.restart_required ? '<span class="config-badge restart">перезапуск</span>' : '<span class="config-badge live">сразу</span>',
      field.secret ? '<span class="config-badge secret">секрет</span>' : '',
      field.readonly ? '<span class="config-badge protected">защищено</span>' : '',
    ].join('');
    return `<label class="config-field" data-config-search="${esc(`${field.label} ${field.description || ''} ${field.path}`.toLowerCase())}">
      <span class="config-field-title"><b>${esc(field.label)}</b>${badges}</span>
      ${inputHtml(field)}
      <small class="config-field-description">${esc(field.description || 'Описание пока не задано.')}</small>
      <code class="config-field-path">${esc(field.path)}</code>
    </label>`;
  }

  function renderSnapshot(snapshot) {
    if (!snapshot || !Array.isArray(snapshot.groups) || snapshot.groups.some(group => !Array.isArray(group.fields))) {
      throw new Error('Сервер не вернул ожидаемый список настроек. Данные формы не изменены.');
    }
    // The legacy response sanitizer stringifies secret metadata (False/True).
    // The string "False" must not hide values or submit untouched fields.
    for (const group of snapshot.groups || []) for (const field of group.fields || []) {
      for (const key of ['secret', 'secret_set']) {
        field[key] = field[key] === true || String(field[key]).toLowerCase() === 'true';
      }
    }
    state.snapshot = snapshot;
    const category = $('#configCategory');
    if (category) {
      const selected = category.value;
      category.innerHTML = '<option value="">Все категории</option>' + (snapshot.groups || []).map(group => `<option value="${esc(group.title.toLowerCase())}">${esc(group.title)}</option>`).join('');
      if ([...category.options].some(option => option.value === selected)) category.value = selected;
    }
    state.baseline.clear();
    const grid = $('#configSettingsGrid');
    if (!grid) return;
    grid.innerHTML = (snapshot.groups || []).map(group => {
      const fields = (group.fields || []).map(field => {
        state.baseline.set(field.path, encodeBaseline(field.value));
        return renderField(field);
      }).join('');
      return `<details class="config-group card" data-config-group="${esc(group.title.toLowerCase())}" open>
        <summary class="config-group-head"><h3>${esc(group.title)}</h3><span class="config-group-count">${group.fields.length} параметров</span><span class="config-group-toggle">свернуть</span></summary>
        <div class="config-group-fields">${fields}</div>
      </details>`;
    }).join('');
    // Optional null fields render as empty controls. Compare against that same
    // representation, so simply opening this page never creates edits.
    grid.querySelectorAll('[data-config-path]').forEach(input => {
      const field = descriptor(input.dataset.configPath);
      if (field) state.baseline.set(field.path, encodeBaseline(fieldValue(field, input)));
    });
    grid.querySelectorAll('.config-group').forEach(group => {
      group.addEventListener('toggle', () => {
        const hint = group.querySelector('.config-group-toggle');
        if (hint) hint.textContent = group.open ? 'свернуть' : 'развернуть';
      });
    });
    state.loaded = true;
    applyFilter();
    updateDirtyState();
  }

  function applyFilter() {
    const query = ($('#configSettingsSearch')?.value || '').trim().toLowerCase();
    const category = $('#configCategory')?.value || '';
    let matched = 0;
    document.querySelectorAll('.config-group').forEach(group => {
      let visible = 0;
      group.querySelectorAll('.config-field').forEach(field => {
        const match = (!category || category === group.dataset.configGroup) && (!query || (field.dataset.configSearch || '').includes(query) || (group.dataset.configGroup || '').includes(query));
        field.hidden = !match;
        if (match) visible += 1;
      });
      group.hidden = visible === 0;
      if (visible && (query || category)) group.open = true;
      matched += visible;
      const count = group.querySelector('.config-group-count');
      if (count) count.textContent = visible + ' из ' + group.querySelectorAll('.config-field').length;
    });
    if ($('#configFilterCount')) $('#configFilterCount').textContent = state.loaded ? `Показано параметров: ${matched}` : '';
    const quick = document.querySelector('.settings-quick');
    if (quick) quick.hidden = !!(query || category);
    const empty = $('#configSettingsEmpty');
    if (empty) empty.hidden = !state.loaded || !!document.querySelector('.config-group:not([hidden])');
  }

  function updateDirtyState() {
    const count = Object.keys(collectUpdates()).length;
    const button = $('#configSaveBtn');
    if (button) {
      button.disabled = state.busy || !state.loaded || count === 0;
      button.textContent = state.busy ? 'Сохраняем…' : count ? `Сохранить и применить (${count})` : 'Нет изменений';
    }
    if ($('#configResetBtn')) $('#configResetBtn').disabled = state.busy || !count;
    const applyBar = $('#configApplyBar');
    if (applyBar) applyBar.hidden = !state.loaded || count === 0;
    const summary = $('#configDirtySummary');
    if (summary) summary.textContent = count ? `Есть несохранённые изменения: ${count}` : 'Изменений нет';
  }

  function resetConfigSettings() {
    if (!state.loaded || state.busy) return;
    if (!window.confirm('Отменить несохранённые правки? Файл настроек не изменится.')) return;
    renderSnapshot(state.snapshot);
    notify('Несохранённые правки отменены. Файл не изменён.', 'ok');
  }

  function descriptor(path) {
    for (const group of state.snapshot?.groups || []) {
      const found = (group.fields || []).find(field => field.path === path);
      if (found) return found;
    }
    return null;
  }

  function collectUpdates() {
    const updates = {};
    document.querySelectorAll('[data-config-path]').forEach(input => {
      const path = input.dataset.configPath;
      const field = descriptor(path);
      if (!field || field.readonly) return;
      const value = fieldValue(field, input);
      if (field.secret) {
        if (String(value || '').trim()) updates[path] = value;
        return;
      }
      if (encodeBaseline(value) !== state.baseline.get(path)) updates[path] = value;
    });
    return updates;
  }

  async function loadConfigSettings(force = false) {
    if (state.busy || state.loading) return;
    if (state.loaded && force && Object.keys(collectUpdates()).length) {
      notify('Есть несохранённые изменения. Сначала сохраните их или перезагрузите страницу, чтобы отменить.', 'warn');
      return;
    }
    if (state.loaded && !force) return;
    state.loading = true;
    notify('Читаю актуальный config.yaml…');
    try {
      const snapshot = await jsonFetch('/api/admin/config');
      renderSnapshot(snapshot);
      notify(`Загружено ${(snapshot.groups || []).reduce((n, g) => n + (g.fields || []).length, 0)} настроек.`, 'ok');
    } catch (error) {
      notify(`Не удалось загрузить настройки: ${error.message}`, 'error');
      if (!state.loaded && $('#configSettingsGrid')) $('#configSettingsGrid').textContent = 'Настройки недоступны. Попробуйте «Перечитать», когда сервер снова будет доступен.';
    } finally {
      state.loading = false;
    }
    updateDirtyState();
  }

  async function saveConfigSettings() {
    if (state.busy) return;
    if (!state.loaded) await loadConfigSettings(true);
    if (!state.loaded) return;
    const updates = collectUpdates();
    if (!Object.keys(updates).length) {
      notify('Изменений для сохранения нет.', 'ok');
      return;
    }
    state.busy = true;
    updateDirtyState();
    const inputs = [...document.querySelectorAll('[data-config-path]:not(:disabled)')];
    inputs.forEach(input => { input.disabled = true; });
    notify(`Проверяю и сохраняю ${Object.keys(updates).length} изменений…`);
    try {
      const result = await jsonFetch('/api/admin/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({updates}),
      });
      if (result.config) renderSnapshot(result.config);
      const restart = result.restart_required || [];
      const changed = result.changed || [];
      const message = restart.length
        ? `Сохранено: ${changed.length}. Для применения нужен перезапуск: ${restart.join(', ')}.`
        : `Сохранено: ${changed.length}. Применено без перезапуска.`;
      notify(message, restart.length ? 'warn' : 'ok');
      if (typeof window.toast === 'function') window.toast(message);
    } catch (error) {
      notify(`Настройки не сохранены: ${error.message}`, 'error');
    } finally {
      state.busy = false;
      inputs.forEach(input => { input.disabled = false; });
      updateDirtyState();
    }
  }

  async function restartConfiguredLlm() {
    notify('Запрашиваю перезапуск локального LLM…');
    try {
      const result = await jsonFetch('/api/admin/restart-llm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
      notify(result.message || 'Перезапуск LLM запрошен.', 'warn');
    } catch (error) {
      notify(`LLM не перезапущен: ${error.message}`, 'error');
    }
  }

  $('#configSettingsSearch')?.addEventListener('input', applyFilter);
  $('#configCategory')?.addEventListener('change', applyFilter);
  $('#configSettingsGrid')?.addEventListener('input', updateDirtyState);
  window.loadConfigSettings = loadConfigSettings;
  window.resetConfigSettings = resetConfigSettings;
  window.saveConfigSettings = saveConfigSettings;
  window.restartConfiguredLlm = restartConfiguredLlm;
  window.addEventListener('beforeunload', event => {
    if (state.busy || Object.keys(collectUpdates()).length) { event.preventDefault(); event.returnValue = ''; }
  });

  document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('[data-page="settings"].act')) loadConfigSettings();
  });
})();
