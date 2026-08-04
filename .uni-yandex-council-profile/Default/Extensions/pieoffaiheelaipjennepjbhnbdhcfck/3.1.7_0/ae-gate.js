// [v2.6.5 audit r7] Gate-страница для DNR-based auto-enable.
// Браузер перенаправляется сюда через DNR-правило до DNS-резолва — только так работает
// в Yandex Browser и некоторых Chromium-форках, где tabs.onUpdated/onBeforeRequest
// приходят слишком поздно. URL цели приходит в location.hash.

(function () {
    'use strict';

    // Minimal i18n: RU vs EN based on browser UI language
    var isRu = (function () {
        try {
            var l = (chrome.i18n && chrome.i18n.getUILanguage) ? chrome.i18n.getUILanguage() : navigator.language || 'en';
            return String(l).toLowerCase().startsWith('ru');
        } catch { return false; }
    })();

    var STR = isRu ? {
        title: 'Подключаем VPN…',
        msg:   'Включаем защищённое соединение для этого сайта.',
        onTitle: 'VPN подключён',
        onMsg:   'Открываем сайт через VPN…',
        errTitle: 'Не удалось включить VPN',
        errNoTarget: 'Не удалось определить адрес сайта.',
        errNoExt: 'Нет связи с расширением. Перезагрузите Chrome.',
        errNotAllowed: 'Этот сайт не в списке автовключения.',
        errToggle: 'Не удалось включить VPN. Проверьте интернет и попробуйте снова.',
        // [v2.7.1 fix F98] Specific сообщение для storage quota — направляем юзера на Clear Cache.
        errStorage: 'Память расширения переполнена. Очистите кэш в настройках расширения.',
        openDirect: 'Открыть без VPN',
        retry: 'Повторить'
    } : {
        title: 'Enabling VPN…',
        msg:   'Turning on a secure connection for this site.',
        onTitle: 'VPN connected',
        onMsg:   'Opening the site through VPN…',
        errTitle: 'Failed to enable VPN',
        errNoTarget: 'Could not determine site address.',
        errNoExt: 'No connection to the extension. Restart Chrome.',
        errNotAllowed: 'This site is not in the auto-enable list.',
        errToggle: 'Could not enable VPN. Check internet and try again.',
        errStorage: 'Extension storage is full. Clear cache in extension settings.',
        openDirect: 'Open without VPN',
        retry: 'Retry'
    };

    var $ = function (id) { return document.getElementById(id); };
    var titleEl = $('title'), msgEl = $('msg'), targetEl = $('target'),
        spinnerEl = $('spinner'), actionsEl = $('actions');

    // [a11y] sync html lang с detected — скринридеры применяют правила соответствующего языка
    document.documentElement.lang = isRu ? 'ru' : 'en';
    titleEl.textContent = STR.title;
    msgEl.textContent = STR.msg;

    // Parse target URL from hash
    var raw = (location.hash || '').slice(1);
    // [v2.7.0 fix F51] Cap длины hash — location.hash принимает до ~64K, malicious iframe
    // может прогнать большой URL через new URL() + propagate его через sendMessage в SW.
    // Легитимные URL не превышают 2048 символов (RFC 7230 рекомендация).
    if (raw.length > 2048) { showError(STR.errTitle, STR.errNoTarget, false); return; }
    var target = '';
    try {
        var u = new URL(raw);
        if (u.protocol === 'http:' || u.protocol === 'https:') {
            // [v2.7.0 fix F26] Strip userinfo — `https://fake@legit.com` показывал в UI
            // "fake@legit.com", юзер мог спутать с автором сайта. location.replace и так
            // игнорирует userinfo, но textContent показывал его буквально.
            target = u.origin + u.pathname + u.search + u.hash;
        }
    } catch { /* malformed */ }

    if (!target) {
        showError(STR.errTitle, STR.errNoTarget, false);
        return;
    }
    targetEl.textContent = target;

    function showError(ttl, msg, showOpenDirect) {
        spinnerEl.classList.add('hidden');
        titleEl.textContent = ttl;
        titleEl.className = 'err';
        msgEl.textContent = msg;
        actionsEl.innerHTML = '';
        if (showOpenDirect) {
            var btn = document.createElement('button');
            btn.textContent = STR.openDirect;
            btn.addEventListener('click', function () { location.replace(target); });
            actionsEl.appendChild(btn);
        }
        var retry = document.createElement('button');
        retry.textContent = STR.retry;
        retry.className = showOpenDirect ? 'secondary' : '';
        retry.addEventListener('click', function () { location.reload(); });
        actionsEl.appendChild(retry);
    }

    function showSuccess() {
        titleEl.textContent = STR.onTitle;
        msgEl.textContent = STR.onMsg;
        // Small delay so the user sees the success state briefly, then navigate via VPN.
        setTimeout(function () { location.replace(target); }, 250);
    }

    // Ask SW to enable VPN; SW validates target is in user's autoEnableDomains list.
    // [v2.6.6 audit] 15-секундный hard-timeout на случай если SW завис посреди
    // doToggleProxy — без этого gate-страница показывала бы «Подключаем VPN…» вечно.
    // 15s > 10s race в SW + запас на медленный warm-up.
    var responded = false;
    var hardTimer = setTimeout(function () {
        if (responded) return;
        responded = true;
        showError(STR.errTitle, STR.errToggle, true);
    }, 15000);
    try {
        chrome.runtime.sendMessage({ action: 'autoEnableViaGate', target: target }, function (res) {
            if (responded) return;
            responded = true;
            clearTimeout(hardTimer);
            // [v2.8.2 audit-7 F37] +typeof check — `!res` пропустит non-object payload (string,
            // number) от malformed extension response. Defensive guard перед res.ok / res.reason.
            if (chrome.runtime.lastError || !res || typeof res !== 'object') {
                showError(STR.errTitle, STR.errNoExt, true);
                return;
            }
            if (res.ok) { showSuccess(); return; }
            if (res.reason === 'not_in_list') {
                // [v2.7.5 audit r3] showOpenDirect=false: site НЕ в user's auto-enable list,
                // значит user это НЕ авторизовал. "Open Direct" button → phishing vector
                // (третья сторона embed'ит iframe с malicious URL → user thinks normal flow,
                // gets redirected to attacker.com БЕЗ VPN). Показываем только Retry.
                showError(STR.errTitle, STR.errNotAllowed, false);
                return;
            }
            // [v2.7.1 fix F98] Specific quota message — иначе юзер видит generic
            // «проверьте интернет» вместо реальной причины (storage full).
            if (res.reason === 'storage_quota_exceeded') {
                showError(STR.errTitle, STR.errStorage, true);
                return;
            }
            showError(STR.errTitle, STR.errToggle, true);
        });
    } catch (e) {
        if (responded) return;
        responded = true;
        clearTimeout(hardTimer);
        showError(STR.errTitle, STR.errNoExt, true);
    }
})();
