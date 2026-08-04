// Background service worker for AnonVPN extension
// === CONSTANTS ===
// [v2.8.0] Session tier system: free-юзеры с верифицированным аккаунтом → 60 мин, без → 30 мин.
// Premium – без таймера. accountVerified читается из storage.local (синхронизируется через
// /AnonVPN/check-account.php). Default (undefined / first-install) → 30 мин – это intentional
// поведение: мотивация юзера зарегистрироваться + подтвердить email.
const VPN_DURATION_VERIFIED_MS = 60 * 60 * 1000;
const VPN_DURATION_ANON_MS = 30 * 60 * 1000;
async function getVpnDurationMs() {
    try {
        const d = await chrome.storage.local.get(['accountVerified']);
        return d.accountVerified === true ? VPN_DURATION_VERIFIED_MS : VPN_DURATION_ANON_MS;
    } catch (e) {
        return VPN_DURATION_ANON_MS;
    }
}
const VPN_ALARM_NAME = 'vpn_timer';
// [v3.1.1] Предупреждение за 5 мин до конца free-сессии. Alarm НЕ критичен (пропуск = нет
// уведомления, НЕ unlimited VPN) – обращение с ним мягче, чем с VPN_ALARM_NAME.
const VPN_WARN_ALARM_NAME = 'vpn_timer_warn';
const VPN_WARN_BEFORE_MS = 5 * 60 * 1000;
const VPN_DEADLINE_KEY = 'vpnDeadline';
const HEARTBEAT_ALARM = 'heartbeat_alarm';
// [v3.1.2] Ghost-ping: тихое фоновое обновление пингов серверов. Без фиксированной 5-мин паузы –
// за один проход пингуем ПОДРЯД всё устаревшее/непроверенное, пауза только когда проверять нечего.
const GHOST_PING_ALARM = 'ghost_ping_alarm';
const GHOST_PING_FRESH_MS = 30 * 60 * 1000; // [v3.1.3] 60→30 мин: свежее = точнее автовыбор «по скорости»; пинг копеечный (мгновенный 407-ответ прокси, наш API не трогается)
const GHOST_PING_TIMEOUT_MS = 3000;
const GHOST_PING_GAP_MS = 1500;             // пауза между серверами (тик пингует по одному + самопродолжение)
// [v2.8.0] check-account.php endpoint оставлен server-side для совместимости, но клиент
// его не вызывает после link – accountVerified ставится один раз при успешном link-uid и
// больше не перепроверяется. См. checkAccountStatus() ниже.
// [v2.8.7] Multi-domain API fallback. Если primary заблокирован РКН – клиент
// автоматически переключается на следующий. Тот же физический сервер, но другой
// домен → переживает DNS/HTTP-фильтрацию.
// Порядок = приоритет. Last-working domain persist'ится в storage.local
// под ключом `_apiActiveDomain` – после первого успеха больше не делаем
// попыток в primary, пока активный не упадёт.
// [v3.0.0] Переезд на новую инфраструктуру: 5 независимых api-доменов (отдельный VPS,
// своя БД с live-репликацией). balancing.apiget.ru НЕ в списке – это subdomain apiget.ru,
// разделит его судьбу при блокировке РКН; используется только для ссылок, не для API.
// Старые apiget.ru/cdn.* обслуживают только клиентов <3.0.0 (нет version/3.0.0/ endpoints).
const API_DOMAINS = ['https://api.bot-support.ru', 'https://n1.bot-support.ru', 'https://g1.bot-support.ru', 'https://api.unkill.ru', 'https://n1.unkill.ru', 'https://g1.unkill.ru', 'https://api.sibirlife.ru', 'https://n1.sibirlife.ru', 'https://g1.sibirlife.ru', 'https://api.1150.ru', 'https://n1.1150.ru', 'https://g1.1150.ru', 'https://api.foofle.ru', 'https://n1.foofle.ru', 'https://g1.foofle.ru'];
const API_ACTIVE_KEY = '_apiActiveDomain';
const API_DOMAINS_HOSTS = API_DOMAINS.map(function(d){ try { return new URL(d).hostname; } catch(e){ return ''; } }).filter(Boolean);
// [v3.0.4] Periodic re-probe: `_apiActiveDomain` sticky и НЕ ресетится (KNOWN, не STALE) → юзер,
// залипший на медленном/блокнутом фолбэк-домене, остаётся на нём → fetchServerStatsSW (4с) чаще
// падает → пустые stats → пробой блока 75 (стадо на pool[0]). Раз в 6ч пробуем домены по приоритету
// и ставим active на первый ЖИВОЙ (возврат на быстрый primary, когда его разблокировали). См.
// project_anonvpn_291_planning (sticky-fallback не возвращался на primary).
const API_PROBE_ALARM = 'api_domain_probe';
const API_PROBE_INTERVAL_MIN = 360;

// Возвращает домены по приоритету: [persistedActive, ...other]. Если persisted нет –
// порядок из API_DOMAINS как есть.
async function _getApiDomainsByPriority() {
    try {
        const got = await chrome.storage.local.get(API_ACTIVE_KEY);
        const active = got && got[API_ACTIVE_KEY];
        if (active && API_DOMAINS.indexOf(active) >= 0) {
            return [active].concat(API_DOMAINS.filter(function(d){ return d !== active; }));
        }
    } catch (e) {}
    return API_DOMAINS.slice();
}

async function _persistActiveApiDomain(domain) {
    try { await chrome.storage.local.set({ [API_ACTIVE_KEY]: domain }); } catch (e) {}
}

// apiFetch(path, opts) – обёртка над fetch с автосменой домена.
// path: '/AnonVPN/timestamp.php' (с ведущим слэшем, без домена).
// При network error / timeout / HTTP 5xx – пробует следующий домен.
// HTTP 4xx (401, 403, 429, …) НЕ триггерит fallback – это валидный ответ домена.
async function apiFetch(path, opts) {
    const domains = await _getApiDomainsByPriority();
    let lastErr = null;
    for (let i = 0; i < domains.length; i++) {
        const d = domains[i];
        const url = d + path;
        // [v3.1.5 audit В1] Если общий AbortSignal вызывающего уже исчерпан на медленном/
        // заблокированном предыдущем домене — НЕ передаём мёртвый сигнал: уже-абортнутый сигнал
        // валит все оставшиеся домены мгновенным AbortError → реле n1/g1 не пробуется (у юзера
        // в стране, режущей RU-IP через drop пакетов, первый домен висит в таймаут → фолбэк мёртв).
        // Даём оставшимся доменам свежее короткое окно.
        let attemptOpts = opts;
        if (opts && opts.signal && opts.signal.aborted) {
            attemptOpts = Object.assign({}, opts, { signal: AbortSignal.timeout(3000) });
        }
        try {
            const resp = await fetch(url, attemptOpts);
            // Любой HTTP-статус < 500 = домен жив, ответил
            if (resp.status < 500) {
                await _persistActiveApiDomain(d);
                return resp;
            }
            lastErr = new Error('HTTP ' + resp.status + ' from ' + d);
            try { logDiag('api.fallback_5xx', { from: d, status: resp.status }); } catch(e){}
        } catch (e) {
            lastErr = e;
            try { logDiag('api.fallback_neterr', { from: d, msg: (e && e.message) || String(e) }); } catch(_){}
        }
    }
    throw lastErr || new Error('All API domains unreachable');
}

// [v3.0.4] Пробуем API-домены по приоритету, ставим active на ПЕРВЫЙ живой (status<500). Возвращает
// юзера, залипшего на низкоприоритетном фолбэке, на primary когда тот снова доступен. Вызов – раз в 6ч
// (API_PROBE_ALARM). Лёгкий GET на timestamp.php, 4с таймаут на домен, тихий fail.
async function probeApiDomains() {
    for (let i = 0; i < API_DOMAINS.length; i++) {
        try {
            const resp = await fetch(API_DOMAINS[i] + '/AnonVPN/timestamp.php', { cache: 'no-store', signal: AbortSignal.timeout(4000) });
            if (resp && resp.status < 500) {
                await _persistActiveApiDomain(API_DOMAINS[i]);
                try { logDiag('api', 'reprobe_active', { domain: API_DOMAINS_HOSTS[i] || i }); } catch (_) {}
                return;
            }
        } catch (e) { /* следующий домен */ }
    }
}

const LINK_UID_PATH = '/AnonVPN/link-uid.php';
const LINK_UID_URL = 'https://apiget.ru/AnonVPN/link-uid.php'; // legacy, не используется напрямую
// [v2.6.10] Persisted TTL для heartbeat – гвард против инфляции на cold-wake SW.
// startHeartbeat() вызывается в initialize() при каждом cold-wake (если proxyEnabled),
// и до 2.6.10 immediate sendHeartbeat() слал запрос каждый wake (~30-60 сек на активных
// юзерах с DNR/webNav listeners из 2.6.5+). Сервер видел до 2000+ heartbeats/день вместо
// физического максимума 288 (24*12). Симметрично proxy_list TTL из 2.6.9.
// Период alarm = 5 мин, TTL = 4.5 мин – запас на jitter alarm-firing, чтобы legit
// onAlarm-вызовы проходили guard.
const HEARTBEAT_TTL_MS = 4.5 * 60 * 1000;
const HEARTBEAT_AT_KEY = 'lastHeartbeatAt';
const PREMIUM_CHECK_ALARM = 'premium_check_alarm';
const EXT_VERSION = chrome.runtime.getManifest().version;
// [v2.8.7] Все API-пути теперь относительные. apiFetch(path, opts) собирает URL
// с активным доменом и при отказе переключается на fallback. Старые const'ы оставлены
// для backward compat в местах, где fetch'ы ещё не мигрированы.
const API_PATH_BASE = '/AnonVPN/version/' + EXT_VERSION;
const PROXY_LIST_PATH = API_PATH_BASE + '/proxy_list.php';
const HEARTBEAT_PATH = API_PATH_BASE + '/heartbeat.php';
const DISCONNECT_PATH = API_PATH_BASE + '/disconnect.php';
const LATEST_VERSION_PATH = '/AnonVPN/version/latest.json';
// Legacy константы (НЕ используются напрямую в новых apiFetch вызовах, оставлены
// для обратной совместимости со старыми local-var ссылками если такие найдутся):
const API_BASE = 'https://apiget.ru/AnonVPN/version/' + EXT_VERSION;
// [3.1.5] per-server прокси-схема: сервер шлёт scheme:'https' для TLS-нод (stunnel:443). По умолчанию http.
function _proxyScheme(px){ return (px && px.scheme === 'https') ? 'https' : 'http'; }
// [v3.1.5] IP-preauth для TLS-нод (вариант A, production). Нода на 443 пускает только allowlist'нутые IP
// (firewall), proxy-авторизации нет вовсе → нет 407 → нет окна пароля и гонки onAuthRequired. Клиент
// НЕ ходит на ноду напрямую и НЕ знает токена: шлём HMAC-подписанный POST на balancing/node_preauth.php,
// сервер проверяет подпись+ext_id+premium, берёт реальный IP клиента (REMOTE_ADDR) и релеит на ноду
// server-side токеном. api.*-домены в BYPASS_LIST → запрос идёт DIRECT → сервер видит настоящий IP.
async function _nodePreauth(host) {
    if (!host) return false;
    try {
        const built = await buildHmacHeaders();
        const r = await apiFetch(API_PATH_BASE + '/node_preauth.php', {
            method: 'POST',
            headers: built.headers,
            body: JSON.stringify({ node: String(host) }),
            signal: AbortSignal.timeout(6000)
        });
        const ok = !!(r && r.ok);
        try { logDiag('preauth', ok ? 'ok' : 'bad', { host: String(host).slice(0, 40) }); } catch (_) {}
        return ok;
    } catch (e) { try { logDiag('preauth', 'fail', { host: String(host).slice(0, 40), msg: String((e && e.message) || '').slice(0, 60) }); } catch (_) {} return false; }
}
const PROXY_LIST_URL = API_BASE + '/proxy_list.php';
const HEARTBEAT_URL = API_BASE + '/heartbeat.php';
const DISCONNECT_URL = API_BASE + '/disconnect.php';
const LATEST_VERSION_URL = 'https://apiget.ru/AnonVPN/version/latest.json';
const API_DOMAIN = 'apiget.ru'; // legacy single-domain, BYPASS_LIST использует API_DOMAINS_HOSTS

// [v2.8.1] Стабильный идентификатор сервера – host:port. Заменил старые fN/pN
// (позиционные индексы), которые ломались при перетасовке n_proxies.txt:
// добавил сервер в середину → старая статистика «прилипла» к новой строке.
function _serverKey(p) {
    return p && p.host && p.port ? (String(p.host) + ':' + String(p.port)) : '';
}

// [v3.0.5] Персист пинг-результатов в selector-store: serverPings (auto-select) +
// checkerLastResults.ping.results (UI ms-плашки в списке серверов, fN/pN-ключи + cls). Зеркалит
// save-блок bulk-ping (~L4720, «Проверка серверов») – чтобы «Полная диагностика» тоже заполняла
// пинги у селекторов. accumPings={hp:{ms,ts}} ответившие; failedPings={hp:ts} НЕ ответившие (✗).
// Merge поверх существующих serverPings – не тестированные серверы не теряют пинги.
// ⚠ При правке порогов ping-cls (250/500/1000мс) синхронь bulk-ping save-блок.
async function _persistPingResults(accumPings, failedPings) {
    accumPings = accumPings || {}; failedPings = failedPings || {};
    const existing = await chrome.storage.local.get(['checkerLastResults', 'serverPings']);
    const mergedPings = (existing.serverPings && typeof existing.serverPings === 'object' && !Array.isArray(existing.serverPings)) ? Object.assign({}, existing.serverPings) : {};
    Object.keys(accumPings).forEach(function(hp){
        if (accumPings[hp] && typeof accumPings[hp].ms === 'number' && accumPings[hp].ms > 0) mergedPings[hp] = accumPings[hp];
    });
    let clr = (existing.checkerLastResults && typeof existing.checkerLastResults === 'object') ? existing.checkerLastResults : {};
    if (!clr.ping || !clr.ping.results) clr.ping = { ts: Date.now(), results: {} };
    const fullList = serverList || [];
    const idxMap = new Map();
    fullList.filter(function(p){ return p.type !== 'premium'; }).forEach(function(p, idx){ idxMap.set(_serverKey(p), 'f' + idx); });
    fullList.filter(function(p){ return p.type === 'premium'; }).forEach(function(p, idx){ idxMap.set(_serverKey(p), 'p' + idx); });
    Object.keys(accumPings).forEach(function(hp){
        const ms = accumPings[hp] && accumPings[hp].ms;
        const ts = accumPings[hp] && accumPings[hp].ts;
        const fKey = idxMap.get(hp);
        if (!fKey || typeof ms !== 'number' || ms <= 0) return;
        let cls = 'ping-3';
        if (ms < 250) cls = 'ping-1';
        else if (ms < 500) cls = 'ping-2';
        else if (ms < 1000) cls = 'ping-3';
        else cls = 'ping-4';
        clr.ping.results[fKey] = { cls: cls, text: String(ms) + ' ms', ts: ts || Date.now(), hp: hp };
    });
    Object.keys(failedPings).forEach(function(hp){
        const fKey = idxMap.get(hp);
        if (!fKey) return;
        clr.ping.results[fKey] = { cls: 'fail', text: '✗', ts: failedPings[hp] || Date.now(), hp: hp };
    });
    clr.ping.ts = Date.now();
    // [v3.1.3] Сервер, проваливший РЕАЛЬНУЮ проверку туннеля (✗), метим сломанным → авто-подбор
    // его исключает (getBrokenServers → excluded). Иначе ghost-ping видит только TCP-доступность
    // (быстрый 407-ответ) и считает сервер «живым», из-за чего авто-подбор выбирает мёртвый-по-
    // туннелю сервер (кейс DK-№33: ghost 102мс, но реальный туннель ✗). TTL 5 мин – сам истечёт.
    const _failedHps = Object.keys(failedPings);
    let _bsMerge = null;
    if (_failedHps.length) {
        const _bsData = await chrome.storage.local.get(['brokenServers']);
        _bsMerge = (_bsData.brokenServers && typeof _bsData.brokenServers === 'object' && !Array.isArray(_bsData.brokenServers)) ? _bsData.brokenServers : {};
        const _bnow = Date.now();
        _failedHps.forEach(function(hp){ _bsMerge[hp] = _bnow; });
        for (const _bk in _bsMerge){ if (_bnow - _bsMerge[_bk] > BROKEN_SERVER_TTL_MS) delete _bsMerge[_bk]; }
    }
    const _persistObj = {
        serverPings: mergedPings,
        serverPingsRunAt: Date.now(),
        checkerLastResults: clr
    };
    if (_bsMerge) _persistObj.brokenServers = _bsMerge;
    await chrome.storage.local.set(_persistObj);
}

// [v3.0.1] Однонаправленный хеш сервера из IP для диагностики. В результат диагностики
// (diagLastResult в storage + broadcast) НЕ кладём host:port – иначе после проверки весь
// пул прокси осел бы в storage плейнтекстом, обходя шифрование proxyListEnc. Кладём только
// этот хеш. Функция ИДЕНТИЧНА popup.js _srvHash и admin/proxy-settings.php (итеративно
// (h*31 + charCode) mod 2^32 → base36, префикс S_) – владелец сверяет сервер по хешу.
function _diagSrvHash(ip) {
    ip = String(ip || '');
    let h = 0;
    for (let i = 0; i < ip.length; i++) { h = (h * 31 + ip.charCodeAt(i)) >>> 0; }
    return 'S_' + h.toString(36);
}

// [v3.1.4] Connected-проба диагностики по HTTPS закрывает дыру ложного connected: прозрачный
// HTTP-прокси провайдера (фильтрующие сети – Китай/Иран/RU-регионалы, анализ no_ipchange
// 07-10.07.2026) отвечал на HTTP HEAD сам, не доставляя запрос до нашего сервера → connected=true
// при мёртвом туннеле → запутывающий вердикт no_ipchange вместо честного all_blocked_dpi.
// [v3.1.4 hotfix] Включаем HTTPS-пробу ТОЛЬКО на Windows-десктопе, где она проверена и работает
// (Win7+). На macOS / Android-Chromium (Kiwi 137 подтверждён) SW-fetch HTTPS через прокси-CONNECT
// даёт ложный connected=false рабочему VPN → диагностика врёт «заблокировано». Там HTTP-проба
// как в 3.1.3 (надёжна: DNR инжектит Proxy-Authorization в проксированный GET; ipify-HTTPS,
// не менявшийся с 3.1.3, определяет смену IP независимо). Требует одновременно Chrome ≥116.
function _diagHttpsProbeOk() {
    try {
        var ua = navigator.userAgent || '';
        if (!/Windows/i.test(ua)) return false;
        var m = ua.match(/Chrome\/(\d+)/);
        return m ? (parseInt(m[1], 10) >= 116) : false;
    } catch (e) { return false; }
}

// [v2.6.5] UTM helpers – analytics for site purchases
function upsellUrl(medium) {
    return chrome.runtime.getURL('premium-upsell.html') + '?utm_medium=' + encodeURIComponent(medium);
}

// [v2.8.8] Российские TLD – DIRECT (не через VPN) когда `bypassRuDomains` включён.
// Default ON. Цель – российские сайты не «стучат в РКН» что зашли через иностранный IP.
//
// ВАЖНО: только ASCII-домены. Cyrillic `*.рф` в Chrome's bypassList = Chrome
// reject'ит весь setting → connection timeout. Punycode `*.xn--p1ai` покрывает .рф
// потому что Chrome нормализует IDN-host в Punycode ДО bypass-проверки.
// PAC-сравнение `h.endsWith(".рф")` тоже не работает – host приходит уже в Punycode.
const RU_BYPASS_DOMAINS = ['*.ru', '*.xn--p1ai'];
// Те же TLD без `*.` – для setProxyAuthRule, чтобы DNR rule НЕ добавлял
// Proxy-Authorization header к DIRECT-routed .ru/.рф запросам (utечка credentials).
const RU_AUTH_EXCLUDE_DOMAINS = ['ru', 'xn--p1ai'];

// [v2.9.0] УБРАНЫ ВСЕ Google-домены. Раньше держались в bypass потому что в эпоху
// FIX #6 (v2.4.x-2.5.x) Chrome возвращал 407 на эти internal-запросы – webRequest
// не успевал инжектить Proxy-Authorization до того как Chrome ловил их. С тех пор
// поведение Chrome поменялось, список никто не пересматривал → выяснилось что
// accounts.youtube.com, play.google.com, clients.google.com **заблокированы РКН
// на TCP/DNS уровне**: будучи в bypass-листе они шли мимо VPN с реального IP
// юзера и timeout'или → нельзя было войти в YouTube/Google аккаунт даже с ВПН.
// Теперь все Google-запросы идут через прокси с иностранного IP.
const BYPASS_LIST = [
    // [v2.8.7] Все API-домены AnonVPN (primary + fallback) – должны идти DIRECT
    // мимо VPN, иначе CONNECT-loop через свой же прокси.
    ...API_DOMAINS_HOSTS,
    '<-loopback>'
];

// [v2.5.8] Зашифрованный обмен прокси-листом с сервером.
// [audit] ВАЖНО: эти константы НЕ являются конфиденциальными секретами – CRX-файл
// расширения публичный, любой может их извлечь. Реальная защита протокола:
//   • server-side nonce cache (окно ±300 сек) – анти-replay
//   • ext_id whitelist на сервере – запросы только от легитимных установок
//   • per-UID rate limit (30/hr)
// Должны совпадать с PHP-стороной (common.php константы ANONVPN_*).
const SHARED_SECRET_HEX = '98b84a9c7dd4a12f29b6eb074642174a7e4fff4255b0d2a344d17a6e847505b4';
const HMAC_KEY_HEX      = '901734b2192c892f416365f223a6b91717780030770ec6c2f5d8bcab379037f8';
const HKDF_INFO         = 'AnonVPN-ProxyList-v1';
const PROTO_VERSION     = 1;

// [v2.7.3] Free-юзеры не подключаются к серверам с нагрузкой >= 75 (оранжевый уровень).
// Premium – без лимита. Порог согласован с popup.js FREE_LOAD_LIMIT + badge рендер.
// Guard в doToggleProxy проверяет serverUserCounts против этого порога для selectedProxy.
const FREE_LOAD_LIMIT = 75;

// [v2.8.0] Список стран, исключаемых из auto-select при первой установке.
// Ping для большинства юзеров из RU/EU обычно 5000+ ms – auto-select мог автоматом
// подключать к ним и юзер видел «VPN тормозит». Теперь исключаются по умолчанию,
// но остаются доступны для ручного выбора (юзер может вернуть их через "+" в списке).
// Применяется ОДИН РАЗ при первом успешном fetch'е серверного списка после install.
// [v2.9.1 user feedback] Отключено – auto-исключение по стране скрывало серверы
// от юзеров. Логика applyFirstInstallExclusionsIfPending остаётся (функция в коде),
// просто список пуст – при первом install ничего не добавляется в excludedFromAutoSelect.
// Чтобы вернуть – добавить страны обратно в массив.
const FIRST_INSTALL_EXCLUDE_COUNTRIES = [];

// === Crypto helpers ===
// [v2.8.0 audit r2] Defensive validation – odd-length hex или non-hex chars раньше давали
// silent corruption: parseInt('xx',16)=NaN→0 byte. Теперь throws → outer try/catch ловит
// в decrypt/HMAC paths с чистым diag-сообщением, а не «MAC verify failed» от мусорных байт.
function hex2bytes(hex) {
    if (typeof hex !== 'string') throw new Error('hex_type');
    if (hex.length % 2 !== 0) throw new Error('hex_len');
    if (hex.length && !/^[0-9a-fA-F]+$/.test(hex)) throw new Error('hex_chars');
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < hex.length; i += 2) out[i / 2] = parseInt(hex.slice(i, i + 2), 16);
    return out;
}
function bytes2hex(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += bytes[i].toString(16).padStart(2, '0');
    return s;
}
function utf8(str) { return new TextEncoder().encode(str); }

async function hmacSignHex(keyBytes, dataStr) {
    const key = await crypto.subtle.importKey(
        'raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
    );
    const sig = await crypto.subtle.sign('HMAC', key, utf8(dataStr));
    return bytes2hex(new Uint8Array(sig));
}

// Возвращает {encKey, macKey} – оба готовы к использованию через subtle.decrypt/verify
async function deriveProxyListKeys(secretBytes, uid, ts) {
    const baseKey = await crypto.subtle.importKey(
        'raw', secretBytes, 'HKDF', false, ['deriveBits']
    );
    const km = new Uint8Array(await crypto.subtle.deriveBits(
        {
            name: 'HKDF',
            hash: 'SHA-256',
            salt: utf8(uid + '|' + ts),
            info: utf8(HKDF_INFO)
        },
        baseKey,
        512 // 64 байта
    ));
    const encKey = await crypto.subtle.importKey(
        'raw', km.slice(0, 32), { name: 'AES-CBC', length: 256 }, false, ['decrypt']
    );
    const macKey = await crypto.subtle.importKey(
        'raw', km.slice(32, 64), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
    );
    return { encKey, macKey };
}

// AES-256-CBC + HMAC-SHA256 (encrypt-then-MAC) расшифровка ответа сервера
async function decryptProxyListResponse(env, uid, extId, version) {
    // [v2.7.6 audit Pass13] Defensive null/object check – `env.v` на null бросает
    // TypeError "Cannot read properties of null", outer catch его поймает но diagnostic
    // получает шумный stack. Чистый Error('format') легче читается в support-логах.
    if (!env || typeof env !== 'object') throw new Error('format');
    if (env.v !== 1) throw new Error('proto');
    // [v2.7.6 audit Pass7] Defensive type-checks. hex2bytes(undefined/non-string) throws
    // на iter operation – outer try/catch ловит, но diagnostic шумный. Явная проверка
    // перед conversion даёт чистый error-path при malformed server response.
    if (typeof env.iv !== 'string' || typeof env.ct !== 'string' || typeof env.mac !== 'string'
        || typeof env.ts !== 'number') {
        throw new Error('format');
    }
    const ts = env.ts;
    const iv = hex2bytes(env.iv);
    const ct = hex2bytes(env.ct);
    const mac = hex2bytes(env.mac);
    // [v2.7.6 audit Pass7] AES-CBC IV должен быть ровно 16 байт. Web Crypto throws
    // OperationError на wrong length – defensive check для clean diagnostic.
    if (iv.length !== 16) throw new Error('iv_len');
    const { encKey, macKey } = await deriveProxyListKeys(hex2bytes(SHARED_SECRET_HEX), uid, ts);

    // Verify MAC over (aad || iv || ct) – обязательно ДО расшифровки
    const aadBytes = utf8(extId + '|' + version);
    const macInput = new Uint8Array(aadBytes.length + iv.length + ct.length);
    macInput.set(aadBytes, 0);
    macInput.set(iv, aadBytes.length);
    macInput.set(ct, aadBytes.length + iv.length);
    const ok = await crypto.subtle.verify('HMAC', macKey, mac, macInput);
    if (!ok) throw new Error('mac');

    // AES-CBC расшифровка (Web Crypto автоматически снимает PKCS7 padding)
    const pt = await crypto.subtle.decrypt({ name: 'AES-CBC', iv }, encKey, ct);
    return JSON.parse(new TextDecoder().decode(pt));
}

// === Локальный кэш прокси-листа: AES-GCM с ключом, выведенным из runtime.id ===
async function getLocalCacheKey() {
    const baseKey = await crypto.subtle.importKey(
        'raw', hex2bytes(SHARED_SECRET_HEX), 'HKDF', false, ['deriveKey']
    );
    return crypto.subtle.deriveKey(
        {
            name: 'HKDF',
            hash: 'SHA-256',
            salt: utf8(chrome.runtime.id || 'anon'),
            info: utf8('AnonVPN-LocalCache-v1')
        },
        baseKey,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
    );
}
async function saveListToEncryptedCache(list) {
    try {
        const key = await getLocalCacheKey();
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const pt = utf8(JSON.stringify(list));
        const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, pt);
        await chrome.storage.local.set({
            proxyListEnc: { iv: bytes2hex(iv), ct: bytes2hex(new Uint8Array(ct)) }
        });
    } catch (e) {
        // [v2.8.0 audit r2] Cache-save failure non-fatal, но раньше полностью silent.
        // logDiag даёт видимость в support-логах – quota/IO errors отслеживаемы.
        logDiag('net', 'cache_save_fail', { msg: String((e && e.message) || e).slice(0, 80) });
    }
}
// [v2.6.9] Pure-decrypt helper – принимает уже прочитанные encData; используется
// в ensureProxyList'е чтобы слить storage.get кэша + TTL-timestamp в один batch-вызов.
async function decryptCachedList(encData) {
    if (!encData) return null;
    // [v2.7.6 audit Pass7] Type-check IV/CT перед hex2bytes – defensive против
    // corrupted local storage (manual edit, partial write, etc.).
    if (typeof encData.iv !== 'string' || typeof encData.ct !== 'string') return null;
    try {
        const key = await getLocalCacheKey();
        const ivBytes = hex2bytes(encData.iv);
        // AES-GCM IV должен быть 12 байт (NIST recommendation, Web Crypto standard).
        if (ivBytes.length !== 12) return null;
        const pt = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv: ivBytes },
            key,
            hex2bytes(encData.ct)
        );
        const arr = JSON.parse(new TextDecoder().decode(pt));
        return Array.isArray(arr) ? arr : null;
    } catch (e) {
        // [v2.7.6 audit Pass13] logDiag вместо silent – corrupted local cache раньше
        // распознавался только как «нет кэша», без telemetry. Помогает support-cases
        // если юзер жалуется на медленный first-load (cache всегда invalid).
        logDiag('crypto', 'cache_decrypt_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        return null;
    }
}
async function loadListFromEncryptedCache() {
    try {
        const d = await chrome.storage.local.get(['proxyListEnc']);
        return decryptCachedList(d.proxyListEnc);
    } catch { return null; }
}

// In-memory список – единственный источник правды для proxyList
let serverList = null;

// [v2.5.8 audit] Флаг блокировки: если сервер уже сказал version_too_old / unknown_ext_id,
// не дергаем сеть повторно до следующего успешного fetch (или SW restart).
// [v2.6.0] vpnBlockedAt – отметка времени установки флага. Спустя VPN_BLOCKED_COOLDOWN_MS
// lazy-reset даёт сети новый шанс – спасает от «застревания» при транзиентном 403.
let vpnBlocked = false;
let vpnBlockedAt = 0;
const VPN_BLOCKED_COOLDOWN_MS = 60 * 1000;

// [v2.6.1] Смещение часов клиента относительно сервера (сек). Применяется к ts подписи
// proxy_list.php, чтобы отстающие/спешащие часы пользователя не ломали replay-окно.
// Выставляется при первом получении 401 err:"clock" через запрос timestamp.php.
// Живёт в памяти до SW-рестарта – при cold start пересчитаем при следующем err:"clock".
let clockOffsetSec = 0;

// [FIX #7] Guard от двойного нажатия toggleProxy
let toggleInProgress = false;
// [v2.6.9] In-flight guards для recoverPremium/requestTrial – на двойной клик второй вызов
// получает {ok:false, reason:'in_flight'} вместо повторного HTTP-запроса (server-side idempotent,
// но экономим квоту). Popup re-enable'ит кнопку после 1й success-ответа.
let _recoverInFlight = false;
let _trialInFlight = false;
// [v2.8.0] In-flight guards для check-account / link-uid endpoints (тот же паттерн).
let _checkAccountInFlight = false;
let _linkUidInFlight = false;
// [v3.1.1] Guard против гонки двух popup, одновременно шлющих reportSetupDone (дубль setup-сигнала).
let _setupReportInFlight = false;
// [v2.8.8] Guard против spam-click bypassRuToggle → 5 concurrent setProxy calls.
let _reapplyInFlight = false;
// [v2.6.2] Guard против race с pingProxy: массовая проверка меняет chrome.proxy.settings
// на тестируемый сервер, одновременный toggleProxy перезаписал бы его мусором.
let pingInProgress = false;

// [v2.6.2] Ad/tracker blocker – статический ruleset из manifest.json, по умолчанию
// disabled. Включается на премиум-подписчиках, выключается на не-премиум.
const AD_BLOCKER_RULESET_ID = 'ad_blocker';
async function setAdBlockerEnabled(enabled) {
    try {
        const current = await chrome.declarativeNetRequest.getEnabledRulesets();
        const isOn = Array.isArray(current) && current.indexOf(AD_BLOCKER_RULESET_ID) >= 0;
        if (enabled === isOn) return;
        await chrome.declarativeNetRequest.updateEnabledRulesets(
            enabled
                ? { enableRulesetIds: [AD_BLOCKER_RULESET_ID] }
                : { disableRulesetIds: [AD_BLOCKER_RULESET_ID] }
        );
        logDiag('adblock', enabled ? 'on' : 'off');
    } catch (e) {
        logDiag('adblock', 'err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
    }
}
// [v2.7.0 fix F24] applyPremiumState вызывается из 4+ мест (initialize, storage.onChanged,
// recoverPremium, requestTrial). Без mutex параллельные `setAdBlockerEnabled` →
// `chrome.declarativeNetRequest.updateEnabledRulesets` могут rejecting друг друга silently
// → ruleset state неопределён. Также read-write race на autoSelectScope (между sw:233
// read и sw:241 write юзер мог изменить scope). Симметрично _heartbeatQueue/_dnrSyncQueue.
let _applyPremiumStateQueue = Promise.resolve();
// [v2.8.2 audit-2] Serialize accountVerified extend/shrink handlers – без него rapid
// verify→unverify→verify gives parallel async IIFEs racing на VPN_DEADLINE_KEY + chrome.alarms.create.
let _accountVerifiedQueue = Promise.resolve();
function applyPremiumState() {
    // [v2.8.2 audit-3 F19] logDiag в catch чтобы silent failures были видны в diagnostic ring buffer.
    // Раньше .catch(() => {}) глушил все errors – debugging stale premium state был невозможен.
    _applyPremiumStateQueue = _applyPremiumStateQueue.catch(e => {
        logDiag('premium', 'queue_prev_fail', { msg: String((e && e.message) || '').slice(0, 80) });
    }).then(() => _applyPremiumStateBody());
    return _applyPremiumStateQueue;
}
async function _applyPremiumStateBody() {
    const d = await chrome.storage.local.get(['isPremium', 'adBlockerEnabled', 'autoSelectScope']);
    // [v2.7.6] Default OFF for new users – `=== true` instead of `!== false`.
    // Раньше default был ON (undefined → !== false = true), сейчас default OFF (undefined
    // → === true = false). Существующие юзеры с явно установленным adBlockerEnabled=true
    // (через popup toggle) сохраняют ON; кто никогда не trogal – теперь OFF (юзер
    // включает вручную через Premium tab).
    const want = !!d.isPremium && d.adBlockerEnabled === true;
    await setAdBlockerEnabled(want);
    // [v2.6.4 fix] Новый Premium-юзер → autoSelectScope='all' (использовать все серверы включая premium).
    // Иначе остаётся default 'free' → балансировщик игнорирует premium-пул. Переписываем только undefined,
    // чтобы уважать явный выбор юзера (если он ранее переключил dropdown на 'free').
    if (d.isPremium && !d.autoSelectScope) {
        // [v2.7.6 audit Pass13] Wrap quota fail – silent skip OK (юзер может вручную
        // переключить scope через popup-dropdown, autoSelectScope=undefined продолжит
        // работать как 'free' default). Без guard'а throw каскадирует через _applyPremiumStateQueue.
        try { await chrome.storage.local.set({ autoSelectScope: 'all' }); }
        catch (e) { logDiag('premium', 'autoscope_set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    }
    // [v2.9.2 critical fix] Если юзер стал Premium И список серверов в кэше НЕ содержит
    // premium-серверов – форсим fresh fetch. Покрывает кейсы когда `premiumActivated` message
    // потерян (popup closed before sendMessage callback, SW asleep, _trialInFlight skip,
    // toggleInProgress skip) И серверный кэш premium-check вернул stale ответ для предыдущего
    // proxy_list.php fetch. Юзер активировал ключ → popup reopen → premium-серверов нет.
    // Reentrancy-safe: ensureProxyList(true) использует serverListPromise mutex.
    if (d.isPremium) {
        try {
            const list = Array.isArray(serverList) ? serverList : [];
            const hasPremium = list.some(p => p && p.type === 'premium');
            if (!hasPremium) {
                logDiag('premium', 'force_proxy_refresh', { listLen: list.length });
                // Не await – фоновый refresh, getProxies сам ждёт обновления при следующем popup-open
                doRefreshProxyList().catch(e => logDiag('premium', 'force_refresh_fail', { msg: String((e && e.message) || '').slice(0, 80) }));
            }
        } catch (e) {
            logDiag('premium', 'refresh_check_err', { msg: String((e && e.message) || '').slice(0, 80) });
        }
    }
    // [v2.7.4 audit r6] Per CLAUDE.md: applyPremiumState – single source of truth для
    // premium-derived UI state (ad-blocker ruleset, badge, timer). storage.onChanged
    // на isPremium уже триггерит updateBadge (line 1950), но direct callers
    // (initialize, requestTrial, recoverPremium, _doLogout) – нет. Defensive single-call
    // гарантирует sync даже при пути без storage.onChanged.
    try { await updateBadge(); } catch {}
}

// [v2.6.2] Единый список всех storage-ключей, используемых текущей версией.
// ⚠ ВАЖНО: при добавлении нового chrome.storage.local.set({newKey:...}) где-либо в коде –
// обязательно дописать newKey сюда, иначе cleanupUnknownStorageKeys() сотрёт его
// на следующем реальном апдейте версии как «мусор от старой версии».
const KNOWN_STORAGE_KEYS = new Set([
    // Core
    'uid', 'proxyEnabled', VPN_DEADLINE_KEY,
    // [v2.8.7] Multi-domain API fallback – last-working domain (persisted чтобы переживать
    // SW restart). НЕ в STALE_KEYS: переживание апдейта важнее для РКН-юзеров (иначе
    // post-bump первый apiFetch снова идёт в primary apiget.ru → timeout → fallback).
    API_ACTIVE_KEY,
    // Proxy
    'selectedProxy', 'proxyList', 'proxyListEnc', // proxyList – legacy <2.5.8, в STALE_KEYS → инвариант STALE⊆KNOWN
    'brokenServers', // [v3.0.3] {host:port→ts} сломанные туннели (TTL 5мин, self-prune) – метка в popup + авто-избегание
    // Premium
    'isPremium', 'premiumKey', 'expiresAt', 'expires_timestamp',
    // User prefs
    'language', 'colorTheme',
    // [v3.1.1] Настройки уведомлений о конце free-сессии (default ON: undefined → включено).
    // User-data → НЕ в STALE_KEYS.
    'notifySessionEnd', 'notifySessionSoon',
    'autoSelectServer', 'autoSelectScope',
    'favoriteServers', 'excludedFromAutoSelect',
    'firstInstallExclusionsPending', // [v2.8.0 legacy] vestigial; supersededed by defaultAutoSelectExclusionsApplied – оставлен в KNOWN_STORAGE_KEYS чтобы cleanupUnknownStorageKeys не cтёр на real bump (юзеры могут иметь false)
    'defaultAutoSelectExclusionsApplied', // [v2.8.0 round 14] one-shot sentinel: true = default-исключения для KR/TW/TR/JP уже применены
    'lastCheckerRunAt', // [v2.8.0 legacy] vestigial – заменён checkerRunHistory; не стираем чтобы не наследовать на новой проверке
    'checkerRunHistory', // [v2.8.0] sliding-window history {ping:[ts...], site:[ts...]} – mode-aware rate limit (ping=1/час, site=3/час)
    'checkerLastResults', // [v2.8.0] кэш результатов последней проверки {ts, mode, site, results:{key→{cls,text,ts}}}
    'checkerMode', // [v2.8.0] last-selected mode ('ping' | 'site') – restore при reopen popup
    'checkerSelectedSite', // [v2.8.0] last-selected option value из <select id="checker-site"> (URL или 'custom')
    'checkerCustomSite', // [v2.8.0] значение custom-input (используется если checkerSelectedSite === 'custom')
    'siteCheckByServer', // [v3.1.7] накопитель проверок «Доступность сайта» по серверам {hp:{siteHost:{cls,text,ts}}} – подсказка при наведении на сервер

    'blacklistDomains', 'whitelistDomains', 'exclusionsMode',
    'excludedDomains', // применяемая копия для bypass-list (не мусор)
    'adBlockerEnabled', 'serverSortMode',
    // [v3.1.7] serverSiteHintsEnabled – default true. Подсказка проверенных сайтов при наведении на сервер.
    // НЕ в STALE_KEYS: user preference, переживает real bump.
    'serverSiteHintsEnabled',
    // [v2.8.8] bypassRuDomains – default true. Российские TLD (.ru/.рф) идут DIRECT.
    // НЕ в STALE_KEYS: user preference, переживает real bump (если юзер отключил – должно остаться отключено).
    'bypassRuDomains',
    // Cache (clearable)
    // [v3.0.2] cachedServerStatsAt – timestamp последнего fetchServerStats (TTL 30 мин в popup
    // refreshServerStats). Тот же lifecycle что cachedServerStats → в KNOWN + STALE + CACHE_KEYS.
    'cachedProxyList', 'cachedServerStats', 'cachedServerStatsAt', 'cachedNews', 'cachedTranslationsData', 'cachedTranslationsVersion',
    // State flags
    'updateRequired', 'minVersion', 'updateUrl', 'illegalExtId',
    'updateAvailable', 'updateAvailableDismissed',
    'sessionExpired',
    // [v2.8.5] онбординг-модалка показана и закрыта крестиком (one-shot; НЕ в STALE_KEYS)
    'onboardingSeen',
    // [v2.9.1] V2-онбординг с выбором критерия авто-выбора (load/ping/both) +
    // массовая пропинговка топ-серверов по нагрузке. Отдельный sentinel –
    // на real-update показывается заново всем юзерам (старый onboardingSeen=true
    // не подавляет v2-flow). НЕ в STALE_KEYS – one-shot.
    'onboardingV2Done',
    // [v3.1.1] setupReported – сигнал о завершении первичной настройки уже отправлен на сервер.
    // Ставится ОДИН раз при первой установке. НЕ в STALE_KEYS – переживает апдейт, чтобы после
    // апдейта (onboardingV2Done стёрт → мастер показывается снова) сигнал НЕ ушёл повторно.
    'setupReported',
    // [v2.9.1] Критерий авто-выбора: 'load' (по нагрузке, default) | 'ping' (по
    // latency) | 'both' (комбинированная нормализованная оценка). User preference,
    // НЕ в STALE_KEYS.
    'autoSelectMethod',
    // [v2.9.1] Кэш измеренных пингов: {[host:port]: {ms: number, ts: timestamp_ms}}.
    // Измеряется в onboarding или по кнопке в settings. TTL ~24ч (старые игнорим).
    // В STALE_KEYS – формат может меняться между версиями.
    'serverPings',
    // [v2.9.1] Timestamp последнего bulk-ping run (для throttle re-run + UI label
    // "обновлено N часов назад"). В STALE_KEYS.
    'serverPingsRunAt',
    // [v2.9.1 audit fix] inflight-marker bulk-ping для popup-recovery: {done,total,ts}.
    // SW set'ит при старте/каждой итерации, remove на done. popup при init читает –
    // если есть и ts свежий → показывает индикатор и ждёт broadcast'ов. В STALE_KEYS.
    'bulkPingProgress',
    // [v3.0.1] Полная диагностика – recovery при popup-reopen во время прогона:
    // diagRunning {ts} (идёт), diagProgress {phase,done,total} (текущий шаг),
    // diagLastResult (последний результат для reopened-popup). Transient.
    'diagRunning', 'diagProgress', 'diagLastResult', 'fullDiagLastRun',
    // [v2.6.3] Trial CTA state – dismiss решение юзера + флаг что trial уже исчерпан
    'trialCtaDismissed', 'trialAlreadyIssued',
    // [v2.6.4] Auto-enable VPN: включатель + список доменов + debounce-история
    'autoEnableEnabled', 'autoEnableDomains', 'autoEnableHistory',
    // [v2.6.5] Флаг отказа от webNavigation permission – не дёргаем повторно
    '_webNavRefused',
    // [v2.7.1 fix F116] vpnConflictList/Seen – кэш management.getAll() conflict-scan
    // (writeprefer'ed на permission grant, removed на revoke в _onPermissionsRemovedHandler).
    // Без регистрации в KNOWN_STORAGE_KEYS cleanupUnknownStorageKeys стирал бы их на каждом
    // real bump (двойной wipe с STALE_KEYS) И на любой запуск cleanup'а – юзер терял scan
    // результаты неожиданно.
    'vpnConflictList', 'vpnConflictLastSeen',
    // [v2.8.2 vpn-conflict-block] Bool флаг – popup пишет true когда детектировал
    // другие активные VPN-расширения через chrome.management. SW читает в isVpnConflictBlocked
    // для блокировки toggle/trial/recover (defense-in-depth когда popup закрыт).
    'vpnConflictBlocked',
    // [v2.6.9] Persisted timestamp последнего успешного proxy_list-фетча для TTL-гварда
    'proxyListFetchAt',
    // [v2.8.4] Причина последнего фейла fetchProxyList – 'network' | 'server'.
    // Popup читает чтобы показать конкретный текст вместо общего «Нет серверов».
    // На успешном fetch удаляется (proxyListFetchError также wiped).
    'proxyListFetchError', 'proxyListFetchErrorAt',
    // [v2.6.10] Persisted timestamp последнего успешного heartbeat для TTL-гварда
    'lastHeartbeatAt',
    // [v2.7.5] Persisted traffic accumulator (bytes_in/bytes_out/requests). Резетится
    // на успешном heartbeat-POST'е сервером. Без регистрации тут – cleanup сотрёт
    // на real version bump, потеряем накопленный трафик последнего интервала.
    'pendingTraffic',
    // [v2.8.0] Bot-detection rate-limit state (приходит 403 с err='rate_limited' от
    // proxy_list/heartbeat). UI показывает баннер «превышен лимит активности до X».
    // На версию-bump очищается (stale block от прошлой версии не должен пережить update).
    'rateLimited', 'rateLimitedReason', 'rateLimitedUntil',
    // [v2.8.0] Session-tier account-link state. accountVerified управляет 30/60-мин таймером.
    // accountEmail – obfuscated email для отображения в popup.
    // [v2.8.0] Session-tier account-link state. accountVerifyDismissed был УДАЛЁН (банер висел
    // пока не верифицируешь почту / не активируешь Premium). [v3.1.7] dismiss ВЕРНУЛИ, но только
    // после ≥3ч суммарного ВПН (accountVerifyBannerDismissed) — новичок закрыть не может.
    'accountVerified', 'accountEmail', 'accountVerifyBannerDismissed',
    'serverLegendSeen', // [v3.1.6] one-time: легенда обозначений в выборе сервера уже показана (НЕ в STALE)
    '_pendingAutopickSite', // [v3.1.7] transient: баннер/гибрид просит popup подобрать сервер для сайта (popup читает+удаляет)
    // Feedback form
    'feedback_text', 'feedback_email', 'feedback_rating',
    // Stats / log
    'vpnStats', 'lastNewsTime', 'diagnosticLog',
    // [v3.1.1] Старт текущей сессии для счётчика в popup (переживает SW-рестарты,
    // в отличие от vpnStats.currentSessionStart). НЕ в STALE – сессия может пережить апдейт.
    'vpnStartedAt',
    // [v2.8.5] read-tracking системных сообщений (вкладка «Новости»). НЕ в STALE_KEYS –
    // переживает обновление расширения, иначе юзер заново увидит все сообщения после апдейта.
    // seenSysMsgIds – keyexp «увидено»; readAdminMsgIds – админ-сообщения «прочитано» (кнопка).
    'seenSysMsgIds', 'readAdminMsgIds'
]);

// Удалить все storage-ключи, которых нет в KNOWN_STORAGE_KEYS.
// Вызывается при реальном апдейте версии – чистит остатки от предыдущих релизов.
async function cleanupUnknownStorageKeys() {
    try {
        const all = await chrome.storage.local.get(null);
        const toRemove = Object.keys(all).filter(k => !KNOWN_STORAGE_KEYS.has(k));
        if (toRemove.length) {
            await chrome.storage.local.remove(toRemove);
            logDiag('cleanup', 'unknown_removed', {
                count: toRemove.length,
                keys: toRemove.slice(0, 20)
            });
        }
    } catch (e) {
        logDiag('cleanup', 'err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
    }
}

// [v2.6.2] Мягкая проверка актуальной версии (soft, non-blocking).
// Сервер отдаёт AnonVPN/version/latest.json вида {"latest":"X.Y.Z"}.
// Если latest > EXT_VERSION – пишем в storage.updateAvailable; popup показывает баннер.
// В отличие от updateRequired (hard-block через proxy_list.php), этот флаг только уведомляет.
function compareSemver(a, b){
    const pa = String(a).split('.').map(n => parseInt(n,10));
    const pb = String(b).split('.').map(n => parseInt(n,10));
    for (let i = 0; i < 3; i++) {
        const ai = isFinite(pa[i]) ? pa[i] : 0;
        const bi = isFinite(pb[i]) ? pb[i] : 0;
        if (ai > bi) return 1;
        if (ai < bi) return -1;
    }
    return 0;
}
async function checkLatestVersion(){
    try {
        const res = await apiFetch(LATEST_VERSION_PATH + '?t=' + Date.now(), {
            cache: 'no-store',
            signal: AbortSignal.timeout(10000)
        });
        if (!res.ok) return;
        const data = await res.json();
        const latest = data && typeof data.latest === 'string' ? data.latest.trim() : '';
        if (!/^\d+\.\d+\.\d+$/.test(latest)) return;
        if (compareSemver(latest, EXT_VERSION) > 0) {
            await chrome.storage.local.set({ updateAvailable: latest });
            logDiag('update', 'available', { latest });
        } else {
            // Мы current или новее – чистим флаг (иначе застрянет после обновления)
            await chrome.storage.local.remove(['updateAvailable', 'updateAvailableDismissed']);
        }
    } catch { /* silent – не критично */ }
}

// [v2.8.5] Адресные сообщения от администратора. Popup при открытии шлёт getUserMessages;
// SW HMAC-подписывает запрос (UID в подписанном заголовке) → AnonVPN/user-messages.php.
// Некритичная фича – при любой ошибке возвращаем {ok:false}, popup просто не покажет
// админ-сообщения (предупреждение об окончании ключа считается клиентом отдельно).
async function getUserMessages(readIds) {
    let h;
    try { h = await buildHmacHeaders(); } catch (e) { return { ok: false, reason: 'hmac_err' }; }
    var payload = { uid: h.uid };
    // readIds – id админ-сообщений для отметки прочитанными (read-receipt). Сервер
    // помечает их read_at (idempotent) и всё равно вернёт актуальный список сообщений.
    if (Array.isArray(readIds) && readIds.length) {
        payload.read = readIds.filter(function(x){ return typeof x === 'number' && isFinite(x); }).slice(0, 50);
    }
    let res;
    try {
        res = await apiFetch('/AnonVPN/user-messages.php', {
            method: 'POST',
            headers: h.headers,
            body: JSON.stringify(payload),
            cache: 'no-store',
            signal: AbortSignal.timeout(10000)
        });
    } catch (e) { return { ok: false, reason: 'network' }; }
    if (!res.ok) return { ok: false, reason: 'http_' + res.status };
    let data;
    try { data = await res.json(); } catch (e) { return { ok: false, reason: 'bad_json' }; }
    if (!data || data.ok !== true || !Array.isArray(data.messages)) {
        return { ok: false, reason: (data && data.reason) || 'bad_response' };
    }
    return { ok: true, messages: data.messages };
}

// [v2.4.1] Credential cache
let cachedCredentials = null;
function updateCredentialCache(proxy) {
    cachedCredentials = (proxy && proxy.username) ? { username: proxy.username, password: proxy.password } : null;
}

// Load credentials ASAP on SW startup
chrome.storage.local.get(['selectedProxy'], d => {
    if (d.selectedProxy) updateCredentialCache(d.selectedProxy);
});

// [v2.5.9] Diagnostic log – ring buffer for support debugging.
// NOT for routine observability. Logged events:
//   • net.proxy_list_{start,ok,err}  – proxy list fetch attempts
//   • blocked.{version,ext_id}        – server-initiated blocks
//   • timer.expired                   – free session ended
//   • lifecycle.{install,update,wake} – SW lifecycle events
//   • toggle.{on,off,fail}            – VPN toggle outcomes
// NEVER logs: premium keys, proxy credentials, full UIDs (truncated to 10 chars).
//
// Serialized through a promise queue – prevents race conditions when multiple
// logDiag calls fire concurrently (e.g. alarm during in-flight fetch). Without
// serialization, concurrent read-modify-writes on diagnosticLog storage key
// would drop entries (last-writer-wins with stale snapshot).
const DIAG_LOG_MAX = 100;
let _logDiagQueue = Promise.resolve();
function logDiag(category, event, data) {
    // [v2.7.1 fix F92] .catch на chain – symmetric с другими 5 очередями
    // (_heartbeatQueue, _autoEnableQueue, _vpnStatsQueue, _dnrSyncQueue, _applyPremiumStateQueue).
    // Inner try/catch уже покрывает storage errors, но catch на chain – defense-in-depth
    // против будущего рефактора, где async-callback может бросить unhandled rejection.
    _logDiagQueue = _logDiagQueue.then(async () => {
        try {
            const d = await chrome.storage.local.get(['diagnosticLog']);
            const log = Array.isArray(d.diagnosticLog) ? d.diagnosticLog : [];
            const now = Math.floor(Date.now() / 1000);
            // [v2.8.6] Коалесцируем «шумные» lifecycle-события (частые перезапуски SW
            // sw_start + пропуск фонового рефреша по TTL bg_skipped_ttl). Без этого
            // 30+ минут churn'а SW забивали весь ринг-буфер на 100 записей, вытесняли
            // полезные события – диагностический лог становился бесполезным для поддержки.
            // Подряд идущие шумные события сворачиваются в одну запись lifecycle.churn
            // со счётчиком n; первое же НЕшумное событие снова открывает обычную запись.
            const isNoisy = (category === 'lifecycle' && event === 'sw_start')
                         || (category === 'net' && event === 'bg_skipped_ttl');
            const last = log.length ? log[log.length - 1] : null;
            if (isNoisy && last && last.c === 'lifecycle' && last.e === 'churn') {
                last.t = now;
                last.d = last.d || {};
                last.d.n = (last.d.n || 1) + 1;
            } else if (isNoisy) {
                log.push({ t: now, c: 'lifecycle', e: 'churn', d: { n: 1 } });
            } else {
                log.push({ t: now, c: category, e: event, d: data || null });
            }
            while (log.length > DIAG_LOG_MAX) log.shift();
            await chrome.storage.local.set({ diagnosticLog: log });
        } catch { /* ignore – logging must never break primary flow */ }
    }).catch(() => {});
    return _logDiagQueue;
}

// [v2.6.5 audit] Serialize get→mutate→set sequences to prevent lost updates when
// multiple events fire concurrently (nav events for different domains; timer alarm +
// user toggle at the same moment).
let _autoEnableQueue = Promise.resolve();
let _vpnStatsQueue = Promise.resolve();

// [v2.6.5 audit r3] In-memory cache для fast-path auto-enable check. Без этого каждая
// навигация/переключение таба (частые события) делали 5-key storage.get – для 99%
// юзеров без настроенных доменов это впустую жжёт I/O. Обновляется при старте SW
// и через storage.onChanged.
// [v2.6.5 audit r4] Serialize refresh через очередь – при быстрых подряд onChanged'ах
// (bulk-импорт доменов) promises могут резолвнуться out-of-order и оставить stale-данные.
let _autoEnableCache = { enabled: null, domains: null };
let _autoEnableRefreshQueue = Promise.resolve();
function _refreshAutoEnableCache() {
    _autoEnableRefreshQueue = _autoEnableRefreshQueue.then(async () => {
        try {
            const d = await chrome.storage.local.get(['autoEnableEnabled', 'autoEnableDomains']);
            _autoEnableCache.enabled = d.autoEnableEnabled !== false;
            _autoEnableCache.domains = Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : [];
        } catch {
            _autoEnableCache.enabled = null;
            _autoEnableCache.domains = null;
        }
    }).catch(() => {});
    return _autoEnableRefreshQueue;
}
_refreshAutoEnableCache();

// [v2.6.5 audit r7] DNR-based auto-enable intercept. Event-based tier 1/2/3 срабатывают
// поздно в Yandex Browser и ряде Chromium-форков – к моменту события браузер уже начал
// TCP к прямому IP заблокированного домена, и пользователь ждёт timeout. DNR-правила
// применяются на сетевом слое ДО DNS – единственный способ перехватить навигацию
// заранее в любом MV3-совместимом браузере.
const AE_DNR_RULE_ID_START = 3000;
const AE_DNR_RULE_ID_END = 3999;
const AE_DNR_MAX_DOMAINS = 500;
// [v3.1.1 audit] Множество bare-доменов, РЕАЛЬНО покрытых DNR-редиректом (tier-0 → ae-gate).
// Для них tier-1/2 (beforenav/request) избыточны – gate обрабатывает плавнее (location.replace
// без about:blank-мелькания, pre-empt DNS). Заполняется ТОЛЬКО после успешной установки DNR-правил
// (единый источник истины), чтобы tier-1/2 могли уступить. Домены за cap-ом (501+) остаются на tier-1/2/3.
let _dnrCoveredDomains = new Set();
let _dnrSyncQueue = Promise.resolve();
function syncAutoEnableDnrRules() {
    _dnrSyncQueue = _dnrSyncQueue.then(async () => {
        try {
            const d = await chrome.storage.local.get(['proxyEnabled', 'autoEnableEnabled', 'autoEnableDomains', 'isPremium']);
            const shouldActivate = !d.proxyEnabled
                && !!d.isPremium
                && d.autoEnableEnabled !== false
                && Array.isArray(d.autoEnableDomains)
                && d.autoEnableDomains.length > 0;
            const existing = await chrome.declarativeNetRequest.getDynamicRules();
            const oldIds = existing
                .filter(r => r.id >= AE_DNR_RULE_ID_START && r.id <= AE_DNR_RULE_ID_END)
                .map(r => r.id);
            if (!shouldActivate) {
                _dnrCoveredDomains = new Set(); // DNR неактивен → tier-1/2 снова обрабатывают всё
                if (oldIds.length) {
                    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: oldIds });
                    logDiag('autoEnable', 'dnr_removed', { count: oldIds.length });
                }
                return;
            }
            const gateUrl = chrome.runtime.getURL('ae-gate.html');
            // [v2.6.9] Defense-in-depth: явный Array.isArray-guard на случай рефактора shouldActivate
            const domains = (Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : []).slice(0, AE_DNR_MAX_DOMAINS);
            // [v2.7.0 fix F25] Filter ДО enumerate – иначе ASCII-fail domain создавал gap
            // в rule-ids, при re-sync oldIds получал меньше чем addIds ставит, orphan-rules
            // накапливались. Теперь валидные domains получают contiguous ids.
            const validDomains = domains
                .map(dom => String(dom).toLowerCase().replace(/^www\./, ''))
                .filter(bare => /^[a-z0-9.-]+$/.test(bare));
            const newRules = validDomains.map((bare, idx) => {
                const escaped = bare.replace(/\./g, '\\.');
                return {
                    id: AE_DNR_RULE_ID_START + idx,
                    priority: 100,
                    action: { type: 'redirect', redirect: { regexSubstitution: gateUrl + '#\\0' } },
                    condition: {
                        regexFilter: '^https?://([^/]+\\.)*' + escaped + '(/.*)?$',
                        resourceTypes: ['main_frame']
                    }
                };
            });
            await chrome.declarativeNetRequest.updateDynamicRules({
                removeRuleIds: oldIds,
                addRules: newRules
            });
            // [v3.1.1 audit] Только ПОСЛЕ успешной установки – ровно те домены, что DNR редиректит.
            // Если updateDynamicRules бросит выше, set не обновится (старое состояние валидно –
            // updateDynamicRules атомарен: при throw ни add, ни remove не применились).
            _dnrCoveredDomains = new Set(validDomains);
            logDiag('autoEnable', 'dnr_active', { count: newRules.length });
        } catch (e) {
            logDiag('autoEnable', 'dnr_err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
        }
    }).catch(() => {});
    return _dnrSyncQueue;
}
// Sync at SW start
syncAutoEnableDnrRules();

// Log SW wake up (fires on cold start + every SW restart)
logDiag('lifecycle', 'sw_start', { ver: EXT_VERSION });

// [v2.5.9 → v2.9.1] Auto-select сервер. Scope игнорируется для free (forced to 'free').
// excluded – массив 'host:port'.
// [v2.9.1] method/pings опциональные. method ∈ {'load','ping','both'} (default 'load').
//   load: min users (как в 2.5.9).
//   ping: min ms (свежие ≤24ч). Сервер без свежего пинга = Infinity → выбран последним.
//   both: normalized combo (0.5*users/LIMIT + 0.5*ms/600). Если ping нет – fallback на users.
// pings: {[host:port]: {ms:number, ts:timestamp_ms}}.
function pickBestServer(list, scope, isPremium, stats, excluded, method, pings, favorites) {
    if (!Array.isArray(list) || list.length === 0) return null;
    stats = stats || {};
    excluded = excluded || [];
    pings = (pings && typeof pings === 'object' && !Array.isArray(pings)) ? pings : {};
    method = (method === 'ping' || method === 'both') ? method : 'load';
    const PING_TTL_MS = 24 * 60 * 60 * 1000;
    const now = Date.now();
    const freeList = list.filter(p => p.type !== 'premium');
    const premList = list.filter(p => p.type === 'premium');
    let pool;
    if (!isPremium) pool = freeList;
    else if (scope === 'premium') pool = premList.length ? premList : freeList;
    else if (scope === 'all') pool = list;
    else pool = freeList.length ? freeList : list; // 'free' (default)
    // Remove user-excluded servers
    if (excluded.length) {
        pool = pool.filter(p => excluded.indexOf(p.host + ':' + p.port) < 0);
    }
    if (pool.length === 0) return null;
    // [v3.1.5 audit] shuffle НА КОПИИ: при scope 'all' (premium) или free-fallback без exclusions pool
    // алиасит module-level serverList (передан как list) → in-place Fisher-Yates мутировал бы его порядок,
    // сдвигая list[0]/find-фолбэки в applySelectedProxy. .filter выше копирует только при excluded.length.
    pool = pool.slice();
    // [v3.0.4] Random tie-break: при РАВНЫХ score (напр. stats пустые/недоступны – у всех load=0)
    // не берём детерминированно pool[0], иначе ВСЕ юзеры без нагрузки садятся на первый сервер
    // списка (корень «стада»). Шафл → среди равных выбирается случайный → нагрузка размазывается.
    // При реальных данных уникальный min-load всё равно побеждает (порядок не важен).
    for (let _s = pool.length - 1; _s > 0; _s--) {
        const _r = Math.floor(Math.random() * (_s + 1));
        const _tmp = pool[_s]; pool[_s] = pool[_r]; pool[_r] = _tmp;
    }
    // [v3.1.2] Scoring по method вынесен в под-функцию – чтобы прогнать сначала на избранных,
    // затем на полном пуле.
    const _pickFrom = (candidates) => {
        let best = null, bestScore = Infinity;
        for (const p of candidates) {
            // [v2.8.1] cachedServerStats indexed by host:port – стабильный ключ.
            const _sk = _serverKey(p);
            const users = _sk ? (Number(stats[_sk]) || 0) : 0;
            // [v2.7.3 audit] free-юзерам нельзя auto-select'ом на перегруженный free-сервер (>= LIMIT).
            if (!isPremium && p.type !== 'premium' && users >= FREE_LOAD_LIMIT) continue;
            // [v2.9.1] Свежий ping (≤24ч) или Infinity (load работает; ping/both fallback).
            let ms = Infinity;
            if (_sk && pings[_sk] && typeof pings[_sk].ms === 'number' && pings[_sk].ms > 0 &&
                typeof pings[_sk].ts === 'number' && (now - pings[_sk].ts) < PING_TTL_MS) {
                ms = pings[_sk].ms;
            }
            let score;
            if (method === 'ping') {
                // [audit fix critical-1] ping-mode пропускает серверы без свежего пинга (иначе random).
                if (!Number.isFinite(ms)) continue;
                score = ms;
            } else if (method === 'both') {
                const usersN = users / FREE_LOAD_LIMIT;
                // [2026-06-29] Штраф +100 беспинговому: пинганутые впереди (score<2), среди беспинговых – по нагрузке.
                if (!Number.isFinite(ms)) score = usersN + 100;
                else score = 0.5 * usersN + 0.5 * (Math.min(ms, 1500) / 600);
            } else {
                score = users; // 'load' – backward compat
            }
            if (score < bestScore) { bestScore = score; best = p; }
        }
        return best;
    };
    // [v3.1.2] Приоритет избранных: если у юзера есть избранные, сначала выбираем лучший из тех
    // избранных, что попали в pool (доступны по scope, не excluded). Если среди них никто не подошёл
    // (нет/перегружены/в ping-mode без пинга) – выбираем из полного пула. Fallback обязателен –
    // иначе юзер с «мёртвыми»/перегруженными избранными остался бы без сервера.
    if (Array.isArray(favorites) && favorites.length) {
        const _favSet = new Set(favorites);
        const favPool = pool.filter(p => _favSet.has(p.host + ':' + p.port));
        if (favPool.length) {
            const favBest = _pickFrom(favPool);
            if (favBest) return favBest;
        }
    }
    return _pickFrom(pool);
}

// [v3.0.3] SW тянет ЖИВУЮ статистику нагрузки САМ. Раньше и auto-select, и load-guard
// читали cachedServerStats, который наполняет ТОЛЬКО popup. Юзер, подключающийся через
// Alt+Shift+V или на чистой установке (popup не открывал), имел ПУСТОЙ cachedServerStats →
// pickBestServer видел у всех users=0 → исключение ≥75 не срабатывало → брался ПЕРВЫЙ
// сервер n_proxies.txt, и load-guard его не блокировал. Итог: 140+ free-юзеров на одном
// сервере (первом в списке). Тот же live-эндпоинт, что у popup (apiFetch + failover по
// API_DOMAINS). In-memory кэш 60с (частые toggle не спамят), fail-open (сбой фетча НЕ
// ломает toggle – возвращаем last-known/null, дальше fallback на cachedServerStats).
let _swServerStats = null;
let _swServerStatsAt = 0;
const SW_SERVER_STATS_TTL_MS = 60 * 1000;
async function fetchServerStatsSW() {
    const age = Date.now() - _swServerStatsAt;
    if (_swServerStats && age >= 0 && age < SW_SERVER_STATS_TTL_MS) return _swServerStats;
    try {
        const resp = await apiFetch('/AnonVPN/stats/server-stats.json?t=' + Date.now(), { cache: 'no-store', signal: AbortSignal.timeout(4000) }); // [v3.0.4] 2500→4000: 2.5с мало для failover по 5 доменам (первый медленный → аборт до 2-го) → чаще пустые stats → пробой блока. Кэш 60с/guard reuse → одна такая задержка на toggle.
        if (resp && resp.ok) {
            const data = await resp.json();
            if (data && typeof data === 'object' && !Array.isArray(data)) {
                _swServerStats = data;
                _swServerStatsAt = Date.now();
                // Делимся свежими данными с popup/guard через общий ключ.
                chrome.storage.local.set({ cachedServerStats: data, cachedServerStatsAt: Date.now() }, function(){ if (chrome.runtime && chrome.runtime.lastError) { /* ignore */ } });
                return _swServerStats;
            }
        }
    } catch (e) {
        try { logDiag('auto-select', 'sw_stats_fetch_fail', { msg: String((e && e.message) || e).slice(0, 60) }); } catch(_){}
    }
    return _swServerStats; // last-known (может быть null) – fail-open, НЕ блокируем toggle
}

// [v3.0.3] Транзиентный набор серверов, чей туннель только что оказался сломан (ipify через
// прокси упал – ERR_TUNNEL_CONNECTION_FAILED). host:port→ts, TTL 5 мин. Auto-select их избегает.
const BROKEN_SERVER_TTL_MS = 5 * 60 * 1000;
// [v3.0.3] Storage-key `brokenServers` {host:port→ts} – ЕДИНЫЙ источник: SW пишет (rescue),
// popup читает (метка «не работает» в списке серверов) + триггерит rescue. Авто-prune по TTL 5 мин.
async function getBrokenServers(){
    const d = await chrome.storage.local.get(['brokenServers']);
    const bs = (d.brokenServers && typeof d.brokenServers === 'object' && !Array.isArray(d.brokenServers)) ? d.brokenServers : {};
    const now = Date.now(); let changed = false;
    for (const k in bs){ if (now - bs[k] > BROKEN_SERVER_TTL_MS){ delete bs[k]; changed = true; } }
    if (changed){ try { await chrome.storage.local.set({ brokenServers: bs }); } catch (e) {} }
    return bs;
}
async function markServerBroken(key){
    if (!key) return;
    const bs = await getBrokenServers();
    bs[key] = Date.now();
    try { await chrome.storage.local.set({ brokenServers: bs }); } catch (e) {}
}

// [v3.0.3] Проверка туннеля: ipify идёт ЧЕРЕЗ прокси (НЕ в bypass) → сломанный сервер даёт
// fetch-reject (ERR_TUNNEL_CONNECTION_FAILED) или не-IP. 1 ретрай через 1.5с (как popup loadIpInfo).
// [v3.1.4 hotfix] Определить exit-IP через активный прокси-туннель. Пробуем HTTPS И HTTP
// ПАРАЛЛЕЛЬНО, берём первый валидный IP. Причина двух схем: на части платформ (Android/Kiwi 137,
// возможно macOS) SW-fetch HTTPS через прокси-CONNECT не получает Proxy-Authorization → падает
// даже на ЖИВОМ туннеле (кейс Kiwi: swTunnelReachable ложно false → rescue churn'ил рабочие
// серверы, «подбираем рабочий…»). HTTP-GET через прокси DNR-авторизуется надёжно везде. Параллель,
// а не последовательный фолбэк – чтобы не удваивать задержку на рабочем VPN. IP-строка или null.
function _fetchTunnelExitIp(timeoutMs){
    timeoutMs = timeoutMs || 10000;
    return new Promise(function(resolve){
        var pending = 2, settled = false;
        function fin(ip){
            if (settled) return;
            if (ip){ settled = true; resolve(ip); }
            else if (--pending === 0){ resolve(null); }
        }
        function tryUrl(url){
            fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(timeoutMs) })
                .then(function(r){ return (r && r.ok) ? r.json() : null; })
                .then(function(d){ fin(d && typeof d.ip === 'string' && d.ip.trim() ? d.ip.trim() : null); })
                .catch(function(){ fin(null); });
        }
        tryUrl('https://api.ipify.org?format=json');
        tryUrl('http://api.ipify.org?format=json');
    });
}

async function swTunnelReachable(attempts, timeoutMs){
    // [v3.0.5] Параметризовано. [v3.1.0 FIX регресс, чат #614] Тайминги УВЕЛИЧЕНЫ: медленные-но-ЖИВЫЕ
    // серверы на Win7/Chrome 109 не успевали ответить за короткий таймаут (4-8с) и ложно метились битыми
    // → накапливались в brokenServers → у юзера «работает только 1 сервер». Дефолт 2/10000; rescue-цикл
    // зовёт (2, 10000) вместо (1, 4000) – даём медленным серверам 10с и 2 попытки.
    attempts = attempts || 2;
    timeoutMs = timeoutMs || 10000;
    for (let attempt = 0; attempt < attempts; attempt++){
        // [v3.1.4 hotfix] HTTPS+HTTP параллельно (Kiwi/Android: HTTPS через прокси-CONNECT из SW
        // ложно падает на живом туннеле → churn). Достаточно любой схемы с валидным IP.
        const _ip = await _fetchTunnelExitIp(timeoutMs);
        if (_ip) return true;
        if (attempt < attempts - 1) { await new Promise(function(res){ setTimeout(res, 1500); }); }
    }
    return false;
}

// [v3.0.3] Подбор рабочего сервера, исключая сломанный + broken-set + user-exclusions, по живой
// нагрузке. null если альтернатив нет (все перегружены/исключены/сломаны).
async function swPickExcludingBroken(brokenKey){
    const list = Array.isArray(serverList) && serverList.length ? serverList : [];
    if (!list.length) return null;
    const data = await chrome.storage.local.get(['isPremium','autoSelectScope','excludedFromAutoSelect','favoriteServers']);
    const isPremium = !!data.isPremium;
    const scope = isPremium ? (data.autoSelectScope || 'free') : 'free';
    const excluded = Array.isArray(data.excludedFromAutoSelect) ? data.excludedFromAutoSelect.slice() : [];
    const _bs = await getBrokenServers();
    for (const k in _bs){ if (excluded.indexOf(k) < 0) excluded.push(k); }
    if (brokenKey && excluded.indexOf(brokenKey) < 0) excluded.push(brokenKey);
    const stats = (await fetchServerStatsSW()) || {};
    // [v3.1.2] Замену сломанному серверу тоже ищем сначала среди избранных (сломанный уже в excluded).
    const favorites = Array.isArray(data.favoriteServers) ? data.favoriteServers : [];
    const picked = pickBestServer(list, scope, isPremium, stats, excluded, 'load', {}, favorites);
    if (picked && _serverKey(picked) === brokenKey) return null;
    return picked || null;
}

// [v3.0.3] Браузерное уведомление с i18n (как freeBlocked-нотификация). Fallback ru.
async function swNotifyI18n(idPrefix, titleKey, msgKey, fbTitle, fbMsg){
    try {
        const d = await chrome.storage.local.get(['language','cachedTranslationsData']);
        const lang = d.language || 'ru';
        const dd = d.cachedTranslationsData || {};
        const tr = dd[lang] || dd.en || {};
        const tEn = dd.en || {};
        const title = tr[titleKey] || tEn[titleKey] || fbTitle;
        const msg = tr[msgKey] || tEn[msgKey] || fbMsg;
        chrome.notifications.create(idPrefix + '_' + Date.now(), {
            type: 'basic', iconUrl: '/icons/AnonVPN128.png', title: title, message: msg, priority: 1
        }).catch(function(){});
    } catch (e) {}
}

// [v3.0.3] Проверка туннеля + (если авто-выбор ВКЛ) авто-смена сервера при сломе. ОБЩАЯ для:
//  - hotkey (onCommand, notify=true → браузерное уведомление, popup закрыт);
//  - popup (message 'rescueTunnel', notify=false → popup сам показывает статус).
// ⚠ Если авто-выбор ВЫКЛЮЧЕН (юзер вручную закрепил сервер) – НЕ переключаем, уважаем выбор:
// только помечаем broken (→ метка ✕) + сообщаем «смените вручную». Иначе – цикл: берём следующий
// рабочий, ПЕРЕПРОВЕРЯЕМ, до рабочего или MAX_SWITCHES. Сломанные fail-fast (ERR_TUNNEL). Мьютекс.
// Возврат {ok, switched, manual, busy}. Смена = set selectedProxy → onChanged переподключает.
// [v3.0.3] Step-guarded disconnect VPN (как handleVersionBlocked / VPN_ALARM / checkPremiumExpiration):
// КАЖДЫЙ шаг в своём try/catch – throw в одном НЕ должен оставить proxyEnabled=true = unlimited VPN
// (прецедент v2.6.10). Снимает прокси, ТАЙМЕР сессии (clearVpnTimer), heartbeat, keepalive, иконку.
// Зовётся из rescue когда рабочий туннель установить НЕ удалось – чтобы таймер не тикал на битом
// подключении и ВПН не висел «включённым» вхолостую.
async function swDisconnectVpn(reason){
    if (!(await isProxyEnabled())) return;
    cachedCredentials = null;
    try { await recordSessionEnd(); } catch {}
    try { await chrome.storage.local.set({ proxyEnabled: false }); } catch {}
    try { await setProxy(false); } catch {}
    try { updateIcon(false); } catch {}
    try { await clearVpnTimer(); } catch {}
    try { stopHeartbeat(); } catch {}
    try { sendDisconnect(reason).catch(function(){}); } catch {}
    try { stopKeepalive(); } catch {}
    try { chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: false, reason: reason }).catch(function(){}); } catch {}
}

let _rescueInProgress = false;
async function verifyAndRescueTunnel(opts){
    opts = opts || {};
    const notify = opts.notify !== false; // default true (hotkey)
    if (_rescueInProgress) return { ok: null, busy: true };
    _rescueInProgress = true;
    try {
        // 1. Туннель работает?
        if (await swTunnelReachable()) return { ok: true, switched: false };
        // 2. Сломан → помечаем текущий сервер broken (→ метка ✕ в popup), в т.ч. в ручном режиме.
        const st = await chrome.storage.local.get(['selectedProxy', 'autoSelectServer']);
        let brokenKey = (st.selectedProxy && st.selectedProxy.host) ? _serverKey(st.selectedProxy) : '';
        if (brokenKey) await markServerBroken(brokenKey);
        logDiag('toggle', 'tunnel_broken', { sk: brokenKey, auto: st.autoSelectServer !== false });
        // 3. Авто-выбор ВЫКЛ → НЕ переключаем (юзер закрепил сервер сам). Только сообщаем.
        if (st.autoSelectServer === false) {
            if (notify) swNotifyI18n('ipbroken_manual', 'ipBrokenTitle', 'ipBrokenManual',
                'Сервер не отвечает', 'Выбранный сервер не отвечает. Выберите другой или включите «Автовыбор сервера».');
            await swDisconnectVpn('tunnel_manual'); // ручной закреп битого сервера – не переключаем, но выключаем (таймер не тикает на битом)
            return { ok: false, manual: true, switched: false };
        }
        // 4. Авто-выбор ВКЛ → перебираем серверы ДО рабочего ИЛИ пока не кончится весь список.
        // [v3.0.5] Убран фикс-кап 6 (юзер: доходить до рабочего, даже если он дальше 6-го). Цикл
        // завершается сам: swPickExcludingBroken исключает ВЕСЬ broken-set → пул сжимается каждую
        // итерацию → picked=null, когда все помечены битыми. MAX = размер пула + буфер – это лишь
        // safety-cap от бесконечного цикла (если markServerBroken тихо не запишется), не рабочий лимит.
        const _poolN = (Array.isArray(serverList) ? serverList.length : 0);
        const MAX_SWITCHES = Math.min(120, (_poolN > 0 ? _poolN : 20) + 3);
        // [v3.0.5] Тайм-бюджет – ОБЯЗАТЕЛЬНАЯ страховка от MV3 SW-kill (~5мин hard-лимит): rescue
        // await-ится, Chrome держит SW живым, но если перебор длиннее лимита – SW убьют посреди,
        // оставив proxyEnabled=true на битом сервере. Fast-fail пул целиком влезает (<2мин); при
        // silent-drop DPI бюджет обрывает на ~30 серверах – но 30 разных подряд битых = 100% DPI,
        // остальные тоже мертвы, продолжать бессмысленно.
        const _rescueStart = Date.now();
        const RESCUE_BUDGET_MS = 150000; // 2.5 мин – с запасом под MV3 5-мин лимит
        for (let i = 0; i < MAX_SWITCHES; i++){
            if (Date.now() - _rescueStart > RESCUE_BUDGET_MS){
                logDiag('toggle', 'tunnel_budget', { tried: i, ms: Date.now() - _rescueStart });
                if (notify) swNotifyI18n('ipbroken_no', 'ipBrokenTitle', 'ipBrokenNoServer',
                    'Сервер не отвечает', 'Сервер не отвечает, других доступных нет. Попробуйте позже или смените сервер вручную.');
                await swDisconnectVpn('tunnel_no_server'); // тайм-бюджет исчерпан (всё битое) → выключаем ВПН
                return { ok: false, switched: i > 0 };
            }
            // [v3.0.5] Юзер выключил ВПН посреди перебора → прекращаем (иначе set selectedProxy ниже
            // переподключит прокси поверх его OFF). Окно перебора теперь до 2.5мин – проверка важна.
            if (!(await isProxyEnabled())){ logDiag('toggle', 'tunnel_abort_off', { tried: i }); return { ok: false, aborted: true }; }
            const picked = await swPickExcludingBroken(brokenKey);
            if (!picked){
                logDiag('toggle', 'tunnel_no_alt', { tried: i });
                if (notify) swNotifyI18n('ipbroken_no', 'ipBrokenTitle', 'ipBrokenNoServer',
                    'Сервер не отвечает', 'Сервер не отвечает, других доступных нет. Попробуйте позже или смените сервер вручную.');
                await swDisconnectVpn('tunnel_no_server'); // весь список пройден, рабочих нет → выключаем ВПН
                return { ok: false, switched: i > 0 };
            }
            // [v3.0.5] Прогресс перебора → popup (длинный перебор не выглядит зависшим спиннером).
            try { chrome.runtime.sendMessage({ action: 'rescueProgress', tried: i + 1, max: MAX_SWITCHES }).catch(function(){}); } catch (ePg) {}
            await chrome.storage.local.set({ selectedProxy: picked }); // onChanged → setProxy reconnect
            await new Promise(function(res){ setTimeout(res, 1200); }); // дать переподключению примениться
            // [v3.1.0 FIX] Прайм авторизации кандидата ПЕРЕД проверкой. На Chrome 109 onAuthRequired
            // для CONNECT надёжно срабатывает только при загрузке страницы во вкладке – без прайма
            // swTunnelReachable (SW-fetch) на новом сервере ловит 407 → ЖИВОЙ сервер метится битым →
            // rescue churn'ит весь пул → у юзера «работает только 1 сервер» (кейс Анастасии). Прайм
            // (фоновая вкладка на HTTPS, гейт <116 внутри openWarmupPage) кэширует пароль → честная проверка.
            try { await openWarmupPage(); } catch (ePrime) {}
            if (await swTunnelReachable(2, 10000)){ // [v3.1.0 FIX #614] 2 попытки/10с – (1/4с) ложно метила живые-но-медленные серверы битыми (Win7/Chrome109)
                logDiag('toggle', 'tunnel_rescued', { switches: i + 1 });
                if (notify) swNotifyI18n('ipbroken_sw', 'ipBrokenTitle', 'ipBrokenSwitched',
                    'Сервер не отвечал', 'Выбранный сервер не отвечал – мы переключили вас на другой рабочий сервер.');
                return { ok: true, switched: true };
            }
            // picked тоже сломан → помечаем, следующая итерация (исключится из swPickExcludingBroken).
            brokenKey = _serverKey(picked);
            await markServerBroken(brokenKey);
            logDiag('toggle', 'tunnel_broken', { sk: brokenKey, attempt: i + 1 });
        }
        logDiag('toggle', 'tunnel_exhausted', { cap: MAX_SWITCHES });
        if (notify) swNotifyI18n('ipbroken_no', 'ipBrokenTitle', 'ipBrokenNoServer',
            'Сервер не отвечает', 'Сервер не отвечает, других доступных нет. Попробуйте позже или смените сервер вручную.');
        await swDisconnectVpn('tunnel_no_server'); // safety-cap (пул слишком большой) → выключаем ВПН
        return { ok: false, switched: true };
    } finally {
        _rescueInProgress = false;
    }
}

// [v2.5.9] Called from doToggleProxy BEFORE proxyEnabled=true, so the storage.onChanged
// handler skips re-entry (it checks isProxyEnabled, which is still false at this point).
async function maybeAutoSelectServer() {
    const data = await chrome.storage.local.get([
        'autoSelectServer', 'autoSelectScope', 'isPremium',
        'selectedProxy', 'cachedServerStats', 'excludedFromAutoSelect',
        // [v2.9.1] метод выбора + кэш пингов
        // [v2.9.2 critical fix] +checkerLastResults – auto-select игнорировал пинги из
        // «Проверка серверов» (Premium-tab), читая только bulk-ping-store serverPings.
        'autoSelectMethod', 'serverPings', 'checkerLastResults',
        // [v3.1.2] избранные серверы – приоритет в auto-select
        'favoriteServers'
    ]);
    if (data.autoSelectServer === false) return;
    const list = Array.isArray(serverList) && serverList.length ? serverList : [];
    if (list.length === 0) return;
    const isPremium = !!data.isPremium;
    const scope = isPremium ? (data.autoSelectScope || 'free') : 'free';
    const method = (data.autoSelectMethod === 'ping' || data.autoSelectMethod === 'both') ? data.autoSelectMethod : 'ping';
    // [v2.9.2 critical fix] Merge оба источника пингов (bulk-ping + checker-tab).
    // На конфликт по host:port побеждает более свежий по ts. Без merge – auto-select
    // не видел пингов из checker-tab и юзер залипал на load-fallback.
    const _bulkPings = (data.serverPings && typeof data.serverPings === 'object' && !Array.isArray(data.serverPings)) ? data.serverPings : {};
    const pings = {};
    const _clr = data.checkerLastResults;
    if (_clr && _clr.ping && _clr.ping.results) {
        Object.keys(_clr.ping.results).forEach(k => {
            const r = _clr.ping.results[k];
            if (!r || !r.hp) return;
            const ms = parseInt(r.text, 10);
            if (isNaN(ms) || ms <= 0) return;
            pings[r.hp] = { ms: ms, ts: r.ts || 0 };
        });
    }
    Object.keys(_bulkPings).forEach(hp => {
        const sp = _bulkPings[hp];
        if (!sp || typeof sp.ms !== 'number' || sp.ms <= 0) return;
        const ex = pings[hp];
        if (!ex || (Number(sp.ts) || 0) > (Number(ex.ts) || 0)) {
            pings[hp] = { ms: sp.ms, ts: sp.ts || 0 };
        }
    });
    // [v3.0.3] ЖИВАЯ нагрузка из SW-фетча (не пустой popup-кэш – корень бага «все на первом
    // сервере»). Fallback: cachedServerStats → {}.
    let stats = {};
    const _liveStats = await fetchServerStatsSW();
    if (_liveStats && typeof _liveStats === 'object' && !Array.isArray(_liveStats)) {
        stats = _liveStats;
    } else if (data.cachedServerStats && typeof data.cachedServerStats === 'object' && !Array.isArray(data.cachedServerStats)) {
        stats = data.cachedServerStats;
    }
    const excluded = Array.isArray(data.excludedFromAutoSelect) ? data.excludedFromAutoSelect.slice() : [];
    // [v3.0.3] Избегаем недавно-сломанных серверов (туннель упал на проверке, TTL 5 мин).
    const _bsMap = await getBrokenServers();
    for (const _bk in _bsMap){ if (excluded.indexOf(_bk) < 0) excluded.push(_bk); }
    // [v3.1.2] Избранные серверы (host:port) – pickBestServer выберет сначала из них.
    const favorites = Array.isArray(data.favoriteServers) ? data.favoriteServers : [];
    let picked = pickBestServer(list, scope, isPremium, stats, excluded, method, pings, favorites);
    const pingsFreshCount = Object.keys(pings).filter(k => pings[k] && typeof pings[k].ms === 'number' && pings[k].ms > 0 && typeof pings[k].ts === 'number' && (Date.now() - pings[k].ts) < (24*60*60*1000)).length;
    // [audit fix critical-1 → load fallback] Если ping mode не нашёл ни одного сервера
    // со свежим пингом – fallback на load. Иначе юзер останется на старом selected
    // (или random) и попадёт в ту же проблему: VPN включился на «случайный» server.
    if (!picked && method !== 'load') {
        logDiag('auto-select', 'fallback_to_load', { reason: 'no_fresh_pings', method: method, fresh_pings: pingsFreshCount });
        picked = pickBestServer(list, scope, isPremium, stats, excluded, 'load', {}, favorites);
    }
    if (!picked) {
        // [v3.0.3] Последняя попытка была load-методом (fallback выше / method='load' по умолчанию),
        // а он у free-юзера исключает ТОЛЬКО ≥75. Значит null при наличии free-серверов = ВСЕ
        // перегружены → сигналим вызывающему (doToggleProxy → hotkey покажет уведомление).
        // Premium ≥75 не исключает, так что его null = пустой список, не перегруз.
        if (!isPremium && list.some(function(p){ return p.type !== 'premium'; })) return 'all_overloaded';
        return;
    }
    // [v2.9.1] Лог выбора – пригодится в support chat
    const sk = _serverKey(picked);
    const pingMs = (pings[sk] && pings[sk].ms) ? pings[sk].ms : null;
    const users = stats[sk] ? Number(stats[sk]) : null;
    logDiag('auto-select', 'picked', { method: method, server: sk, country: picked.country || '', users: users, ping_ms: pingMs, fresh_pings: pingsFreshCount });
    const curr = data.selectedProxy;
    // [v2.8.5 audit R8] String()-coerce port – number/string variance after storage
    // roundtrip (same fix-class as v2.7.3 getServerLoadFor / popup-side comparisons).
    if (curr && curr.host === picked.host && String(curr.port) === String(picked.port)) return;
    await chrome.storage.local.set({ selectedProxy: picked });
}

// [v2.5.1] Warmup: silent fetch to prime proxy auth (no visible tab)
async function openWarmupPage() {
    // [v3.1.0 FIX Chrome 109-115] onAuthRequired для proxy-CONNECT на старом Chrome срабатывает
    // НАДЁЖНО только при загрузке страницы во ВКЛАДКЕ, а SW-fetch триггерит его непостоянно →
    // новый сервер не авторизуется → первый запрос юзера ловит 407 «IP недоступен / не подключается».
    // (Юзер подтвердил: ручное открытие https-страницы в момент подключения = сервер оживает.)
    // Праймим авторизацию активного прокси короткой фоновой вкладкой на HTTPS: она создаёт CONNECT →
    // onAuthRequired срабатывает → Chrome кэширует пароль прокси → дальнейший сёрфинг работает сразу.
    // Гейтим по версии: на новом Chrome (116+) desktop onAuthRequired и так надёжен → вкладка не нужна (без флэша).
    // [v3.1.4 hotfix] НО на Android-Chromium (Kiwi 137) onAuthRequired для SW/popup-fetch CONNECT НЕ
    // срабатывает даже на ≥116 (лог Кости: ERR_TUNNEL_CONNECTION_FAILED 407 на api.ipify.org из
    // popup.js:2926) → без прайм-вкладки первый через-прокси запрос ловит 407, «Сервер не отвечает,
    // подбираем рабочий…» крутится вечно. Открываем вкладку и на Android – как на Win7/Chrome 109.
    let chromeMajor = 999;
    let _isAndroid = false;
    try { const _ua = navigator.userAgent || ''; const _m = _ua.match(/Chrome\/(\d+)/); if (_m) chromeMajor = parseInt(_m[1], 10); _isAndroid = /Android/i.test(_ua); } catch (e0) {}
    // [v3.1.5] ОТКАЧЕНО: открытие прайм-вкладки для https-схемы. На современном Chrome вкладка на
    // https://cp.cloudflare.com сама триггерила окно пароля (креды ещё не в cachedCredentials на момент
    // её CONNECT), а через 3с удалялась → «окно пароля само пропадает» + возня съедала 10с-таймаут
    // коннекта → «сервер не отвечает». Возвращаемся к базовому гейту (Chrome<116/Android). Прайминг
    // https-нод надо решать иначе (не через видимую вкладку) — см. memory project_anonvpn_315_https_nodes.
    if (chromeMajor < 116 || _isAndroid) {
        try {
            const _tab = await chrome.tabs.create({ url: 'https://cp.cloudflare.com/', active: false });
            await new Promise(function (res) { setTimeout(res, 3000); }); // дать CONNECT + onAuthRequired отработать
            try { if (_tab && _tab.id != null) await chrome.tabs.remove(_tab.id); } catch (e1) {}
            return;
        } catch (eTab) { /* нет tabs API / отказ – падаем в fetch-фолбэк ниже */ }
    }
    // Новый Chrome или фолбэк: старый warm-up через SW-fetch (снижает latency первого запроса)
    try {
        await fetch('http://cp.cloudflare.com', {
            method: 'HEAD', cache: 'no-store', signal: AbortSignal.timeout(5000)
        });
    } catch(e) {}
}

// [v2.4.1] declarativeNetRequest – проактивный Proxy-Authorization заголовок
// Правило переживает сон service worker, браузер никогда не получает 407
const PROXY_AUTH_RULE_ID = 1;

async function setProxyAuthRule(proxy, extraExcludeDomains, onlyDomains) {
    try {
        await chrome.declarativeNetRequest.updateDynamicRules({
            removeRuleIds: [PROXY_AUTH_RULE_ID]
        });
    } catch(e) {}
    if (!proxy || !proxy.username || !proxy.password) return;
    // [v3.1.5 audit K1] DNR requestDomains/excludedRequestDomains требуют КАНОНИЧЕСКИЕ домены
    // (без схемы/пути/wildcard). Кривая запись из пользовательских исключений (напр. "*.foo.com",
    // "http://foo/bar", домен с пробелом) → updateDynamicRules throw → catch ниже снимал scoping и
    // переставлял правило с urlFilter:'*' → Proxy-Authorization (Basic user:pass) утекал на ВСЕ
    // DIRECT/bypass-сайты. Чистим и выбрасываем невалидные записи ЗАРАНЕЕ, чтобы throw не наступил.
    function _cleanDnrDomain(d) {
        if (typeof d !== 'string') return '';
        var s = d.toLowerCase().trim().replace(/^[a-z]+:\/\//, '').replace(/[\/?#].*$/, '').replace(/^\*\./, '').replace(/[^a-z0-9.\-]/g, '');
        s = s.replace(/^[.\-]+/, '').replace(/[.\-]+$/, '');
        return /^[a-z0-9]([a-z0-9.\-]*[a-z0-9])?$/.test(s) ? s : '';
    }
    try {
        const authValue = 'Basic ' + btoa(proxy.username + ':' + proxy.password);
        // [v2.5.4] Исключаем bypass-домены, чтобы не отправлять прокси-креденшелы на прямые соединения
        const excludeDomains = BYPASS_LIST
            .filter(d => d !== '<-loopback>')
            .map(d => d.replace(/^\*\./, '').toLowerCase());
        if (extraExcludeDomains && extraExcludeDomains.length > 0) {
            extraExcludeDomains.forEach(d => { const cd = _cleanDnrDomain(d); if (cd && excludeDomains.indexOf(cd) < 0) excludeDomains.push(cd); });
        }
        const cleanOnly = Array.isArray(onlyDomains) ? onlyDomains.map(_cleanDnrDomain).filter(Boolean) : onlyDomains;
        const rule = {
            id: PROXY_AUTH_RULE_ID,
            priority: 1,
            action: {
                type: 'modifyHeaders',
                requestHeaders: [{
                    header: 'Proxy-Authorization',
                    operation: 'set',
                    value: authValue
                }]
            },
            condition: {
                urlFilter: '*',
                resourceTypes: ['main_frame','sub_frame','stylesheet','script','image','font','xmlhttprequest','ping','media','websocket','other']
            }
        };
        if (Array.isArray(onlyDomains) && cleanOnly.length === 0) {
            // [v3.1.5 audit] Whitelist-режим с ПУСТЫМ списком: правило уже снято выше (removeRuleIds),
            // просто выходим → Proxy-Authorization не инжектится НИКУДА (совпадает с PAC: пустой whitelist
            // = всё DIRECT). Без этого пустой onlyDomains проваливался в else-ветку → инжект на '*' →
            // креды прокси (Basic) утекали на сторонние сайты, роутящиеся напрямую.
            return;
        }
        if (cleanOnly && cleanOnly.length > 0) {
            // Whitelist: отправлять ТОЛЬКО на эти домены
            rule.condition.requestDomains = cleanOnly;
        } else if (excludeDomains.length > 0) {
            rule.condition.excludedRequestDomains = excludeDomains;
        }
        try {
            await chrome.declarativeNetRequest.updateDynamicRules({ addRules: [rule] });
        } catch (eRule) {
            // [v3.1.0 FIX старые браузеры] requestDomains/excludedRequestDomains – Chrome 101+.
            // Старый Chromium (<101, напр. старый Kiwi) reject'ит ВСЁ правило из-за неизвестного ключа
            // (throw ловится нижним catch → в консоли НЕТ ошибки) → Proxy-Authorization НЕ инжектится →
            // прокси отвечает 407 на все запросы → трафик не проходит → «IP не меняется» (сервер
            // «подключился» = 407-ответ resolve'ится, но 0/35 сменили IP). Повторяем БЕЗ 101+-ключей:
            // креды уйдут и на bypass-домены (минорно – это наши apiget/cloudflare), зато VPN на старом
            // браузере заработает. Chromium 101+ берёт полное правило первой попыткой.
            try { delete rule.condition.requestDomains; } catch (_e1) {}
            try { delete rule.condition.excludedRequestDomains; } catch (_e2) {}
            await chrome.declarativeNetRequest.updateDynamicRules({ addRules: [rule] });
        }
    } catch(e) {
        // declarativeNetRequest rule failed – proxy auth may require onAuthRequired fallback
    }
}

async function clearProxyAuthRule() {
    try {
        await chrome.declarativeNetRequest.updateDynamicRules({
            removeRuleIds: [PROXY_AUTH_RULE_ID]
        });
    } catch(e) {}
}

// [v2.4.1] Offscreen keepalive – prevents SW from sleeping while VPN is active
let keepalivePort = null;
const KEEPALIVE_ALARM = 'keepalive_alarm';
// [v2.7.5 audit r3] Mutex против concurrent createDocument. Без него быстрый
// toggle ON×2 обходит hasDocument check (оба проходят между "false" и create) →
// два createDocument → second throws "already exists" → silent fail в catch.
let _keepaliveStarting = false;

async function startKeepalive() {
    // Method 1: Offscreen document (Chrome 109+)
    if (chrome.offscreen) {
        if (_keepaliveStarting) return;
        _keepaliveStarting = true;
        try {
            // [v3.1.0 FIX Chrome 109-115] hasDocument() – Chrome 116+; на 109-115 оно undefined → throw
            // ДО createDocument (который РАБОТАЕТ с 109). Раньше throw глотался нижним catch → offscreen
            // НЕ создавался → keepalive только на слабом alarm → SW чаще умирает → нестабильность
            // (жалобы Win7/8.1-юзеров Chrome 109: «IP недоступен / не подключается / сервер не отвечает»).
            // Guard'им hasDocument; нет его – просто пробуем createDocument, «already exists» ловит catch.
            let existing = false;
            if (typeof chrome.offscreen.hasDocument === 'function') {
                existing = await chrome.offscreen.hasDocument();
            }
            if (!existing) {
                // [v2.7.0 fix F41] reason 'WORKERS' введён Chrome 116+, но min_chrome=109.
                // На 109-115 createDocument с 'WORKERS' throws → offscreen fail → SW засыпает
                // каждые 30 сек. Используем 'BLOBS' – доступен 109+, семантически неточный,
                // но Chrome принимает его для любого offscreen-дока (формальность для API).
                await chrome.offscreen.createDocument({
                    url: 'keepalive.html',
                    reasons: ['BLOBS'],
                    justification: 'Keep service worker alive for proxy authentication'
                });
                try { logDiag('lifecycle', 'offscreen_created', {}); } catch (_o1) {} // [v3.1.0 diag]
            } else {
                try { logDiag('lifecycle', 'offscreen_exists', {}); } catch (_o2) {} // [v3.1.0 diag]
            }
        } catch(e) {
            try { logDiag('lifecycle', 'offscreen_fail', { msg: String((e && e.message) || '').slice(0, 80) }); } catch (_o3) {} // [v3.1.0 diag]
            // Offscreen not supported – alarm fallback will handle keepalive
        } finally {
            _keepaliveStarting = false;
        }
    }
    // [v2.7.0 fix F10] periodInMinutes:0.5 (sub-minute = 30 сек) требует Chrome 120+.
    // Для min_chrome=109 ставим 1 минуту – keepalive alarm это fallback после offscreen-port
    // (primary mechanism). На 109-119 Chrome всё равно clamp'ил 0.5→1, console.warning'ит.
    // [v2.7.0 fix F13] await + try/catch для consistency с F3/F12. Если offscreen-port
    // также fails, KEEPALIVE silent fail → SW sleep каждые 30 сек → VPN drops.
    try {
        await chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 1 });
    } catch (e) {
        logDiag('lifecycle', 'keepalive_alarm_fail', { msg: String((e && e.message) || '').slice(0, 80) });
    }
}

async function stopKeepalive() {
    if (chrome.offscreen) {
        try {
            // [v3.1.0 FIX Chrome 109-115] hasDocument 116+ – guard; на 109-115 просто пробуем закрыть (нет дока → catch).
            if (typeof chrome.offscreen.hasDocument === 'function') {
                const existing = await chrome.offscreen.hasDocument();
                if (existing) await chrome.offscreen.closeDocument();
            } else {
                await chrome.offscreen.closeDocument();
            }
        } catch(e) {}
    }
    keepalivePort = null;
    // [v2.7.0 fix F42] .catch – Chrome 120+ возвращает Promise; без catch возможен
    // unhandled rejection если alarm уже удалён (race с другим clear). Симметрично F33.
    try { chrome.alarms.clear(KEEPALIVE_ALARM).catch(() => {}); } catch {}
}

// Handle keepalive port connections
chrome.runtime.onConnect.addListener((port) => {
    // [v2.7.1 fix F114] Belt-and-suspenders sender.id guard симметрично onMessage
    // (sw:2060). externally_connectable не в manifest → external невозможны, но guard
    // защищает от future manifest change.
    if (port.sender && port.sender.id && port.sender.id !== chrome.runtime.id) return;
    if (port.name === 'keepalive') {
        keepalivePort = port;
        // [v2.7.0 fix F49] Closure captures `port` by reference; когда Chrome reopens offscreen
        // doc и keepalive.js переподключается, новый port присваивается в keepalivePort. Старый
        // port асинхронно disconnects позже – раньше тот callback занулял keepalivePort, обнуляя
        // ссылку на валидный новый port. Теперь callback обнуляет ТОЛЬКО если текущий keepalivePort
        // – это именно disconnecting-port (closure-capture), иначе новый сохраняется.
        const thisPort = port;
        port.onDisconnect.addListener(() => {
            if (keepalivePort === thisPort) keepalivePort = null;
        });
    }
});

// === UID ===
// [v2.7.0 fix F34] Валидация формата UID при чтении. Без неё подмена uid (например,
// через storage manipulation) может содержать `|`, что ломает HMAC sigInput
// `uid|ts|nonce|extid|version` – позволяет подменять поля подписи. Regex требует
// формат `u_<base36>_<base36>`; при несоответствии – regenerate.
const UID_VALID_RE = /^u_[0-9a-z]+_[0-9a-z]+$/;
// [v2.7.5 audit r3] Promise-mutex против race на first install. Cold-wake +
// heartbeat-alarm parallel могут оба вызвать getUID до того как первый запишет
// storage → оба генерируют, second overwrites → UID non-deterministic между
// сессиями. Mutex даёт ВСЕМ параллельным callers одинаковый Promise.
let _uidPromise = null;
async function getUID() {
    if (_uidPromise) return _uidPromise;
    _uidPromise = (async () => {
        const data = await chrome.storage.local.get(['uid']);
        if (typeof data.uid === 'string' && UID_VALID_RE.test(data.uid)) return data.uid;
        // [v2.7.0 fix F43 + v2.7.3 audit] crypto.getRandomValues + proper 40-bit base36 encoding.
        // Старая реализация `byte.toString(36)` конкатенацией теряла энтропию (byte>=36 → 2 chars,
        // byte<36 → 1 char; slice(0,8) мог отрезать половину байта → реально 24-32 бит вместо 40).
        // Собираем 5 байт в 40-бит integer (влезает в Number.MAX_SAFE_INTEGER=2^53), конвертируем
        // в base36 и padStart до 8 chars – получаем полные 40 бит энтропии.
        const r = crypto.getRandomValues(new Uint8Array(5));
        let n = 0;
        for (let i = 0; i < 5; i++) n = n * 256 + r[i];
        const rand = n.toString(36).padStart(8, '0');
        const uid = 'u_' + Date.now().toString(36) + '_' + rand;
        // [v2.8.2 audit] logDiag на storage.set fail – раньше silent catch скрывал quota/corruption,
        // и при следующем cold-wake генерировался новый UID (потеря identity для server-side cooldown).
        try { await chrome.storage.local.set({ uid }); }
        catch (e) { logDiag('uid', 'store_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        return uid;
    })().finally(() => {
        // Mutex resets after promise resolves – следующий call читает свежий storage.
        // Если результат скеширован в memory одного call – это OK, читатель получит то же.
        setTimeout(() => { _uidPromise = null; }, 0);
    });
    return _uidPromise;
}

// === STATS ===
// [v2.6.5 audit] Both functions serialize on _vpnStatsQueue to prevent lost updates when
// timer-alarm fires concurrently with user toggle OFF (both call recordSessionEnd).
// [v2.7.0 fix F35] Guard от corrupted storage: если vpnStats – строка/массив/null (corruption),
// `stats = data.vpnStats || {...}` возвращал corrupted значение и далее `stats.xxx = ...` throw'ил.
// Проверяем тип явно; на corrupt пересоздаём с дефолтом (потеря истории статистики – приемлемо).
function _safeVpnStats(raw) {
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
    return { totalSeconds: 0, totalSessions: 0, serverUsage: {}, dailySeconds: {} };
}
function recordSessionStart() {
    _vpnStatsQueue = _vpnStatsQueue.then(async () => {
        const data = await chrome.storage.local.get(['vpnStats', 'selectedProxy']);
        const stats = _safeVpnStats(data.vpnStats);
        stats.currentSessionStart = Date.now();
        stats.totalSessions = (stats.totalSessions || 0) + 1;
        // [v2.8.1] vpnStats.serverUsage – приватная статистика юзера «как часто использовал
        // сервер». Ключ host:port (стабильный); list/serverList валидация больше не нужна.
        const sp = data.selectedProxy;
        const sk = _serverKey(sp);
        if (sk) {
            stats.serverUsage = stats.serverUsage || {};
            stats.serverUsage[sk] = (stats.serverUsage[sk] || 0) + 1;
        }
        // [v3.1.1] vpnStartedAt – отдельный ключ для счётчика длительности безлимитной сессии
        // в popup. НЕ обнуляется recordSessionEnd (тот зовётся из initialize() на КАЖДОМ
        // SW-рестарте и закрывает СТАТ-сессию даже при живом VPN – из-за этого счётчик
        // «Безлимитный доступ · ⏱» терял источник). Протухшее значение безвредно: popup
        // показывает его только при proxyEnabled, новый connect перезаписывает.
        await chrome.storage.local.set({ vpnStats: stats, vpnStartedAt: stats.currentSessionStart });
    }).catch(() => {});
    return _vpnStatsQueue;
}

function recordSessionEnd() {
    _vpnStatsQueue = _vpnStatsQueue.then(async () => {
        const data = await chrome.storage.local.get(['vpnStats', HEARTBEAT_AT_KEY]);
        // [v2.7.0 fix F35] тот же guard – см. recordSessionStart
        const stats = _safeVpnStats(data.vpnStats);
        if (!stats.currentSessionStart) return;
        // [v3.1.7 fix] НЕ засчитывать время, что браузер был ЗАКРЫТ с включённым ВПН.
        // recordSessionEnd зовётся из initialize() на cold-wake: сессия могла «висеть» в storage
        // с закрытого браузера, тогда (now - start) = весь простой (часы/дни) → totalSeconds раздувался
        // (симптом: «Общее время ВПН» в разы больше реального — 203ч у 15-дневного юзера при 4ч сессий).
        // Heartbeat замолкает при закрытии браузера, поэтому lastHeartbeatAt = последний момент реальной
        // активности; ограничиваем им конец сессии (+2×TTL запас на jitter). Живые длинные сессии
        // (heartbeat свежий → _actEnd≈now) считаются как раньше; закрытое время не капает.
        const _hb = Number(data[HEARTBEAT_AT_KEY]) || 0;
        const _actEnd = (_hb > stats.currentSessionStart)
            ? _hb + HEARTBEAT_TTL_MS * 2                        // есть heartbeat этой сессии → активна до него
            : stats.currentSessionStart + HEARTBEAT_TTL_MS * 2; // heartbeat не успел (короткая/до 1-го) → максимум ~интервал
        const duration = Math.max(0, Math.floor((Math.min(Date.now(), _actEnd) - stats.currentSessionStart) / 1000));
        if (duration > 0) {
            stats.totalSeconds = (stats.totalSeconds || 0) + duration;
            const today = new Date().toISOString().split('T')[0];
            stats.dailySeconds = stats.dailySeconds || {};
            stats.dailySeconds[today] = (stats.dailySeconds[today] || 0) + duration;
            // [v2.5.6] Очистка записей старше 90 дней
            const cutoff = new Date(Date.now() - 90 * 86400000).toISOString().split('T')[0];
            for (const d in stats.dailySeconds) {
                if (d < cutoff) delete stats.dailySeconds[d];
            }
        }
        stats.currentSessionStart = null;
        await chrome.storage.local.set({ vpnStats: stats });
    }).catch(() => {});
    return _vpnStatsQueue;
}

// === NOTIFICATIONS ===
async function notifyDisconnect(reason) {
    // [v2.5.8 audit] Используем cachedTranslationsData (popup кладёт его при первом запуске)
    // для всех 48 языков. Хардкод en/ru – fallback если переводы ещё не загружены.
    const data = await chrome.storage.local.get(['language', 'cachedTranslationsData', 'notifySessionEnd']);
    // [v3.1.1] Настройка «уведомление об окончании сессии» (default ON). Гейтим ТОЛЬКО
    // reason='timer' – premium expired/device_changed важнее и не отключаемы.
    if (reason === 'timer' && data.notifySessionEnd === false) return;
    const lang = data.language || 'en';
    const tr = (data.cachedTranslationsData && data.cachedTranslationsData[lang]) || {};

    const fallbacks = {
        timer: {
            ru: 'Время подключения к бесплатной сессии истекло. Для продолжения переподключитесь.',
            en: 'Free session time has expired. Reconnect to continue.'
        },
        expired: {
            ru: 'Premium истёк, VPN отключён',
            en: 'Premium expired, VPN disconnected'
        },
        device_changed: {
            ru: 'Premium активирован на другом устройстве',
            en: 'Premium activated on another device'
        }
    };
    const fb = fallbacks[reason] || fallbacks.timer;

    let text;
    if (reason === 'expired') {
        text = tr.premiumExpired || fb[lang] || fb.en;
    } else if (reason === 'device_changed') {
        text = tr.deviceChanged || fb[lang] || fb.en;
    } else {
        text = tr.notifTimerExpired || fb[lang] || fb.en;
    }

    const notifId = 'vpn-' + reason + '-' + Date.now();
    const notifOptions = {
        type: 'basic',
        iconUrl: '/icons/AnonVPN128.png',
        title: 'AnonVPN',
        message: text
    };
    // [v2.5.9] Для timer-disconnect добавляем кнопку «Premium» → открывает внутреннюю страницу
    if (reason === 'timer') {
        const premiumBtnTitle = tr.notifPremiumBtn
            || (lang === 'ru' ? 'Получить Premium' : 'Get Premium');
        notifOptions.buttons = [{ title: premiumBtnTitle }];
    }
    try {
        // [v2.7.0 fix F33] .catch – Promise-returning API; try/catch не ловит async rejection.
        chrome.notifications.create(notifId, notifOptions).catch(() => {});
    } catch(e) {}
}

// [v3.1.1] Предупреждение за 5 минут до конца free-сессии (отключаемо: notifySessionSoon).
// Id 'vpn-timersoon-*' СОЗНАТЕЛЬНО матчится startsWith('vpn-timer') в onClicked → клик
// открывает Premium-страницу (как у end-уведомления). Кнопки нет.
async function notifySoonExpiring() {
    const data = await chrome.storage.local.get(['language', 'cachedTranslationsData', 'notifySessionSoon']);
    if (data.notifySessionSoon === false) return;
    const lang = data.language || 'en';
    const tr = (data.cachedTranslationsData && data.cachedTranslationsData[lang]) || {};
    const fb = {
        ru: 'Бесплатная сессия закончится через 5 минут. После окончания можно сразу переподключиться.',
        en: 'Your free session ends in 5 minutes. You can reconnect right after it ends.'
    };
    const text = tr.notifTimerSoon || fb[lang] || fb.en;
    try {
        chrome.notifications.create('vpn-timersoon-' + Date.now(), {
            type: 'basic',
            iconUrl: '/icons/AnonVPN128.png',
            title: 'AnonVPN',
            message: text
        }).catch(() => {});
    } catch (e) {}
}

// [v2.5.9] Клик по самому уведомлению (вне кнопки) → открывает внутреннюю upsell-страницу
chrome.notifications.onClicked.addListener((notifId) => {
    // [v2.7.0 fix F46] autoenable_* notifs используют уникальный ID (`autoenable_<domain>_<ms>`),
    // раньше они накапливались в системном трее. По клику – очищаем.
    if (notifId.startsWith('autoenable_')) {
        try { chrome.notifications.clear(notifId).catch(() => {}); } catch {}
        return;
    }
    if (notifId.startsWith('vpn-timer')) {
        // [v2.7.0 fix F33] .catch – Promise-returning API; без catch unhandled rejection
        // при pop-up/quota-fail может убить Service Worker.
        chrome.tabs.create({ url: upsellUrl('session_notif') }).catch(() => {});
    }
    chrome.notifications.clear(notifId).catch(() => {});
});

// [v2.5.9] Клик по кнопке Premium в уведомлении → внутренняя страница
chrome.notifications.onButtonClicked.addListener((notifId, btnIdx) => {
    if (notifId.startsWith('vpn-timer') && btnIdx === 0) {
        // [v2.7.0 fix F33] .catch – см. onClicked выше.
        chrome.tabs.create({ url: upsellUrl('session_notif_btn') }).catch(() => {});
    }
    chrome.notifications.clear(notifId).catch(() => {});
});

// === HELPER: читает proxyEnabled из storage (надёжно после усыпления SW) ===
async function isProxyEnabled() {
    const d = await chrome.storage.local.get(['proxyEnabled']);
    return !!d.proxyEnabled;
}

// === HEARTBEAT ===
// [v2.6.10] Persisted-TTL для heartbeat. Чтение HEARTBEAT_AT_KEY делается inline
// в sendHeartbeat'овском batch storage.get (вместе с proxyEnabled/isPremium/selectedProxy).
async function setLastHeartbeatAt(ts) {
    // [v2.8.0 audit r2] logDiag в catch – silent fail на storage.set ломал TTL-guard
    // (timestamp не персистился → следующий wake bypass guard → heartbeat-spam). Раньше
    // полностью silent, теперь хотя бы видно в support-логах.
    try { await chrome.storage.local.set({ [HEARTBEAT_AT_KEY]: ts }); }
    catch (e) { logDiag('hb', 'set_at_fail', { msg: String((e && e.message) || e).slice(0, 80) }); }
}

// [v2.6.10 audit r2] Сериализация sendHeartbeat – без неё concurrent вызовы (onAlarm в момент
// когда initialize() в середине своей sendHeartbeat-цепочки) оба читают одинаковый stale
// lastHeartbeatAt, оба проходят TTL guard и оба шлют heartbeat. Окно гонки = от storage.get
// до setLastHeartbeatAt включает await fetch (≤15с). Симметрично _logDiagQueue/_autoEnableQueue/
// _dnrSyncQueue/_vpnStatsQueue. После первого успешного fetch второй вызов читает свежий
// timestamp и скипается по guard'у.
let _heartbeatQueue = Promise.resolve();

function sendHeartbeat(opts) {
    _heartbeatQueue = _heartbeatQueue.catch(() => {}).then(() => _sendHeartbeatBody(opts));
    return _heartbeatQueue;
}

// [v2.6.10] opts.force=true пропускает TTL-гвард (используется при явном VPN-ON через
// doToggleProxy – сервер должен сразу зафиксировать новую сессию). Без force гвард
// блокирует immediate-вызовы из startHeartbeat() на cold-wake SW и из onAlarm если
// alarm стрельнул раньше периода (Chrome иногда так делает на wake).
async function _sendHeartbeatBody(opts) {
    const force = !!(opts && opts.force);
    // [v2.6.10 audit] Batch storage.get – TTL key + main fields в одном IPC-вызове.
    // Симметрично паттерну из 2.6.9 ensureProxyList (sw:1200-1207). На skip-path
    // (cold-wake hot case) – тот же один storage IO; на send-path – было 2, стало 1.
    const d = await chrome.storage.local.get(['proxyEnabled', 'isPremium', 'selectedProxy', HEARTBEAT_AT_KEY]);
    if (!force) {
        const age = Date.now() - (Number(d[HEARTBEAT_AT_KEY]) || 0);
        // age < 0 – clock rollback (NTP-resync, ручная перевода часов): считаем кэш
        // протухшим и шлём heartbeat, иначе риск зависнуть в skip-forever до перезапуска SW.
        if (age >= 0 && age < HEARTBEAT_TTL_MS) return;
    }
    if (!d.proxyEnabled) return;
    const { isPremium, selectedProxy } = d;
    try {
        const uid = await getUID();
        // [v2.8.1] Стабильный server-id – host:port из selectedProxy. Раньше слали
        // serverIdx=fN/pN (позиция в массиве): любая перетасовка n_proxies.txt
        // ломала связку «ключ → реальный сервер», статистика лжёт. Сейчас отправляем
        // host+port напрямую; serverList lookup и filter/findIndex больше не нужны.
        // [v2.7.0 fix R1] Timestamp пишем ДО fetch – атомарно. До 2.7.0: setLastHeartbeatAt
        // ПОСЛЕ await fetch (≤15 сек). MV3 SW killed в этом окне → timestamp не persisted →
        // следующий wake видел 0 → guard bypass → heartbeat снова. Реальный bug 2.6.10:
        // 20.04 юзеры показывали avg gap 60-95 сек вместо целевых 300 (5 мин period).
        // Trade-off: при network-fail пропускаем retry в течение TTL (~4.5 мин) – приемлемо для аналитики.
        // [v2.8.1 audit r2] Guard ДО setLastHeartbeatAt – иначе corrupt-state скип
        // обновляет TTL, но heartbeat не отправлен → следующий wake в окне 4.5 мин
        // тоже скипает (TTL свежий). Loss window устраняется: TTL обновляется только
        // после успешной отправки. Если selectedProxy починится через 30s – heartbeat
        // в этот же tick (TTL не обновлён → guard прошёл).
        const spHost = selectedProxy && selectedProxy.host ? String(selectedProxy.host) : '';
        const spPort = selectedProxy && selectedProxy.port ? String(selectedProxy.port) : '';
        if (!spHost || !spPort) {
            logDiag('hb', 'skip_no_proxy', {});
            return;
        }
        // [v3.1.5] re-preauth TLS-ноды (вариант A): держим свой IP в allowlist ноды (firewall timeout 6ч).
        // Fire-and-forget; хост ноды в bypass (applySelectedProxy) → fetch идёт напрямую, не через прокси.
        if (_proxyScheme(selectedProxy) === 'https') { _nodePreauth(spHost).catch(function () {}); }
        await setLastHeartbeatAt(Date.now());
        // [v2.7.5] Drain traffic accumulator → отправляем в body. На HTTP-fail (catch
        // или !res.ok) кладём обратно в pendingTraffic, чтобы попробовать на следующем
        // heartbeat. Локальная переменная видна в catch – re-store работает.
        var traffic = await _drainTrafficForHeartbeat();
        const hbRes = await apiFetch(HEARTBEAT_PATH, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uid,
                host: spHost,
                port: spPort,
                premium: isPremium ? 1 : 0,
                version: EXT_VERSION,
                ext_id: chrome.runtime.id || '',
                bytes_in:  traffic.bytes_in,
                bytes_out: traffic.bytes_out,
                requests:  traffic.requests
            }),
            signal: AbortSignal.timeout(15000)
        });
        // [v2.7.0 fix F57] `!res.ok` check – 500/502/503 с HTML-телом от CDN раньше не
        // детектились (throw только на network-level). Логируем для диагностики; TTL
        // уже записан pre-fetch, так что retry по свежей логике не ломает rate-limit.
        if (!hbRes.ok) {
            logDiag('net', 'heartbeat_http_err', { status: hbRes.status });
            await _restoreTrafficOnFail(traffic);
            // [v2.8.0] 403 с err='rate_limited' – bot-detection ban. Парсим body, вызываем handler.
            // [v2.8.0 audit] Если JSON parse fail на 403 – всё равно фолбэчим на ban-flow:
            // server.heartbeat.php возвращает 403 ТОЛЬКО при rate_limited (другие коды это 400/500).
            // Раньше parse-fail полностью пропускал handleRateLimited → юзер продолжал heartbeat'ить
            // несмотря на бан → сервер бесконечно отвечает 403 → infinite loop trash.
            if (hbRes.status === 403) {
                let parsedBody = null;
                try { parsedBody = await hbRes.json(); } catch { parsedBody = null; }
                // Если структура совпадает – handle. Если parse fail или поле не то – всё равно фолбэк на rate_limited
                // (статус 403 от heartbeat.php = ban; нет других сценариев). reason/until останутся defaults.
                await handleRateLimited(parsedBody && parsedBody.err === 'rate_limited' ? parsedBody : {});
            }
        } else {
            // [v2.8.0 audit r4+r5] Symmetric с fetchProxyList success path (line ~1591) –
            // на successful heartbeat очищаем rateLimited flags. Без этого после server-side
            // ban-lift banner оставался виснуть до Clear Cache / version bump.
            // Round 5 optimization: conditional remove только если флаг был установлен –
            // экономит ~88% storage writes (heartbeat = 288/day, ban-rate ~12%).
            try {
                const rlState = await chrome.storage.local.get(['rateLimited']);
                if (rlState.rateLimited) {
                    await chrome.storage.local.remove(['rateLimited', 'rateLimitedUntil', 'rateLimitedReason']);
                }
            } catch {}
            if (traffic.requests > 0) {
                // Server accepted – clear persisted (in-memory was zeroed in _drain).
                await _clearPendingTraffic();
            }
            // [v2.8.7 audit-fix] Premium validity check: сервер вернул premium_invalid:true →
            // ключ в БД отсутствует/истёк, а клиентский storage всё ещё думает что premium.
            // Зеркалирует disconnect-cascade из checkPremiumExpiration/checkDeviceBinding:
            //   - explicit per-step try/catch (НЕ doToggleProxy – у того нет args, race c popup-toggle)
            //   - notifyDisconnect('expired') – иначе silent disconnect, юзер видит deanonymisation
            //   - sendMessage premiumDeactivated – popup нужен для clearInterval(timerInterval),
            //     resetPremiumFeatures и т.д. (storage.onChanged покрывает только UI-flag).
            try {
                const hbBody = await hbRes.json();
                if (hbBody && hbBody.premium_invalid === true) {
                    const st = await chrome.storage.local.get(['isPremium']);
                    if (st.isPremium === true) {
                        logDiag('premium', 'invalid_server_response', {});
                        await chrome.storage.local.remove([
                            'isPremium', 'expiresAt', 'expires_timestamp',
                            'premiumKey', 'selectedProxy', 'proxyList', 'proxyListEnc',
                            'proxyListFetchAt', 'lastHeartbeatAt'
                        ]);
                        serverList = null;
                        cachedCredentials = null;
                        await chrome.storage.local.set({ colorTheme: 'default', excludedDomains: [], exclusionsMode: 'blacklist' });
                        const enabled = await isProxyEnabled();
                        if (enabled) {
                            try { await recordSessionEnd(); } catch (e) { logDiag('premInv', 'recEnd_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                            try { await chrome.storage.local.set({ proxyEnabled: false }); } catch (e) { logDiag('premInv', 'storage_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                            try { await setProxy(false); } catch (e) { logDiag('premInv', 'setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                            try { updateIcon(false); } catch {}
                            try { await clearVpnTimer(); } catch (e) { logDiag('premInv', 'clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                            try { stopHeartbeat(); } catch {}
                            try { sendDisconnect('premium_invalid'); } catch {}
                            try { stopKeepalive(); } catch {}
                            try { notifyDisconnect('expired'); } catch {}
                        }
                        try { await applyPremiumState(); } catch {}
                        chrome.runtime.sendMessage({ action: 'premiumDeactivated', reason: 'invalid' }).catch(() => {});
                    }
                }
            } catch (e) { /* parse fail – игнорируем */ }
        }
    } catch(e) {
        // Network error / abort – restore traffic snapshot для следующего heartbeat.
        if (typeof traffic !== 'undefined' && traffic && traffic.requests > 0) {
            await _restoreTrafficOnFail(traffic);
        }
    }
}

// [v2.8.0] reason – для session-audit (vpn_sessions.end_reason). Допустимые значения:
//   'user' (default), 'timer' (60-мин таймер), 'rate_limited' (bot-detection),
//   'version_too_old', 'illegal_ext', 'premium_expired', 'device_changed'.
// Сервер sanitize'ит – допустимы только [a-z0-9_]{1,32}.
async function sendDisconnect(reason) {
    try {
        const uid = await getUID();
        const reasonSafe = (typeof reason === 'string' && /^[a-z0-9_]{1,32}$/.test(reason)) ? reason : 'user';
        await apiFetch(DISCONNECT_PATH, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uid, reason: reasonSafe }),
            signal: AbortSignal.timeout(10000)
        });
    } catch(e) { /* ignore */ }
}

// [v2.8.8] Отправка результата попытки подключения на сервер. Используется в
// admin/proxy-settings.php → вкладка «📈 Подключения» для расчёта success rate
// per server и обнаружения мёртвых прокси по client-side данным (не только cron).
// Server endpoint: AnonVPN/connection_stat.php. Без HMAC (low-stakes data,
// аналогично disconnect.php). Errors swallowed – не блокируем VPN-toggle.
// errorCode: stable short string [a-z0-9_]{1,48}, например 'ping_timeout',
// 'http_407', 'tls_error', 'http_5xx'. Передаётся пустым на status='ok'.
async function sendConnectionStat(server, status, errorCode, latencyMs) {
    try {
        if (status !== 'ok' && status !== 'fail') return;
        if (!server || typeof server !== 'string') return;
        const uid = await getUID();
        const codeSafe = (typeof errorCode === 'string' && /^[a-z0-9_]{1,48}$/.test(errorCode)) ? errorCode : '';
        const latencySafe = Number.isFinite(latencyMs) ? Math.max(0, Math.min(60000, Math.round(latencyMs))) : 0;
        await apiFetch('/AnonVPN/connection_stat.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uid,
                server: String(server).slice(0, 64),
                status,
                error_code: codeSafe,
                latency_ms: latencySafe,
                version: EXT_VERSION
            }),
            signal: AbortSignal.timeout(8000)
        });
    } catch (e) { /* ignore – stat doesn't block UX */ }
}

// [v3.1.1] Сигнал серверу о завершении ПЕРВИЧНОЙ настройки (мастер onboarding). Для воронки
// install → setup_completed → работа/uninstall: понять, доходят ли новые юзеры до рабочего
// состояния (много удалений даже без первого запуска). Без HMAC (low-stakes, как connection_stat).
// Вызывается из reportSetupDone-handler ОДИН раз (guard setupReported). check_passed = прошёл
// проверку серверов; working_servers = сколько рабочих нашлось (0 = не смог подключиться).
async function sendSetupDone(payload) {
    try {
        const uid = await getUID();
        const pd = (payload && typeof payload === 'object') ? payload : {};
        let premium = false;
        try { const d = await chrome.storage.local.get(['isPremium']); premium = !!d.isPremium; } catch (_) {}
        // [v3.1.1] Активен ли ДРУГОЙ VPN/proxy-extension на момент настройки. Через levelOfControl
        // (НЕ требует management-perm): 'controlled_by_other_extensions' = чужой extension держит
        // прокси прямо сейчас. Гипотеза Кости: часть новичков не включают наш VPN из-за уже
        // активного другого (ставили другой, чтобы под автотриал сменить адрес). Это measure, НЕ блок.
        // Наш VPN на шаге setup обычно выключен → значение отражает реально сторонний контроль.
        let otherVpn = 0;
        try {
            const loc = await _getLevelOfControl(1500);
            if (loc === 'controlled_by_other_extensions') otherVpn = 1;
        } catch (_) {}
        await apiFetch('/AnonVPN/setup_done.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uid,
                check_passed: pd.checkPassed ? 1 : 0,
                working_servers: Math.max(0, Math.min(9999, pd.workingServers | 0)),
                premium: premium ? 1 : 0,
                other_vpn: otherVpn,
                version: EXT_VERSION
            }),
            signal: AbortSignal.timeout(8000)
        });
    } catch (e) { /* ignore – analytics doesn't block UX */ }
}

// [v3.1.1] Отправка результата ПОЛНОЙ диагностики на сервер (для техподдержки – быстро ориентироваться
// при обращении юзера). Без HMAC (low-stakes, как setup_done/connection_stat), best-effort.
async function sendDiagRun(payload) {
    try {
        const uid = await getUID();
        const pd = (payload && typeof payload === 'object') ? payload : {};
        let chromeVer = '';
        try { const m = ((self.navigator && navigator.userAgent) || '').match(/Chrome\/(\d+)/); if (m) chromeVer = m[1]; } catch (_) {}
        await apiFetch('/AnonVPN/diag_log.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uid,
                verdict: String(pd.verdict || ''),
                servers_total: pd.servers_total | 0,
                servers_connected: pd.servers_connected | 0,
                servers_working: pd.servers_working | 0,
                internet_ok: pd.internet_ok ? 1 : 0,
                api_reachable: pd.api_reachable | 0,
                blocks: String(pd.blocks || ''),
                proxy_control: String(pd.proxy_control || ''),
                other_vpns: String(pd.other_vpns || ''),
                old_chrome: pd.old_chrome ? 1 : 0,
                chrome_ver: chromeVer,
                version: EXT_VERSION
            }),
            signal: AbortSignal.timeout(8000)
        });
    } catch (e) { /* ignore – analytics doesn't block UX */ }
}

// ════════════════════════════════════════════════════════════════════════
// [v2.7.5] TRAFFIC TRACKING (client-side, webRequest.onCompleted-based)
// ════════════════════════════════════════════════════════════════════════
// Трафик считаем клиентом (доступа к прокси-серверам нет – сторонние). Каждый
// успешный response добавляет Content-Length в _trafficCounter, плюс fixed
// approximation за заголовки. На каждом heartbeat сливаем accumulator в POST
// body и обнуляем после success-ответа (server INSERT...ON DUPLICATE KEY UPDATE
// аккумулирует в stats_user_daily).
//
// Точность ±15-25%: Content-Length отсутствует на chunked/SSE, не учитывает
// TLS overhead, headers – приблизительно. Достаточно для analytics, не для billing.
//
// SW kill: in-memory часть теряется. Persistence на disconnect (proxy OFF) +
// при partial-failure heartbeat (network down → put back в `pendingTraffic`).
let _trafficCounter = { bytes_in: 0, bytes_out: 0, requests: 0 };
const PENDING_TRAFFIC_KEY = 'pendingTraffic';
const TRAFFIC_REQ_HEADERS_APPROX = 500;        // [v2.7.5 audit r3] HTTP/2 + TLS обычно 500-700 bytes/req (was 350 – undercount)
const TRAFFIC_HEARTBEAT_CAP = 50 * 1024 * 1024 * 1024;  // 50 GB / heartbeat – server-side cap зеркало

let _trafficVpnActive = false;
chrome.storage.local.get(['proxyEnabled']).then(d => { _trafficVpnActive = !!d.proxyEnabled; }).catch(() => {});
// [v2.8.8] Cache bypassRuDomains для traffic accounting – иначе .ru/.рф трафик который
// идёт DIRECT (через bypass) учитывается как proxy-трафик → inflated bytes_in/out.
let _trafficBypassRuOn = true; // default ON, mirror SW config
chrome.storage.local.get(['bypassRuDomains']).then(d => { _trafficBypassRuOn = (d.bypassRuDomains !== false); }).catch(() => {});

function _onWebRequestCompletedHandler(details) {
    if (!_trafficVpnActive) return;
    // Skip extension/background-page requests (tabId === -1) – они не идут через прокси.
    if (typeof details.tabId !== 'number' || details.tabId < 0) return;
    // [v2.7.5 audit Pass5] Skip BYPASS_LIST domains – Chrome routes их DIRECT (не через
    // прокси), поэтому учитывать в proxy-traffic нельзя. Без фильтра трафик к
    // apiget.ru/Google services/gstatic/cp.cloudflare.com инфлирует analytics на ~5-15%.
    try {
        const u = new URL(details.url);
        const host = u.hostname.toLowerCase();
        for (let i = 0; i < BYPASS_LIST.length; i++) {
            const b = BYPASS_LIST[i];
            if (b === '<-loopback>') continue;  // Chrome's special bypass token
            if (b.length > 2 && b.charCodeAt(0) === 42 /* '*' */ && b.charCodeAt(1) === 46 /* '.' */) {
                const suffix = b.slice(1);  // '.gstatic.com'
                if (host === b.slice(2) || (host.length > suffix.length && host.endsWith(suffix))) return;
            } else if (host === b) {
                return;
            }
        }
        // [v2.8.8] Также скипаем .ru/.xn--p1ai когда bypassRuDomains активен – эти hosts
        // routятся DIRECT через PAC/bypass-list, учитывать как proxy-traffic нельзя.
        if (_trafficBypassRuOn) {
            if (host === 'ru' || host.endsWith('.ru')) return;
            if (host === 'xn--p1ai' || host.endsWith('.xn--p1ai')) return;
        }
    } catch { /* malformed URL – count anyway, defensive */ }
    let bytesIn = 0;
    if (Array.isArray(details.responseHeaders)) {
        for (let i = 0; i < details.responseHeaders.length; i++) {
            const h = details.responseHeaders[i];
            if (h && h.name && h.name.toLowerCase() === 'content-length') {
                const n = parseInt(h.value, 10);
                if (!isNaN(n) && n > 0) bytesIn = n;
                break;
            }
        }
    }
    _trafficCounter.bytes_in += bytesIn;
    _trafficCounter.bytes_out += TRAFFIC_REQ_HEADERS_APPROX;
    _trafficCounter.requests += 1;
}
if (chrome.webRequest && chrome.webRequest.onCompleted && !chrome.webRequest.onCompleted.hasListener(_onWebRequestCompletedHandler)) {
    chrome.webRequest.onCompleted.addListener(
        _onWebRequestCompletedHandler,
        { urls: ['http://*/*', 'https://*/*'] },
        ['responseHeaders']
    );
}

// Persist in-memory counter в storage (используется на VPN-toggle-OFF).
// [v2.7.6 audit Pass6] Optional `snap` argument: если caller передал готовый snapshot –
// используем его (caller уже сделал sync-zeroing counter перед setting flag, чтобы
// избежать race с webRequest events между flag-set и async storage.set). Если без
// аргумента – берём текущий counter и нулим (legacy path).
// [v2.8.1 audit] Serialization queue – read-modify-write of PENDING_TRAFFIC_KEY race-safe.
// Без queue: два concurrent storage.onChanged proxyEnabled events (multi-popup, или
// timer-expiry+manual toggle в один tick) оба читают одинаковую персистную base →
// второй set перезаписывает первый → потерянные traffic bytes. Симметрично с
// _logDiagQueue/_autoEnableQueue/_vpnStatsQueue/_dnrSyncQueue/_applyPremiumStateQueue.
let _persistTrafficQueue = Promise.resolve();
function _persistTrafficCounter(snap) {
    _persistTrafficQueue = _persistTrafficQueue.then(() => _persistTrafficCounterBody(snap)).catch(() => {});
    return _persistTrafficQueue;
}
async function _persistTrafficCounterBody(snap) {
    if (!snap) {
        // [v2.7.6 audit Pass7] Guard симметричен snap-path: учитываем bytes тоже,
        // не только requests, иначе orphan bytes остаётся в counter если каким-то
        // edge-case'ом ResponseSize пришёл а requests-counter не инкрементировался.
        if (!_trafficCounter.requests && !_trafficCounter.bytes_in && !_trafficCounter.bytes_out) return;
        snap = _trafficCounter;
        _trafficCounter = { bytes_in: 0, bytes_out: 0, requests: 0 };
    } else if (!snap.requests && !snap.bytes_in && !snap.bytes_out) {
        return;
    }
    try {
        const data = await chrome.storage.local.get([PENDING_TRAFFIC_KEY]);
        const persisted = (data && data[PENDING_TRAFFIC_KEY]) || { bytes_in: 0, bytes_out: 0, requests: 0 };
        // [v2.7.6 audit Pass10] Math.max(0, ...) – sanitize negative values от corrupted
        // persisted storage (manual edit, partial write, version downgrade leftover).
        // Симметрично с _restoreTrafficOnFail (Pass 9 fix).
        await chrome.storage.local.set({
            [PENDING_TRAFFIC_KEY]: {
                bytes_in:  Math.max(0, (Number(persisted.bytes_in)  || 0) + snap.bytes_in),
                bytes_out: Math.max(0, (Number(persisted.bytes_out) || 0) + snap.bytes_out),
                requests:  Math.max(0, (Number(persisted.requests)  || 0) + snap.requests)
            }
        });
    } catch (e) {
        // [v2.7.6 audit Pass13] logDiag вместо silent – persist fail = traffic не
        // дойдёт до сервера на следующий heartbeat (in-memory restore только до next
        // SW-kill). Telemetry помогает выявить quota issues в production.
        logDiag('traffic', 'persist_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        // Restore on storage failure
        _trafficCounter.bytes_in  += snap.bytes_in;
        _trafficCounter.bytes_out += snap.bytes_out;
        _trafficCounter.requests  += snap.requests;
    }
}

// Drain in-memory + persisted в один объект для отправки в heartbeat.
// [v2.7.6 fix] Pending очищается ATOMARNO в drain (после merge в total), НЕ после
// HTTP-success как раньше. Корневая причина 2.7.5-bug: при HTTP-fail
// `_restoreTrafficOnFail(total)` добавлял `total` (= snap + pending) обратно в
// УЖЕ-непустой pending → `pending = P + (snap + P) = snap + 2P`. Каждый
// последующий fail удваивал pending геометрически (P → 2P → 4P → 8P …) →
// за 10-15 циклов клампился на 50 GiB cap. Production data: 0.26% юзеров на
// 2.7.5 имели bytes_out = ровно 50 GiB. Теперь pending очищается в drain;
// _restoreTrafficOnFail SET-ит (не add) – нет ничего к чему добавлять.
async function _drainTrafficForHeartbeat() {
    const snap = _trafficCounter;
    _trafficCounter = { bytes_in: 0, bytes_out: 0, requests: 0 };
    let total = { bytes_in: snap.bytes_in, bytes_out: snap.bytes_out, requests: snap.requests };
    // [v3.1.1 audit] PENDING get→merge→remove через _persistTrafficQueue – единый владелец
    // PENDING_TRAFFIC_KEY. Раньше drain читал/удалял ВНЕ очереди: конкурентный _persistTrafficCounter
    // (VPN-OFF flush, storage.onChanged) мог приземлить set между drain.get и drain.remove → blind
    // remove сносил только что добавленные байты (потеря трафика). Snap снят синхронно ВЫШЕ –
    // атомарность относительно webRequest-events сохранена; сериализуются лишь storage-операции с
    // PENDING. Dry-run: старая логика 450 вместо 350 (гонка), новая – стабильно 350; 50GiB-геометрия
    // не воспроизводится (S2 линейно).
    _persistTrafficQueue = _persistTrafficQueue.then(async () => {
        try {
            const data = await chrome.storage.local.get([PENDING_TRAFFIC_KEY]);
            const persisted = data && data[PENDING_TRAFFIC_KEY];
            if (persisted && typeof persisted === 'object') {
                total.bytes_in  += (Number(persisted.bytes_in)  || 0);
                total.bytes_out += (Number(persisted.bytes_out) || 0);
                total.requests  += (Number(persisted.requests)  || 0);
                // [v2.7.6] Clear immediately after merge – see comment block above.
                await chrome.storage.local.remove([PENDING_TRAFFIC_KEY]);
            }
        } catch (e) {
            // [v2.7.6 audit Pass13] logDiag вместо silent – storage.get/.remove fail на
            // pendingTraffic раньше silent. Если quota issue → traffic стат пропадают,
            // нужна telemetry для диагностики.
            logDiag('traffic', 'drain_storage_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        }
    }).catch(() => {});
    await _persistTrafficQueue;
    // Cap зеркало server-side: bad-client с inflated values отсекается клиентом тоже.
    if (total.bytes_in  > TRAFFIC_HEARTBEAT_CAP) total.bytes_in  = TRAFFIC_HEARTBEAT_CAP;
    if (total.bytes_out > TRAFFIC_HEARTBEAT_CAP) total.bytes_out = TRAFFIC_HEARTBEAT_CAP;
    if (total.requests  > 100000) total.requests = 100000;
    return total;
}
function _clearPendingTraffic() {
    // [v2.7.6] No-op в большинстве случаев (pending уже очищен в drain), но keep
    // для safety: если drain не достиг storage.remove (catch ветка), success-clear
    // подтирает остаток. Идемпотентно.
    // [v3.1.1 audit] Через _persistTrafficQueue – единый владелец PENDING_TRAFFIC_KEY (remove не
    // должен пересекаться с конкурентным persist get→add→set). Возвращает Promise (caller await'ит).
    _persistTrafficQueue = _persistTrafficQueue.then(async () => {
        try { await chrome.storage.local.remove([PENDING_TRAFFIC_KEY]); } catch {}
    }).catch(() => {});
    return _persistTrafficQueue;
}
function _restoreTrafficOnFail(snapshot) {
    // [v2.7.6 audit Pass6] Раньше guard только на requests – orphan'ило bytes_in/out
    // если requests=0 при non-zero bytes (legacy 2.7.5 leftover в pendingTraffic).
    if (!snapshot) return Promise.resolve();
    if (!snapshot.requests && !snapshot.bytes_in && !snapshot.bytes_out) return Promise.resolve();
    // [v3.1.1 audit] Через _persistTrafficQueue – единый владелец PENDING_TRAFFIC_KEY. SET-семантика
    // СОХРАНЕНА (сознательный anti-50GiB выбор 2.7.6: pending очищен в drain, добавлять не к чему).
    // Dry-run S2: линейное накопление (20000), НЕ геометрия 10^9; S4: restore=800 корректен.
    _persistTrafficQueue = _persistTrafficQueue.then(async () => {
        try {
            // [v2.7.6 fix] SET pending = snapshot напрямую (was: add to existing pending).
            // Pending был очищен в drain атомарно – добавлять не к чему. Если parallel restore
            // запустится (race с _persistTrafficCounter на VPN OFF) – last-writer-wins;
            // приемлемо vs. геометрический рост из 2.7.5.
            await chrome.storage.local.set({
                [PENDING_TRAFFIC_KEY]: {
                    // [v2.7.6 audit Pass9] Math.max(0, ...) – sanitize negative values
                    // (corrupted persisted data from external manipulation, partial writes).
                    bytes_in:  Math.max(0, Number(snapshot.bytes_in)  || 0),
                    bytes_out: Math.max(0, Number(snapshot.bytes_out) || 0),
                    requests:  Math.max(0, Number(snapshot.requests)  || 0)
                }
            });
        } catch (e) {
            // [v2.7.6 audit Pass13] logDiag вместо silent – restore fail = lost traffic
            // events. Telemetry для production-monitoring.
            logDiag('traffic', 'restore_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        }
    }).catch(() => {});
    return _persistTrafficQueue;
}

// Sync flag + final-flush на VPN-toggle. _trafficVpnActive контролирует listener
// (только VPN-трафик считаем). На OFF – persistим in-memory counter в storage.
// [v2.7.6 audit Pass6] Sync-snapshot ПЕРЕД установкой flag – без этого webRequest
// events между fire-forget _persistTrafficCounter() и flag set могли потеряться
// (flag уже false → listener skip) или продублироваться (counter еще не nulled
// в момент когда async persist read его). Снимаем snap синхронно, передаём в persist.
chrome.storage.onChanged.addListener(function(changes, area) {
    if (area !== 'local') return;
    // [v2.8.8] Live-sync bypassRuDomains для traffic accounting (mirror SW state).
    if (changes.bypassRuDomains) {
        _trafficBypassRuOn = (changes.bypassRuDomains.newValue !== false);
    }
    // [v3.1.2] Сразу запускаем ghost-ping (не ждём минутного alarm), когда:
    //  • завершена первоначальная настройка (onboardingV2Done) — до этого ghost стоит по guard;
    //  • активирован premium (isPremium→true) — теперь доступны premium-серверы, их надо начать
    //    пинговать без задержки (иначе premium-пинги ждали бы следующего alarm-тика до минуты;
    //    типовой случай: юзер прошёл setup без ключа, а ключ ввёл потом).
    if ((changes.onboardingV2Done && changes.onboardingV2Done.newValue) ||
        (changes.isPremium && changes.isPremium.newValue)) {
        setTimeout(function(){ ghostPingTick().catch(function(){}); }, 500);
    }
    if (!changes.proxyEnabled) return;
    const newVal = !!changes.proxyEnabled.newValue;
    if (_trafficVpnActive && !newVal) {
        // Атомарный snap – counter обнуляется до того как любой следующий webRequest event
        // дойдёт до accumulation (event loop is single-threaded, _trafficVpnActive=newVal
        // ещё не set → новые events еще считаются в counter? нет: они уйдут в новый zeroed
        // counter. То что было до – снято в snap, persist'нем asynchronously).
        const snap = _trafficCounter;
        _trafficCounter = { bytes_in: 0, bytes_out: 0, requests: 0 };
        _persistTrafficCounter(snap).catch(() => {});
    }
    _trafficVpnActive = newVal;
});

// [v2.7.1 fix F78] Корневая причина heartbeat-spam 2.7.0 (топ-юзеры показали intensity
// 425-721% = 1 heartbeat каждые 42 сек вместо 5 мин):
//
// MV3 SW часто просыпается от webRequest.onAuthRequired (proxy challenge на каждый request
// → wake каждые секунды при активном браузинге). Каждый wake вызывает initialize() → startHeartbeat()
// → stopHeartbeat() СТИРАЕТ alarm → sendHeartbeat() immediate → chrome.alarms.create() новый 5-мин.
// Immediate sendHeartbeat() защищён TTL-guard'ом через `lastHeartbeatAt` в storage, НО:
//   1. Если SW убит между `setLastHeartbeatAt(now)` и storage.set flush → TS не записан → age=huge → spam.
//   2. При update с STALE_KEYS wipe `lastHeartbeatAt` → первый wake видит age=huge → send.
//      Каждый следующий wake до ~4.5мин тоже видит huge age (возможно race с commit'ом).
//
// Новая логика:
//   - force=true (VPN-ON от юзера): immediate send + reset alarm (сервер должен сразу видеть сессию).
//   - force=false (cold-wake re-init): если alarm уже существует – НЕ трогаем; если нет – создаём
//     без immediate send. Alarm сам стрельнёт через 5 мин, и TTL-guard на alarm-fire защитит от
//     повторов если новый wake случился быстро.
// Это полностью убирает зависимость heartbeat-частоты от частоты cold-wake'ов.
async function startHeartbeat(opts) {
    const force = !!(opts && opts.force);
    if (force) {
        stopHeartbeat();
        sendHeartbeat(opts).catch(function(e){
            // [v2.8.0] logDiag вместо silent catch – force-send fails (network down при VPN-ON)
            // не блокировались логически, но юзер копирующий diag log не видел причину почему
            // server не зафиксировал session start. Next 5-мин alarm всё равно retry'нет.
            logDiag('hb', 'force_send_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        });
        try { chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: 5 }); } catch {}
        return;
    }
    // Non-force path: если alarm жив, оставить существующую периодичность.
    let existing = null;
    try { existing = await chrome.alarms.get(HEARTBEAT_ALARM); } catch {}
    if (!existing) {
        try { chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: 5 }); } catch {}
    }
    // immediate send ПРОПУСКАЕТСЯ намеренно – alarm обеспечит 5-мин интервал. На первой
    // сессии юзер получит первый heartbeat через 5 мин (VPN-ON уже отправил force-heartbeat).
}

function stopHeartbeat() {
    // [v2.7.0 fix F42] .catch – см. stopKeepalive выше.
    try { chrome.alarms.clear(HEARTBEAT_ALARM).catch(() => {}); } catch {}
}

// === ICON ===
function updateIcon(enabled) {
    const path = enabled ? '/icons/enabledop.png' : '/icons/disabledop.png';
    // [v2.7.0 fix F58] .catch – Promise-returning API; без catch редкий fail (manifest error,
    // file inaccessible) даёт unhandled rejection, может завалить SW.
    try { chrome.action.setIcon({ path }).catch(() => {}); } catch {}
    // [v2.8.0 audit r2] updateBadge() – async; без .catch unhandled rejection при storage IO fail.
    updateBadge().catch(() => {});
}

// [v2.5.9] Remaining-minutes counter on the action icon (free users only).
async function updateBadge() {
    try {
        const d = await chrome.storage.local.get(['proxyEnabled', 'isPremium', VPN_DEADLINE_KEY]);
        // [v2.7.1 fix F127] .catch на Promise-returning chrome.action.* – sync try/catch не ловит
        // async rejection (rare manifest/perm errors). Без catch – unhandled rejection в SW.
        // [v2.7.1 fix F145] Сбрасываем background к прозрачному при clear – иначе после
        // free→premium switch в action остаётся пустая красная/синяя пилюля от прошлого badge.
        if (!d.proxyEnabled || d.isPremium) {
            chrome.action.setBadgeText({ text: '' }).catch(() => {});
            chrome.action.setBadgeBackgroundColor({ color: [0, 0, 0, 0] }).catch(() => {});
            return;
        }
        const deadline = d[VPN_DEADLINE_KEY];
        // [v2.7.4 audit r4] Number.isFinite-guard – corrupt storage (manual edit / quota write
        // partial) мог дать deadline="abc" или {}. msLeft = NaN → Math.min(99, NaN) = NaN →
        // String(NaN) = "NaN" badge. Truthy-check (!deadline) пропускал non-numeric truthy.
        if (!deadline || typeof deadline !== 'number' || !Number.isFinite(deadline)) {
            chrome.action.setBadgeText({ text: '' }).catch(() => {});
            chrome.action.setBadgeBackgroundColor({ color: [0, 0, 0, 0] }).catch(() => {});
            return;
        }
        const msLeft = deadline - Date.now();
        if (msLeft <= 0) {
            chrome.action.setBadgeText({ text: '' }).catch(() => {});
            chrome.action.setBadgeBackgroundColor({ color: [0, 0, 0, 0] }).catch(() => {});
            return;
        }
        // [v2.7.0 fix F47] cap на 99 – free-session максимум 60 мин, но при corrupted deadline
        // (bug или storage manipulation) minLeft мог бы превысить 4-char лимит badge.
        const minLeft = Math.min(99, Math.ceil(msLeft / 60000));
        chrome.action.setBadgeText({ text: String(minLeft) }).catch(() => {});
        chrome.action.setBadgeBackgroundColor({ color: minLeft <= 5 ? '#f44336' : '#2196f3' }).catch(() => {});
        if (chrome.action.setBadgeTextColor) {
            chrome.action.setBadgeTextColor({ color: '#ffffff' }).catch(() => {});
        }
    } catch {}
}

// === PREMIUM LOGIC ===
async function checkPremiumExpiration() {
    const data = await chrome.storage.local.get(['isPremium', 'expires_timestamp']);
    if (!data.isPremium || !data.expires_timestamp) return false;
    // [v2.7.1 fix F89] Symmetric с v2.6.7 type-guard на activation. Corrupt storage
    // со строкой "NaN" или объектом дал бы `serverTimestamp > nonNumber` = false,
    // премиум никогда бы не истёк локально. Normalize → число или early return.
    const expTs = Number(data.expires_timestamp);
    if (!Number.isFinite(expTs) || expTs <= 0) return false;
    try {
        // [FIX #4] apiget.ru в bypassList – запрос идёт напрямую даже при VPN ON
        const response = await apiFetch('/AnonVPN/timestamp.php', { signal: AbortSignal.timeout(15000) });
        // [v2.6.9] HTML-страница ошибки от CDN/прокси не должна попасть в parseInt
        if (!response.ok) return false;
        const serverTimestamp = parseInt(await response.text(), 10);
        // [v2.6.0] Защита от NaN: если сервер вернул пустой/невалидный ответ, не трогаем премиум.
        // Иначе `NaN > expires_timestamp` всегда false → тихо пропускаем проверку истечения.
        if (isNaN(serverTimestamp) || serverTimestamp <= 0) return false;
        if (serverTimestamp > expTs) {
            // [v2.8.5 fix R2] Re-read свежий expires_timestamp ПЕРЕД revoke – fetch
            // timestamp.php занимает до 15с; за это время юзер мог продлить/пере-активировать
            // Premium. Без re-read мы бы затёрли свежую активацию по устаревшему expTs.
            const _freshExp = await chrome.storage.local.get(['isPremium', 'expires_timestamp']);
            if (!_freshExp.isPremium) return false;
            const _fe = Number(_freshExp.expires_timestamp);
            if (Number.isFinite(_fe) && _fe > 0 && serverTimestamp <= _fe) return false;
            // [FIX #9] Очищаем и proxyListEnc, чтобы при переподключении загрузить свежий
            // [v2.7.2 fix F150] +proxyListFetchAt +lastHeartbeatAt – без этого TTL-guard после
            // premium-expire думал что кэш свежий и пропускал refresh на новых premium-creds.
            await chrome.storage.local.remove(['isPremium', 'expiresAt', 'expires_timestamp', 'premiumKey', 'selectedProxy', 'proxyList', 'proxyListEnc', 'proxyListFetchAt', 'lastHeartbeatAt']);
            serverList = null;
            // [v2.7.0 fix F36] Обнулить cachedCredentials – selectedProxy удалён, но кэш
            // в памяти SW мог сохранить старые premium-creds, которые onAuthRequired
            // fast-path передал бы proxy'у при следующем включении.
            cachedCredentials = null;
            await chrome.storage.local.set({ colorTheme: 'default', excludedDomains: [], exclusionsMode: 'blacklist' });
            const enabled = await isProxyEnabled();
            if (enabled) {
                // [v2.8.1 audit] Per-step try/catch – симметрично F17 в doToggleProxy OFF.
                // Throw в одном step (recordSessionEnd network fail) НЕ должен оставить
                // proxyEnabled=true при отключённой прокси. Класс v2.6.10 unlimited-VPN.
                try { await recordSessionEnd(); } catch (e) { logDiag('premiumExp', 'recEnd_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { await chrome.storage.local.set({ proxyEnabled: false }); } catch (e) { logDiag('premiumExp', 'storage_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { await setProxy(false); } catch (e) { logDiag('premiumExp', 'setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { updateIcon(false); } catch {}
                try { await clearVpnTimer(); } catch (e) { logDiag('premiumExp', 'clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { stopHeartbeat(); } catch {}
                // [v2.8.1 audit] reason='premium_expired' – без него session-audit
                // показывал все expiry как 'user', пересечение с user-toggle статистикой.
                try { sendDisconnect('premium_expired'); } catch {}
                try { stopKeepalive(); } catch {}
                try { notifyDisconnect('expired'); } catch {}
            }
            // [round 10] Синхронно sync ad-blocker DNR ruleset. storage.onChanged на
            // isPremium запустит applyPremiumState() асинхронно – но между revoke и
            // listener-fire может проскочить toggle/init который прочитает stale state.
            // Direct call закрывает race, _applyPremiumStateQueue гарантирует idempotency.
            try { await applyPremiumState(); } catch {}
            // [v2.5.4] Уведомляем popup всегда, не только при VPN ON
            chrome.runtime.sendMessage({ action: "premiumDeactivated", reason: "expired" }).catch(() => {});
            return true;
        }
    } catch {
        // Network error – will retry on next alarm
    }
    return false;
}

// v2.4.2: Проверка привязки Premium к устройству (каждые 5 мин, даже при VPN ON)
async function checkDeviceBinding() {
    const data = await chrome.storage.local.get(['isPremium', 'premiumKey']);
    if (!data.isPremium || !data.premiumKey) return;
    try {
        const uid = await getUID();
        const res = await apiFetch('/AnonVPN/check-key.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: data.premiumKey, device_id: uid }),
            signal: AbortSignal.timeout(15000)
        });
        // [v2.6.5 audit] res.ok check – иначе 500/503/ошибочный JSON (например от CDN-страницы)
        // с отсутствующим .valid==true → премиум снимается без причины.
        if (!res.ok) return;
        const result = await res.json();
        // [v2.8.5 audit R1] Revoke ТОЛЬКО при явном valid:false. Malformed-но-валидный-JSON
        // ответ ({}, число, строка, массив, null) → раньше result.valid!==true → ложная
        // revocation у платящего юзера из-за сервер-глюка. Не-объект / нет явного false –
        // inconclusive, премиум не трогаем (compromised сервер и так может прислать valid:true).
        if (!result || typeof result !== 'object') return;
        if (result.valid === false) {
            // [v2.8.5 fix R2] Re-read – fetch check-key.php занимает до 15с; юзер мог
            // пере-активировать Premium (новый ключ) за это время. Если premiumKey уже
            // сменился – проверка относилась к старому ключу, новую активацию не трогаем.
            const _freshKey = await chrome.storage.local.get(['isPremium', 'premiumKey']);
            if (!_freshKey.isPremium || _freshKey.premiumKey !== data.premiumKey) return;
            // Ключ невалиден (device_changed, revoked, expired и т.д.) – полный выход
            // [v2.7.2 fix F150] +proxyListFetchAt +lastHeartbeatAt – см. checkPremiumExpiration
            await chrome.storage.local.remove([
                'isPremium', 'expiresAt', 'expires_timestamp',
                'premiumKey', 'selectedProxy', 'proxyList', 'proxyListEnc',
                'proxyListFetchAt', 'lastHeartbeatAt'
            ]);
            serverList = null;
            // [v2.7.0 fix F36] Обнулить cachedCredentials – см. checkPremiumExpiration
            cachedCredentials = null;
            await chrome.storage.local.set({ colorTheme: 'default', excludedDomains: [], exclusionsMode: 'blacklist' });
            const enabled = await isProxyEnabled();
            if (enabled) {
                // [v2.8.1 audit] Per-step try/catch – same as checkPremiumExpiration.
                try { await recordSessionEnd(); } catch (e) { logDiag('deviceBind', 'recEnd_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { await chrome.storage.local.set({ proxyEnabled: false }); } catch (e) { logDiag('deviceBind', 'storage_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { await setProxy(false); } catch (e) { logDiag('deviceBind', 'setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { updateIcon(false); } catch {}
                try { await clearVpnTimer(); } catch (e) { logDiag('deviceBind', 'clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                try { stopHeartbeat(); } catch {}
                // [v2.8.1 audit] reason mirror'ит result.reason: device_changed = смена
                // привязки устройства, иначе premium_expired (revoked/expired).
                try { sendDisconnect(result.reason === 'device_changed' ? 'device_changed' : 'premium_expired'); } catch {}
                try { stopKeepalive(); } catch {}
                try { notifyDisconnect(result.reason === 'device_changed' ? 'device_changed' : 'expired'); } catch {}
            }
            // [round 10] Синхронный applyPremiumState – см. checkPremiumExpiration выше.
            try { await applyPremiumState(); } catch {}
            chrome.runtime.sendMessage({ action: 'premiumDeactivated', reason: result.reason || 'expired' }).catch(() => {});
        }
    } catch {
        // Ошибка сети – не разлогиниваем, проверим в следующий раз
    }
}

// [FIX #1] chrome.alarms вместо setInterval для проверки премиума
// [v2.7.0 fix F12] await + try/catch. PREMIUM_CHECK_ALARM КРИТИЧЕН – если silent fail
// (quota), checkPremiumExpiration никогда не запустится → premium не wipe'нется после
// истечения → юзер бесплатно держит premium. Server-side heartbeat не валидирует expiry.
(async () => {
    try {
        await chrome.alarms.create(PREMIUM_CHECK_ALARM, { periodInMinutes: 5 });
    } catch (e) {
        logDiag('lifecycle', 'premium_check_alarm_fail', { msg: String((e && e.message) || '').slice(0, 80) });
    }
    // [v3.0.4] API-probe alarm (раз в 6ч). get-first: НЕ пересоздаём если уже есть – иначе частые
    // SW-wake'и (toggle/сообщения/др. alarm) сбрасывали бы 6ч-таймер и alarm никогда бы не сработал.
    try {
        const _ap = await chrome.alarms.get(API_PROBE_ALARM);
        if (!_ap) await chrome.alarms.create(API_PROBE_ALARM, { periodInMinutes: API_PROBE_INTERVAL_MIN });
    } catch (e) {}
    // [v3.1.2] Ghost-ping alarm (1 мин – минимум Chrome). Служит будильником: раз в минуту
    // проверяет, не устарело ли что-то, и если да – прогоняет очередь подряд. Когда всё свежее,
    // тик выходит мгновенно (пауза до устаревания). get-first ОБЯЗАТЕЛЕН: heartbeat будит SW,
    // безусловный create сбрасывал бы таймер на каждом wake'е – alarm не сработал бы никогда.
    try {
        const _gp = await chrome.alarms.get(GHOST_PING_ALARM);
        if (!_gp) {
            await chrome.alarms.create(GHOST_PING_ALARM, { periodInMinutes: 1 });
            // [v3.1.2] Первый alarm сработает только через ~1 мин. Для пропустивших первоначальную
            // настройку (method='ping', пингов ещё нет) это критичная минута на load-fallback. Стартуем
            // ghost раньше: короткая задержка, чтобы список серверов успел загрузиться (onInstalled →
            // ensureProxyList в фоне). Список ещё пуст → тик выйдет рано, alarm догонит через минуту.
            // Условие !_gp = alarm ещё не было (свежая установка / обновление), а не рядовой SW-wake.
            setTimeout(function(){ ghostPingTick().catch(function(){}); }, 6000);
        }
    } catch (e) {}
})();

// === PROXY LOGIC ===
// [v2.5.8] Подписанный + зашифрованный запрос proxy_list
async function fetchProxyList() {
    // [v2.5.8 audit] Если уже заблокированы – не дёргаем сеть. Сбрасывается на успешном fetch.
    // [v2.6.0] Lazy reset: если с момента установки флага прошло >VPN_BLOCKED_COOLDOWN_MS,
    // даём сети новый шанс. Нужно, чтобы «застревание» после транзиентного 403 не приводило
    // к бесконечному пустому списку до ручного reload.
    if (vpnBlocked) {
        const age = Date.now() - vpnBlockedAt;
        // [v2.7.0 fix F44] age < 0 – clock rollback (NTP resync, ручная установка).
        // Раньше: застрявший vpnBlocked оставался до естественного advance часов (часы/дни).
        // Теперь: трактуем rollback как «пора освежиться», reset и даём сети шанс.
        if (age > VPN_BLOCKED_COOLDOWN_MS || age < 0) {
            vpnBlocked = false;
            vpnBlockedAt = 0;
            logDiag('net', 'vpnBlocked_reset', { ageMs: age });
        } else {
            logDiag('net', 'proxy_list_skipped', { reason: 'vpnBlocked', ageMs: age });
            return [];
        }
    }
    const extId = chrome.runtime.id || '';
    const uid = await getUID();
    // [v2.6.1] ts с компенсацией clockOffsetSec (0 до первого err:"clock")
    let ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
    let retriedOnClockErr = false;
    try {
        while (true) {
            logDiag('net', 'proxy_list_start', { ext: extId, ver: EXT_VERSION, clientTs: ts, uid: uid.slice(0, 10) });
            const nonce = bytes2hex(crypto.getRandomValues(new Uint8Array(16)));
            const sigInput = uid + '|' + ts + '|' + nonce + '|' + extId + '|' + EXT_VERSION;
            const sig = await hmacSignHex(hex2bytes(HMAC_KEY_HEX), sigInput);

            const res = await apiFetch(PROXY_LIST_PATH, {
                method: 'POST',
                cache: 'no-store',
                headers: {
                    'X-AnonVPN-Proto': String(PROTO_VERSION),
                    'X-AnonVPN-Version': EXT_VERSION,
                    'X-AnonVPN-ExtID': extId,
                    'X-AnonVPN-UID': uid,
                    'X-AnonVPN-Timestamp': String(ts),
                    'X-AnonVPN-Nonce': nonce,
                    'X-AnonVPN-Sig': sig
                },
                // [v2.5.8] 7 сек, чтобы успеть упасть до 10-сек race в doToggleProxy
                signal: AbortSignal.timeout(7000)
            });
            if (!res.ok) {
                // [v2.5.8] Парсим тело даже на 403 – может быть version_too_old/unknown_ext_id
                let errCode = null;
                try {
                    const errBody = await res.json();
                    if (errBody && typeof errBody.err === 'string') errCode = errBody.err;
                    if (errBody && errBody.err === 'version_too_old') {
                        await handleVersionBlocked(errBody);
                    } else if (errBody && errBody.err === 'unknown_ext_id') {
                        await handleIllegalExtId();
                    } else if (errBody && errBody.err === 'rate_limited') {
                        // [v2.8.0] Bot-detection ban: temporary block 24h
                        await handleRateLimited(errBody);
                    }
                } catch { /* not JSON or parse error */ }
                logDiag('net', 'proxy_list_err', { status: res.status, err: errCode });
                // [v2.6.1] err:"clock" – часы клиента ушли за окно сервера. Запрашиваем
                // серверное время, считаем offset, один раз ретраим с подправленным ts.
                if (res.status === 401 && errCode === 'clock' && !retriedOnClockErr) {
                    retriedOnClockErr = true;
                    const newOffset = await fetchServerClockOffset();
                    if (newOffset !== null) {
                        clockOffsetSec = newOffset;
                        logDiag('net', 'clock_adjusted', { offsetSec: newOffset });
                        ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
                        continue;
                    }
                }
                // [v2.8.4] Сохраняем причину фейла для popup'а – но ТОЛЬКО если это не один
                // из 403-кейсов c собственным баннером (rate_limited/version_too_old/unknown_ext_id).
                // Те уже обработаны выше (handleRateLimited / handleVersionBlocked / handleIllegalExtId)
                // и показывают свой specific banner – общий «нет серверов»-fallback не нужен.
                if (errCode !== 'rate_limited' && errCode !== 'version_too_old' && errCode !== 'unknown_ext_id') {
                    try { await chrome.storage.local.set({ proxyListFetchError: 'server', proxyListFetchErrorAt: Date.now() }); } catch {}
                }
                throw new Error('HTTP ' + res.status);
            }
            const env = await res.json();
            // Detect clock skew: compare client-sent ts with server-returned ts
            if (env && typeof env.ts === 'number') {
                const skew = ts - env.ts;
                if (Math.abs(skew) > 30) {
                    logDiag('net', 'clock_skew', { skew });
                }
            }
            const data = await decryptProxyListResponse(env, uid, extId, EXT_VERSION);

            // [v2.5.8 audit] Успешный ответ – снимаем блокировку (вдруг сервер изменил конфиг)
            vpnBlocked = false;
            vpnBlockedAt = 0;
            // [v2.7.1 fix F99] Безусловно стираем `illegalExtId` (раньше очищался только в
            // handleIllegalExtId через `data.update_required` ветку и легко переживал admin
            // unblock). После F96 stale flag триггерил vpnBlocked recovery → permanent block.
            try { await chrome.storage.local.remove(['illegalExtId']); } catch {}

            if (data.update_required) {
                // [v2.6.6 audit] await – иначе SW может быть выгружен между set() и реальной
                // записью в chrome.storage. Флаг updateRequired должен успеть persist'нуться до
                // следующего onMessage в popup, иначе баннер не появится до очередного рестарта.
                await chrome.storage.local.set({ updateRequired: true, minVersion: data.min_version || '' });
            } else {
                // [v2.8.0 audit r3] +rateLimited/rateLimitedUntil/rateLimitedReason – после
                // server-side ban-lift (admin вручную или автоматический unban) успешный
                // fetch должен убрать rateLimit-banner. Раньше banner оставался до version
                // bump (STALE_KEYS wipe) или Clear Cache, юзер думал что блок не снят.
                await chrome.storage.local.remove(['updateRequired', 'minVersion', 'updateUrl', 'illegalExtId', 'rateLimited', 'rateLimitedUntil', 'rateLimitedReason']);
            }
            const rawProxies = (data.ok && Array.isArray(data.proxies)) ? data.proxies : [];
            // [v2.6.2 audit] Defense-in-depth: фильтруем невалидные элементы. Если сервер
            // вернёт поломанные записи, renderProxySelect/applySelectedProxy упадут на .host.
            const proxies = rawProxies.filter(p =>
                p && typeof p === 'object'
                && typeof p.host === 'string' && p.host.length > 0
                && (typeof p.port === 'number' || typeof p.port === 'string')
                // [v3.1.5 audit В2] https-ноды (scheme:'https', IP-preauth) законно без креденшелов —
                // connect-путь их терпит (updateCredentialCache/setProxyAuthRule no-op при !username).
                // Требуем креды строками только для обычных (http) прокси, иначе https-ноды молча
                // выпадали из serverList → pickBestServer их не видел.
                && (p.scheme === 'https' || (typeof p.username === 'string' && typeof p.password === 'string'))
            ).map(p => {
                if (typeof p.username !== 'string') p.username = '';
                if (typeof p.password !== 'string') p.password = '';
                return p;
            });
            logDiag('net', 'proxy_list_ok', { count: proxies.length, serverTs: env.ts });
            // [v2.8.4] Успешный fetch – сбрасываем сохранённую причину прошлого фейла.
            try { await chrome.storage.local.remove(['proxyListFetchError', 'proxyListFetchErrorAt']); } catch {}
            return proxies;
        }
    } catch (err) {
        // Network/crypto error fetching proxy list – fallback to cache
        logDiag('net', 'proxy_list_catch', { msg: (err && err.message) ? String(err.message).slice(0, 80) : 'unknown' });
        // [v2.8.4] Сохраняем причину для popup'а. AbortError / NetworkError / fetch timeout = network.
        // Если выше throw был с префиксом 'HTTP ' – proxyListFetchError уже стоит = 'server', не дублируем.
        const isHttpThrow = err && err.message && /^HTTP /.test(String(err.message));
        // [v3.1.5 audit М3] Парс/крипто-ошибка на 2xx (пустое тело, битый JSON, MAC-fail) — это сбой
        // СЕРВЕРА/ответа, а не сети. Не помечаем как 'network' (иначе юзеру «нет интернета» при живой сети).
        const isParseThrow = err && (err.name === 'SyntaxError' || /JSON|decrypt|MAC|parse/i.test(String((err && err.message) || '')));
        if (!isHttpThrow) {
            try { await chrome.storage.local.set({ proxyListFetchError: isParseThrow ? 'server' : 'network', proxyListFetchErrorAt: Date.now() }); } catch {}
        }
        return [];
    }
}

// [v2.6.1] Получить смещение clock клиента относительно сервера. Идёт в timestamp.php
// (он в BYPASS_LIST, подписи не требует). Sanity-кап ±24ч – защита от поломки сервера.
async function fetchServerClockOffset() {
    try {
        const res = await apiFetch('/AnonVPN/timestamp.php', {
            method: 'GET',
            cache: 'no-store',
            signal: AbortSignal.timeout(5000)
        });
        if (!res.ok) { logDiag('net', 'clock_offset_fail', { status: res.status }); return null; }
        const txt = await res.text();
        const serverTs = parseInt(String(txt).trim(), 10);
        if (!isFinite(serverTs) || serverTs <= 0) { logDiag('net', 'clock_offset_fail', { reason: 'non_numeric' }); return null; }
        const offset = serverTs - Math.floor(Date.now() / 1000);
        // [v2.8.1 audit] >24h offset = compromised сервер или реально неправильные клиентские
        // часы. Блокируем подобные значения чтобы не сломать HMAC-подпись для всех версионных
        // запросов на следующий час (replay-window сервера ±300с).
        if (Math.abs(offset) > 24 * 3600) { logDiag('net', 'clock_offset_fail', { reason: 'out_of_range', offsetSec: offset }); return null; }
        return offset;
    } catch (e) {
        // [v2.8.1 audit] silent return null раньше скрывал network/timeout проблемы;
        // диагностика помогает отличить «timestamp.php недоступен» от «clock skew valid».
        logDiag('net', 'clock_offset_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        return null;
    }
}

// [v2.8.0] Build standard HMAC headers for AnonVPN endpoints (proxy_list / recover-premium /
// request-trial / check-account / link-uid). Returns {headers, ts} – caller can re-use ts
// to detect server-skew for clock-error retry.
async function buildHmacHeaders() {
    const uid = await getUID();
    const extId = chrome.runtime.id || '';
    const ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
    const nonce = bytes2hex(crypto.getRandomValues(new Uint8Array(16)));
    const sigInput = uid + '|' + ts + '|' + nonce + '|' + extId + '|' + EXT_VERSION;
    const sig = await hmacSignHex(hex2bytes(HMAC_KEY_HEX), sigInput);
    return {
        uid: uid,
        headers: {
            'Content-Type': 'application/json',
            'X-AnonVPN-Proto': String(PROTO_VERSION),
            'X-AnonVPN-Version': EXT_VERSION,
            'X-AnonVPN-ExtID': extId,
            'X-AnonVPN-UID': uid,
            'X-AnonVPN-Timestamp': String(ts),
            'X-AnonVPN-Nonce': nonce,
            'X-AnonVPN-Sig': sig
        }
    };
}

// [v2.8.0] Read-only возврат текущего account-state из storage.
// УПРОЩЕНО: после успешного link-uid флаг accountVerified ставится один раз и не
// перепроверяется. Server-side check-account.php эндпоинт оставлен на сервере для
// совместимости, но не вызывается. Логика: если юзер найдёт способ keep 60-min обходом
// (например админ revoke email_verified, но storage не обновится) – единичные случаи,
// not worth серверной нагрузки на регулярные пинги.
async function checkAccountStatus(_force) {
    try {
        const d = await chrome.storage.local.get(['accountVerified', 'accountEmail']);
        return {
            ok: true,
            cached: true,
            verified: d.accountVerified === true,
            email: d.accountEmail || ''
        };
    } catch {
        return { ok: false, reason: 'storage_err' };
    }
}

// [v2.8.0] Bind UID to web user via 8-hex code from site. Server-side sanitizes the code
// and re-binds web_user → uid в БД. Server response: {ok, verified, email_obfuscated}.
async function linkUidWithCode(code) {
    let retried = false;
    while (true) {
        let h;
        try { h = await buildHmacHeaders(); } catch (e) { return { ok: false, reason: 'hmac_err' }; }
        let res;
        try {
            res = await apiFetch(LINK_UID_PATH, {
                method: 'POST',
                cache: 'no-store',
                headers: h.headers,
                body: JSON.stringify({ code }),
                signal: AbortSignal.timeout(10000)
            });
        } catch (e) {
            logDiag('account', 'link_fetch_err', { msg: String((e && e.message) || '').slice(0, 80) });
            return { ok: false, reason: 'network_error' };
        }
        let body = null;
        try { body = await res.json(); } catch (_) { body = null; }
        if (!res.ok) {
            const reason = (body && body.reason) ? String(body.reason) : ('http_' + res.status);
            if (res.status === 401 && body && body.reason === 'clock' && !retried) {
                retried = true;
                const newOffset = await fetchServerClockOffset();
                if (newOffset !== null) {
                    clockOffsetSec = newOffset;
                    continue;
                }
            }
            logDiag('account', 'link_http_err', { status: res.status, reason });
            return { ok: false, reason };
        }
        // [v2.8.0 audit r3] body=null + res.ok=true (CDN error page, JSON parse fail) раньше
        // молча сохранял verified=false, email='' → юзер видел «привязка прошла» в UI, но
        // accountVerified=false, сессия оставалась 30 мин. Возвращаем явный error чтобы юзер
        // мог ретраить.
        if (!body || typeof body !== 'object') {
            logDiag('account', 'link_bad_resp', {});
            return { ok: false, reason: 'bad_server_response' };
        }
        const verified = !!body.verified;
        // [v2.8.0 audit r5+r6] Length cap для server-controlled email_obfuscated. RFC 5321 email
        // max = 254 chars. Round 6 fix: Array.from() итерирует по code-points (Unicode-aware),
        // .slice(0,256) на UTF-16 code-units могла разрезать surrogate pair (emoji/CJK) →
        // invalid Unicode → textContent renders U+FFFD. Array.from возвращает массив с surrogate
        // pair как 1 элемент, .join('') reconstructs valid string. Edge case (most emails ASCII),
        // но без cost.
        const emailRaw = body.email_obfuscated ? String(body.email_obfuscated) : '';
        const email = emailRaw ? Array.from(emailRaw).slice(0, 256).join('') : '';
        try {
            await chrome.storage.local.set({
                accountVerified: verified,
                accountEmail: email
            });
        } catch (e) {
            // [v2.8.0 audit] storage.set fail (quota) – server в БД уже привязал UID, но клиент
            // не может persist флаг → следующий toggle не получит 60 мин. Возвращаем error
            // вместо tihogo ok:true – popup покажет «Не удалось сохранить» и юзер поймёт что
            // нужно очистить кэш / ретраить. На сервере остается lingering link, но он
            // перезатрётся при следующем gen_ext_code (UNIQUE constraint).
            logDiag('account', 'link_store_err', { msg: String((e && e.message) || '').slice(0, 80) });
            return { ok: false, reason: 'storage_quota_exceeded' };
        }
        logDiag('account', 'link_ok', { verified });
        return { ok: true, verified, email };
    }
}

// [v2.5.8] Обработка нелегальной копии расширения (ext_id не в whitelist):
// та же логика что и version_blocked – выключаем VPN, чистим кэш, ставим флаг
async function handleIllegalExtId() {
    logDiag('blocked', 'ext_id', { ext: chrome.runtime.id });
    vpnBlocked = true; // [v2.5.8 audit] предотвратить повторные fetch до SW restart / успешного fetch
    vpnBlockedAt = Date.now(); // [v2.6.0] для lazy-reset в fetchProxyList
    // [v2.7.5 audit r3] try/catch – storage quota fail не должен обрывать handler
    // до выключения VPN и broadcast баннера (downstream actions critical).
    try { await chrome.storage.local.set({ illegalExtId: true }); }
    catch (e) { logDiag('blocked', 'set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    // [v2.7.1 fix F126] try/catch – см. handleVersionBlocked, симметрично
    // [v2.7.2 fix F150] +proxyListFetchAt +lastHeartbeatAt – иначе stale TTL после смены ext_id
    try { await chrome.storage.local.remove(['proxyListEnc', 'proxyListFetchAt', 'lastHeartbeatAt']); } catch {}
    serverList = null;
    const enabled = await isProxyEnabled();
    if (enabled) {
        // [v2.8.2 audit-5 F30] cachedCredentials reset ВВЕРХУ – symmetric с VPN_ALARM (audit-4 F27).
        cachedCredentials = null;
        // [v2.8.5 audit R1] Per-step try/catch – symmetric с handleRateLimited (audit-6 F34)
        // и checkPremiumExpiration. Throw в одном step (recordSessionEnd quota-fail и т.п.)
        // НЕ должен пропустить proxyEnabled=false + setProxy(false) → класс v2.6.10 unlimited-VPN.
        try { await recordSessionEnd(); } catch {}
        try { await chrome.storage.local.set({ proxyEnabled: false }); } catch {}
        try { await setProxy(false); } catch {}
        try { updateIcon(false); } catch {}
        try { await clearVpnTimer(); } catch {}
        try { stopHeartbeat(); } catch {}
        // [v2.8.1 audit] reason='illegal_ext' для session-audit.
        try { sendDisconnect('illegal_ext').catch(() => {}); } catch {}
        try { stopKeepalive(); } catch {}
    }
    chrome.runtime.sendMessage({ action: 'illegalExtId' }).catch(() => {});
    // [v2.7.3 audit] reason='illegal' – popup distinguish от generic off
    chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: false, reason: 'illegal' }).catch(() => {});
}

// [v2.5.8] Обработка hard-блокировки версии: выключаем VPN, чистим кэш,
// поднимаем флаг чтобы popup показал баннер «требуется обновление»
async function handleVersionBlocked(errBody) {
    logDiag('blocked', 'version', { minVer: errBody && errBody.min_version, current: EXT_VERSION });
    vpnBlocked = true; // [v2.5.8 audit] предотвратить повторные fetch до SW restart / успешного fetch
    vpnBlockedAt = Date.now(); // [v2.6.0] для lazy-reset в fetchProxyList
    // [v2.6.2 audit] Defense-in-depth: сервер – trusted, но compromised-server scenario
    // может вернуть `data:` или `javascript:` URL → открытие фишинга через chrome.tabs.create.
    const FALLBACK_UPDATE_URL = 'https://chromewebstore.google.com/detail/pieoffaiheelaipjennepjbhnbdhcfck';
    const rawUpdateUrl = errBody.update_url;
    // [v2.6.5 audit] Полная URL-валидация через URL-парсер – ранее regex только проверял
    // начало строки, что позволяло сервер-compromise атаке `https://ok.com#javascript:...` и
    // подобным обходам. Теперь только https: протокол проходит.
    // [v2.6.5 audit r3] Реконструируем URL без userinfo/hash – `u.toString()` сохраняет
    // `https://evil@good.com/...`, что в status-bar'е браузера выглядит как `evil` и может
    // обмануть юзера при compromised-apiget.ru.
    let updateUrl = FALLBACK_UPDATE_URL;
    if (typeof rawUpdateUrl === 'string') {
        try {
            const u = new URL(rawUpdateUrl);
            if (u.protocol === 'https:') updateUrl = u.origin + u.pathname + u.search;
        } catch { /* malformed URL – fallback остаётся */ }
    }
    // [v2.7.5 audit r3] try/catch – storage quota fail не должен прерывать version-block
    // handler (downstream: VPN disable, broadcast баннер, cache wipe). Лучше частично
    // обработать blocking чем aborting middlway.
    try {
        await chrome.storage.local.set({
            updateRequired: true,
            minVersion: errBody.min_version || '',
            updateUrl: updateUrl
        });
    } catch (e) { logDiag('blocked', 'set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    // Стираем зашифрованный кэш и память – нельзя дать использовать старую версию
    // [v2.7.1 fix F126] try/catch – storage.remove fail не должен прерывать остальной cleanup
    // (выключение VPN, broadcast баннера). Кэш будет повторно затёрт на следующем 403.
    // [v2.7.2 fix F150] +proxyListFetchAt +lastHeartbeatAt – иначе TTL-guard блокирует refresh
    try { await chrome.storage.local.remove(['proxyListEnc', 'proxyListFetchAt', 'lastHeartbeatAt']); } catch {}
    serverList = null;
    // Если VPN активен – выключаем
    const enabled = await isProxyEnabled();
    if (enabled) {
        // [v2.8.2 audit-5 F30] cachedCredentials reset ВВЕРХУ – symmetric с handleIllegalExtId.
        cachedCredentials = null;
        // [v2.8.5 audit R1] Per-step try/catch – symmetric с handleRateLimited / checkPremiumExpiration.
        // Throw в одном step не должен оставить proxyEnabled=true = unlimited-VPN (класс v2.6.10).
        try { await recordSessionEnd(); } catch {}
        try { await chrome.storage.local.set({ proxyEnabled: false }); } catch {}
        try { await setProxy(false); } catch {}
        try { updateIcon(false); } catch {}
        try { await clearVpnTimer(); } catch {}
        try { stopHeartbeat(); } catch {}
        // [v2.8.1 audit] reason='version_too_old' для session-audit.
        try { sendDisconnect('version_too_old').catch(() => {}); } catch {}
        try { stopKeepalive(); } catch {}
    }
    // Уведомляем popup
    chrome.runtime.sendMessage({
        action: 'updateRequired',
        minVersion: errBody.min_version || '',
        updateUrl: updateUrl
    }).catch(() => {});
    // [v2.7.3 audit] reason='updateRequired' – popup distinguish от generic off
    chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: false, reason: 'updateRequired' }).catch(() => {});
}

// [v2.8.0] Обработка rate_limited бана. Структурно идентичен handleVersionBlocked /
// handleIllegalExtId: vpnBlocked=true, wipe кэша, выключение VPN, broadcast баннера.
// Но НЕ ставим updateRequired (юзер не должен получать кнопку «обновить» – это не про версию).
// Premium-активация снимает rate_limit на сервере (см. cron – premium=0 фильтр), на клиенте
// обнуляется при следующем успешном fetch (vpnBlocked=false, removed rateLimited storage).
async function handleRateLimited(errBody) {
    const reason = (errBody && typeof errBody.reason === 'string') ? errBody.reason.slice(0, 40) : 'rate_limited';
    const until = (errBody && typeof errBody.until === 'string') ? errBody.until.slice(0, 32) : '';
    logDiag('blocked', 'rate_limit', { reason: reason, until: until });
    vpnBlocked = true;
    vpnBlockedAt = Date.now();
    try {
        await chrome.storage.local.set({
            rateLimited: true,
            rateLimitedReason: reason,
            rateLimitedUntil: until
        });
    } catch (e) { logDiag('blocked', 'rl_set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    // Стираем зашифрованный кэш + TTL-таймстампы (как при version-blocked / illegal-ext)
    try { await chrome.storage.local.remove(['proxyListEnc', 'proxyListFetchAt', 'lastHeartbeatAt']); } catch {}
    serverList = null;
    // Выключаем VPN если активен
    const enabled = await isProxyEnabled();
    if (enabled) {
        // [v2.8.2 audit-6 F34] cachedCredentials reset ВВЕРХУ – symmetric с handleIllegalExtId,
        // handleVersionBlocked, doToggleProxy OFF, VPN_ALARM (audit-4 F27, audit-5 F30).
        // Раньше был внизу + обёрнут в try/catch – early throw в одном из step'ов мог
        // пропустить reset → stale premium creds leak в onAuthRequired при следующем connect.
        cachedCredentials = null;
        try { await recordSessionEnd(); } catch {}
        try { await chrome.storage.local.set({ proxyEnabled: false }); } catch {}
        try { await setProxy(false); } catch {}
        try { updateIcon(false); } catch {}
        try { await clearVpnTimer(); } catch {}
        try { stopHeartbeat(); } catch {}
        // sendDisconnect c reason='rate_limited' – для session-audit
        try { sendDisconnect('rate_limited').catch(() => {}); } catch {}
        try { stopKeepalive(); } catch {}
    }
    chrome.runtime.sendMessage({ action: 'rateLimited', reason: reason, until: until }).catch(() => {});
    chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: false, reason: 'rate_limited' }).catch(() => {});
}

// [v2.5.8] In-memory + зашифрованный кэш. Plaintext в storage больше не пишется.
let serverListPromise = null; // защита от параллельных сетевых fetch

// [v2.6.9] TTL для фонового рефреша proxy_list.php.
// v2.6.7 ввёл in-memory `_lastProxyListFetchAt` + 5-мин TTL, но MV3 убивает SW
// каждые ~30 сек idle – на cold-wake переменная сбрасывалась в 0, age=∞, TTL не работал.
// v2.6.9: храним timestamp в chrome.storage.local – TTL переживает SW-restart.
// Forced-refresh пути (toggle ON, premium activate, recovery, trial) идут в сеть мимо TTL.
const PROXY_LIST_REFRESH_TTL_MS = 5 * 60 * 1000;
const PROXY_LIST_FETCH_AT_KEY = 'proxyListFetchAt';

// [v2.7.1 fix F83] Удалена dead function getLastProxyListFetchAt – никогда не вызывалась,
// inline-чтение в ensureProxyList (через batch storage.get) покрывает use-case.

async function setLastProxyListFetchAt(ts) {
    await chrome.storage.local.set({ [PROXY_LIST_FETCH_AT_KEY]: ts });
}

// [v2.8.0] One-shot apply default-exclusions для high-ping стран. Триггер: первая загрузка
// серверного списка (любым путём – cache, fetch, fallback). Идемпотентен: проверяет sentinel
// `defaultAutoSelectExclusionsApplied !== true`, после применения ставит true → больше не fire'ит.
//
// Идентификатор сервера в excludedFromAutoSelect – `host:port` строка (см. popup.js:200, 203).
// Раньше я ошибочно писал `srv.id` который в server-объекте отсутствует → 0 совпадений → флаг
// снимался без эффекта. Sentinel переименован чтобы юзеры с stale `firstInstallExclusionsPending=false`
// получили повторный apply на новой логике.
async function applyFirstInstallExclusionsIfPending(list) {
    try {
        const d = await chrome.storage.local.get(['defaultAutoSelectExclusionsApplied', 'excludedFromAutoSelect']);
        if (d.defaultAutoSelectExclusionsApplied === true) return; // уже применено
        if (!Array.isArray(list) || list.length === 0) return; // ждём непустой список
        const existing = Array.isArray(d.excludedFromAutoSelect) ? d.excludedFromAutoSelect : [];
        const exclSet = new Set(existing);
        const adds = [];
        for (const srv of list) {
            if (!srv || !srv.host || !srv.port) continue;
            const cc = String(srv.country || '').toUpperCase();
            if (FIRST_INSTALL_EXCLUDE_COUNTRIES.indexOf(cc) < 0) continue;
            const id = srv.host + ':' + srv.port; // формат как в popup.js:200,203
            if (exclSet.has(id)) continue;
            adds.push(id);
            exclSet.add(id);
        }
        // Даже при 0 совпадений ставим sentinel=true чтобы не зацикливаться на проверке при
        // каждом load. Если country-кодов KR/TW/TR/JP в серверном списке нет – это просто
        // значит сервера удалены админом, для юзера done.
        const set = { defaultAutoSelectExclusionsApplied: true };
        if (adds.length > 0) set.excludedFromAutoSelect = existing.concat(adds);
        await chrome.storage.local.set(set);
        logDiag('init', 'default_exclusions_applied', { added: adds.length, listSize: list.length });
    } catch (e) {
        logDiag('init', 'default_exclusions_fail', { msg: String((e && e.message) || '').slice(0, 80) });
    }
}

async function doRefreshProxyList() {
    if (serverListPromise) return serverListPromise;
    serverListPromise = (async () => {
        // [v3.1.5 audit М1] Снимок vpnBlocked: если за время fetch сработал security-block
        // (version_too_old / illegal_ext / rate_limited — все ставят vpnBlocked=true, обнуляют
        // serverList и стирают proxyListEnc), НЕ воскрешаем список и зашифрованный кэш.
        const _blockedAtStart = vpnBlocked;
        const fresh = await fetchProxyList();
        if (!_blockedAtStart && vpnBlocked) {
            logDiag('net', 'refresh_discarded_blocked', null);
            return [];
        }
        if (fresh.length > 0) {
            // [v2.6.9] persisted TTL-гвард; try/catch чтобы редкий storage.set fail не съел свежий список
            try { await setLastProxyListFetchAt(Date.now()); } catch {}
            serverList = fresh;
            // [v2.8.2 audit-2] try/catch на cache-save: storage quota / crypto fail не должен
            // отменять ENTIRE doRefreshProxyList – fresh уже в memory (line above), callers
            // получают valid list. Без guard'а IIFE rejected → все awaited callers throw.
            try { await saveListToEncryptedCache(fresh); }
            catch (e) { logDiag('net', 'cache_save_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
            // [v2.8.0] Apply one-shot default-exclusions для high-ping стран. Идёт ПОСЛЕ
            // saveListToEncryptedCache чтобы не блокировать критический путь returning fresh list.
            applyFirstInstallExclusionsIfPending(fresh).catch(() => {});
            return fresh;
        }
        // [v2.5.8] Сеть упала – fallback на зашифрованный кэш
        // [v2.6.0] КРИТИЧНО: если в памяти уже был непустой список, не затираем его –
        // пустой результат от сети означает транзиентную ошибку, а не реальное отсутствие серверов.
        if (Array.isArray(serverList) && serverList.length > 0) {
            logDiag('net', 'preserve_inmem', { count: serverList.length });
            return serverList;
        }
        const cached = await loadListFromEncryptedCache();
        if (cached && cached.length > 0) {
            serverList = cached;
            applyFirstInstallExclusionsIfPending(cached).catch(() => {});
            logDiag('net', 'fallback_cache', { count: cached.length });
            return serverList;
        }
        logDiag('net', 'list_empty_fallback', null);
        return [];
    })().finally(() => { serverListPromise = null; });
    return serverListPromise;
}

// [v2.9.2 critical fix] Defensive premium-mismatch check: если юзер Premium И в текущем
// списке нет ни одного premium-сервера – запускаем background refresh. Покрывает кейсы:
// (a) premiumActivated message потерян, (b) серверный кэш premium-check вернул stale,
// (c) предыдущий fetch произошёл до того как юзер стал Premium. Не блокирует callers.
// Broadcast'им popup'у когда premium-сервера действительно пришли – для перерисовки UI.
let _premiumMismatchRefreshInFlight = false;
async function _kickPremiumMismatchRefreshIfNeeded(currentList) {
    try {
        if (_premiumMismatchRefreshInFlight) return;
        const d = await chrome.storage.local.get(['isPremium']);
        if (!d.isPremium) return;
        const arr = Array.isArray(currentList) ? currentList : [];
        const hasPremium = arr.some(p => p && p.type === 'premium');
        if (hasPremium) return;
        if (serverListPromise) return; // уже идёт refresh
        logDiag('premium', 'mismatch_refresh', { listLen: arr.length });
        _premiumMismatchRefreshInFlight = true;
        (async () => {
            try {
                const fresh = await doRefreshProxyList();
                const freshHasPremium = Array.isArray(fresh) && fresh.some(p => p && p.type === 'premium');
                logDiag('premium', 'mismatch_refresh_done', { listLen: (fresh || []).length, premium: freshHasPremium });
                if (freshHasPremium) {
                    // popup перерендерит список – увидит premium-серверы без reopen
                    chrome.runtime.sendMessage({ action: 'proxyListUpdated', premiumAdded: true }).catch(() => {});
                }
            } catch (e) {
                logDiag('premium', 'mismatch_refresh_fail', { msg: String((e && e.message) || '').slice(0, 80) });
            } finally {
                _premiumMismatchRefreshInFlight = false;
            }
        })();
    } catch (_) {}
}

async function ensureProxyList(forceRefresh) {
    // forceRefresh: всегда сеть, ждём результата
    if (forceRefresh) return doRefreshProxyList();
    // Memory hit – моментально
    // [v2.8.0] applyFirstInstallExclusionsIfPending – также на memory-hit, потому что
    // ensureProxyList может вернуться до того как любой network-fetch произойдёт (cold-wake
    // SW → onAuthRequired → init с уже-cached serverList).
    if (Array.isArray(serverList) && serverList.length > 0) {
        applyFirstInstallExclusionsIfPending(serverList).catch(() => {});
        _kickPremiumMismatchRefreshIfNeeded(serverList);
        return serverList;
    }
    // Если уже идёт сетевой запрос – ждём его
    if (serverListPromise) return serverListPromise;
    // Cache hit – возвращаем сразу, в фоне освежаем (но не чаще раз в TTL).
    // [v2.6.9] Batch один storage.get для encrypted-кэша + TTL-timestamp вместо двух последовательных
    // (экономия ~3-5мс на cache-hit'е, который в hot path popup-open).
    const storedData = await chrome.storage.local.get(['proxyListEnc', PROXY_LIST_FETCH_AT_KEY]);
    const cached = await decryptCachedList(storedData.proxyListEnc);
    if (cached && cached.length > 0) {
        serverList = cached;
        // [v2.8.0] Apply default-exclusions при cache-hit (typical hot path: cold-wake SW →
        // popup открыт → ensureProxyList без forceRefresh → cache-hit → return). Без этого
        // юзеры с заранее cached'нутым proxyListEnc никогда не получили бы first-install defaults.
        applyFirstInstallExclusionsIfPending(cached).catch(() => {});
        // [v2.9.2 critical fix] Premium-mismatch refresh – см. helper выше.
        _kickPremiumMismatchRefreshIfNeeded(cached);
        // [v2.6.9] Persisted TTL-гвард переживает MV3 SW-restart.
        // age < 0 = часы юзера откатились назад (NTP-resync/ручная установка); считаем кэш
        // протухшим, иначе зависнем без рефреша до тех пор, пока часы не догонят lastAt.
        const lastAt = Number(storedData[PROXY_LIST_FETCH_AT_KEY]) || 0;
        const age = Date.now() - lastAt;
        if (age > PROXY_LIST_REFRESH_TTL_MS || age < 0) {
            // [v3.1.5 audit М2] НЕ пишем TTL заранее: doRefreshProxyList сам ставит его ТОЛЬКО после
            // успешного непустого fetch. Иначе неудачный фоновый рефреш (сеть легла / SW убит на await)
            // всё равно бампал TTL → 5 мин без ретрая на протухшем списке. Штурм-дедуп concurrent-рефрешей
            // обеспечивает serverListPromise-мьютекс внутри doRefreshProxyList.
            doRefreshProxyList().catch(() => {}); // фон, не блокируем
        } else {
            logDiag('net', 'bg_skipped_ttl', { ageMs: age });
        }
        return serverList;
    }
    // Cache miss – ждём сеть
    // [v2.6.0] Если первый fetch вернул пусто И памяти/кэша тоже нет, делаем ОДНУ повторную
    // попытку через 2 сек. Покрывает транзиентные сбои сети при первом открытии popup.
    const first = await doRefreshProxyList();
    if (Array.isArray(first) && first.length > 0) return first;
    if (Array.isArray(serverList) && serverList.length > 0) return serverList;
    logDiag('net', 'retry_scheduled', null);
    await new Promise(r => setTimeout(r, 2000));
    return doRefreshProxyList();
}

async function applySelectedProxy() {
    const data = await chrome.storage.local.get(['selectedProxy', 'isPremium']);
    let proxy = data.selectedProxy;
    // [v2.5.8] proxyList – в памяти SW. Если ещё не загружен, подтягиваем.
    let list = serverList;
    if (!Array.isArray(list) || list.length === 0) list = await ensureProxyList();
    list = list || [];
    const isPremium = !!data.isPremium;

    // Блокировка: free-пользователь не может использовать premium-сервер
    if (proxy && proxy.type === 'premium' && !isPremium) {
        const firstFree = list.find(p => p.type !== 'premium');
        proxy = firstFree || (list.length > 0 ? list[0] : null);
        if (proxy) await chrome.storage.local.set({ selectedProxy: proxy });
    }

    // [v2.7.1 fix F95] Stale-server fallback: после browser restart / server-side cleanup
    // selectedProxy может ссылаться на сервер, которого больше нет в свежем serverList.
    // Без проверки applySelectedProxy применит stale host:port → ERR_TUNNEL_CONNECTION_FAILED,
    // юзер видит «нет интернета» и не понимает причину. Подменяем на адекватный fallback.
    // [v2.7.1 fix F100] Premium-aware fallback: paid premium юзер не должен silently
    // получать free-сервер. Сначала пытаемся подобрать другой premium из списка.
    if (proxy && Array.isArray(list) && list.length > 0) {
        const stillExists = list.some(p => p && p.host === proxy.host && String(p.port) === String(proxy.port));
        if (!stillExists) {
            // [v3.0.5] Выбранный сервер исчез из свежего списка (удалён на сервере / stale-список у клиента).
            // РАНЬШЕ молча брали ПЕРВЫЙ free-сервер → юзер выбрал X, попал на «первый» БЕЗ предупреждения.
            // Теперь: ЛУЧШИЙ доступный (swPickExcludingBroken – исключает битые/excluded, по нагрузке) + УВЕДОМЛЯЕМ.
            // selectedProxy обновляем → уведомление сработает один раз (следующий apply увидит валидный сервер).
            let fallback = null;
            try { fallback = await swPickExcludingBroken(''); } catch (e) {}
            if (!fallback) {
                fallback = isPremium ? (list.find(p => p.type === 'premium') || list.find(p => p.type !== 'premium') || list[0])
                                     : (list.find(p => p.type !== 'premium') || list[0]);
            }
            logDiag('toggle', 'stale_proxy_fallback', { from: String(proxy.host || '').slice(0, 30), to: String((fallback && fallback.host) || '').slice(0, 30), prem: !!isPremium });
            proxy = fallback;
            await chrome.storage.local.set({ selectedProxy: proxy });
            try { swNotifyI18n('stale_switch', 'staleSwitchTitle', 'staleSwitchText', 'Сервер сменился', 'Выбранный сервер стал недоступен – мы подключили вас к другому рабочему серверу.'); } catch (e) {}
            try { chrome.runtime.sendMessage({ action: 'serverSwitched', reason: 'stale' }).catch(function(){}); } catch (e) {}
        }
    }

    if (!proxy && list.length > 0) {
        proxy = list.find(p => p.type !== 'premium') || list[0];
        await chrome.storage.local.set({ selectedProxy: proxy });
    }
    if (!proxy) {
        await chrome.proxy.settings.set({ value: { mode: 'direct' }, scope: 'regular' });
        await clearProxyAuthRule();
        return false; // [v2.5.4] сигнал: прокси не применён
    }

    // [v2.7.1 fix F86] Defense-in-depth: validate proxy.host (non-empty string) и
    // proxy.port (1-65535 integer). Данные приходят с HMAC-подписанного сервера, но
    // corrupt storage или будущий рефактор могут подсунуть malformed объект – setProxy
    // с пустым host даст PAC 'PROXY :NaN', Chrome тихо отклонит конфиг → VPN не включается.
    const portNum = parseInt(proxy.port, 10);
    if (typeof proxy.host !== 'string' || proxy.host.trim() === '' ||
        !Number.isFinite(portNum) || portNum < 1 || portNum > 65535) {
        logDiag('toggle', 'invalid_proxy', { hostType: typeof proxy.host, port: String(proxy.port).slice(0, 10) });
        await chrome.proxy.settings.set({ value: { mode: 'direct' }, scope: 'regular' });
        await clearProxyAuthRule();
        return false;
    }

    updateCredentialCache(proxy);

    // Load exclusions config
    const exclData = await chrome.storage.local.get(['excludedDomains', 'exclusionsMode', 'bypassRuDomains']);
    const excluded = exclData.excludedDomains || [];
    const mode = exclData.exclusionsMode || 'blacklist'; // 'blacklist' | 'whitelist'
    // [v2.8.8] bypassRuDomains: default true. Активный → +*.ru/*.рф/*.xn--p1ai в BYPASS.
    const bypassRuOn = (exclData.bypassRuDomains !== false);
    const effectiveBypass = bypassRuOn ? [...BYPASS_LIST, ...RU_BYPASS_DOMAINS] : [...BYPASS_LIST];
    // [v3.1.5] TLS-нода с IP-preauth (вариант A): у неё нет proxy-авторизации (firewall пускает по
    // allowlist). Регистрируем свой IP через balancing ДО установки прокси (preauth идёт на api.*,
    // которые в bypass → DIRECT → сервер видит реальный IP; на heartbeat повторяется).
    if (_proxyScheme(proxy) === 'https') {
        await _nodePreauth(proxy.host);
    }
    const proxyStr = (_proxyScheme(proxy) === 'https' ? 'HTTPS ' : 'PROXY ') + proxy.host.replace(/[^a-zA-Z0-9.\-\[\]:]/g, '') + ':' + parseInt(proxy.port, 10);

    // [v2.5.4] Proxy-Authorization: ограничиваем отправку только на проксируемые домены.
    // [v2.7.3] Убран && excluded.length > 0 – при пустом whitelist логика должна
    // совпадать с PAC (ничего не прокси), а не падать в else и вести себя как blacklist.
    // [v2.8.8] При bypassRuOn – добавляем RU TLDs в excluded, чтобы DNR не вешал
    // Proxy-Authorization header на DIRECT-routed .ru/.рф (иначе утечка proxy creds к
    // сторонним российским сайтам, которые видят `Basic <base64>` в чистом HTTP).
    const ruAuthExtra = bypassRuOn ? RU_AUTH_EXCLUDE_DOMAINS : [];
    if (mode === 'whitelist') {
        // Whitelist: отправлять заголовок ТОЛЬКО на whitelisted-домены (пустой список = нигде).
        // RU bypass в whitelist mode – edge case (юзер whitelisted .ru + bypassRu=ON);
        // header может уйти если whitelisted host = .ru. Не фиксим – конфликт намерений
        // юзера, исключение должен решать он сам через выключение bypassRu.
        await setProxyAuthRule(proxy, null, excluded.map(d => d.toLowerCase()));
    } else {
        // Blacklist: исключить bypass + blacklisted + (опционально) RU TLDs.
        const blacklistExtra = excluded.map(d => d.toLowerCase()).concat(ruAuthExtra);
        await setProxyAuthRule(proxy, blacklistExtra);
    }

    // [v2.5.1] Sanitize domain for PAC script (prevent injection).
    // [v2.7.3] Lower-case защита: Chrome передаёт host в PAC в lowercase (per PAC spec),
    // но domains в storage могут быть mixed-case из legacy / ручного редактирования.
    // Без .toLowerCase() сравнение `h === "Example.COM"` не совпадёт с `example.com`.
    function sanitizeDomain(d) {
        return d.replace(/[^a-zA-Z0-9.\-*]/g, '').toLowerCase();
    }

    if (mode === 'whitelist') {
        // [v2.7.3] PAC: whitelist = прокси ТОЛЬКО для перечисленных доменов.
        // Пустой whitelist → прокси НИ ДЛЯ ЧЕГО (кроме BYPASS_LIST который всегда DIRECT).
        // До 2.7.3 пустой whitelist падал в else-ветку (fixed_servers+blacklist) и
        // проксировал весь трафик – ровно противоположное поведение.
        const bypassConditions = effectiveBypass.map(d => {
            if (d === '<-loopback>') return 'if(h==="localhost"||h==="127.0.0.1"||h==="[::1]")return D;';
            const sd = sanitizeDomain(d);
            if (sd.startsWith('*.')) return 'if(h.endsWith("' + sd.substring(1) + '"))return D;';
            return 'if(h==="' + sd + '"||h.endsWith(".' + sd + '"))return D;';
        }).join('\n');
        const whiteConditions = excluded.map(d => {
            const sd = sanitizeDomain(d);
            return 'if(h==="' + sd + '"||h.endsWith(".' + sd + '"))return P;';
        }).join('\n');

        const pac = 'function FindProxyForURL(u,h){\n'
            + 'var P="' + proxyStr + '",D="DIRECT";\n'
            + bypassConditions + '\n'
            + whiteConditions + '\n'
            + 'return D;\n}';

        // [v2.8.2 audit-2] try/catch + re-throw на chrome.proxy.settings.set: если позже понадобится
        // diag (storage/permission throw), будет видно в logDiag. Caller doToggleProxy ловит throw в
        // outer Promise.race → rollback to OFF. Без local catch – пропадало без telemetry.
        try {
            await chrome.proxy.settings.set({
                value: { mode: 'pac_script', pacScript: { data: pac } },
                scope: 'regular'
            });
        } catch (e) {
            logDiag('toggle', 'proxy_settings_pac_fail', { msg: String((e && e.message) || '').slice(0, 80) });
            throw e;
        }
    } else {
        // Blacklist: bypass listed domains (default behavior)
        const fullBypass = [...effectiveBypass];
        excluded.forEach(d => { fullBypass.push(d); fullBypass.push('*.' + d); });

        // [v2.8.2 audit-2] См. комментарий выше – symmetric для fixed_servers режима.
        try {
            await chrome.proxy.settings.set({
                value: {
                    mode: 'fixed_servers',
                    rules: {
                        singleProxy: { scheme: _proxyScheme(proxy), host: proxy.host, port: parseInt(proxy.port, 10) },
                        bypassList: fullBypass
                    }
                },
                scope: 'regular'
            });
        } catch (e) {
            logDiag('toggle', 'proxy_settings_fixed_fail', { msg: String((e && e.message) || '').slice(0, 80) });
            throw e;
        }
    }

    // [v2.6.2] Warm-up: prime onAuthRequired/TLS с прокси параллельно, с общим cap 5.5с.
    // До 2.6.2 два последовательных fetch по 5с давали до 10с на медленных сетях (Китай
    // с фильтрацией Cloudflare) – doToggleProxy упирался в свой 10с race → toggle.fail timeout.
    await Promise.race([
        Promise.allSettled([
            fetch('http://cp.cloudflare.com',  { method:'HEAD', cache:'no-store', signal: AbortSignal.timeout(5000) }),
            fetch('https://cp.cloudflare.com', { method:'HEAD', cache:'no-store', signal: AbortSignal.timeout(5000) })
        ]),
        new Promise(r => setTimeout(r, 5500))
    ]);
}

// [FIX #2] setProxy принимает явное состояние, не зависит от in-memory переменной
async function setProxy(enabled) {
    if (enabled === undefined) {
        enabled = await isProxyEnabled();
    }
    if (enabled) {
        await ensureProxyList();
        const ok = await applySelectedProxy();
        if (ok === false) {
            // [v2.5.4] Прокси недоступен – откатываем состояние
            // [v2.7.6 audit Pass13] try/catch – quota fail здесь оставлял in-memory
            // proxyEnabled=true (storage.set throws → не reach updateIcon/clearVpnTimer).
            try { await chrome.storage.local.set({ proxyEnabled: false }); }
            catch (e) { logDiag('toggle', 'rollback_set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
            updateIcon(false);
            await clearVpnTimer();
            stopHeartbeat();
            stopKeepalive();
            cachedCredentials = null;
            // [v2.7.3 audit] reason='illegal' – popup distinguish от generic off
            chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: false, reason: 'illegal' }).catch(() => {});
            return false;
        }
    } else {
        // [v2.8.0 audit r2] Per-step try/catch – без него throw на chrome.proxy.settings.set
        // (rare: extension context invalidated, policy override) пропускал clearProxyAuthRule
        // и cachedCredentials=null. Stale auth rule + stale creds на следующем toggle ON =
        // 407 Proxy-Auth Required на новом сервере. Симметрично VPN_ALARM disconnect F2.
        try { await chrome.proxy.settings.set({ value: { mode: 'direct' }, scope: 'regular' }); }
        catch (e) { logDiag('toggle', 'set_direct_fail', { msg: String((e && e.message) || e).slice(0, 80) }); }
        try { await clearProxyAuthRule(); }
        catch (e) { logDiag('toggle', 'clear_auth_fail', { msg: String((e && e.message) || e).slice(0, 80) }); }
        cachedCredentials = null;
    }
}

// === TIMER LOGIC ===
async function startVpnTimer() {
    const d = await chrome.storage.local.get(['isPremium']);
    if (d.isPremium) {
        // [v2.7.6 audit Pass13] Per-step try/catch – quota fail на storage.remove
        // не должен прерывать alarms.clear (или наоборот). Симметрично с clearVpnTimer.
        try { await chrome.alarms.clear(VPN_ALARM_NAME); } catch (e) { logDiag('timer', 'prem_alarm_clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await chrome.alarms.clear(VPN_WARN_ALARM_NAME); } catch (e) { logDiag('timer', 'prem_warn_clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await chrome.storage.local.remove(VPN_DEADLINE_KEY); } catch (e) { logDiag('timer', 'prem_deadline_remove_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        return;
    }
    // [v2.8.0] Dynamic duration: 30 мин для анонов, 60 для верифицированных, см. getVpnDurationMs().
    const duration = await getVpnDurationMs();
    const deadline = Date.now() + duration;
    // [v2.7.5 audit r3] try/catch – раздельные guard'ы для storage и alarm.create.
    // Без этого quota/alarm-create fail throws → VPN-on без 60-min timer → unlimited
    // free (тот же класс bug что R2 v2.7.0 disconnect chain).
    try { await chrome.storage.local.set({ [VPN_DEADLINE_KEY]: deadline }); }
    catch (e) { logDiag('timer', 'deadline_set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    // [v2.8.1 audit] alarm.create THROW propagates → caller doToggleProxy rollback
    // (proxyEnabled=true БЕЗ alarm = unlimited free VPN, тот же класс bug что R2 v2.7.0).
    // Per CLAUDE.md «chrome.alarms.create always await for VPN_ALARM_NAME – silent fail
    // = unlimited VPN. Wrap caller Promise.race в try/catch – alarm.create throw w/o
    // rollback = proxyEnabled=true + no alarm = same symptom». До 2.8.1 catch проглатывал throw.
    await chrome.alarms.create(VPN_ALARM_NAME, { when: deadline });
    // [v3.1.1] Warn-alarm за 5 мин до конца. НЕ критичен → try/catch, throw НЕ пробрасываем
    // (иначе caller doToggleProxy откатит подключение из-за необязательного уведомления).
    try {
        if (duration > VPN_WARN_BEFORE_MS + 60 * 1000) {
            await chrome.alarms.create(VPN_WARN_ALARM_NAME, { when: deadline - VPN_WARN_BEFORE_MS });
        } else {
            await chrome.alarms.clear(VPN_WARN_ALARM_NAME);
        }
    } catch (e) { logDiag('timer', 'warn_create_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
}

async function clearVpnTimer() {
    // [v2.7.6 audit Pass13] Per-step try/catch – quota fail на одной операции не должен
    // прерывать другую. clearVpnTimer вызывается из VPN_ALARM disconnect-chain (per-step F2),
    // премиум активации, OFF-toggle. Если внутренний throw здесь – caller получает throw без
    // партиального cleanup'а (alarm может остаться, deadline – стёрт, или наоборот).
    try { await chrome.alarms.clear(VPN_ALARM_NAME); } catch (e) { logDiag('timer', 'clear_alarm_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    try { await chrome.alarms.clear(VPN_WARN_ALARM_NAME); } catch (e) { logDiag('timer', 'clear_warn_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    try { await chrome.storage.local.remove(VPN_DEADLINE_KEY); } catch (e) { logDiag('timer', 'clear_deadline_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
}

// [v3.1.2] Ghost-ping: фоновое обновление пингов БЕЗ вмешательства – в отличие от bulk-ping
// НЕ трогает chrome.proxy.settings (тот на время замера гонит весь трафик браузера через
// тестируемый сервер). Физика: прямой fetch http://host:port – живой HTTP-прокси отвечает
// 407 за ~RTT (замер 2026-07-08: ~0.25с), мёртвый/недоступный – timeout/ошибка → fail.
// Точность ниже туннельного замера (близость сети, не скорость выхода) – для сортировки и
// auto-select достаточно; дохлые каналы ДЦ отсекает серверный speed-check cron.
// Очередь: без success-пинга свежее 60 мин, сортировка по давности последней попытки
// (max(ts,aTs) asc) – живые и мёртвые в одном круге, мёртвые не чаще раза в час.
// Добор: если устаревших < батча – перепроверяем недавно не ответившие (fail).
// Fail НЕ затирает прежние ms/ts: auto-select держит старый валидный пинг до своего 24ч TTL.
async function _ghostPingOne(hp) {
    // [v3.1.2 smoke-fix] Прямой fetch к HTTP-прокси-порту ВСЕГДА реджектится: прокси отвечает
    // 407 Proxy Authentication Required, а Chrome вне прокси-контекста трактует 407 как
    // протокольную ошибку (ERR_UNEXPECTED_PROXY_AUTH → TypeError "Failed to fetch"). Проверено
    // на smoke-тесте: живой сервер даёт reject за ~116мс. Поэтому меряем ВРЕМЯ ДО reject:
    //   • быстрый fail (< timeout) = сервер на том конце ответил → ЖИВ, RTT = elapsed;
    //   • дошли до таймаута (abort) = хост недоступен/дропает → МЁРТВ (-1).
    // chrome.proxy при этом не трогается вообще – трафик юзера не затрагивается.
    const t0 = Date.now();
    const ctl = new AbortController();
    const killer = setTimeout(() => { try { ctl.abort(); } catch (_) {} }, GHOST_PING_TIMEOUT_MS);
    try {
        await fetch('http://' + hp + '/', { method: 'GET', mode: 'no-cors', cache: 'no-store', credentials: 'omit', signal: ctl.signal });
        return Date.now() - t0; // opaque-успех (редко) – тоже валидный RTT
    } catch (e) {
        const elapsed = Date.now() - t0;
        // AbortError или elapsed у таймаута = мёртв. Быстрый reject = живой сервер, RTT=elapsed.
        if (e && e.name === 'AbortError') return -1;
        if (elapsed >= GHOST_PING_TIMEOUT_MS * 0.85) return -1;
        return elapsed > 0 ? elapsed : 1;
    } finally {
        clearTimeout(killer);
    }
}
// [v3.1.3] Когда ближайший сервер пула станет «устаревшим» (lastTouch + 30 мин) – для честного
// отсчёта «До проверки» в шапке выбора сервера. Пул и lastTouch считаются по тем же правилам,
// что и очередь в ghostPingTick (free не пингует premium; lastTouch = max(ts, aTs)).
// Непроверенные серверы (lastTouch=0) дают время в прошлом → «уже пора» → caller покажет ближайший тик.
// Возвращает 0, если списка серверов нет (fallback на alarm-время у caller'а).
async function _ghostNextEligibleAt() {
    let list = (Array.isArray(serverList) && serverList.length) ? serverList : null;
    if (!list) {
        try {
            const st = await chrome.storage.local.get(['proxyListEnc']);
            const dec = await decryptCachedList(st.proxyListEnc);
            if (Array.isArray(dec) && dec.length) list = dec;
        } catch (e) {}
    }
    if (!list || !list.length) return 0;
    const stored = await chrome.storage.local.get(['serverPings', 'isPremium']);
    const pings = (stored.serverPings && typeof stored.serverPings === 'object' && !Array.isArray(stored.serverPings)) ? stored.serverPings : {};
    let minAt = Infinity;
    const seen = new Set();
    for (const p of list) {
        if (!p || !p.host || !p.port) continue;
        if (!stored.isPremium && p.type === 'premium') continue;
        const hp = p.host + ':' + p.port;
        if (seen.has(hp)) continue;
        seen.add(hp);
        const r = pings[hp];
        const lastTouch = r ? Math.max(Number(r.ts) || 0, Number(r.aTs) || 0) : 0;
        const at = lastTouch + GHOST_PING_FRESH_MS;
        if (at < minAt) minAt = at;
    }
    return (minAt === Infinity) ? 0 : minAt;
}
let _ghostPingBusy = false;
// [v3.1.3] «Очередь обрабатывается» (включая 1.5с-паузы между серверами) – для статуса в шапке
// модалки «Выбор сервера». _ghostPingBusy мерцает (true только на время одного пинга ≤3с),
// поэтому для UI держим отдельный флаг на весь проход очереди; сбрасывается на guard-выходах.
let _ghostLoopActive = false;
async function ghostPingTick() {
    if (_ghostPingBusy) return; // re-entry: активный проход сам обновит _ghostLoopActive
    if (pingInProgress || toggleInProgress) { _ghostLoopActive = false; return; }
    if (vpnBlocked) { _ghostLoopActive = false; return; }
    if (await isProxyEnabled()) { _ghostLoopActive = false; return; } // VPN ON: замер пошёл бы через туннель = мусор; сервер уже выбран
    _ghostPingBusy = true;
    try {
        // Список ТОЛЬКО из локальных источников (память → decrypt кэша). НЕ ensureProxyList:
        // его сетевой TTL 5 мин совпадает с периодом тика → дёргали бы proxy_list.php каждые 5 мин.
        let list = (Array.isArray(serverList) && serverList.length) ? serverList : null;
        if (!list) {
            try {
                const st = await chrome.storage.local.get(['proxyListEnc']);
                const dec = await decryptCachedList(st.proxyListEnc);
                if (Array.isArray(dec) && dec.length) list = dec;
            } catch (e) {}
        }
        if (!list || !list.length) { _ghostLoopActive = false; return; }
        const stored = await chrome.storage.local.get(['serverPings', 'isPremium', 'favoriteServers', 'onboardingV2Done']);
        // [v3.1.2] Не пингуем, пока первоначальная настройка не ЗАВЕРШЕНА (пройдена/пропущена явно
        // через _setupFinish). Если юзер закрыл мастер крестиком (не нажал «Пропустить») –
        // onboardingV2Done не стоит → ждём: после завершения setup storage.onChanged разбудит ghost.
        if (!stored.onboardingV2Done) { _ghostLoopActive = false; return; }
        const pings = (stored.serverPings && typeof stored.serverPings === 'object' && !Array.isArray(stored.serverPings)) ? Object.assign({}, stored.serverPings) : {};
        const now = Date.now();
        // Free пингует только free-серверы (premium ему недоступны – не жжём батч впустую).
        const hps = [];
        const seen = new Set();
        for (const p of list) {
            if (!p || !p.host || !p.port) continue;
            if (!stored.isPremium && p.type === 'premium') continue;
            const hp = p.host + ':' + p.port;
            if (!seen.has(hp)) { seen.add(hp); hps.push(hp); }
        }
        const fresh = hp => { const r = pings[hp]; return !!(r && typeof r.ms === 'number' && r.ms > 0 && typeof r.ts === 'number' && (now - r.ts) < GHOST_PING_FRESH_MS); };
        const lastTouch = hp => { const r = pings[hp]; return r ? Math.max(Number(r.ts) || 0, Number(r.aTs) || 0) : 0; };
        // [v3.1.2] Избранные пингуем первыми: юзер чаще подключается к ним → их пинг должен быть
        // максимально свежим. Сортировка сначала по «избранный ли» (fav → раньше), затем по давности.
        const _favSet = new Set(Array.isArray(stored.favoriteServers) ? stored.favoriteServers : []);
        const _byFavThenTouch = (a, b) => {
            const fa = _favSet.has(a) ? 0 : 1, fb = _favSet.has(b) ? 0 : 1;
            if (fa !== fb) return fa - fb;
            return lastTouch(a) - lastTouch(b);
        };
        // Очередь: серверы без свежего пинга, чья последняя ПОПЫТКА старше GHOST_PING_FRESH_MS (30 мин).
        // lastTouch=max(ts,aTs) включает время неудачной попытки (aTs), поэтому пауза действует ОДИНАКОВО на
        // пропингованные и на не ответившие серверы: fail тоже ждёт 30 мин до перепроверки, а не крутится
        // бесконечно (без aTs-паузы он попадал бы в очередь каждый тик). Избранные идут первыми.
        const queue = hps.filter(hp => !fresh(hp) && (now - lastTouch(hp)) >= GHOST_PING_FRESH_MS)
            .sort(_byFavThenTouch);
        if (!queue.length) { _ghostLoopActive = false; return; } // нечего проверять → пауза до следующего alarm (когда что-то устареет)
        // [v3.1.2] ПО ОДНОМУ серверу за тик – короткий тик надёжно переживает MV3-усыпление SW.
        // Длинный проход мог обрываться на середине → пропустившие первоначальную настройку
        // (у них autoSelectMethod='ping', но пингов нет) оставались без данных → авто-подбор
        // вечно фолбэчил на нагрузку. Пингуем ПЕРВЫЙ из очереди (избранные/устаревшие впереди),
        // пишем сразу. Если очередь не пуста – самоперепланируем следующий через короткий setTimeout,
        // пока SW жив (быстрое наполнение); SW усыпится – alarm (1 мин) продолжит с того же места.
        _ghostLoopActive = true;
        const hp = queue[0];
        const ms = await _ghostPingOne(hp);
        const prev = (pings[hp] && typeof pings[hp] === 'object') ? pings[hp] : {};
        if (ms > 0) {
            pings[hp] = { ms: ms, ts: Date.now(), aTs: Date.now() }; // новый объект – fail-метка снята
        } else {
            pings[hp] = Object.assign({}, prev, { aTs: Date.now(), fail: true }); // ms/ts прежние
        }
        try { await chrome.storage.local.set({ serverPings: pings }); } catch (e) {}
        if (ms <= 0) logDiag('ghostping', 'tick', { hp: hp, fail: true, left: queue.length - 1 });
        // Самопродолжение: ещё есть что пинговать И юзер не начал toggle/ручной пинг/VPN →
        // следующий сервер через короткий setTimeout. _ghostPingBusy снимется в finally ДО таймера.
        if (queue.length > 1 && !pingInProgress && !toggleInProgress && !(await isProxyEnabled())) {
            setTimeout(function(){ ghostPingTick().catch(function(){}); }, GHOST_PING_GAP_MS);
        } else {
            _ghostLoopActive = false; // очередь исчерпана (или проход прерван) – проверка завершена
        }
    } catch (e) {
        _ghostLoopActive = false;
        logDiag('ghostping', 'tick_fail', { msg: String((e && e.message) || '').slice(0, 80) });
    } finally {
        _ghostPingBusy = false;
    }
}

// === ALARM HANDLER (единая точка для всех alarms) ===
chrome.alarms.onAlarm.addListener(async (alarm) => {
    // [v3.0.4] Периодический re-probe API-доменов (возврат на быстрый primary). Независимый, лёгкий.
    if (alarm.name === API_PROBE_ALARM) { try { await probeApiDomains(); } catch (e) {} return; }
    // [v3.1.2] Ghost-ping: тихое фоновое обновление пингов. Все guards внутри тика.
    if (alarm.name === GHOST_PING_ALARM) { try { await ghostPingTick(); } catch (e) {} return; }
    if (alarm.name === KEEPALIVE_ALARM) {
        // Refresh credentials cache on each tick
        if (!cachedCredentials) {
            const d = await chrome.storage.local.get(['selectedProxy']);
            if (d.selectedProxy) updateCredentialCache(d.selectedProxy);
        }
        // [v2.8.1 audit] updateBadge async – .catch чтобы storage IO fail не давал
        // unhandled rejection в alarm handler (симметрично 1380, 2676, 2713).
        updateBadge().catch(() => {});
        return;
    }
    if (alarm.name === HEARTBEAT_ALARM) {
        sendHeartbeat().catch(() => {});
        return;
    }
    if (alarm.name === PREMIUM_CHECK_ALARM) {
        // [v2.7.0 fix F27] Serialize – раньше оба .catch fire параллельно. Если оба
        // приводили к disconnect (expired premium + device mismatch), юзер получал
        // ДВА notifyDisconnect подряд. Теперь sequential: первый wipe'ает isPremium,
        // второй видит стираный state и выходит рано (both have isPremium guard).
        (async () => {
            try { await checkPremiumExpiration(); } catch {}
            try { await checkDeviceBinding(); } catch {}
        })();
        return;
    }
    if (alarm.name === VPN_WARN_ALARM_NAME) {
        // [v3.1.1] «Сессия закончится через 5 минут». Guards: VPN включён, не premium,
        // deadline реально в ближайшие ~6 мин. После продления (verified) / сжатия (unlink)
        // warn-alarm пересоздаётся (create с тем же именем = replace), но стейл-fire после
        // clock-skew или shrink-to-now отсекаем окном 30с..6.5мин.
        try {
            const d = await chrome.storage.local.get(['proxyEnabled', 'isPremium', VPN_DEADLINE_KEY]);
            if (!d.proxyEnabled || d.isPremium) return;
            const dl = d[VPN_DEADLINE_KEY];
            if (typeof dl !== 'number') return;
            const left = dl - Date.now();
            if (left < 30 * 1000 || left > 6.5 * 60 * 1000) { logDiag('timer', 'warn_stale_skip', { leftSec: Math.round(left / 1000) }); return; }
            await notifySoonExpiring();
            logDiag('timer', 'warn_shown', { leftSec: Math.round(left / 1000) });
        } catch (e) { logDiag('timer', 'warn_fire_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        return;
    }
    if (alarm.name === VPN_ALARM_NAME) {
        // [v2.8.1 audit] Concurrent manual disconnect race: если юзер нажал toggle OFF
        // в момент alarm fire – alarm-handler делает recordSessionEnd/setProxy/notify
        // параллельно с doToggleProxy OFF-веткой → double-disconnect (две notify, два
        // sendDisconnect, два proxy.settings.set last-writer-wins). Skip – manual toggle
        // OFF сам всё закроет, а alarm пере-выстрелит на cold-wake recovery если нужно.
        if (toggleInProgress) {
            logDiag('timer', 'toggle_busy_skip');
            return;
        }
        // [v2.7.0 fix F8] Guard trial/premium – если trial активирован (isPremium=true)
        // но alarm.clear failed в requestTrial/recoverPremium handler'е, старый 60-мин
        // alarm стреляет и disconnect'ит trial-юзера. Проверяем isPremium первым,
        // чистим orphan-alarm если есть.
        // [v2.7.0 fix F8.1] storage.get может throw (quota, storage API corrupt) → handler
        // reject. Раньше: trial-юзер НЕ disconnect'ился (good) но free-юзер тоже НЕ
        // disconnect'ился (unlimited). Теперь: default isPremium=false (fail-safe) –
        // storage fail приводит к disconnect free-юзера, premium лог показывает проблему.
        let __isPremium = false;
        try {
            const gpd = await chrome.storage.local.get(['isPremium']);
            __isPremium = !!gpd.isPremium;
        } catch (e) {
            logDiag('timer', 'isPrem_read_fail', { msg: String((e && e.message) || '').slice(0, 80) });
        }
        if (__isPremium) {
            logDiag('timer', 'premium_skip');
            try { await chrome.alarms.clear(VPN_ALARM_NAME); } catch {}
            return;
        }
        logDiag('timer', 'expired_start');
        // [v2.7.0 fix R2] Каждый шаг в try/catch – без них одна throw из recordSessionEnd
        // или storage.set оставляла proxyEnabled=true и chrome.proxy продолжал маршрутизацию.
        // Реальный bug 2.6.10: 7+ free-юзеров с 8-часовой continuous сессией (alarm срабатывал,
        // но disconnect не завершался – следующие await не выполнялись после throw).
        // [v2.8.2 audit-4 F27] cachedCredentials reset перенесён ВВЕРХ – раньше был внизу
        // (после всех disconnect step'ов), но если step throw'ил БЕЗ его try/catch (ранний
        // sync throw до per-step await), reset не выполнялся → stale creds leak. Сейчас:
        // моментальный reset → даже если что-то ниже throw, кэш уже null.
        cachedCredentials = null;
        try { await recordSessionEnd(); } catch (e) { logDiag('timer', 'recEnd_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        // Critical disconnect (proxyEnabled=false + setProxy + clearVpnTimer + stop*) – каждый
        // шаг изолирован, чтобы fail одного не блокировал остальные.
        try { await chrome.storage.local.set({ proxyEnabled: false, sessionExpired: true }); }
        catch (e) { logDiag('timer', 'set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await setProxy(false); }
        catch (e) { logDiag('timer', 'setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { updateIcon(false); } catch {}
        try { await clearVpnTimer(); } catch (e) { logDiag('timer', 'clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { stopHeartbeat(); } catch {}
        // [v2.8.1 audit] reason='timer' (60-мин истёк) – без него session-audit
        // путал автодисконнект с user-toggle.
        try { sendDisconnect('timer'); } catch {}
        try { stopKeepalive(); } catch {}
        try { notifyDisconnect('timer'); } catch {}
        // [v2.5.9] Передаём reason='timer' чтобы popup показал sticky-баннер
        // [v2.7.5 audit r3] try/catch – sync-throw chrome.runtime.sendMessage (extension context
        // invalidated mid-call) обрывал logDiag(expired_done) downstream. Все остальные disconnect-шаги
        // обёрнуты, этот был исключением (v2.7.0 R2 step-guard pattern).
        try { chrome.runtime.sendMessage({ action: "proxyStateChanged", proxyEnabled: false, reason: 'timer' }).catch(() => {}); } catch {}
        logDiag('timer', 'expired_done');
    }
});

function getRemainingTime(callback) {
    chrome.storage.local.get([VPN_DEADLINE_KEY, 'isPremium'], (data) => {
        if (data.isPremium) { callback(999999); return; }
        const deadline = data[VPN_DEADLINE_KEY];
        if (!deadline) { callback(0); return; }
        const diff = deadline - Date.now();
        // [v2.7.0 fix F75] Cap 3600s – если clock rolls back, diff мог вырасти до суток.
        // Free-сессия максимум 60 мин, любой больший результат – clock-skew bug, обрезаем.
        const secs = diff > 0 ? Math.min(3600, Math.floor(diff / 1000)) : 0;
        callback(secs);
    });
}

// === INITIALIZATION ===
async function initialize() {
    // [v2.7.0 fix R5] Каждый init-step в try/catch – без них throw из recordSessionEnd
    // (vpnStats corrupted) пропускала весь оставшийся initialize, включая критичный
    // alarm-recreation для free-юзеров на cold-wake. Это один из путей 8-часовых
    // непрерывных сессий, наблюдаемых в продакшене 2.6.10.
    try { await recordSessionEnd(); } catch (e) { logDiag('init', 'recEnd_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    // [v2.7.1 fix F96] Recovery: vpnBlocked живёт в SW memory и сбрасывается на cold-wake,
    // но storage флаги updateRequired/illegalExtId persist. Без recovery каждый cold-wake
    // делал 1 fetch → 403 → wasted bandwidth, пока серверный admin не снимет блок. Восстанавливаем
    // in-memory state из persistent flags чтобы fetchProxyList сразу пропускал запрос.
    try {
        const flagData = await chrome.storage.local.get(['updateRequired', 'illegalExtId', 'rateLimited', 'rateLimitedUntil']);
        // [v3.1.5 audit] rateLimited добавлен в recovery: без него rate-limited юзер на каждом cold-wake
        // (SW умирает ~30с) слал fetch → 403 → wasted bandwidth весь бан. Гейтим по rateLimitedUntil,
        // чтобы не блокировать после истечения (у updateRequired/illegalExtId expiry нет — снимает admin).
        // [v3.1.5 audit М6] rateLimitedUntil хранится строкой; если сервер пришлёт нечисловой/ISO-until,
        // прямое сравнение строки с Date.now() даёт NaN → false → recovery не срабатывал → fetch-спам весь
        // бан. Fail-safe: нет until → активен (бан снимает admin); невалидный → активен; число → пока не истёк.
        const _rlUntilNum = Number(flagData.rateLimitedUntil);
        const rlActive = flagData.rateLimited && (!flagData.rateLimitedUntil || !isFinite(_rlUntilNum) || _rlUntilNum > Date.now());
        if (flagData.updateRequired || flagData.illegalExtId || rlActive) {
            vpnBlocked = true;
            vpnBlockedAt = Date.now();
            logDiag('init', 'vpnBlocked_recovered', { ur: !!flagData.updateRequired, ill: !!flagData.illegalExtId, rl: !!rlActive });
        }
    } catch {}
    try { await checkPremiumExpiration(); } catch (e) { logDiag('init', 'premExp_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    try { await checkDeviceBinding(); } catch (e) { logDiag('init', 'devBind_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    // [v3.1.5 audit] fail-safe: голый get мог бросить (storage IO) → initialize reject ДО alarm-recreate
    // и ДО setProxy → chrome.proxy остаётся активным + proxyEnabled=true, но alarm нет = сессия без таймера
    // (класс v2.6.10). При сбое трактуем как VPN off → setProxy(false) ниже отключит прокси.
    let data;
    try { data = await chrome.storage.local.get(['proxyEnabled', VPN_DEADLINE_KEY, 'isPremium']); }
    catch (e) { logDiag('init', 'stateRead_fail', { msg: String((e && e.message) || '').slice(0, 80) }); data = {}; }
    let enabled = !!data.proxyEnabled;

    if (enabled && !data.isPremium) {
        const deadline = data[VPN_DEADLINE_KEY];
        if (deadline && deadline > Date.now()) {
            // [v2.7.0 fix R3] await – см. startVpnTimer
            // [v2.7.0 fix F5.1] try/catch вокруг alarm.create – если throw (quota/invalid),
            // раньше initialize reject'ил silently → proxyEnabled=true остаётся + нет alarm
            // = unlimited free VPN на всё время SW-сессии. Теперь: fail-safe disconnect.
            try {
                await chrome.alarms.create(VPN_ALARM_NAME, { when: deadline });
                // [v3.1.1] Warn-alarm пересоздать на cold-wake (browser restart стирает alarms).
                // Отдельный try – его fail НЕ должен приводить к fail-safe disconnect ниже.
                try {
                    if (deadline - Date.now() > VPN_WARN_BEFORE_MS + 30 * 1000) {
                        await chrome.alarms.create(VPN_WARN_ALARM_NAME, { when: deadline - VPN_WARN_BEFORE_MS });
                    }
                } catch (we) { logDiag('init', 'warn_create_fail', { msg: String((we && we.message) || '').slice(0, 80) }); }
            } catch (e) {
                logDiag('init', 'alarm_create_fail', { msg: String((e && e.message) || '').slice(0, 80) });
                enabled = false;
                // [v3.1.5 audit] per-step guard: без него throw на storage.set пробрасывался из initialize
                // и пропускал setProxy(false) ниже → chrome.proxy оставался активным = сессия без таймера.
                try { await chrome.storage.local.set({ proxyEnabled: false }); } catch (se) { logDiag('init', 'disc_set_fail', { msg: String((se && se.message) || '').slice(0, 80) }); }
                try { await clearVpnTimer(); } catch (ce) { logDiag('init', 'disc_clr_fail', { msg: String((ce && ce.message) || '').slice(0, 80) }); }
            }
        } else {
            enabled = false;
            try { await chrome.storage.local.set({ proxyEnabled: false }); } catch (se) { logDiag('init', 'disc_set_fail2', { msg: String((se && se.message) || '').slice(0, 80) }); }
            try { await clearVpnTimer(); } catch (ce) { logDiag('init', 'disc_clr_fail2', { msg: String((ce && ce.message) || '').slice(0, 80) }); }
        }
    }

    // [v2.7.5 audit r3] try/catch – chrome.proxy.settings.set может throw на quota/config
    // error. Без этого initialize() reject → пропускаются startHeartbeat/startKeepalive/
    // applyPremiumState ниже. Лучше частичная инициализация чем полный fail.
    try { await setProxy(enabled); }
    catch (e) { logDiag('init', 'setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
    updateIcon(enabled);
    // [v2.7.2] Убран prefetch proxy_list при VPN OFF на cold-wake: premium-юзеры
    // имеют PREMIUM_CHECK_ALARM каждые 5 мин, каждый wake дёргал proxy_list.php,
    // создавая ~4 req/s фоновой нагрузки без пользы. Lazy-load: popup сам спросит
    // через getProxies, toggle ON вызовет ensureProxyList(true). При ON список уже
    // загружен в setProxy выше.
    if (enabled) { startHeartbeat(); startKeepalive(); }
    // [v2.7.2 fix F151] symmetry – если cold-wake видит proxyEnabled=false но alarm
    // остался от предыдущей сессии (SW crashed mid-OFF, browser force-quit при VPN ON),
    // HEARTBEAT_ALARM персистит → каждые 5 мин fires no-op. stopHeartbeat + stopKeepalive
    // идемпотентны (silent noop если alarm не существует).
    else { stopHeartbeat(); stopKeepalive(); }
    // [v2.6.2] Sync ad-blocker ruleset с премиум-статусом (на cold start SW)
    await applyPremiumState();
    // [v2.7.4] Убран immediate checkLatestVersion() + 24h alarm.
    // Теперь опрос только по message 'checkLatestVersion' от popup (popup.js applyUpdateBanner).
    // Cleanup orphan alarm от 2.6.2-2.7.3 – после миграции остаётся в Chrome scheduler,
    // fires no-op forever (handler удалён выше). Silent если alarm нет.
    chrome.alarms.clear('version_check_alarm').catch(() => {});
    // [v2.8.0] На cold-wake перепро­ставляем uninstall URL (Chrome сохраняет setUninstallURL
    // через restart, но если SW крашился между accountVerified change и URL set – sync здесь).
    // [v2.8.2 audit-4 F23] .catch() – async fail (storage quota / setUninstallURL throw) shouldn't break init.
    _updateUninstallURL().catch(() => {});
}

// [v2.5.6] Promise-мьютекс – гарантирует что initialize() не запустится параллельно
let initPromise = null;

async function safeInitialize() {
    if (initPromise) return initPromise;
    initPromise = initialize().catch(() => {}).finally(() => { initPromise = null; });
    return initPromise;
}

safeInitialize();

// [v2.8.0] Динамический uninstall URL – для верифицированных юзеров uid позволяет серверу
// отвязать расширение от web-аккаунта (web_user_extensions DELETE + web_users.uninstall_count++).
// Не используем email в URL – приватнее (uid не PII).
// [v2.8.4] UID передаётся ВСЕГДА (не только при accountVerified) – сервер помечает
// stats_user_seen.uninstalled_at чтобы analytics могла отличать «удалил» от «не заходит».
// Если uid ещё не сгенерирован (теоретически только до первого getUID() – почти никогда),
// generateUID() здесь же создаст и persist'нет.
async function _updateUninstallURL() {
    try {
        var uid = await getUID();
        var url = 'https://balancing.apiget.ru/AnonVPN/lk/uninstall.php';
        if (uid) {
            url += '?uid=' + encodeURIComponent(uid);
        }
        await chrome.runtime.setUninstallURL(url);
    } catch (e) {
        logDiag('lifecycle', 'uninstall_url_fail', { msg: String((e && e.message) || '').slice(0, 80) });
    }
}

// [FIX #5] onInstalled: различаем install vs update
chrome.runtime.onInstalled.addListener(async (details) => {
    logDiag('lifecycle', details.reason, { prev: details.previousVersion || null, cur: EXT_VERSION });
    _updateUninstallURL().catch(() => {}); // [v2.8.2 audit-4 F23]
    if (details.reason === 'install') {
        // Первая установка – VPN выключен, показать help
        // Автоопределение языка браузера
        var supported = ['en','ru','zh','es','de','fr','pt','ja','ko','it','nl','pl','tr','ar','hi','vi','th','id','sv','am','bg','bn','ca','cs','da','el','et','fa','fi','fil','gu','he','hr','hu','kn','lt','lv','ml','mr','ms','no','ro','sk','sl','sr','sw','ta','te'];
        var uiLang = (chrome.i18n.getUILanguage() || 'en').toLowerCase().replace('-', '_');
        var baseLang = uiLang.split('_')[0];
        var detectedLang = supported.indexOf(uiLang) >= 0 ? uiLang : (supported.indexOf(baseLang) >= 0 ? baseLang : 'en');
        // [v2.8.0] При install НЕ ставим firstInstallExclusionsPending=true явно – sentinel-логика
        // в applyFirstInstallExclusionsIfPending триггерит apply на любом значении кроме `false`.
        // Это покрывает и fresh install (default undefined → apply), и upgrade с 2.7.x
        // (тоже undefined у существующих юзеров → apply при первом list-load).
        // [v2.8.1 audit] try/catch – без него storage quota/corruption на install path
        // throws → роняет последующий tabs.create help.html + ensureProxyList → юзер видит
        // пустой экран после установки. Acceptable failure: запись повторится на следующем wake.
        try { await chrome.storage.local.set({ proxyEnabled: false, language: detectedLang }); }
        catch (e) { logDiag('lifecycle', 'install_set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await clearProxyAuthRule(); } catch (e) { logDiag('lifecycle', 'install_clearAuth_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await stopKeepalive(); } catch (e) { logDiag('lifecycle', 'install_stopKa_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        // [v2.6.0] Открываем help-страницу немедленно, не ждём fetch прокси-листа.
        // До 2.6.0 `.finally()` после `ensureProxyList()` задерживал открытие на 7-16 сек
        // при медленной сети – пользователь видел пустой экран после установки.
        // [v2.8.1 audit] logDiag вместо silent – quota/popup-blocker fail на первом install
        // должен быть видим в diagnostic log (telemetry для UX-проблем).
        chrome.tabs.create({ url: chrome.runtime.getURL('help.html') })
            .catch(e => logDiag('lifecycle', 'help_open_fail', { msg: String((e && e.message) || '').slice(0, 80) }));
        ensureProxyList().catch(() => {});
    } else if (details.reason === 'update') {
        // [v2.5.8] Различаем настоящий апдейт версии vs ручной reload в chrome://extensions
        // (Chrome шлёт reason='update' в обоих случаях, но previousVersion === currentVersion при reload)
        // [v2.7.0 fix F73] Если previousVersion отсутствует (очень старая CWS-версия из
        // ранних MV2 – <1.0 не проставляли это поле), treat как realUpdate – defensive wipe.
        // Альтернатива (skip wipe) протаскивает stale-кэши неизвестного формата в 2.7.0.
        const isRealUpdate = (!details.previousVersion) || (details.previousVersion !== EXT_VERSION);
        if (isRealUpdate) {
            // [v2.5.4] Очистка кэша от предыдущих версий – только при реальном бампе
            const STALE_KEYS = [
                VPN_DEADLINE_KEY,         // [v2.7.0 fix F66] free-tier one-shot deadline; без wipe
                                          // новая версия наследует старый timestamp → юзер получает
                                          // обрезанную сессию (если оставалось 10 мин – после update
                                          // сразу disconnect, не освежая 60-мин лимит)
                'proxyList',              // [v2.5.8] старый plaintext-кэш из <2.5.8
                // [v3.0.5] proxyListEnc – зашифрованный список серверов. РАНЬШЕ переживал апдейт
                // (расчёт «формат стабилен → отдадим старый список как фолбэк»). НО ensureProxyList
                // отдаёт stale-список СИНХРОННО, а свежий fetch – лишь фоновый (не-await) → первый
                // коннект после апдейта уходил на устаревшие/мёртвые серверы (ротация n_proxies) =
                // «после обновления не подключается, помогает ручная очистка кэша». Теперь стираем
                // (как ручной Clear Cache) → cache-miss → ensureProxyList ЖДЁТ свежий список.
                // Симметрия с CACHE_KEYS (popup.js). Оффлайн-в-момент-апдейта риск неважен: оффлайн
                // VPN не поднять, а на первом онлайн-коннекте список подтянется.
                'proxyListEnc',
                'cachedProxyList',        // кэш popup
                // [v3.0.4] cachedServerStats/cachedServerStatsAt УБРАНЫ из STALE_KEYS. Их wipe на
                // апдейте → пустой fallback нагрузки → блок 75 пробивался: SW видел load=0 у всех →
                // pickBestServer брал pool[0], guard не блокировал (корень «стада» на первом сервере
                // после миграции 3.0.2→3.0.3). Схема ключей host:port стабильна между версиями;
                // чуть устаревшая нагрузка бесконечно лучше пустоты. Остаются в KNOWN_STORAGE_KEYS.
                'cachedNews',             // новости
                'cachedTranslationsData', 'cachedTranslationsVersion', // переводы – могут измениться между версиями
                'updateRequired',         // флаг обновления от старой версии
                // [v2.7.1 fix F103] illegalExtId – раньше переживал update, после F96
                // (vpnBlocked recovery on init) персистентный stale флаг блокировал юзера
                // навсегда. Wipe на real bump симметрично updateRequired.
                'illegalExtId',
                // [v2.7.1 fix F109] updateUrl – version-specific update metadata, paired
                // с updateRequired. Без wipe stale URL мог направить юзера на неактуальный
                // download endpoint. vpnConflictList/vpnConflictLastSeen – кэш management.
                // getAll(), стайл VPN-list мог содержать удалённые расширения. sessionExpired –
                // sticky banner от старой сессии не должен переживать update.
                'updateUrl',
                'vpnConflictList',
                'vpnConflictLastSeen',
                'sessionExpired',
                'minVersion',
                'selectedProxy',          // выбранный прокси – может быть несовместим с новым списком
                'updateAvailable',        // [v2.6.2] latest от предыдущей версии – иначе баннер покажет фальшиво
                'updateAvailableDismissed',// [v2.6.2] dismiss-флаг привязан к старой версии
                'proxyListFetchAt',       // [v2.6.9] persisted TTL – на апдейте сбросить, чтобы новая версия сразу взяла свежий список
                'lastHeartbeatAt',        // [v2.6.10] persisted heartbeat TTL – на апдейте сбросить, новая версия должна зафиксировать первый heartbeat сразу
                'proxyListFetchError',    // [v2.8.4] stale error от прошлой версии не должен показывать «нет интернета» сразу после апдейта
                'proxyListFetchErrorAt',
                'serverSortMode',         // [v2.7.0] UI sort mode (Сортировка: load/index/country) – сбрасываем к default на реальном апдейте
                // [v2.7.3] autoSelectServer – reset к default (true) на real update. Юзеры,
                // которые сами отключили auto-select (popup ставил autoSelectServer:false),
                // после апдейта получают его обратно включённым. Важно для 2.7.3 free-load-lock:
                // с auto-select ON юзер автоматически попадёт на сервер с низкой нагрузкой
                // вместо застревания на заблокированном №1. Default читается как `!== false` →
                // отсутствие ключа = true = ON. autoSelectScope НЕ сбрасываем – у premium
                // там дефолт 'all', wipe → 'free' → premium pool будет проигнорирован auto-select'ом.
                'autoSelectServer',
                // [v2.7.5 audit Pass5] pendingTraffic – persisted traffic counter (новое в 2.7.5).
                // Wipe на real bump чтобы новая версия не унаследовала stale формат от старой.
                // Если структура изменится между релизами (добавим server_index, premium_flag и т.п.) –
                // старый формат может ломать heartbeat parse → отправит NaN/null → server-side reject.
                'pendingTraffic',
                // [v2.9.1] serverPings/serverPingsRunAt – кэш пингов формата {host:port: {ms,ts}}.
                // На real bump сбрасываем – формат может меняться, новая версия перепингует.
                'serverPings', 'serverPingsRunAt', 'bulkPingProgress',
                // [v3.1.4] brokenServers – метки сломанных туннелей {host:port→ts}. Symmetry с popup
                // CACHE_KEYS: ручная «Очистить кэш» их сбрасывает, real update тоже даёт чистый список
                // (self-prune 5мин делает это почти no-op, но инвариант CACHE⊆STALE держим явно).
                'brokenServers',
                // [v2.7.6 audit Pass9] lastNewsTime – popup CACHE_KEYS (popup.js:CACHE_KEYS) уже
                // включает; для symmetry STALE_KEYS на real update тоже сбрасывает, чтобы новая
                // версия начала news-badge с чистого state (а не унаследовала «уже прочитал X»).
                'lastNewsTime',
                // [v2.8.0] rate-limited state – банн от прошлой версии не должен пережить update.
                // Если юзер действительно ботит, сервер забанит его снова при первом fetch.
                'rateLimited', 'rateLimitedReason', 'rateLimitedUntil',
                // [v3.0.5] Обнуление лимитов фич на реальном апдейте: свежая версия = свежие квоты.
                // checkerRunHistory – rate-limit «Проверки серверов» (ping 1/час, site 3/час);
                // lastCheckerRunAt – legacy того же; fullDiagLastRun – лимит «Полной диагностики»
                // (1/час у free без верификации). Не абузно: юзер не форсит апдейты CWS. Симметрично
                // CACHE_KEYS (ручная «Очистить кэш» их тоже сбрасывает).
                'checkerRunHistory', 'lastCheckerRunAt', 'fullDiagLastRun',
                // [v2.8.0] accountVerified/accountEmail НЕ в STALE_KEYS – флаг ставится один раз
                // при link-uid, дальше не перепроверяется. Юзер не должен заново линковаться
                // после каждого update.
            ];
            // [v2.8.1 audit] try/catch – quota/storage-corruption на remove не должен
            // блокировать дальнейший cleanupUnknownStorageKeys + opens update_page.
            try { await chrome.storage.local.remove(STALE_KEYS); }
            catch (e) { logDiag('lifecycle', 'stale_remove_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
            // [v3.0.5] proxyListEnc ТЕПЕРЬ в STALE_KEYS (стёрт выше вместе с остальными). Раньше
            // переживал апдейт → ensureProxyList отдавал stale-список синхронно (фоновый рефреш
            // не-await) → первый коннект на мёртвые серверы. decryptCachedList(null) на стёртом
            // ключе корректно уходит в сетевой fetch (cache-miss → await свежий список).
            // [v2.6.2] Дополнительно чистим ключи от ещё более старых версий
            // (не входят в KNOWN_STORAGE_KEYS – значит deprecated или ренеймнуты)
            await cleanupUnknownStorageKeys();
            // [v2.8.0] Открываем update_page.html (не help.html) для FREE-юзеров на real update.
            // update_page.html – Premium-upsell с инфо «почему вы здесь» + trial-prompt.
            // Help.html (полный) – только при first-install и из popup'а.
            // Premium пропускаем – продавать им trial нет смысла.
            // ?lang=<saved> пробрасывается чтобы страница сразу открывалась на языке popup'а
            // без миганий. update_page.js парсит URL ?lang= с приоритетом.
            try {
                const { isPremium, language } = await chrome.storage.local.get(['isPremium', 'language']);
                if (!isPremium) {
                    const langParam = (typeof language === 'string' && /^[a-z]{2,4}$/.test(language)) ? language : '';
                    const url = chrome.runtime.getURL('update_page.html') + (langParam ? '?lang=' + langParam : '');
                    chrome.tabs.create({ url }).catch(() => {});
                }
            } catch {}
        }
        // [v3.1.2] Самолечение после MV3-обновления. Известный класс багов: при авто-апдейте новый
        // SW стартует, но chrome.proxy остаётся в fixed_servers от предыдущей сессии, а proxyListEnc
        // уже стёрт (STALE_KEYS выше) → прокси указывает на мёртвый адрес. Все SW-fetch к API-доменам
        // уходят в этот дохлый прокси и падают → диагностика показывает api 0/5, «после обновления не
        // подключается» при живом интернете, незаблокированном IP и неизменном коде (чаты #663 Магомед /
        // #664 Виктория, обе 3.1.1 Windows). Обычный setProxy(false) в initialize иногда молча не
        // применяется на свежем-после-апдейта SW → форсим direct с ретраем и ПРОВЕРКОЙ факта. Только при
        // выключенном VPN: если VPN был включён, его прокси восстановит initialize штатно.
        try {
            const _pe = await chrome.storage.local.get(['proxyEnabled']);
            if (!_pe.proxyEnabled) {
                let _ok = false;
                for (let _a = 0; _a < 3 && !_ok; _a++) {
                    try { await chrome.proxy.settings.set({ value: { mode: 'direct' }, scope: 'regular' }); } catch (e) {}
                    try { const _cur = await chrome.proxy.settings.get({}); _ok = !!(_cur && _cur.value && _cur.value.mode === 'direct'); } catch (e) {}
                    if (!_ok) { try { await new Promise(function (r) { setTimeout(r, 400); }); } catch (e) {} }
                }
                try { await clearProxyAuthRule(); } catch (e) {}
                logDiag('lifecycle', 'update_proxy_direct', { ok: _ok });
            }
        } catch (e) { logDiag('lifecycle', 'update_proxy_reset_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        // Обновление/reload – восстановить состояние, НЕ сбрасывать VPN
        // [v2.5.6] Ждём завершения текущего initialize (если идёт), затем запускаем заново
        // [v2.6.0] Не сбрасываем initPromise вручную – это нарушало инвариант мьютекса.
        // `safeInitialize()` уже корректно обрабатывает null после `.finally()` предыдущего init.
        await initPromise;
        safeInitialize();
    }
});

chrome.runtime.onStartup.addListener(() => { safeInitialize(); });

// [v2.6.2] Когда Chrome скачал обновление из CWS – применить его перезагрузкой extension.
// Если VPN активен, reload не делаем: Chrome применит при следующем restart браузера,
// чтобы не обрывать пользовательскую сессию в середине работы.
chrome.runtime.onUpdateAvailable.addListener(async (details) => {
    logDiag('update', 'downloaded', { version: details && details.version || null });
    try {
        const enabled = await isProxyEnabled();
        if (!enabled) {
            // [v2.6.5 audit] Даём pending-очередям добежать до storage ДО reload –
            // иначе последний logDiag/vpnStats/autoEnable write пропадает (reload() терминит SW).
            // Cap 2 сек чтобы «зависшая» очередь не задерживала reload бесконечно.
            try { await Promise.race([
                // [v2.7.1 fix F124] Promise.allSettled вместо Promise.all – fail-fast
                // semantics терял in-flight writes если хоть одна очередь rejects до 2-сек cap.
                // allSettled ждёт завершения ВСЕХ очередей (success или fail), сохраняя
                // максимум pending writes до reload(). 2-сек race-cap всё ещё ограничивает.
                // [v2.7.6 audit Pass9] +_applyPremiumStateQueue – раньше отсутствовала в flush'е,
                // если premium toggle in-flight в момент onUpdateAvailable → reload теряет
                // pending storage write для adBlockerEnabled / autoSelectScope.
                Promise.allSettled([_logDiagQueue, _autoEnableQueue, _vpnStatsQueue, _dnrSyncQueue, _applyPremiumStateQueue]),
                new Promise(r => setTimeout(r, 2000))
            ]); } catch {}
            chrome.runtime.reload();
        }
    } catch {}
});

// [FIX #3] storage.onChanged читает из storage
// [v2.6.0] try/catch на весь listener – без этого unhandled rejection
// при любой ошибке в setProxy (например, chrome.proxy.settings.set отказал).
chrome.storage.onChanged.addListener(async (changes) => {
    try {
        if (changes.selectedProxy) {
            if (changes.selectedProxy.newValue) {
                updateCredentialCache(changes.selectedProxy.newValue);
            }
            // setProxy(true) → applySelectedProxy() обновит и auth rule с exclusions.
            // [v2.8.5 audit R6] Только при newValue: при УДАЛЕНИИ selectedProxy
            // (teardown – logout / премиум-revoke) re-apply бессмысленен; setProxy(true)
            // без selectedProxy сделал бы auto-pick посреди disconnect-цепочки.
            const enabled = await isProxyEnabled();
            // [v3.1.5 audit] !toggleInProgress: не гоняем reconnect поверх идущего toggle — doToggleProxy
            // сам применит прокси. Без guard concurrent toggle-OFF + этот setProxy(true) = stuck-ON
            // (proxyEnabled=false в storage, но chrome.proxy туннелит). Auto-select во время toggle-ON
            // тоже отложится к самому toggle. Ручная смена сервера (без toggle) не задета.
            if (enabled && !toggleInProgress && changes.selectedProxy.newValue) { await setProxy(true); }
        }
        // [v2.6.2] Премиум активирован/снят ИЛИ тоггл ad-blocker переключён – пересинхронизировать
        if (changes.isPremium || changes.adBlockerEnabled) {
            await applyPremiumState();
            // [v2.7.0 fix F62] Badge держит stale «N минут» до следующего keepalive-тика
            // (~1 мин) после смены isPremium; форсируем immediate refresh.
            if (changes.isPremium) updateBadge().catch(() => {}); // [v2.8.2 audit-4 F22]
        }
        // [v2.6.5 audit r3] Обновляем in-memory cache auto-enable при изменении флага/списка,
        // чтобы fast-path в maybeAutoEnableOnUrl видел актуальное состояние.
        if (changes.autoEnableEnabled || changes.autoEnableDomains) {
            _refreshAutoEnableCache();
        }
        // [v2.6.5 audit r7] DNR-правила для network-level перехвата – должны пересчитываться
        // при смене VPN-статуса, premium, флага и списка доменов.
        if (changes.autoEnableEnabled || changes.autoEnableDomains || changes.proxyEnabled || changes.isPremium) {
            syncAutoEnableDnrRules();
        }
        // [v2.8.4] Раньше пере-сохраняли uninstall URL на accountVerified change – теперь URL
        // содержит uid всегда (не зависит от verify), set один раз в init/onInstalled, listener убран.
        // [round 11] accountVerified flips false→true mid-session – extend timer от 30 до 60 мин.
        // Без этого юзер: завёл VPN при unverified (30-min alarm) → во время сессии
        // подтвердил почту → но alarm срабатывает на 30-мин mark → disconnect. Bad UX.
        // Только non-premium с активным VPN – иначе alarm не нужен (premium = unlimited).
        if (changes.accountVerified && changes.accountVerified.newValue === true && !changes.accountVerified.oldValue) {
            // [v2.8.2 audit-2] Serialize through _accountVerifiedQueue – без неё concurrent verify→unverify→verify
            // могут race-условиться (extend и shrink fire параллельно, last-writer-wins на VPN_DEADLINE_KEY +
            // chrome.alarms.create – broken UX когда rapid flip).
            _accountVerifiedQueue = _accountVerifiedQueue.catch(e => {
                logDiag('timer', 'queue_prev_fail', { msg: String((e && e.message) || '').slice(0, 80) });
            }).then(async () => {
                try {
                    const d = await chrome.storage.local.get(['isPremium', 'proxyEnabled', VPN_DEADLINE_KEY]);
                    if (d.isPremium || !d.proxyEnabled) return;
                    // [round 12 self-fix] Additive extension: добавляем разницу (60-30=30 min)
                    // к существующему deadline. Без этого юзер получает Date.now()+60min на момент
                    // верификации = 90+ мин total (30 уже использовано + 60 новых).
                    // Если deadline просрочен (race с alarm-fire) – fallback на now+60.
                    const oldDeadline = d[VPN_DEADLINE_KEY];
                    const now = Date.now();
                    const newDeadline = (typeof oldDeadline === 'number' && oldDeadline > now)
                        ? oldDeadline + (VPN_DURATION_VERIFIED_MS - VPN_DURATION_ANON_MS)
                        : now + VPN_DURATION_VERIFIED_MS;
                    await chrome.storage.local.set({ [VPN_DEADLINE_KEY]: newDeadline });
                    await chrome.alarms.create(VPN_ALARM_NAME, { when: newDeadline });
                    // [v3.1.1] Warn-alarm тоже сдвигаем к новому deadline (create = replace).
                    try { await chrome.alarms.create(VPN_WARN_ALARM_NAME, { when: newDeadline - VPN_WARN_BEFORE_MS }); } catch {}
                    updateBadge().catch(() => {}); // [v2.8.2 audit-4 F22]
                    logDiag('timer', 'verified_extended', { oldDeadline: oldDeadline, newDeadline: newDeadline });
                } catch (e) {
                    logDiag('timer', 'verified_extend_fail', { msg: String((e && e.message) || '').slice(0, 80) });
                }
            });
        }
        // [v2.8.2 audit] Symmetric: accountVerified true→false (logout/unlink) во время активной free-сессии
        // должен сжать оставшийся timer с 60-min обратно к 30-min (от старта сессии).
        // Без этого: юзер verified открыл VPN (60-мин deadline), отвязал почту в середине сессии →
        // продолжает получать остаток 60-мин лимита, хотя политика для anon = 30 мин.
        // Никогда не растягиваем (только Math.min с already-set deadline). Logout мгновенно (сразу alarm).
        if (changes.accountVerified && changes.accountVerified.oldValue === true && !changes.accountVerified.newValue) {
            // [v2.8.2 audit-2] Same queue as extend handler – sequential execution.
            _accountVerifiedQueue = _accountVerifiedQueue.catch(e => {
                logDiag('timer', 'queue_prev_fail', { msg: String((e && e.message) || '').slice(0, 80) });
            }).then(async () => {
                try {
                    const d = await chrome.storage.local.get(['isPremium', 'proxyEnabled', VPN_DEADLINE_KEY]);
                    if (d.isPremium || !d.proxyEnabled) return;
                    const oldDeadline = d[VPN_DEADLINE_KEY];
                    const now = Date.now();
                    if (typeof oldDeadline !== 'number' || oldDeadline <= now) return;
                    // Сжимаем deadline на 30 мин (разница verified − anon). Если получается в прошлом –
                    // сразу disconnect (alarm fire moment Date.now()-1 → instant trigger по chrome.alarms).
                    const shrunkDeadline = oldDeadline - (VPN_DURATION_VERIFIED_MS - VPN_DURATION_ANON_MS);
                    const newDeadline = Math.max(shrunkDeadline, now + 1000);
                    await chrome.storage.local.set({ [VPN_DEADLINE_KEY]: newDeadline });
                    await chrome.alarms.create(VPN_ALARM_NAME, { when: newDeadline });
                    // [v3.1.1] Warn при сжатии: если 5-мин точка уже в прошлом – alarm выстрелит
                    // сразу, но handler-guard (left<30с) отсечёт стейл. Иначе – честное предупреждение.
                    try { await chrome.alarms.create(VPN_WARN_ALARM_NAME, { when: Math.max(newDeadline - VPN_WARN_BEFORE_MS, Date.now() + 1000) }); } catch {}
                    updateBadge().catch(() => {}); // [v2.8.2 audit-4 F22]
                    logDiag('timer', 'unverified_shrunk', { oldDeadline: oldDeadline, newDeadline: newDeadline });
                } catch (e) {
                    logDiag('timer', 'unverified_shrink_fail', { msg: String((e && e.message) || '').slice(0, 80) });
                }
            });
        }
    } catch (e) {
        logDiag('error', 'onChanged', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
    }
});

// [v2.4.1] onAuthRequired – credentials are guaranteed loaded before proxy is active.
// This handler is a safety net. Primary protection is the startup sequence:
// 1. SW starts → proxy DISABLED (line ~38)
// 2. Credentials loaded from storage
// 3. initialize() re-enables proxy
// [v2.6.5 audit] Именованная функция + hasListener – без этого при SW wake возможна
// двойная регистрация (MV3 не гарантирует сохранение listener'ов через sleep).
// [v3.1.0] BLOCKING-режим (синхронный возврат) – на Chrome 109 asyncBlocking НЕ вызывается
// на proxy-CONNECT (подтверждено логами: hasListener=true, но FIRED ни разу, HTTPS=407).
// blocking даёт синхронный ответ; async storage-fallback тут невозможен, но creds грузятся
// при init + держатся offscreen-keepalive'ом.
// [v3.1.5] asyncBlocking + load-on-miss (техника 1VPN). РАНЬШЕ: синхронный ['blocking'] handler на
// холодном старте (cachedCredentials=null) возвращал {} → Chrome показывал ОКНО ПАРОЛЯ прокси. Особенно
// больно для TLS-нод (scheme:https), где onAuthRequired — единственный auth-путь для CONNECT (DNR
// Proxy-Authorization не покрывает CONNECT к secure-прокси) → окно пароля + 10с-таймаут «сервер не
// отвечает». ТЕПЕРЬ: asyncBlocking позволяет прочитать selectedProxy из storage АСИНХРОННО и ВСЕГДА
// ответить кредами, НИКОГДА пусто. Так делает 1VPN (17 free-серверов, без окна пароля).
function _onAuthRequiredHandler(details, callback) {
    const _cb = (typeof callback === 'function') ? callback : function () {};
    if (!details.isProxy) { _cb({}); return; }
    if (cachedCredentials) { _cb({ authCredentials: cachedCredentials }); return; }
    // cold SW / cache miss → грузим креды из selectedProxy в storage, ПОТОМ отвечаем (asyncBlocking).
    let _answered = false;
    const _ans = function (v) { if (_answered) return; _answered = true; _cb(v); };
    try {
        chrome.storage.local.get(['selectedProxy'], function (data) {
            if (!chrome.runtime.lastError && data && data.selectedProxy && data.selectedProxy.username) {
                cachedCredentials = { username: data.selectedProxy.username, password: data.selectedProxy.password };
                _ans({ authCredentials: cachedCredentials });
            } else {
                _ans({});
            }
        });
    } catch (_b) { _ans({}); }
}
try {
    if (!chrome.webRequest.onAuthRequired.hasListener(_onAuthRequiredHandler)) {
        // asyncBlocking — MV3-корректный путь (permission webRequestAuthProvider). Handler отвечает через callback.
        chrome.webRequest.onAuthRequired.addListener(
            _onAuthRequiredHandler,
            { urls: ['<all_urls>'] },
            ['asyncBlocking']
        );
    }
} catch (eReg) {
    // Fallback: sync blocking (старые движки без asyncBlocking/webRequestAuthProvider). Не cancel — {}
    // graceful (страница не рвётся; в худшем случае разовое окно пароля вместо полного обрыва).
    try {
        chrome.webRequest.onAuthRequired.addListener(function (d) { if (!d.isProxy) return {}; return cachedCredentials ? { authCredentials: cachedCredentials } : {}; }, { urls: ['<all_urls>'] }, ['blocking']);
    } catch (_r3) {}
}

// === TOGGLE CORE ===
async function doToggleProxy() {
    await checkPremiumExpiration();
    const current = await isProxyEnabled();
    const newState = !current;
    logDiag('toggle', newState ? 'connecting' : 'disconnecting');
    if (newState) {
        // [v2.8.0] УБРАНО: периодический checkAccountStatus на toggle ON.
        // Флаг accountVerified ставится один раз при link-uid, дальше не перепроверяется
        // (экономим серверную нагрузку – single check вместо повторов на каждый toggle ON).

        // [v2.5.9] Auto-select BEFORE proxyEnabled=true – this way the storage.onChanged
        // handler for selectedProxy skips re-entry (isProxyEnabled() is still false).
        // Uses in-memory serverList if available; otherwise skips (popup pre-warms on open).
        let _autoSelStatus;
        try { _autoSelStatus = await maybeAutoSelectServer(); } catch (_e) { _autoSelStatus = undefined; }
        // [v3.0.3] Free + ВСЕ free-сервера ≥75 → подключать некуда. Бросаем server_overloaded_free
        // (как guard ниже): popup покажет UI, а hotkey-обработчик (onCommand) – браузерное
        // уведомление. throw до set proxyEnabled ниже → VPN остаётся выключенным.
        if (_autoSelStatus === 'all_overloaded') {
            // [v3.0.3] Автовыбор не нашёл сервер (все free ≥75 / сломаны / исключены) → отдельная
            // ошибка no_server_available: popup покажет no-server модалку (кэш/диагностика/поддержка),
            // а не freeBlocked (тот про «выбран перегруженный» + Premium).
            logDiag('toggle', 'free_no_server_available', {});
            throw new Error('no_server_available');
        }

        // [v2.7.3] Guard: free-юзер не может подключиться к free-серверу с нагрузкой >= FREE_LOAD_LIMIT.
        // Popup блокирует выбор в списке, но есть два пути обхода: (1) Alt+Shift+V с уже
        // выбранным перегруженным сервером, (2) race condition – юзер выбрал сервер когда
        // u был 74, потом u вырос до 75 до того как popup доставил toggle-сообщение.
        // [v2.8.1] cachedServerStats теперь indexed by host:port (стабильный ключ) –
        // serverList lookup/findIndex больше не нужен.
        try {
            const guard = await chrome.storage.local.get(['isPremium','selectedProxy','cachedServerStats']);
            // [v3.0.3] ЖИВАЯ нагрузка (тот же SW-фетч, 60с-кэш – обычно уже прогрет
            // maybeAutoSelectServer выше). Fallback на cachedServerStats. Закрывает обход
            // guard'а через Alt+Shift+V на чистой установке (пустой popup-кэш → users=0 → пропуск).
            const _gLive = await fetchServerStatsSW();
            const _gStats = (_gLive && typeof _gLive === 'object' && !Array.isArray(_gLive)) ? _gLive : (guard.cachedServerStats || {});
            // [v2.8.0 audit r5+r6] typeof === 'object' + !Array.isArray guard – без них
            // corrupted storage (selectedProxy = string/number/array) проходил truthy check,
            // потом `.host` = undefined → check skipped → free-юзер обходил free-load-block.
            // typeof null === 'object' исключён через truthy check; typeof [] === 'object'
            // тоже true → отдельная защита Array.isArray. Симметрично F128-F143.
            if (!guard.isPremium && guard.selectedProxy && typeof guard.selectedProxy === 'object' && !Array.isArray(guard.selectedProxy)) {
                const sk = _serverKey(guard.selectedProxy);
                if (sk) {
                    const users = Number(_gStats && _gStats[sk]) || 0;
                    if (users >= FREE_LOAD_LIMIT) {
                        logDiag('toggle', 'free_blocked_load', { sk: sk, users: users });
                        throw new Error('server_overloaded_free');
                    }
                }
            }
        } catch (e) {
            if (e && e.message === 'server_overloaded_free') throw e;
            // Любая другая ошибка при guard-проверке (storage.get, serverList пустой и т.п.) –
            // не блокируем toggle, пропускаем guard. Диагностика в logDiag уже была выше если throw.
        }
    }
    // [v2.7.1 fix F90] Defense-in-depth: storage.set может throw QuotaExceededError при
    // близком к 10MB лимите (типично 545KB, но user мог наполнить 10K доменов в blacklist).
    // Без guard exception всплывает в caller (popup-message handler / keybinding handler) →
    // popup получает {error:...} но state inconsistent: VPN видимо включается через onChanged
    // не fires (set fail), badge остаётся stale. logDiag для post-mortem.
    try {
        await chrome.storage.local.set({ proxyEnabled: newState });
    } catch (e) {
        logDiag('toggle', 'state_set_fail', { msg: String((e && e.message) || e).slice(0, 80) });
        throw new Error('storage_quota_exceeded');
    }
    if (newState) {
        // 10 sec total timeout for connection
        let timedOut = false;
        let timeoutId;
        let connectResult;
        const _connectStart = Date.now(); // [v2.8.8] для sendConnectionStat latency_ms
        try {
            connectResult = await Promise.race([
                (async () => {
                    await ensureProxyList(true);
                    if (timedOut) return 'timeout';
                    const _proxyOk = await setProxy(true);
                    // [v3.1.1 audit] setProxy(true) возвращает false, когда applySelectedProxy не нашёл
                    // валидный сервер – оно УЖЕ откатило proxyEnabled=false + DIRECT + clearVpnTimer.
                    // Раньше return игнорировался → startVpnTimer/startHeartbeat/startKeepalive
                    // пересоздавались, connectResult='ok' → иконка ON при VPN off + фантомный heartbeat.
                    // Теперь роутим в unified rollback (как timeout).
                    if (_proxyOk === false) return 'timeout';
                    if (timedOut) return 'timeout';
                    // [v3.1.0] openWarmupPage перенесён ИЗ race'а вниз (awaited после connect) – прайм
                    // на Chrome 109 открывает вкладку на 3с, внутри 10с-race это рисковало timeout→rollback.
                    await startVpnTimer();
                    if (timedOut) return 'timeout';
                    // [v2.6.10] force=true – при явном VPN-ON immediate heartbeat должен пройти
                    // независимо от TTL (новая сессия, сервер должен сразу зафиксировать start).
                    startHeartbeat({ force: true });
                    // [v2.6.2 audit] Если timeout выиграет race между этими шагами,
                    // outer rollback уже вызвал stopHeartbeat/stopKeepalive – inner не должен их пересоздавать.
                    if (timedOut) { stopHeartbeat(); return 'timeout'; }
                    startKeepalive();
                    if (timedOut) { stopHeartbeat(); stopKeepalive(); return 'timeout'; }
                    await recordSessionStart();
                    if (timedOut) { stopHeartbeat(); stopKeepalive(); return 'timeout'; }
                    return 'ok';
                })(),
                new Promise(resolve => { timeoutId = setTimeout(() => { timedOut = true; resolve('timeout'); }, 10000); })
            ]);
        } catch (e) {
            // [v2.7.0 fix F3.1] Inner async может throw (напр., `await chrome.alarms.create` в
            // startVpnTimer после F3 fix). Раньше throw пропагировал до caller без rollback →
            // proxyEnabled=true + нет alarm = unlimited free VPN. Теперь treat как timeout,
            // идём в unified rollback ниже.
            logDiag('toggle', 'fail', { reason: 'throw', err: String((e && e.message) || '').slice(0, 80) });
            connectResult = 'timeout';
        }
        clearTimeout(timeoutId);
        if (connectResult === 'timeout') {
            if (timedOut) logDiag('toggle', 'fail', { reason: 'timeout' });
            // [v2.7.1 fix F82] Per-step try/catch – симметрично F17 в toggle-off ветке.
            // Раньше: throw из storage.set или setProxy(false) пропускал clearVpnTimer и
            // stopHeartbeat/stopKeepalive → VPN timer alarm оставался активным при
            // proxyEnabled=false → следующий cold-wake мог создать inconsistent state.
            // Каждый disconnect-step должен отработать независимо от предыдущего.
            try { await chrome.storage.local.set({ proxyEnabled: false }); } catch (e) { logDiag('toggle', 'rollback_set_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
            try { await setProxy(false); } catch (e) { logDiag('toggle', 'rollback_setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
            try { updateIcon(false); } catch {}
            try { await clearVpnTimer(); } catch (e) { logDiag('toggle', 'rollback_clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
            try { stopHeartbeat(); } catch {}
            try { stopKeepalive(); } catch {}
            // [v2.7.4 audit r6] Симметрия с success-OFF (line 2120): обнуляем cachedCredentials
            // на timeout-rollback. Иначе stale creds из failed connect-attempt могут просочиться
            // в onAuthRequired при следующем toggle-on на ДРУГОЙ сервер → 407 на первом запросе.
            cachedCredentials = null;
            // [v2.8.8] Stat: connection failed. fire-and-forget, не блокируем rollback.
            (async () => {
                try {
                    const sel = (await chrome.storage.local.get(['selectedProxy'])).selectedProxy;
                    if (sel && sel.host) {
                        sendConnectionStat(sel.host + ':' + sel.port, 'fail',
                            timedOut ? 'timeout' : 'throw',
                            Date.now() - _connectStart).catch(() => {});
                    }
                } catch {}
            })();
            throw new Error('connection_timeout');
        }
        // [v2.8.8] Stat: connection succeeded. fire-and-forget.
        (async () => {
            try {
                const sel = (await chrome.storage.local.get(['selectedProxy'])).selectedProxy;
                if (sel && sel.host) {
                    sendConnectionStat(sel.host + ':' + sel.port, 'ok', '',
                        Date.now() - _connectStart).catch(() => {});
                }
            } catch {}
        })();
        // [v3.1.0 FIX] Прайм авторизации выбранного сервера ПОСЛЕ успешного connect (awaited, вне
        // 10с-race → не рискует timeout→rollback). На Chrome 109 onAuthRequired для CONNECT надёжно
        // срабатывает только при загрузке страницы во вкладке → прайм кэширует пароль ДО начальной
        // проверки verifyAndRescueTunnel (hotkey) и ДО popup loadIpInfo. Без него первый запрос
        // ловит 407 → «IP недоступен» на живом сервере. openWarmupPage сам гейтит по версии (<116).
        try { await openWarmupPage(); } catch (eWarm) {}
    } else {
        // [v2.7.0 fix F17] Per-step try/catch – симметрично F2 в VPN_ALARM handler.
        // Раньше: throw из recordSessionEnd оставлял proxyEnabled=true в storage и
        // chrome.proxy всё ещё routил трафик (остальные шаги disconnect'а skipped).
        // [v2.8.2 audit-5 F30] cachedCredentials reset перенесён ВВЕРХ (раньше был внизу
        // на line 2975 – symmetric с VPN_ALARM audit-4 F27 + handle*Blocked F30).
        cachedCredentials = null;
        try { await recordSessionEnd(); } catch (e) { logDiag('toggle', 'recEnd_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await setProxy(false); } catch (e) { logDiag('toggle', 'setProxy_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { await clearVpnTimer(); } catch (e) { logDiag('toggle', 'clear_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
        try { stopHeartbeat(); } catch {}
        try { sendDisconnect(); } catch {}
        try { stopKeepalive(); } catch {}
    }
    logDiag('toggle', newState ? 'ok_on' : 'ok_off');
    updateIcon(newState);
    return newState;
}

// === KEYBOARD SHORTCUT ===
// [v2.8.2 vpn-conflict-block] Helper: проверяет storage флаг vpnConflictBlocked,
// который popup пишет когда детектирует другие активные VPN-расширения через chrome.management.
// Блокирует toggle/trial/recover на SW-стороне. Defense-in-depth: даже если popup закрыт
// и юзер жмёт Alt+Shift+V, проверка отрабатывает (флаг persisted в chrome.storage.local).
// [v3.1.1] Читает levelOfControl прокси с таймаутом. chrome.proxy.settings.get не имеет своего
// timeout; в теории callback может не прийти (extension-context edge) → страхуемся Promise-таймаутом,
// чтобы не подвесить вызывающий await. Возвращает строку levelOfControl или null.
function _getLevelOfControl(timeoutMs) {
    return new Promise((res) => {
        let done = false;
        const finish = (v) => { if (!done) { done = true; res(v); } };
        try {
            if (!chrome.proxy || !chrome.proxy.settings || !chrome.proxy.settings.get) { finish(null); return; }
            chrome.proxy.settings.get({}, (cfg) => finish((cfg && cfg.levelOfControl) || null));
        } catch (_) { finish(null); }
        setTimeout(() => finish(null), timeoutMs || 1500);
    });
}
async function isVpnConflictBlocked() {
    // [v3.1.1] Клиентский conflict-block ОТКЛЮЧЁН (см. silentVpnConflictCheck в popup): другой VPN,
    // установленный но не проксирующий, не должен мешать включению. Browsec/Hola и др. держат
    // levelOfControl даже вхолостую → блокировать по нему нельзя (ложный блок при неактивном Browsec).
    // Разрешаем попытку; реальный перехват показывает POST-баннер checkProxyControl. Trial-abuse
    // через чужой VPN отсекает СЕРВЕР (request-trial.php: datacenter/VPN-IP → отказ триала).
    return false;
}
chrome.commands.onCommand.addListener(async (command) => {
    // [v2.7.6] Diagnostic: фиксируем срабатывание shortcut'а чтобы саппорт мог
    // отличить «Chrome не fires event» (юзер не настроил chrome://extensions/shortcuts
    // или конфликт shortcut'ом) от «handler fired но toggle упал».
    logDiag('shortcut', 'cmd', { c: String(command || '').slice(0, 32) });
    if (command === 'toggle-vpn') {
        if (toggleInProgress || pingInProgress) {
            logDiag('shortcut', 'busy', {});
            return;
        }
        // [v2.8.2 audit-3 F17 / v3.1.1 audit] toggleInProgress=true СИНХРОННО сразу после guard.
        // Onboarding-check ниже делает await (storage.get + isProxyEnabled); если ставить mutex
        // ПОСЛЕ него (как было в 3.0.5), между guard и set снова открывалось 1-5ms окно на второй
        // хоткей. Держим mutex весь async block; onboarding-return сбрасывает его через finally (~4037).
        toggleInProgress = true;
        let resultState = null;
        try {
            // [v3.0.5] Первичная настройка не пройдена (onboardingV2Done не стоит) И VPN сейчас ВЫКЛ →
            // НЕ подключаем по хоткею, шлём уведомление «откройте расширение». Мастер подберёт рабочий
            // сервер до первого коннекта. Выключить хоткеем (VPN уже ON) не мешаем – гейт только на connect.
            try {
                const _stp = await chrome.storage.local.get(['onboardingV2Done']);
                if (!(_stp && _stp.onboardingV2Done) && !(await isProxyEnabled())) {
                    logDiag('shortcut', 'setup_pending', {});
                    swNotifyI18n('setup_pending', 'setupHotkeyTitle', 'setupHotkeyText',
                        'Нужна первичная настройка', 'Откройте расширение AnonVPN и пройдите быструю настройку – подберём рабочий сервер.');
                    return;
                }
            } catch (eStp) {}
            // [v2.8.2 vpn-conflict-block] Блок Alt+Shift+V если другой VPN активен.
            if (await isVpnConflictBlocked()) {
                logDiag('shortcut', 'vpn_conflict_blocked', {});
                // [v2.8.2 audit-5 F31] Broadcast ACTUAL VPN state – не hardcoded false.
                // Если VPN был ON когда обнаружен конфликт, hardcoded false вызывал UI desync
                // (popup показывал «отключено» когда VPN реально работает). Отказ от toggle ≠
                // «выключен» – текущее состояние не меняется.
                const actualState = await isProxyEnabled();
                chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: actualState, reason: 'vpn_conflict' }).catch(() => {});
                return;
            }
            const newState = await doToggleProxy();
            resultState = newState;
            chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: newState }).catch(() => {});
        } catch (e) {
            // [v2.7.0 fix F18] Раньше: `catch(e) {}` (silent) – юзер нажал Alt+Shift+V,
            // ничего не происходит, popup может остаться в loading-state; при rapid press
            // возможен retry-loop (finally уже сбросил toggleInProgress). Теперь: диаг +
            // broadcast proxyStateChanged с корректным reason → popup обновит UI.
            const errMsg = String((e && e.message) || '').slice(0, 80);
            logDiag('toggle', 'shortcut_fail', { msg: errMsg });
            let reason = 'error';
            if (errMsg === 'connection_timeout') reason = 'timeout';
            else if (errMsg === 'server_overloaded_free') reason = 'server_overloaded_free';
            else if (errMsg === 'no_server_available') reason = 'no_server_available';
            chrome.runtime.sendMessage({
                action: 'proxyStateChanged',
                proxyEnabled: false,
                reason: reason
            }).catch(() => {});
            // [v2.7.3] Alt+Shift+V с перегруженным сервером – popup может быть закрыт,
            // просто broadcast'а недостаточно. System notification с ссылкой на upsell.
            if (reason === 'server_overloaded_free') {
                // [v2.7.4 audit r3] i18n + leading slash в iconUrl + .catch на Promise (F33-style).
                // Async storage.get для cachedTranslationsData (storage key, не SW-memory) +
                // language preference. Fallback на ru если переводы не загружены.
                (async () => {
                    try {
                        const d = await chrome.storage.local.get(['language', 'cachedTranslationsData']);
                        const lang = d.language || 'ru';
                        const data = d.cachedTranslationsData || {};
                        const tr = data[lang] || data.en || {};
                        const tEn = data.en || {};
                        const notifTitle = tr.freeBlockedTitle || tEn.freeBlockedTitle || 'Сервер недоступен';
                        const notifMsg = tr.freeBlockedText || tEn.freeBlockedText || 'Этот сервер перегружен. Free-пользователям доступны только серверы с низкой нагрузкой. Откройте расширение для смены сервера или активации Premium.';
                        chrome.notifications.create('free_overloaded_' + Date.now(), {
                            type: 'basic',
                            iconUrl: '/icons/AnonVPN128.png',
                            title: notifTitle,
                            message: notifMsg,
                            priority: 1
                        }).catch(() => {});
                    } catch {}
                })();
            } else if (reason === 'no_server_available') {
                // [v3.0.3] Автовыбор не нашёл сервер для подключения (hotkey, popup закрыт) – уведомление.
                swNotifyI18n('no_server', 'noServerTitle', 'ipBrokenNoServer',
                    'Не удалось подключиться', 'Не удалось подключиться ни к одному серверу. Откройте расширение.');
            }
        }
        finally { toggleInProgress = false; }
        // [v3.0.3] После hotkey-ВКЛ – проверка туннеля + авто-смена сервера при сломе («IP недоступен»).
        // ВНЕ toggle-мьютекса (toggle уже завершён → не блокируем повторный toggle), но в await
        // listener'а – Chrome держит SW живым до завершения проверки/переключения.
        if (resultState === true) { try { await verifyAndRescueTunnel({ notify: true }); } catch (_e) {} }
    }
});

// [v2.6.8] Авто-rollback по onProxyError убран полностью. Ранее (2.6.5–2.6.7) SW
// считал fatal-ошибки и при достижении порога отключал VPN. На практике это давало
// ложные отключения: переход сетей, краткий TLS-retry, или первые несколько запросов
// при подключении к живому прокси могли добить счётчик. Теперь VPN остаётся включённым
// пока пользователь сам его не выключит – chrome.proxy ошибки только пишутся в
// диагностический лог для копирования в поддержку.
function _onProxyErrorHandler(details) {
    const errMsg = String((details && details.error) || 'unknown').slice(0, 80);
    const fatal = !!(details && details.fatal);
    logDiag('proxy', 'error', { err: errMsg, fatal: fatal });
}
if (chrome.proxy && chrome.proxy.onProxyError && !chrome.proxy.onProxyError.hasListener(_onProxyErrorHandler)) {
    chrome.proxy.onProxyError.addListener(_onProxyErrorHandler);
}

// === MESSAGE HANDLING ===
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // [v2.6.6 audit] Defense-in-depth: отклоняем сообщения от внешних отправителей.
    // externally_connectable в manifest не объявлен – этот путь уже закрыт браузером,
    // но явный guard страхует от случайного добавления в manifest в будущем.
    if (sender && sender.id && sender.id !== chrome.runtime.id) return false;
    // [round 11] message null-guard. message.action read on null/undefined → TypeError
    // crash entire listener path. Возможно если внутренний код шлёт sendMessage без аргумента.
    if (!message || typeof message !== 'object') return false;
    if (message.action === 'rescueTunnel') {
        // [v3.0.3] Popup обнаружил «IP недоступен» → просит SW проверить туннель и сменить сервер
        // на рабочий (notify=false – popup сам показывает статус). Возврат {ok,switched,busy}.
        verifyAndRescueTunnel({ notify: false }).then(function(r){ try { sendResponse(r || {}); } catch (e) {} });
        return true; // async sendResponse
    }
    if (message.action === 'getRemainingTime') {
        // [v2.8.1 audit] try/catch – popup мог закрыться mid-storage.get → sendResponse
        // throws "message port closed" → unhandled rejection. Симметрично остальным async handlers.
        getRemainingTime((seconds) => { try { sendResponse({ secondsLeft: seconds }); } catch {} });
        return true;
    }
    if (message.action === 'getVersion') {
        sendResponse({ version: EXT_VERSION });
        return false;
    }
    // [v2.8.8] Popup просит переапплаить proxy config (например, bypassRuDomains toggled).
    // Re-runs setProxy с текущим selectedProxy – новые bypass-правила вступят сразу,
    // без необходимости off/n cycle. Mutex `_reapplyInFlight` против spam-click race
    // (5 кликов = 5 параллельных setProxy → последний выигрывает, но в середине возможна
    // несогласованность DNR auth-rule и chrome.proxy.settings).
    if (message.action === 'reapplyProxyConfig') {
        (async () => {
            // [v3.1.1 audit] Guard toggleInProgress – reapply (bypassRu toggle) во время активного
            // doToggleProxy = конкурентный setProxy → рассинхрон DNR-auth-rule и chrome.proxy.settings.
            if (toggleInProgress) { try { sendResponse({ ok: false, reason: 'busy' }); } catch {} return; }
            if (_reapplyInFlight) { try { sendResponse({ ok: false, reason: 'in_flight' }); } catch {} return; }
            _reapplyInFlight = true;
            try {
                if (!await isProxyEnabled()) { try { sendResponse({ ok: true, reason: 'not_active' }); } catch {} return; }
                const { selectedProxy } = await chrome.storage.local.get(['selectedProxy']);
                if (selectedProxy && selectedProxy.host) {
                    await setProxy(selectedProxy);
                    logDiag('reapply', 'ok', { reason: String(message.reason || '').slice(0, 24) });
                    try { sendResponse({ ok: true }); } catch {}
                } else {
                    try { sendResponse({ ok: false, reason: 'no_proxy' }); } catch {}
                }
            } catch (e) {
                logDiag('reapply', 'fail', { err: String((e && e.message) || '').slice(0, 80) });
                try { sendResponse({ ok: false, reason: 'exception' }); } catch {}
            } finally {
                _reapplyInFlight = false;
            }
        })();
        return true;
    }
    // [v3.1.3] Статус фоновой проверки скорости для шапки модалки «Выбор сервера»:
    // running (идёт проход очереди), vpnOn (проверка на паузе при включённом ВПН),
    // nextAt (время следующего alarm-тика). kick=true на первом опросе при открытии
    // модалки – будим цикл сразу, не дожидаясь alarm до 60с; guards внутри ghostPingTick
    // сами отсеют лишнее (busy/VPN/пустая очередь/незавершённый setup).
    if (message.action === 'ghostPingStatus') {
        (async () => {
            let alarmAt = 0;
            try { const al = await chrome.alarms.get(GHOST_PING_ALARM); if (al && al.scheduledTime) alarmAt = al.scheduledTime; } catch (e) {}
            const vpnOn = await isProxyEnabled();
            if (message.kick && !_ghostLoopActive && !_ghostPingBusy && !vpnOn) {
                setTimeout(function(){ ghostPingTick().catch(function(){}); }, 50);
            }
            const running = _ghostLoopActive || _ghostPingBusy;
            // [v3.1.3] nextAt = время РЕАЛЬНОЙ перепроверки: когда ближайший пинг пула устареет
            // (до 30 мин), выровненное вверх по минутной alarm-сетке (очередь подхватит первый
            // alarm-тик ПОСЛЕ устаревания). Раньше отдавали ближайший тик (каждую минуту), даже
            // когда он заведомо пустой – отсчёт при полностью свежих пингах был бессмысленным.
            let nextAt = alarmAt;
            if (!running && !vpnOn && alarmAt) {
                try {
                    const eligibleAt = await _ghostNextEligibleAt();
                    if (eligibleAt > alarmAt) nextAt = alarmAt + Math.ceil((eligibleAt - alarmAt) / 60000) * 60000;
                    // eligibleAt ≤ alarmAt (очередь уже созрела / есть непроверенные) → ближайший тик
                } catch (e) {}
            }
            try { sendResponse({ ok: true, running: running, vpnOn: vpnOn, nextAt: nextAt }); } catch (e) {}
        })();
        return true;
    }
    if (message.action === 'checkLatestVersion') {
        // [v2.7.4] Triggered popup-side в applyUpdateBanner перед чтением storage.updateAvailable.
        // checkLatestVersion записывает результат в storage; popup читает после ack.
        checkLatestVersion()
            .then(() => { try { sendResponse({ ok: true }); } catch {} })
            .catch(() => { try { sendResponse({ ok: false }); } catch {} });
        return true;
    }
    if (message.action === 'getUserMessages') {
        getUserMessages(message && Array.isArray(message.readIds) ? message.readIds : null)
            .then(r => { try { sendResponse(r); } catch {} })
            .catch(() => { try { sendResponse({ ok: false, reason: 'err' }); } catch {} });
        return true;
    }
    if (message.action === 'getDiagnosticLog') {
        (async () => {
            try {
                // [v2.6.2] Помимо state дампим ВСЕ storage-ключи + помечаем «неизвестные»
                // (остатки от старых версий). Используется единая KNOWN_STORAGE_KEYS –
                // та же что и для автоочистки в onInstalled update.
                const all = await chrome.storage.local.get(null);
                const keySizes = {};
                const unknownKeys = [];
                // [v2.7.0 fix F74] Защита от выдачи длины plaintext-credentials через диагностику.
                // selectedProxy содержит {host,port,username,password,type} – JSON-length позволяет
                // bruteforce'ить длину password. proxyListEnc/uid/premiumKey тоже редактируем.
                const SENSITIVE_SIZE_KEYS = new Set(['selectedProxy', 'proxyListEnc', 'uid', 'premiumKey']);
                Object.keys(all).forEach(k => {
                    let sz = 0;
                    try { sz = JSON.stringify(all[k]).length; } catch { sz = -1; }
                    keySizes[k] = SENSITIVE_SIZE_KEYS.has(k) ? -2 : sz;
                    if (!KNOWN_STORAGE_KEYS.has(k)) unknownKeys.push(k);
                });
                // [v3.1.2] Активный замер расхождения системных часов с сервером (не ленивый
                // clockOffsetSec, который = 0 до первого 401 err:clock). Ловит сбитые часы юзера ДО
                // того как протухнут HMAC-подписи. null = сервер недоступен/таймаут (оффлайн).
                let _liveClockDiff = null;
                try { _liveClockDiff = await fetchServerClockOffset(); } catch (e) {}
                if (_liveClockDiff !== null && Math.abs(_liveClockDiff) <= 24 * 3600) clockOffsetSec = _liveClockDiff;
                sendResponse({
                    log: all.diagnosticLog || [],
                    state: {
                        proxyEnabled: !!all.proxyEnabled,
                        isPremium: !!all.isPremium,
                        autoSelectServer: all.autoSelectServer !== false,
                        sessionExpired: !!all.sessionExpired,
                        updateRequired: !!all.updateRequired,
                        illegalExtId: !!all.illegalExtId,
                        hasSelectedProxy: !!all.selectedProxy,
                        hasEncryptedCache: !!all.proxyListEnc,
                        vpnDeadline: all[VPN_DEADLINE_KEY] || null,
                        language: all.language || null,
                        serverListSize: Array.isArray(serverList) ? serverList.length : 0,
                        vpnBlockedFlag: vpnBlocked,
                        vpnBlockedAgeMs: vpnBlocked ? (Date.now() - vpnBlockedAt) : 0,
                        clockOffsetSec: clockOffsetSec,
                        serverClockDiff: _liveClockDiff, // [v3.1.2] активный замер расхождения с сервером (сек); null = не удалось
                        extId: chrome.runtime.id || null,
                        // [v2.8.5] Полный UID – нужен юзеру, чтобы сообщить его в поддержку
                        // для адресных сообщений (admin/user-messages.php). В event-логе UID
                        // обрезан до 10 симв., поэтому показываем целиком здесь, в State.
                        uid: all.uid || null,
                        version: EXT_VERSION,
                        storageKeys: Object.keys(all).length,
                        storageKeySizes: keySizes,
                        storageUnknownKeys: unknownKeys
                    }
                });
            } catch (e) {
                sendResponse({ log: [], state: {}, error: e && e.message });
            }
        })();
        return true;
    }
    if (message.action === 'getProxies') {
        // [v2.5.8] не форсим сеть – мгновенно отдаём из памяти/кэша,
        // ensureProxyList сам в фоне обновит
        // [v2.5.8 audit] обязательный .catch – иначе popup зависнет на undefined при ошибке
        // [v2.6.5 audit] try/catch вокруг sendResponse – popup мог закрыться за время fetch,
        // тогда sendResponse throws «message port closed», портит unhandled rejection лог.
        ensureProxyList(false)
            .then(list => { try { sendResponse({ proxies: list || [] }); } catch {} })
            .catch(() => { try { sendResponse({ proxies: [] }); } catch {} });
        return true;
    }
    if (message.action === 'toggleProxy') {
        // [FIX #7] Guard от двойного нажатия
        // [v2.8.2 audit-5 F32] try/catch на ВСЕ sendResponse – popup может закрыться mid-flight,
        // sendResponse на closed port throws. Symmetric с requestTrial/recoverPremium pattern.
        if (toggleInProgress) {
            try { sendResponse({ error: 'busy' }); } catch {}
            return true;
        }
        // [v2.6.2] Не перезаписываем proxy.settings во время активного ping'а
        if (pingInProgress) {
            try { sendResponse({ error: 'ping_active' }); } catch {}
            return true;
        }
        toggleInProgress = true;
        (async () => {
            try {
                // [v2.8.2 vpn-conflict-block] Блок toggle если другой VPN активен.
                // Проверка ВНУТРИ async чтобы корректно отработать toggleInProgress reset в finally.
                if (await isVpnConflictBlocked()) {
                    logDiag('toggle', 'vpn_conflict_blocked', {});
                    try { sendResponse({ error: 'vpn_conflict' }); } catch {}
                    return;
                }
                const newState = await doToggleProxy();
                try { sendResponse({ proxyEnabled: newState }); } catch {}
            } catch(e) {
                if (e.message === 'connection_timeout') {
                    try { sendResponse({ error: 'timeout' }); } catch {}
                } else if (e.message === 'storage_quota_exceeded') {
                    // [v2.7.1 fix F93] Specific reason – popup show'ит translation
                    // 'storageLimitExceeded' вместо generic «нет интернета»
                    try { sendResponse({ error: 'storage_quota_exceeded' }); } catch {}
                } else if (e.message === 'server_overloaded_free' || e.message === 'no_server_available') {
                    // [v3.0.3] Не удалось подобрать сервер → broadcast reason, чтобы popup показал модалку
                    // (freeBlocked для «выбран перегруженный» / no-server для «нечего подключать»). Раньше
                    // падало в else → {proxyEnabled:false} без reason → кнопка просто мигала, фидбэка нет.
                    try { chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: false, reason: e.message }).catch(() => {}); } catch {}
                    try { sendResponse({ proxyEnabled: false, reason: e.message }); } catch {}
                } else {
                    try { sendResponse({ proxyEnabled: await isProxyEnabled() }); } catch {}
                }
            } finally {
                toggleInProgress = false;
            }
        })();
        return true;
    }
    if (message.action === 'premiumActivated') {
        (async () => {
            // [v2.7.0 fix F39] Если сейчас в полёте requestTrial или recoverPremium, эти
            // handler'ы уже wipe'ают selectedProxy + ensureProxyList(true). Параллельный
            // premiumActivated удвоит storage-writes и fetch → race. Ждём завершения.
            if (_trialInFlight || _recoverInFlight) {
                logDiag('premium', 'activated_wait_inflight');
                // Не делаем синхронного wait (может зависнуть если in-flight handler сам throws);
                // просто skip – trial/recover уже сделают всю нужную работу включая applyPremiumState.
                return;
            }
            // [v2.7.3 audit] toggleInProgress guard – user может одновременно нажать
            // Alt+Shift+V когда popup шлёт premiumActivated. Параллельный doToggleProxy
            // использует selectedProxy из storage до того как наш handler его удалит →
            // free-сервер выбирается для premium-юзера. Skip – applyPremiumState через
            // storage.onChanged всё равно подхватит isPremium=true.
            if (toggleInProgress) {
                logDiag('premium', 'activated_toggle_busy');
                return;
            }
            try {
                await chrome.alarms.clear(VPN_ALARM_NAME);
                // [round 11] +rateLimited{,Reason,Until} – premium-юзер обходит лимиты,
                // если ban-флаг от free-периода стоит, popup продолжит показывать банер
                // несмотря на премиум до следующего успешного proxy_list.php fetch.
                await chrome.storage.local.remove(['selectedProxy', 'sessionExpired',
                    'rateLimited', 'rateLimitedReason', 'rateLimitedUntil']);
                // [v2.7.0 fix F36.1] Обнулить кэш creds – был от free-proxy, после activate
                // premium следующий onAuthRequired должен заново подтянуть premium-proxy creds.
                cachedCredentials = null;
                await ensureProxyList(true);
                // [v2.8.1 audit] Explicit applyPremiumState – defense-in-depth с storage.onChanged
                // listener. Гарантирует ad-blocker DNR + badge sync до завершения handler'а,
                // не полагаясь на async fire listener'а после storage.set от popup.
                try { await applyPremiumState(); } catch (e) { logDiag('premium', 'apply_fail', { msg: String((e && e.message) || '').slice(0, 80) }); }
                const enabled = await isProxyEnabled();
                if (enabled) {
                    // [v2.7.0 fix F11.1] startVpnTimer() здесь был no-op (симметрично F11
                    // в recoverPremium): сам внутри проверяет isPremium и сразу clear alarm +
                    // return. Alarm уже clear'ен выше на строке 1914. Удаляем dead-call.
                    await setProxy(true);
                }
            } catch (e) {
                logDiag('premium', 'activated_handler_err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
            }
        })();
        return false;
    }
    if (message.action === 'exclusionsUpdated') {
        (async () => {
            try {
                const en = await isProxyEnabled();
                if (en) await setProxy(true);
            } catch (e) {
                logDiag('exclusions', 'update_err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
            }
        })();
        return false;
    }
    // [v2.6.2] Recovery – восстанавливает активный Premium-ключ из БД по uid.
    // Для случаев "случайно нажал Выйти" или reinstall'а – ключ ещё не expired в premium_users.
    if (message.action === 'recoverPremium') {
        if (_recoverInFlight) {
            try { sendResponse({ ok: false, reason: 'in_flight' }); } catch {}
            return false;
        }
        _recoverInFlight = true;
        (async () => {
            try {
                // [v2.8.2 vpn-conflict-block] Блок recovery если другой VPN активен.
                // Recovery идёт по fp_hash_soft (без ext_id) – другой IP даёт новый fp_hash_soft,
                // и юзер мог бы получить чужой ключ если recover'ил под маскировкой.
                if (await isVpnConflictBlocked()) {
                    logDiag('recover', 'vpn_conflict_blocked', {});
                    try { sendResponse({ ok: false, reason: 'vpn_conflict' }); } catch {}
                    return;
                }
                const uid = await getUID();
                const extId = chrome.runtime.id || '';
                // [v2.8.2 audit-2 F7] Hardware FP – symmetric с requestTrial. Идёт через message
                // payload (popup собирает collectHardwareFp перед sendMessage). Recovery с FP
                // добавляет Tier 1.5 на сервере: survives reinstall + IP change → правильный owner.
                const clientFp = (typeof message.clientFp === 'string' && /^[a-f0-9]{64}$/.test(message.clientFp)) ? message.clientFp : '';
                const useProto2 = (clientFp !== '');
                let ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
                let retriedOnClock = false;
                let res, body = null;
                // [v2.6.2] Auto-retry один раз на reason='clock' – спасает юзеров с дрейфом часов
                while (true) {
                    const nonce = bytes2hex(crypto.getRandomValues(new Uint8Array(16)));
                    let sigInput = uid + '|' + ts + '|' + nonce + '|' + extId + '|' + EXT_VERSION;
                    if (useProto2) sigInput += '|' + clientFp;
                    const sig = await hmacSignHex(hex2bytes(HMAC_KEY_HEX), sigInput);

                    const headers = {
                        'Content-Type': 'application/json',
                        'X-AnonVPN-Proto': useProto2 ? '2' : '1',
                        'X-AnonVPN-Version': EXT_VERSION,
                        'X-AnonVPN-ExtID': extId,
                        'X-AnonVPN-UID': uid,
                        'X-AnonVPN-Timestamp': String(ts),
                        'X-AnonVPN-Nonce': nonce,
                        'X-AnonVPN-Sig': sig
                    };
                    if (useProto2) headers['X-AnonVPN-ClientFP'] = clientFp;

                    res = await apiFetch('/AnonVPN/recover-premium.php', {
                        method: 'POST',
                        cache: 'no-store',
                        headers: headers,
                        body: '{}',
                        signal: AbortSignal.timeout(15000)
                    });

                    body = null;
                    try { body = await res.json(); } catch(_) { body = null; }

                    if (!res.ok && body && body.reason === 'clock' && !retriedOnClock) {
                        retriedOnClock = true;
                        const newOffset = await fetchServerClockOffset();
                        if (newOffset !== null) {
                            clockOffsetSec = newOffset;
                            logDiag('recover', 'clock_adjusted', { offsetSec: newOffset });
                            ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
                            continue;
                        }
                    }
                    break;
                }

                if (!res.ok || !body || !body.ok) {
                    const reason = (body && body.reason) || 'error';
                    logDiag('recover', 'fail', { reason: reason, status: res.status });
                    try { sendResponse({ ok: false, reason: reason }); } catch {}
                    return;
                }

                // Восстанавливаем как обычный premium
                // [v2.6.7 audit] Defense-in-depth: см. коммент в requestTrial handler.
                const expTs = Number(body.expires_timestamp);
                if (!Number.isFinite(expTs) || expTs <= 0) {
                    logDiag('recover', 'bad_resp', { ts: typeof body.expires_timestamp });
                    try { sendResponse({ ok: false, reason: 'bad_server_response' }); } catch {}
                    return;
                }
                // [v2.7.1 fix F102] Reject empty premium_key – на ok:true сервер обязан
                // вернуть ключ. Без проверки `String(body.premium_key || '')` сохранил бы
                // пустую строку → next checkPremiumExpiration cycle wipe → user spinner.
                const recoveredKey = String(body.premium_key || '').trim();
                if (!recoveredKey) {
                    logDiag('recover', 'empty_key', {});
                    try { sendResponse({ ok: false, reason: 'bad_server_response' }); } catch {}
                    return;
                }
                // [v2.7.1 fix F90] Quota-guard на критическом пути активации premium.
                // Без него storage-fail = silent corruption: popup видит ok:true, но
                // isPremium не персистится → premium статус потерян после SW restart.
                try {
                    await chrome.storage.local.set({
                        isPremium: true,
                        premiumKey: String(body.premium_key || ''),
                        expiresAt: String(body.expires_at || ''),
                        expires_timestamp: expTs
                    });
                } catch (e) {
                    logDiag('recover', 'set_fail', { msg: String((e && e.message) || e).slice(0, 80) });
                    try { sendResponse({ ok: false, reason: 'storage_quota_exceeded' }); } catch {}
                    return;
                }
                await chrome.alarms.clear(VPN_ALARM_NAME);
                await chrome.storage.local.remove(['sessionExpired']);
                // [v2.7.0 fix F63] Симметрия с requestTrial wasOn-логикой. Popup-guard
                // блокирует recoverPremium при VPN-on, но edge-case race возможен:
                // если VPN on – оставляем текущую сессию живой, только снимаем 60-мин таймер;
                // если VPN off – wipe selectedProxy, next toggle подхватит premium-сервер.
                const wasOn = await isProxyEnabled();
                if (wasOn) {
                    await clearVpnTimer();
                } else {
                    await chrome.storage.local.remove(['selectedProxy']);
                    // [v2.7.0 fix F36.1] Обнулить кэш creds – следующий onAuthRequired
                    // подтянет premium-creds из нового selectedProxy.
                    cachedCredentials = null;
                }
                await ensureProxyList(true);
                await applyPremiumState();

                logDiag('recover', 'ok');
                chrome.runtime.sendMessage({ action: 'premiumActivated' }).catch(() => {});

                // [v2.8.2 audit-4 F24] try/catch – symmetric с requestTrial. См. комментарий там.
                try {
                    sendResponse({
                        ok: true,
                        expires_at: body.expires_at,
                        expires_timestamp: body.expires_timestamp
                    });
                } catch {}
            } catch (e) {
                const msg = (e && e.message) ? String(e.message).slice(0, 80) : 'unknown';
                logDiag('recover', 'err', { msg: msg });
                try { sendResponse({ ok: false, reason: 'network_error' }); } catch {}
            } finally {
                _recoverInFlight = false;
            }
        })();
        return true;
    }
    // [v2.6.2] Trial request – one-click 3-day Premium через server-side abuse detection.
    // Endpoint: AnonVPN/request-trial.php. Защита: HMAC-подпись, fingerprint, ASN-blocklist.
    if (message.action === 'requestTrial') {
        if (_trialInFlight) {
            try { sendResponse({ ok: false, reason: 'in_flight' }); } catch {}
            return false;
        }
        _trialInFlight = true;
        (async () => {
            try {
                // [v2.8.2 vpn-conflict-block] Блок trial если другой VPN активен (popup детектировал
                // через chrome.management). Без этого юзер с другим VPN получает свежий /24 IP →
                // обходит subnet_rate_limit → новый trial при каждой смене IP.
                if (await isVpnConflictBlocked()) {
                    logDiag('trial', 'vpn_conflict_blocked', {});
                    try { sendResponse({ ok: false, reason: 'vpn_conflict' }); } catch {}
                    return;
                }
                const uid = await getUID();
                const extId = chrome.runtime.id || '';
                // [v2.8.2 Этап Б] Hardware FP от popup. Format check (64 hex) – иначе fallback
                // на proto=1 (без FP). Защита от corrupted message.clientFp; legacy popup'ы (если
                // когда-нибудь будут) шлют без поля → '' → proto=1.
                const clientFp = (typeof message.clientFp === 'string' && /^[a-f0-9]{64}$/.test(message.clientFp)) ? message.clientFp : '';
                const useProto2 = (clientFp !== '');
                let ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
                let retriedOnClock = false;
                let res, body = null;
                // [v2.6.2] Auto-retry один раз на reason='clock' – спасает юзеров с дрейфом часов
                while (true) {
                    const nonce = bytes2hex(crypto.getRandomValues(new Uint8Array(16)));
                    // [v2.8.2 Этап Б] proto=2 включает clientFp в HMAC sigInput. Сервер симметричен.
                    let sigInput = uid + '|' + ts + '|' + nonce + '|' + extId + '|' + EXT_VERSION;
                    if (useProto2) sigInput += '|' + clientFp;
                    const sig = await hmacSignHex(hex2bytes(HMAC_KEY_HEX), sigInput);

                    const headers = {
                        'Content-Type': 'application/json',
                        'X-AnonVPN-Proto': useProto2 ? '2' : '1',
                        'X-AnonVPN-Version': EXT_VERSION,
                        'X-AnonVPN-ExtID': extId,
                        'X-AnonVPN-UID': uid,
                        'X-AnonVPN-Timestamp': String(ts),
                        'X-AnonVPN-Nonce': nonce,
                        'X-AnonVPN-Sig': sig
                    };
                    if (useProto2) headers['X-AnonVPN-ClientFP'] = clientFp;

                    res = await apiFetch('/AnonVPN/request-trial.php', {
                        method: 'POST',
                        cache: 'no-store',
                        headers: headers,
                        body: '{}',
                        signal: AbortSignal.timeout(15000)
                    });

                    body = null;
                    try { body = await res.json(); } catch(_) { body = null; }

                    if (!res.ok && body && body.reason === 'clock' && !retriedOnClock) {
                        retriedOnClock = true;
                        const newOffset = await fetchServerClockOffset();
                        if (newOffset !== null) {
                            clockOffsetSec = newOffset;
                            logDiag('trial', 'clock_adjusted', { offsetSec: newOffset });
                            ts = Math.floor(Date.now() / 1000) + clockOffsetSec;
                            continue;
                        }
                    }
                    break;
                }

                if (!res.ok || !body || !body.ok) {
                    const reason = (body && body.reason) || 'error';
                    logDiag('trial', 'fail', { reason: reason, status: res.status });
                    // [v2.6.5 audit r9] Spread вместо Object.assign – последний использует
                    // Set-семантику, которая триггерит __proto__ setter и меняет prototype
                    // локального объекта при compromised server-response. Spread использует
                    // CreateDataProperty (ES2018) – защищён от prototype pollution.
                    try { sendResponse({ ok: false, reason: reason, ...(body || {}) }); } catch {}
                    return;
                }

                // Успех: активируем как обычный premium-ключ
                // [v2.6.7 audit] Defense-in-depth: strict type-check expires_timestamp.
                // Если compromised-server вернёт "infinity"/string/null – checkPremiumExpiration
                // сравнивает через `>`, "infinity" > num = false, премиум никогда не истечёт.
                // [v2.7.1 fix F102] Reject empty premium_key – symmetric с recoverPremium.
                const trialKey = String(body.premium_key || '').trim();
                if (!trialKey) {
                    logDiag('trial', 'empty_key', {});
                    try { sendResponse({ ok: false, reason: 'bad_server_response' }); } catch {}
                    return;
                }
                const expTs = Number(body.expires_timestamp);
                if (!Number.isFinite(expTs) || expTs <= 0) {
                    logDiag('trial', 'bad_resp', { ts: typeof body.expires_timestamp });
                    try { sendResponse({ ok: false, reason: 'bad_server_response' }); } catch {}
                    return;
                }
                // [v2.7.1 fix F90] Quota-guard на критическом пути активации trial.
                // См. recoverPremium handler выше – symmetric pattern.
                try {
                    await chrome.storage.local.set({
                        isPremium: true,
                        premiumKey: String(body.premium_key || ''),
                        expiresAt: String(body.expires_at || ''),
                        expires_timestamp: expTs
                    });
                } catch (e) {
                    logDiag('trial', 'set_fail', { msg: String((e && e.message) || e).slice(0, 80) });
                    try { sendResponse({ ok: false, reason: 'storage_quota_exceeded' }); } catch {}
                    return;
                }
                // [v2.6.3] Бесшовная активация: если VPN уже on (urgency CTA под таймером),
                // не трогаем selectedProxy и не переподключаемся – текущая сессия продолжается без лимита.
                // Если VPN off – очищаем selectedProxy, чтобы next toggle выбрал premium-сервер автоматически.
                await chrome.alarms.clear(VPN_ALARM_NAME); // снимаем 60-мин free-таймер
                await chrome.storage.local.remove(['sessionExpired']);
                await ensureProxyList(true); // обновить список (premium-серверы доступны с этого момента)
                const wasOn = await isProxyEnabled();
                if (wasOn) {
                    await clearVpnTimer(); // убрать badge countdown – premium = unlimited
                } else {
                    await chrome.storage.local.remove(['selectedProxy']);
                    // [v2.7.0 fix F36.1] Обнулить кэш creds – см. recoverPremium выше.
                    cachedCredentials = null;
                }
                await applyPremiumState(); // включает ad-blocker для premium

                logDiag('trial', 'ok', { days: body.days_granted });
                // Broadcast чтобы popup обновил UI
                chrome.runtime.sendMessage({ action: 'premiumActivated' }).catch(() => {});

                // [v2.8.2 audit-4 F24] try/catch – popup может закрыться mid-flight (35s timeout
                // на FP-collect), sendResponse на closed port throws "message port closed". Storage
                // уже persisted (line 3501), trial активирован независимо от response delivery.
                try {
                    sendResponse({
                        ok: true,
                        days_granted: body.days_granted,
                        expires_at: body.expires_at,
                        expires_timestamp: body.expires_timestamp
                    });
                } catch {}
            } catch (e) {
                const msg = (e && e.message) ? String(e.message).slice(0, 80) : 'unknown';
                logDiag('trial', 'err', { msg: msg });
                try { sendResponse({ ok: false, reason: 'network_error', msg: msg }); } catch {}
            } finally {
                _trialInFlight = false;
            }
        })();
        return true;
    }
    // [v2.8.2 audit-4 F25] premiumDeactivated handler. Popup шлёт при logout (popup.js:1339);
    // SW также broadcast'ит сам (line 1488/1544). storage.onChanged listener уже вызывает
    // applyPremiumState через isPremium change – это primary defense. Этот handler – explicit
    // fallback на случай race (popup logout до того как storage.onChanged fired в SW). Idempotent
    // через _applyPremiumStateQueue. Sender не различаем (popup vs self) – applyPremiumState читает
    // fresh storage, double-call безопасен.
    if (message.action === 'premiumDeactivated') {
        // [v2.8.2 audit-5 F29] .catch – applyPremiumState возвращает _applyPremiumStateQueue
        // promise. Внутри queue уже есть .catch с logDiag, но если IIFE chain упадёт неожиданно
        // (corruption), unhandled rejection пропадёт. Defense-in-depth.
        applyPremiumState().catch(() => {});
        // Force badge refresh (free tier → нет «N мин» индикатора)
        updateBadge().catch(() => {});
        return false;
    }
    // [v2.8.0] Account-link API: проверка статуса (linked + verified) для тира 30/60 мин.
    // Force-refresh через `force:true` (popup при открытии); иначе TTL-guard 30 мин.
    if (message.action === 'checkAccount') {
        if (_checkAccountInFlight) {
            try { sendResponse({ ok: false, reason: 'in_flight' }); } catch {}
            return false;
        }
        _checkAccountInFlight = true;
        (async () => {
            try {
                const force = !!(message && message.force);
                const result = await checkAccountStatus(force);
                try { sendResponse(result); } catch {}
            } catch (e) {
                const msg = (e && e.message) ? String(e.message).slice(0, 80) : 'unknown';
                logDiag('account', 'check_err', { msg });
                try { sendResponse({ ok: false, reason: 'network_error', msg }); } catch {}
            } finally {
                _checkAccountInFlight = false;
            }
        })();
        return true;
    }
    // [v2.8.0] Link-UID: юзер ввёл код в popup → отправляем на сервер вместе с UID.
    if (message.action === 'linkUid') {
        if (_linkUidInFlight) {
            try { sendResponse({ ok: false, reason: 'in_flight' }); } catch {}
            return false;
        }
        _linkUidInFlight = true;
        (async () => {
            try {
                const code = (message && message.code) ? String(message.code).trim() : '';
                if (!/^[a-zA-Z0-9]{6,16}$/.test(code)) {
                    try { sendResponse({ ok: false, reason: 'bad_code_format' }); } catch {}
                    return;
                }
                const result = await linkUidWithCode(code);
                try { sendResponse(result); } catch {}
            } catch (e) {
                const msg = (e && e.message) ? String(e.message).slice(0, 80) : 'unknown';
                logDiag('account', 'link_err', { msg });
                try { sendResponse({ ok: false, reason: 'network_error', msg }); } catch {}
            } finally {
                _linkUidInFlight = false;
            }
        })();
        return true;
    }
    // [v3.1.1] Сигнал о завершении первичной настройки – ОДИН раз при первой установке. Guard
    // setupReported ставится ДО отправки (idempotent: если apiFetch упадёт, повторно не шлём –
    // best-effort). setupReported переживает апдейт (не в STALE), поэтому повторный мастер после
    // апдейта сигнал НЕ отправляет – интересна именно первая установка.
    if (message.action === 'reportSetupDone') {
        (async () => {
            // [v3.1.1 audit] In-memory guard от гонки двух popup: sync check-set (без await между) атомарен
            // в single-thread JS → вторая concurrent-попытка увидит true и выйдет, не дублируя сигнал.
            if (_setupReportInFlight) { try { sendResponse({ ok: true, already: true }); } catch {} return; }
            _setupReportInFlight = true;
            try {
                const d = await chrome.storage.local.get(['setupReported']);
                if (d.setupReported) { try { sendResponse({ ok: true, already: true }); } catch {} return; }
                await chrome.storage.local.set({ setupReported: true });
                await sendSetupDone(message.payload || {});
                try { sendResponse({ ok: true }); } catch {}
            } catch (e) { try { sendResponse({ ok: false }); } catch {} }
            finally { _setupReportInFlight = false; }
        })();
        return true;
    }
    // [v3.1.1] Результат полной диагностики → сервер (для техподдержки). Без guard: юзер может делать
    // проверку многократно, каждая = отдельная строка diagnostic_runs (история запусков).
    if (message.action === 'reportDiagRun') {
        (async () => {
            try { await sendDiagRun(message.payload || {}); try { sendResponse({ ok: true }); } catch {} }
            catch (e) { try { sendResponse({ ok: false }); } catch {} }
        })();
        return true;
    }
    // [v2.8.0] Отвязка: server-side DELETE FROM web_user_extensions + локальный wipe.
    // Server call защищён HMAC, fail-tolerant – если сеть лежит, всё равно чистим storage
    // (юзер ожидает что отвязка сработает; следующий generate-code на сайте всё равно
    // создаст свежую запись и заместит старую через ON CONFLICT).
    if (message.action === 'unlinkAccount') {
        (async () => {
            let serverOk = false;
            let serverReason = null;
            try {
                const h = await buildHmacHeaders();
                const res = await apiFetch('/AnonVPN/unlink-uid.php', {
                    method: 'POST',
                    cache: 'no-store',
                    headers: h.headers,
                    body: '{}',
                    signal: AbortSignal.timeout(8000)
                });
                if (res.ok) {
                    serverOk = true;
                } else {
                    let body = null;
                    try { body = await res.json(); } catch {}
                    serverReason = (body && body.reason) ? String(body.reason) : ('http_' + res.status);
                    logDiag('account', 'unlink_server_err', { status: res.status, reason: serverReason });
                }
            } catch (e) {
                serverReason = 'network_err';
                logDiag('account', 'unlink_fetch_err', { msg: String((e && e.message) || '').slice(0, 80) });
            }
            try {
                // [v2.8.2 audit-4 F26] +sessionExpired: stale free-session-expired banner после
                // toggle-off → unlink → toggle-on путал юзера (unlink сжал таймер с 60→30 мин,
                // banner от старой 60-мин сессии не убрался). Очищаем атомарно с unlink.
                await chrome.storage.local.remove(['accountVerified', 'accountEmail', 'sessionExpired']);
                try { sendResponse({ ok: true, serverOk: serverOk, serverReason: serverReason }); } catch {}
            } catch (e) {
                try { sendResponse({ ok: false, reason: 'storage_err' }); } catch {}
            }
        })();
        return true;
    }
    // v2.4.5: Ping proxy from user's perspective
    if (message.action === 'pingProxy') {
        (async () => {
            // [v2.5.4] Guard: нельзя пинговать при активном VPN – сломает соединение
            if (await isProxyEnabled()) { try { sendResponse({error:'vpn_active'}); } catch {} return; }
            // [v2.6.2] Guard: не пускаем параллельные ping'и (chrome.proxy.settings singleton)
            if (pingInProgress) { try { sendResponse({error:'ping_busy'}); } catch {} return; }
            // [v2.7.0 fix F61] Guard: VPN-toggle mid-flight уже дёргает chrome.proxy.settings;
            // ping параллельно перезапишет его, последовательность chrome.proxy.settings.set
            // получится last-writer-wins. Симметрично guard'у в chrome.commands.onCommand.
            if (toggleInProgress) { try { sendResponse({error:'toggle_busy'}); } catch {} return; }
            pingInProgress = true;
            // [v2.6.2 audit] Внешний try/finally гарантирует освобождение pingInProgress
            // даже если ensureProxyList() / другие async-операции до actual-ping-try бросят.
            // Иначе mutex залипал бы навсегда → все последующие ping'и failed бы.
            try {
                const key = message.serverKey;
                // [v2.5.8] список из памяти SW
                const list = serverList || await ensureProxyList() || [];
                const type = key.charAt(0) === 'p' ? 'premium' : 'free';
                const idx = parseInt(key.substring(1), 10);
                const filtered = list.filter(p => type === 'premium' ? p.type === 'premium' : p.type !== 'premium');
                const proxy = filtered[idx];
                if (!proxy) { try { sendResponse({error:'not_found'}); } catch {} return; }

                // [v2.6.0] Внутренний try/finally – восстановление direct-mode даже при exception в середине ping'а
                var pingMs = -1;
                var errMsg = null;
                try {
                    // [v2.7.4 audit r4] Defensive port-guard symmetric с setProxy (line 1518).
                    // Если server вернёт corrupt port (string или missing) – parseInt = NaN,
                    // Chrome silently rejects → ping fail без diagnostics.
                    const portNum = parseInt(proxy.port, 10);
                    if (!Number.isFinite(portNum) || portNum <= 0 || portNum > 65535) {
                        errMsg = 'invalid port';
                        throw new Error('invalid_port');
                    }
                    // Temporarily set proxy
                    updateCredentialCache(proxy);
                    await setProxyAuthRule(proxy);
                    await chrome.proxy.settings.set({
                        value: { mode:'fixed_servers', rules:{
                            singleProxy:{scheme:_proxyScheme(proxy),host:proxy.host,port:portNum},
                            bypassList: BYPASS_LIST
                        }},
                        scope:'regular'
                    });

                    // Warm-up: prime proxy connection (TCP + auth + TLS handshake)
                    try {
                        await fetch('http://cp.cloudflare.com', {
                            method:'HEAD', cache:'no-store',
                            signal: AbortSignal.timeout(10000)
                        });
                    } catch(e) {}

                    // Measure: User → Proxy → Cloudflare → back (clean, no setup overhead)
                    try {
                        var t0 = performance.now();
                        await fetch('http://cp.cloudflare.com', {
                            method:'HEAD', cache:'no-store',
                            signal: AbortSignal.timeout(10000)
                        });
                        pingMs = Math.round(performance.now() - t0);
                    } catch(e) { pingMs = -1; }
                } catch(e) {
                    errMsg = (e && e.message) || 'ping_error';
                } finally {
                    // Restore to direct – ВСЕГДА
                    try { await chrome.proxy.settings.set({value:{mode:'direct'},scope:'regular'}); } catch {}
                    try { await clearProxyAuthRule(); } catch {}
                }
                // [v2.6.5 audit] try/catch – popup мог закрыться пока ping идёт (10+ сек на
                // медленных соединениях), тогда sendResponse бросает «message port closed».
                if (errMsg) { try { sendResponse({error: errMsg}); } catch {} return; }
                try { sendResponse({ping_ms: pingMs}); } catch {}
                return;
            } catch (outerErr) {
                // Защита от exception до начала ping'а (например ensureProxyList throw)
                logDiag('ping', 'outer_err', { msg: (outerErr && outerErr.message) ? String(outerErr.message).slice(0, 80) : 'unknown' });
                try { sendResponse({error: 'setup_error'}); } catch {}
            } finally {
                pingInProgress = false;  // ОБЯЗАТЕЛЬНО освобождается во всех путях
            }
        })();
        return true;
    }
    // [v2.9.1] Bulk-ping топ-N free серверов по нагрузке. Запускается из onboarding
    // или из settings. Последовательный (chrome.proxy.settings singleton).
    // Storage: serverPings={[host:port]:{ms,ts}}; serverPingsRunAt=timestamp;
    // bulkPingProgress={done,total} – для recovery когда popup reopen'ится во время run.
    // [audit fix high-3+4] Cap 15, ~2.5 минуты.
    if (message.action === 'bulkPingTopServers') {
        (async () => {
            if (await isProxyEnabled()) {
                logDiag('bulkping', 'reject_vpn_active');
                try { sendResponse({error:'vpn_active'}); } catch {} return;
            }
            if (pingInProgress) {
                logDiag('bulkping', 'reject_busy');
                try { sendResponse({error:'ping_busy'}); } catch {} return;
            }
            if (toggleInProgress) { try { sendResponse({error:'toggle_busy'}); } catch {} return; }
            // [v2.9.1] Premium-only re-run: первый bulk-ping всем разрешён (в onboarding),
            // повторный – только Premium. Маркер «уже был run» = существование serverPingsRunAt.
            const premiumCheck = await chrome.storage.local.get(['isPremium','serverPingsRunAt']);
            if (premiumCheck.serverPingsRunAt && !premiumCheck.isPremium) {
                logDiag('bulkping', 'reject_premium_required', { lastRunAt: premiumCheck.serverPingsRunAt });
                try { sendResponse({error:'premium_required'}); } catch {} return;
            }
            // [v2.9.1 user feedback] cap снят – пингуем ВСЕ free серверы. Юзер хочет видеть
            // полную картину; ~10s/сервер × 30-40 серверов = 5-7 минут – приемлемо т.к.
            // прогресс виден в индикаторе и popup может закрываться.
            const BULK_PING_MAX_SERVERS = Number.MAX_SAFE_INTEGER;
            // Возьмём свежий список и stats
            const list = serverList || await ensureProxyList() || [];
            const isPremiumUser = !!premiumCheck.isPremium;
            // [v2.9.2 fix] Для Premium юзера пингуем и premium-серверы тоже –
            // иначе ping/all мод выбирает не «самый быстрый», а тот что без пинга →
            // пропускается → выбирается free с min ms (а не premium с min ms).
            const allCandidates = list.filter(p => p && p.host && p.port && (isPremiumUser || p.type !== 'premium'));
            if (allCandidates.length === 0) { try { sendResponse({error:'no_servers'}); } catch {} return; }
            const statsData = await chrome.storage.local.get(['cachedServerStats', 'excludedFromAutoSelect', 'serverPings']);
            const stats = (statsData.cachedServerStats && typeof statsData.cachedServerStats === 'object' && !Array.isArray(statsData.cachedServerStats)) ? statsData.cachedServerStats : {};
            const excludedSet = new Set(Array.isArray(statsData.excludedFromAutoSelect) ? statsData.excludedFromAutoSelect : []);
            // [v2.9.2 critical fix] УБРАЛ scope-aware фильтр. Раньше: Premium-юзер с scope='free'
            // (default) пинговал ТОЛЬКО free, premium-сервера никогда не обновлялись → после
            // STALE_KEYS wipe (reload extension) premium-pings навсегда пустые → auto-select
            // по скорости/комбо в scope='premium' возвращал null. Сейчас: пингуем ВСЕ серверы
            // доступные юзеру (allCandidates уже отфильтрован по premium-доступу). Cost: ~6-7 мин
            // вместо ~3-4 – приемлемо ради robust behavior во всех scope-режимах.
            // Сортируем по нагрузке asc, исключаем excluded.
            // FREE_LOAD_LIMIT-фильтр только для free серверов; premium без ограничения.
            const candidates = allCandidates
                .filter(p => !excludedSet.has(p.host + ':' + p.port))
                // [2026-06-29 user feedback] УБРАН FREE_LOAD_LIMIT-фильтр из пинга: пингуем ВСЕ
                // доступные free-серверы, даже с нагрузкой >= 75. Причина: нагрузка динамична –
                // сервер на 75 освободится, а free-юзер НЕ может перепинговать (re-run premium-only),
                // и без ping-данных не узнает его скорость когда место появится. Лимит 75 остаётся
                // на СЕЛЕКТЕ/КОННЕКТЕ (pickBestServer + doToggleProxy guard) – там live-нагрузка.
                .sort((a, b) => {
                    const ua = Number(stats[_serverKey(a)]) || 0;
                    const ub = Number(stats[_serverKey(b)]) || 0;
                    return ua - ub;
                })
                .slice(0, BULK_PING_MAX_SERVERS);
            if (candidates.length === 0) { try { sendResponse({error:'no_candidates'}); } catch {} return; }
            // Отвечаем popup'у сразу – bulk запущен
            try { sendResponse({started: true, total: candidates.length}); } catch {}
            logDiag('bulkping', 'start', { total: candidates.length, premium: !!premiumCheck.isPremium });
            // [debug 2026-06-29] детальный план пинговки: кого пингуем, кого отсеяли и почему
            try {
                const _ovl = allCandidates.filter(p => p.type !== 'premium' && (Number(stats[_serverKey(p)]) || 0) >= FREE_LOAD_LIMIT);
                const _exc = allCandidates.filter(p => excludedSet.has(p.host + ':' + p.port));
                logDiag('bulkping', 'plan', {
                    listLen: list.length, candidates: allCandidates.length, willPing: candidates.length,
                    overloaded: _ovl.length, excluded: _exc.length,
                    pingList: candidates.map(p => _serverKey(p) + '|' + (p.country || '?') + '|' + (Number(stats[_serverKey(p)]) || 0) + 'u'),
                    currentlyOverloaded: _ovl.map(p => _serverKey(p) + '|' + (p.country || '?') + '|' + (Number(stats[_serverKey(p)]) || 0) + 'u') // [2026-06-29] теперь пингуются тоже, поле информационное
                });
            } catch (e) {}
            // Mutex до конца bulk
            pingInProgress = true;
            const accumPings = (statsData.serverPings && typeof statsData.serverPings === 'object' && !Array.isArray(statsData.serverPings)) ? Object.assign({}, statsData.serverPings) : {};
            const failedPings = {}; // [2026-06-29] hp серверов, не ответивших на пинг в этом прогоне → красная метка в server-list
            const _probeLog = []; // [2026-06-30] коалесцируем per-probe диагностику в одну logDiag-запись (кольцо на 100 не вытесняем)
            const total = candidates.length;
            // [audit fix high-4] Persist progress в storage. popup-reopen читает и показывает.
            try { await chrome.storage.local.set({ bulkPingProgress: { done: 0, total: total, ts: Date.now() } }); } catch {}
            try {
                for (let i = 0; i < candidates.length; i++) {
                    const p = candidates[i];
                    const hp = _serverKey(p);
                    let pingMs = -1, _pErr = '';
                    try {
                        const portNum = parseInt(p.port, 10);
                        if (Number.isFinite(portNum) && portNum > 0 && portNum < 65536) {
                            updateCredentialCache(p);
                            await setProxyAuthRule(p);
                            await chrome.proxy.settings.set({
                                value: { mode:'fixed_servers', rules:{
                                    singleProxy:{scheme:_proxyScheme(p),host:p.host,port:portNum},
                                    bypassList: BYPASS_LIST
                                }},
                                scope:'regular'
                            });
                            // warm-up
                            try {
                                await fetch('http://cp.cloudflare.com', {
                                    method:'HEAD', cache:'no-store',
                                    signal: AbortSignal.timeout(8000)
                                });
                            } catch {}
                            try {
                                const t0 = performance.now();
                                await fetch('http://cp.cloudflare.com', {
                                    method:'HEAD', cache:'no-store',
                                    signal: AbortSignal.timeout(8000)
                                });
                                pingMs = Math.round(performance.now() - t0);
                            } catch (e) { pingMs = -1; _pErr = String((e && e.name) || e).slice(0, 40); }
                        }
                    } catch (innerErr) {
                        pingMs = -1;
                    } finally {
                        try { await chrome.proxy.settings.set({value:{mode:'direct'},scope:'regular'}); } catch {}
                        try { await clearProxyAuthRule(); } catch {}
                    }
                    // [2026-06-30] результат пинга копим в _probeLog → одна коалесцированная logDiag-запись после цикла
                    _probeLog.push(hp + '|' + (p.country || '?') + '|' + (Number(stats[hp]) || 0) + 'u|' + pingMs + (_pErr ? '|' + _pErr : ''));
                    // Сохраняем только успешные (для неудачных оставляем старое значение в accumPings)
                    if (pingMs > 0) {
                        accumPings[hp] = { ms: pingMs, ts: Date.now() };
                        delete failedPings[hp];
                    } else {
                        // [2026-06-29] трекаем провал для красной метки в server-list
                        failedPings[hp] = Date.now();
                    }
                    // Persist progress + broadcast popup'у (fire-and-forget, no-op если popup закрыт)
                    try { await chrome.storage.local.set({ bulkPingProgress: { done: i + 1, total: total, ts: Date.now() } }); } catch {}
                    chrome.runtime.sendMessage({
                        action: 'bulkPingProgress',
                        done: i + 1, total: total,
                        hostPort: hp, ms: pingMs
                    }).catch(() => {});
                }
                // Финальное сохранение: serverPings + checkerLastResults (merge by hp).
                // Sync в checkerLastResults нужен для UI плашек ms в server-list
                // (popup.js _buildPingMap). Делаем PER-ENTRY merge – для каждого hp из
                // accumPings ищем соответствующий fN/pN-ключ и обновляем; entries чьи hp
                // НЕТ в accumPings (например premium-pings от «Проверка серверов» когда
                // bulk-ping их не пинговал) остаются нетронутыми. Real root cause «По скорости
                // не работает» был в reader (reAutoPickAndRefresh не merge'ил источники) –
                // fixed на popup-side, syncing back в checkerLastResults безопасен.
                try {
                    const existing = await chrome.storage.local.get(['checkerLastResults']);
                    let clr = (existing.checkerLastResults && typeof existing.checkerLastResults === 'object') ? existing.checkerLastResults : {};
                    if (!clr.ping || !clr.ping.results) clr.ping = { ts: Date.now(), results: {} };
                    const fullList = serverList || [];
                    const freeFiltered = fullList.filter(p => p.type !== 'premium');
                    const premFiltered = fullList.filter(p => p.type === 'premium');
                    const idxMap = new Map();
                    freeFiltered.forEach((p, idx) => { idxMap.set(_serverKey(p), 'f' + idx); });
                    premFiltered.forEach((p, idx) => { idxMap.set(_serverKey(p), 'p' + idx); });
                    Object.keys(accumPings).forEach(hp => {
                        const ms = accumPings[hp] && accumPings[hp].ms;
                        const ts = accumPings[hp] && accumPings[hp].ts;
                        const fKey = idxMap.get(hp);
                        if (!fKey || typeof ms !== 'number' || ms <= 0) return;
                        let cls = 'ping-3';
                        if (ms < 250) cls = 'ping-1';
                        else if (ms < 500) cls = 'ping-2';
                        else if (ms < 1000) cls = 'ping-3';
                        else cls = 'ping-4';
                        clr.ping.results[fKey] = { cls: cls, text: String(ms) + ' ms', ts: ts || Date.now(), hp: hp };
                    });
                    // [2026-06-29 user feedback] Помечаем не ответившие на пинг серверы красной
                    // плашкой с ✗ (CSS .modal-item-ping.fail уже существует). ПОСЛЕ success-loop,
                    // чтобы перекрыть старое значение если раньше сервер отвечал, а сейчас нет.
                    Object.keys(failedPings).forEach(hp => {
                        const fKey = idxMap.get(hp);
                        if (!fKey) return;
                        clr.ping.results[fKey] = { cls: 'fail', text: '✗', ts: failedPings[hp] || Date.now(), hp: hp };
                    });
                    clr.ping.ts = Date.now();
                    await chrome.storage.local.set({
                        serverPings: accumPings,
                        serverPingsRunAt: Date.now(),
                        checkerLastResults: clr
                    });
                    await chrome.storage.local.remove(['bulkPingProgress']);
                } catch (e) {
                    logDiag('bulkping', 'save_fail', { msg: String((e && e.message) || '').slice(0, 80) });
                }
                logDiag('bulkping', 'probes', { n: total, r: _probeLog });
                logDiag('bulkping', 'done', { measured: total, kept: Object.keys(accumPings).length });
                chrome.runtime.sendMessage({action: 'bulkPingDone', total: total}).catch(() => {});
            } finally {
                pingInProgress = false;
            }
        })();
        return true;
    }
    // [v3.0.1] Полная диагностика – активная самодиагностика с вердиктом.
    // Тестит CLIENT-side (через реальное соединение юзера), чтобы поймать провайдер-DPI:
    // server-side проверка (proxy_check.php) сказала бы «прокси жив», а у юзера он заблокирован.
    // Поток: прямой IP → доступность api-доменов → ПРИНУДИТЕЛЬНОЕ обновление списка →
    // connect+смена-IP каждого доступного сервера (free→free, premium→все) → сайты через
    // рабочий сервер. Возвращает сырые данные; вердикт вычисляется в popup (для локализации).
    // VPN должен быть ВЫКЛЮЧЕН (как ping/bulkPing – chrome.proxy.settings singleton).
    if (message.action === 'runFullDiagnosis') {
        (async () => {
            if (await isProxyEnabled()) { try { sendResponse({error:'vpn_active'}); } catch {} return; }
            if (pingInProgress) { try { sendResponse({error:'ping_busy'}); } catch {} return; }
            if (toggleInProgress) { try { sendResponse({error:'toggle_busy'}); } catch {} return; }
            // [v3.0.1] Анти-спам: free без верификации – 1 полная диагностика в час.
            // Premium ИЛИ привязанная почта – без лимита (как у «Проверки серверов»).
            {
                const _dlim = await chrome.storage.local.get(['isPremium','accountVerified','fullDiagLastRun']);
                if (!_dlim.isPremium && !_dlim.accountVerified) {
                    const _last = Number(_dlim.fullDiagLastRun) || 0;
                    const _age = Date.now() - _last;
                    const _WIN = 60 * 60 * 1000;
                    if (_last && _age >= 0 && _age < _WIN) {
                        try { sendResponse({ error: 'diag_rate_limited', retryInMin: Math.max(1, Math.ceil((_WIN - _age) / 60000)) }); } catch {}
                        return;
                    }
                }
            }
            pingInProgress = true;
            const R = { steps:{}, servers:[], ts: Date.now() };
            // [v3.0.1] Persist state для popup-recovery (reopen во время прогона).
            const prog = function(phase, extra){
                var p = Object.assign({phase:phase}, extra||{});
                try { chrome.storage.local.set({diagProgress: p}); } catch (e) {}
                try { chrome.runtime.sendMessage(Object.assign({action:'diagProgress'}, p)).catch(function(){}); } catch (e) {}
            };
            try { await chrome.storage.local.set({ diagRunning: { ts: Date.now() }, fullDiagLastRun: Date.now() }); } catch (e) {}
            try {
                // ── Шаг 0: прямой интернет + реальный IP (без VPN) ──
                try { await chrome.proxy.settings.set({value:{mode:'direct'},scope:'regular'}); } catch (e) {}
                let directIp = null, directOk = false;
                // [v3.1.2] Retry: на старом Chrome (109–115) переключение в direct-режим применяется не мгновенно →
                // первый fetch уходит через ещё-не-сброшенный прокси и падает (ложный internet_ok=0 при рабочем
                // интернете). Даём режиму примениться и повторяем. Разбор diag-лога u_mr9p5dkm (Chrome 109): 33/33
                // сервера работали, но internet_ok=0 — тот же паттерн на всех старо-Chrome запусках.
                for (let ia = 0; ia < 2 && !directOk; ia++) {
                    if (ia > 0) { try { await new Promise(function(res){ setTimeout(res, 700); }); } catch (e) {} }
                    try {
                        const r = await fetch('https://api.ipify.org?format=json', {cache:'no-store', signal:AbortSignal.timeout(8000)});
                        if (r && r.ok) { const j = await r.json(); directIp = j && j.ip; directOk = !!directIp; }
                    } catch (e) {}
                }
                R.steps.internet = { ok: directOk }; // [v3.0.1] НЕ кладём directIp (свой IP юзера) в результат
                prog('internet');

                // ── Шаг 1: доступность api-доменов (провайдер/РКН режет наши адреса?) ──
                let apiOk = 0;
                for (let di = 0; di < API_DOMAINS.length; di++) {
                    try {
                        const r = await fetch(API_DOMAINS[di] + '/AnonVPN/timestamp.php?t=' + Date.now(), {cache:'no-store', signal:AbortSignal.timeout(6000)});
                        if (r && r.ok) apiOk++;
                    } catch (e) {}
                }
                R.steps.api = { reachable: apiOk, total: API_DOMAINS.length };
                prog('api');

                // ── Шаг 2: ПРИНУДИТЕЛЬНОЕ обновление списка серверов (свежий, не кэш) ──
                let list = [];
                try { list = await ensureProxyList(true) || []; } catch (e) {}
                if ((!list || list.length === 0) && Array.isArray(serverList)) list = serverList;
                const premCk = await chrome.storage.local.get(['isPremium']);
                const isPrem = !!premCk.isPremium;
                const candidates = (list||[]).filter(p => p && p.host && p.port && (isPrem || p.type !== 'premium'));
                R.steps.serverList = { count: candidates.length, premium: isPrem };
                prog('serverlist', {count: candidates.length});

                // ── Серверные блокировки (флаги выставлены force-refresh'ем proxy_list выше) ──
                // illegalExtId=unknown_ext_id, updateRequired=version_too_old, rateLimited=бот-бан
                // (reason: bot_signature=UID-бан, fp_repeat_offender=отпечаток-бан).
                const _blk = await chrome.storage.local.get(['updateRequired','minVersion','illegalExtId','rateLimited','rateLimitedReason','rateLimitedUntil']);
                R.steps.blocks = {
                    illegal_ext: !!_blk.illegalExtId,
                    version_too_old: !!_blk.updateRequired,
                    min_version: _blk.minVersion || '',
                    rate_limited: !!_blk.rateLimited,
                    rl_reason: _blk.rateLimitedReason || '',
                    rl_until: _blk.rateLimitedUntil || '',
                    key_checked: false, key_invalid: false, device_mismatch: false, key_reason: ''
                };
                // [v3.0.1] Premium: read-only check-key – детект блокировки ключа / другого устройства.
                // НЕ снимает премиум (это делает периодический checkDeviceBinding) – только читаем результат.
                if (isPrem) {
                    try {
                        const _pk = await chrome.storage.local.get(['premiumKey']);
                        if (_pk.premiumKey) {
                            const _uid = await getUID();
                            const _kr = await apiFetch('/AnonVPN/check-key.php', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ key: _pk.premiumKey, device_id: _uid }), signal: AbortSignal.timeout(12000) });
                            if (_kr && _kr.ok) {
                                const _kj = await _kr.json();
                                if (_kj && typeof _kj === 'object') {
                                    R.steps.blocks.key_checked = true;
                                    if (_kj.valid === false) {
                                        R.steps.blocks.key_reason = _kj.reason || '';
                                        if (_kj.reason === 'device_changed') R.steps.blocks.device_mismatch = true;
                                        else R.steps.blocks.key_invalid = true;
                                    }
                                }
                            }
                        }
                    } catch (eKey) {}
                }
                prog('blocks');

                if (candidates.length > 0) {
                    // ── Шаг 3: connect + смена-IP тест КАЖДОГО доступного сервера ──
                    // [v3.0.1] Сквозной индекс в пуле (как в списке выбора _freeServerLabel/_premServerLabel:
                    // №{idx+1}, free и premium – отдельные последовательности). НЕ раскрываем host:port.
                    const _freeAll = (list||[]).filter(x => x && x.type !== 'premium');
                    const _premAll = (list||[]).filter(x => x && x.type === 'premium');
                    const total = candidates.length;
                    let bestCand = null, bestLat = Infinity; // [v3.0.1] лучший сервер для шага «сайты» – локально (host:port НЕ кладём в R)
                    // [v3.0.5] Копим пинги локально (host:port) → после цикла в _persistPingResults,
                    // чтобы «Полная диагностика» заполняла ms-плашки в селекторах как «Проверка серверов».
                    const _diagPings = {}, _diagFailed = {};
                    for (let i = 0; i < candidates.length; i++) {
                        const p = candidates[i];
                        const _poolIdx = (p.type === 'premium')
                            ? _premAll.findIndex(x => x.host===p.host && String(x.port)===String(p.port))
                            : _freeAll.findIndex(x => x.host===p.host && String(x.port)===String(p.port));
                        // [v3.0.1] В результат – только хеш сервера, без host:port (см. _diagSrvHash).
                        const e = { hash:_diagSrvHash(p.host), country:p.country||'', type:p.type||'free', idx:_poolIdx, connected:false, ipChanged:false, latency:-1 };
                        try {
                            const portNum = parseInt(p.port, 10);
                            if (Number.isFinite(portNum) && portNum > 0 && portNum < 65536) {
                                updateCredentialCache(p);
                                await setProxyAuthRule(p);
                                await chrome.proxy.settings.set({value:{mode:'fixed_servers', rules:{singleProxy:{scheme:_proxyScheme(p),host:p.host,port:portNum}, bypassList: BYPASS_LIST}}, scope:'regular'});
                                try { await fetch('http://cp.cloudflare.com', {method:'HEAD', cache:'no-store', signal:AbortSignal.timeout(8000)}); } catch (e2) {}
                                try {
                                    const t0 = performance.now();
                                    // [v3.1.4] ≥116 – HTTPS (прозрачный прокси провайдера не подделает ответ), <116 – HTTP как раньше.
                                    await fetch((_diagHttpsProbeOk() ? 'https' : 'http') + '://cp.cloudflare.com', {method:'HEAD', cache:'no-store', signal:AbortSignal.timeout(8000)});
                                    e.latency = Math.round(performance.now() - t0);
                                    e.connected = true;
                                } catch (e3) { e.connected = false; }
                                if (e.connected && directIp) {
                                    try {
                                        // [v3.1.4 hotfix] HTTPS+HTTP параллельно (Kiwi/Android HTTPS-через-прокси ложно падает).
                                        const _exitIp = await _fetchTunnelExitIp(8000);
                                        if (_exitIp) e.ipChanged = (_exitIp !== directIp);
                                    } catch (e4) {}
                                }
                            }
                        } catch (eOuter) {} finally {
                            try { await chrome.proxy.settings.set({value:{mode:'direct'},scope:'regular'}); } catch (e5) {}
                            try { await clearProxyAuthRule(); } catch (e6) {}
                        }
                        R.servers.push(e);
                        // [v3.0.5] host:port только локально (в R – приватность). Пинг для селектора:
                        // ответил → ms, не подключился → красная ✗ (как bulk-ping).
                        const _hp = p.host + ':' + p.port;
                        if (e.connected && e.latency >= 0) _diagPings[_hp] = { ms: e.latency, ts: Date.now() };
                        else if (!e.connected) _diagFailed[_hp] = Date.now();
                        if (e.connected && e.ipChanged && e.latency >= 0 && e.latency < bestLat) { bestLat = e.latency; bestCand = p; }
                        prog('servers', {done:i+1, total:total, connected:e.connected, ipChanged:e.ipChanged, connTotal:R.servers.filter(function(s){return s.connected;}).length});
                    }

                    // [v3.0.5] Персист пингов диагностики в selector-store (как «Проверка серверов») –
                    // ms-плашки появятся в списках выбора серверов. Не критично для диагностики → try.
                    try { await _persistPingResults(_diagPings, _diagFailed); } catch (ePP) { logDiag('diag', 'ping_persist_fail', { msg: String((ePP && ePP.message) || '').slice(0, 80) }); }

                    // [v3.1.2] Если прямая интернет-проверка (шаг 0) не удалась (частый ложный fail на старом
                    // Chrome из-за timing direct-режима), но хотя бы один сервер реально подключился —
                    // интернет ТОЧНО есть. Не даём ложному internet_ok=0 портить вердикт (см. diag u_mr9p5dkm).
                    if (!R.steps.internet.ok && R.servers.some(function(s){ return s.connected; })) {
                        R.steps.internet.ok = true; R.steps.internet.inferred = true;
                    }

                    // ── Шаг 4: популярные сайты через лучший рабочий сервер ──
                    R.steps.sites = { tested:false, results:[] };
                    if (bestCand) {
                        const best = bestCand;
                        {
                            try {
                                const portNum = parseInt(best.port, 10);
                                updateCredentialCache(best);
                                await setProxyAuthRule(best);
                                await chrome.proxy.settings.set({value:{mode:'fixed_servers', rules:{singleProxy:{scheme:_proxyScheme(best),host:best.host,port:portNum}, bypassList: BYPASS_LIST}}, scope:'regular'});
                                const sites = [['YouTube','https://www.youtube.com/favicon.ico'],['Google','https://www.google.com/favicon.ico'],['Cloudflare','http://cp.cloudflare.com']];
                                for (let si = 0; si < sites.length; si++) {
                                    let sok = false;
                                    try { await fetch(sites[si][1], {method:'HEAD', cache:'no-store', mode:'no-cors', signal:AbortSignal.timeout(8000)}); sok = true; } catch (e7) {}
                                    R.steps.sites.results.push({name:sites[si][0], ok:sok});
                                }
                                R.steps.sites.tested = true;
                            } catch (eSite) {} finally {
                                try { await chrome.proxy.settings.set({value:{mode:'direct'},scope:'regular'}); } catch (e8) {}
                                try { await clearProxyAuthRule(); } catch (e9) {}
                            }
                        }
                    }
                    prog('sites');
                }
                logDiag('diag', 'full_done', { srv: R.servers.length, conn: R.servers.filter(s=>s.connected).length, ipchg: R.servers.filter(s=>s.ipChanged).length, api: apiOk });
                try { await chrome.storage.local.set({ diagLastResult: R }); } catch (e) {}
                try { await chrome.storage.local.remove(['diagRunning', 'diagProgress']); } catch (e) {}
                try { chrome.runtime.sendMessage({ action: 'diagDone', result: R }).catch(function(){}); } catch (e) {}
                try { sendResponse({ok:true, result:R}); } catch {}
            } catch (eAll) {
                logDiag('diag', 'full_err', { msg: String((eAll&&eAll.message)||'').slice(0,80) });
                try { await chrome.proxy.settings.set({value:{mode:'direct'},scope:'regular'}); } catch (e) {}
                try { await clearProxyAuthRule(); } catch (e) {}
                try { await chrome.storage.local.remove(['diagRunning', 'diagProgress']); } catch (e) {}
                try { chrome.runtime.sendMessage({ action: 'diagError' }).catch(function(){}); } catch (e) {}
                try { sendResponse({error:'diag_error'}); } catch {}
            } finally {
                // [v3.1.0 FIX регресс #614] Диагностика гоняет chrome.proxy НАПРЯМУЮ (мимо storage.onChanged)
                // и в per-server finally сбрасывает прокси в direct + чистит DNR, а cachedCredentials
                // ОСТАЁТСЯ от последнего проверенного сервера. Итог после диагностики: прокси=direct,
                // но proxyEnabled=true, а cachedCredentials – чужой пароль → активный сервер юзера отдаёт
                // 407 «IP не сменился». Восстанавливаем прокси+креды+DNR к ВЫБРАННОМУ серверу (или чистим).
                try {
                    const _rst = await chrome.storage.local.get(['proxyEnabled', 'selectedProxy']);
                    if (_rst.proxyEnabled && _rst.selectedProxy && _rst.selectedProxy.host) {
                        updateCredentialCache(_rst.selectedProxy);
                        try { await setProxyAuthRule(_rst.selectedProxy); } catch (eAR) {}
                        const _rpn = parseInt(_rst.selectedProxy.port, 10);
                        if (Number.isFinite(_rpn) && _rpn > 0 && _rpn < 65536) {
                            await chrome.proxy.settings.set({ value: { mode: 'fixed_servers', rules: { singleProxy: { scheme: _proxyScheme(_rst.selectedProxy), host: _rst.selectedProxy.host, port: _rpn }, bypassList: BYPASS_LIST } }, scope: 'regular' });
                        }
                        logDiag('diag', 'proxy_restored', { host: String(_rst.selectedProxy.host).slice(0, 24) });
                    } else {
                        cachedCredentials = null; // VPN был выключен – активного сервера нет
                    }
                } catch (eRestore) { logDiag('diag', 'restore_fail', { msg: String((eRestore && eRestore.message) || '').slice(0, 80) }); }
                pingInProgress = false;
            }
        })();
        return true;
    }
    // [v2.6.5 audit r7] Gate-страница DNR-auto-enable просит поднять VPN и проверить, что
    // целевой домен в списке юзера (защита от злоупотребления через WAR-доступ к gate-странице).
    if (message.action === 'autoEnableViaGate') {
        (async () => {
            try {
                const d = await chrome.storage.local.get(['autoEnableEnabled', 'autoEnableDomains', 'isPremium', 'proxyEnabled']);
                if (!d.isPremium || d.autoEnableEnabled === false) {
                    try { sendResponse({ ok: false, reason: 'not_enabled' }); } catch {}
                    return;
                }
                const list = Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : [];
                let targetHost = '';
                try { targetHost = new URL(message.target).hostname.toLowerCase().replace(/^www\./, ''); } catch {}
                const matches = targetHost && list.some(dom => {
                    const low = String(dom).toLowerCase().replace(/^www\./, '');
                    return targetHost === low || targetHost.endsWith('.' + low);
                });
                if (!matches) {
                    try { sendResponse({ ok: false, reason: 'not_in_list' }); } catch {}
                    return;
                }
                if (d.proxyEnabled) {
                    try { sendResponse({ ok: true, reason: 'already_on' }); } catch {}
                    return;
                }
                // [v2.6.5 audit r7 fix #2] Правильный mutex-wait с timeout – раньше после
                // 500ms-wait код безусловно ставил `toggleInProgress = true`, даже если
                // другой toggle ещё выполнялся → race на chrome.proxy.settings. Теперь
                // опрашиваем состояние до 5 сек; если занято – возвращаем `busy`.
                let waited = 0;
                while ((toggleInProgress || pingInProgress) && waited < 5000) {
                    await new Promise(r => setTimeout(r, 100));
                    waited += 100;
                    if (await isProxyEnabled()) { try { sendResponse({ ok: true, reason: 'already_on' }); } catch {} return; }
                }
                if (toggleInProgress || pingInProgress) {
                    try { sendResponse({ ok: false, reason: 'busy' }); } catch {}
                    return;
                }
                toggleInProgress = true;
                try {
                    await doToggleProxy();
                    // [v2.6.5 audit r7 fix] Явно ждём удаления DNR-правил ДО ответа gate'у –
                    // иначе `location.replace(target)` в gate.js попадёт на ещё не снятое
                    // правило и редирект гоняется в цикле пока storage.onChanged-хэндлер не
                    // добежит до updateDynamicRules. Наш queue-based sync serialize'ит
                    // onChanged-вызов и этот явный вызов – двойной сброс, но безопасный.
                    try { await syncAutoEnableDnrRules(); } catch {}
                    logDiag('autoEnable', 'gate_on', { host: targetHost });
                    chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: true, reason: 'autoEnableGate' }).catch(() => {});
                    try { sendResponse({ ok: true }); } catch {}
                } catch (e) {
                    logDiag('autoEnable', 'gate_toggle_err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
                    // [v2.7.1 fix F93] Specific reason для storage_quota – gate page может
                    // показать инструкцию очистить кэш вместо generic «toggle failed».
                    const reason = (e && e.message === 'storage_quota_exceeded') ? 'storage_quota_exceeded' : 'toggle_failed';
                    try { sendResponse({ ok: false, reason: reason }); } catch {}
                } finally {
                    toggleInProgress = false;
                }
            } catch (e) {
                try { sendResponse({ ok: false, reason: 'inner' }); } catch {}
            }
        })();
        return true;
    }
    // [v2.6.5 audit r3] Unknown action fallback – без этого неизвестное сообщение от
    // старого popup (после SW-reload) зависало бы на callback'е до таймаута.
    return false;
});

// [v2.6.4] Auto-enable VPN при посещении сайта из списка (Premium feature).
// Triggers:
//   - chrome.tabs.onUpdated (info.url present = URL-change navigation)
//   - chrome.tabs.onActivated (switch to existing tab already on matched site)
// Match: host exact OR subdomain. Debounce 30 сек per-domain.
// Поведение: NEVER auto-disable – юзер сам решает.
const AUTO_ENABLE_DEBOUNCE_MS = 30 * 1000;
// [v2.6.4 audit] Size cap для history (key = domain, value = timestamp). Без cap словарь
// растёт на каждый уникальный авто-включённый сайт и никогда не чистится.
const AUTO_ENABLE_HISTORY_MAX = 50;

// [v2.6.4 audit] Локализованный текст уведомления о auto-enable. Читаем cachedTranslationsData
// (которую popup кладёт в storage при первом запуске). Если переводов ещё нет – en-fallback.
async function buildAutoEnableNotifMessage(host, reloaded) {
    try {
        const d = await chrome.storage.local.get(['language', 'cachedTranslationsData']);
        const lang = d.language || 'en';
        const data = d.cachedTranslationsData || {};
        const tr = data[lang] || data.en || {};
        const enTr = data.en || {};
        const tpl = tr.autoEnableNotifMsg || enTr.autoEnableNotifMsg
            || (reloaded ? 'VPN turned on for {host} – page reloaded' : 'VPN turned on for {host}');
        // Если в переводе есть плейсхолдер {reloaded}, сервер подставит суффикс; иначе простой шаблон с {host}
        return tpl.replace('{host}', host).replace('{reload}', reloaded ? (tr.autoEnableNotifReloadSuffix || enTr.autoEnableNotifReloadSuffix || '') : '');
    } catch {
        return reloaded ? ('VPN turned on for ' + host + ' – page reloaded') : ('VPN turned on for ' + host);
    }
}

function maybeAutoEnableOnUrl(url, source, tabId) {
    // [v2.7.5] Function CONTRACT: всегда возвращает Promise (даже на early-return).
    // Без этого вызывающие сайты (`_onTabsUpdatedHandler`, `_onTabsActivatedHandler`)
    // делают `.catch(() => {})` на undefined → TypeError. Раньше: 5 early-return'ов
    // возвращали undefined; в Yandex Browser & части Chromium tabs.onUpdated fires
    // часто, ошибка бомбила console каждые несколько секунд.
    if (!url || !/^https?:\/\//i.test(url)) return Promise.resolve();
    // [v2.6.5 audit r3] Fast-path: 99% юзеров не пользуются автовключением. In-memory cache
    // позволяет мгновенно отбросить nav-событие без storage.get + queue-serialization.
    // `enabled===null` значит кэш ещё не прогрет – пропускаем дальше, тело проверит сам.
    if (_autoEnableCache.enabled === false) return Promise.resolve();
    if (_autoEnableCache.enabled === true && _autoEnableCache.domains && _autoEnableCache.domains.length === 0) return Promise.resolve();
    let host = '';
    try { host = new URL(url).hostname.toLowerCase().replace(/^www\./, ''); } catch { return Promise.resolve(); }
    if (!host) return Promise.resolve();
    // [v2.6.5 audit] Serialize – prevents lost autoEnableHistory entries when onBeforeRequest +
    // onBeforeNavigate fire for different domains concurrently (classic get→mutate→set race).
    _autoEnableQueue = _autoEnableQueue.then(() => _maybeAutoEnableBody(url, source, tabId, host)).catch(() => {});
    return _autoEnableQueue;
}

async function _maybeAutoEnableBody(url, source, tabId, host) {
    try {
        const d = await chrome.storage.local.get(['isPremium', 'proxyEnabled', 'autoEnableEnabled', 'autoEnableDomains', 'autoEnableHistory']);
        if (d.autoEnableEnabled === false) { logDiag('autoEnable', 'skip_off', { host: host, src: source }); return; }
        const list = Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : [];
        if (list.length === 0) return;
        let matched = null;
        for (const dom of list) {
            // [v2.6.5] Strip www. с обеих сторон – на случай если в storage сохранён
            // старый домен с префиксом (input strip-ает только новые добавления).
            const low = String(dom).toLowerCase().replace(/^www\./, '');
            if (host === low || host.endsWith('.' + low)) { matched = low; break; }
        }
        if (!matched) { logDiag('autoEnable', 'no_match', { host: host, listLen: list.length, src: source }); return; }
        if (!d.isPremium)     { logDiag('autoEnable', 'skip_nopremium', { dom: matched, src: source }); return; }
        if (d.proxyEnabled)   { logDiag('autoEnable', 'skip_vpnon',      { dom: matched, src: source }); return; }
        if (vpnBlocked)       { logDiag('autoEnable', 'skip_blocked',    { dom: matched, src: source }); return; }
        // [v3.1.1 audit] tier-0 DNR уже перехватывает network-навигацию на покрытые домены через
        // ae-gate (плавнее, без about:blank-мелькания). Не дублируем tier-1/2 (beforenav/request) –
        // gate владеет. tier-3 (nav_early/switch – BFCache/переключение вкладок, DNR их НЕ видит,
        // нет network-request) и домены за DNR-cap (501+, не в _dnrCoveredDomains) продолжают работать.
        if ((source === 'beforenav' || source === 'request') && _dnrCoveredDomains.has(matched)) {
            logDiag('autoEnable', 'skip_dnr_owned', { dom: matched, src: source }); return;
        }
        // [v2.6.4] typeof array === 'object' – guard от corrupted storage (если кто-то записал array)
        const hist = (d.autoEnableHistory && typeof d.autoEnableHistory === 'object' && !Array.isArray(d.autoEnableHistory)) ? d.autoEnableHistory : {};
        const now = Date.now();
        // [v2.6.5 audit r3] `hist[matched] <= now` защита от перевода часов назад:
        // отрицательная дельта (now - hist[matched] < 0) проходила проверку debounce'а
        // вечно, auto-enable спамил.
        if (hist[matched] && hist[matched] <= now && (now - hist[matched]) < AUTO_ENABLE_DEBOUNCE_MS) {
            logDiag('autoEnable', 'skip_debounce', { dom: matched, src: source }); return;
        }
        hist[matched] = now;
        // [v2.6.4 audit] Cap: удаляем самые старые записи, если накопилось > MAX
        const keys = Object.keys(hist);
        if (keys.length > AUTO_ENABLE_HISTORY_MAX) {
            keys.sort((a, b) => hist[a] - hist[b]); // ascending by timestamp (oldest first)
            const toRemove = keys.slice(0, keys.length - AUTO_ENABLE_HISTORY_MAX);
            toRemove.forEach(k => { delete hist[k]; });
        }
        // [v2.7.1 fix F87] storage.set может throw на quota-exceed – outer catch
        // молчаливо глотал → история не персистилась, debounce сбрасывался при SW
        // restart, юзер видел повторные auto-enable на одном домене. Логируем явно.
        try { await chrome.storage.local.set({ autoEnableHistory: hist }); }
        catch (e) { logDiag('autoEnable', 'hist_write_err', { msg: String((e && e.message) || e).slice(0, 80) }); }
        if (toggleInProgress) { logDiag('autoEnable', 'skip_busy', { dom: matched, src: source }); return; }
        // [v2.6.5 audit r8] Захватываем mutex СРАЗУ после синхронной проверки, ДО любого
        // await. Раньше `toggleInProgress = true` стояло после `await chrome.tabs.update
        // (about:blank)` – это yield-окно ~5-50мс, в котором параллельный chrome.commands.
        // onCommand (Alt+Shift+V) мог пройти свой guard и запустить второй doToggleProxy,
        // race на chrome.proxy.settings.set.
        toggleInProgress = true;

        // [v2.6.5] Race fix: для source='request' (onBeforeRequest) Chrome уже начал
        // навигацию – без перебивания на about:blank пользователь будет ждать TCP-таймаут
        // на заблокированном домене. Перенаправляем tab на about:blank ДО toggle, что
        // отменяет pending navigation; после успешного toggle возвращаемся на оригинал.
        // Для source='nav' (fallback через onUpdated на BFCache/preload) about:blank не
        // нужен – страница уже отображается; делаем только reload через VPN.
        // [v2.6.5 audit r5] Для source='nav_early' (onUpdated с info.status='loading')
        // тоже делаем about:blank – нужно для Yandex Browser и некоторых Chromium-сборок,
        // где webRequest.onBeforeRequest приходит ПОСЛЕ старта TCP и tier-3 onUpdated
        // оказывается первым ранним сигналом. Страница в этот момент ещё не отрисована.
        const hasTab = typeof tabId === 'number';
        const isEarlySrc = ((source === 'request' || source === 'beforenav' || source === 'nav_early') && hasTab);
        const willReload = (isEarlySrc || (source === 'nav' && hasTab));
        if (isEarlySrc) {
            try { await chrome.tabs.update(tabId, { url: 'about:blank' }); } catch {}
        }

        try {
            await doToggleProxy();
            logDiag('autoEnable', 'on', { dom: matched, src: source });
            // Возвращаемся на оригинальный URL уже через VPN. Cache-buster нужен на случай,
            // если сервер до VPN успел отдать gated-страницу с длинным TTL.
            if (willReload) {
                // [v2.6.6 audit] URL API вместо `+ '?_ae=ts'` – корректно обрабатывает
                // URL'ы с fragment'ом (иначе `?_ae=...` оказывался бы ВНУТРИ #fragment).
                var freshUrl;
                try {
                    var parsed = new URL(url);
                    parsed.searchParams.set('_ae', String(now));
                    freshUrl = parsed.toString();
                } catch {
                    // Fallback для нестандартных URL, которые new URL() не парсит
                    var sep = url.indexOf('?') >= 0 ? '&' : '?';
                    freshUrl = url + sep + '_ae=' + now;
                }
                try { await chrome.tabs.update(tabId, { url: freshUrl }); } catch { /* tab closed */ }
            }
            try {
                const msg = await buildAutoEnableNotifMessage(matched, willReload);
                // [v2.7.0 fix F33] .catch – Promise-returning API; внешний try/catch не ловит
                // rejected promise (синхронно thrown ≠ async rejected).
                chrome.notifications.create('autoenable_' + matched + '_' + now, {
                    type: 'basic', iconUrl: '/icons/AnonVPN128.png',
                    title: 'AnonVPN',
                    message: msg,
                    priority: 1
                }).catch(() => {});
            } catch {}
            chrome.runtime.sendMessage({ action: 'proxyStateChanged', proxyEnabled: true, reason: 'autoEnable' }).catch(() => {});
        } catch (e) {
            logDiag('autoEnable', 'err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : 'unknown' });
            // [v2.6.5] Если мы перебили навигацию на about:blank и VPN не поднялся –
            // нельзя бросить пользователя на пустой странице. Возвращаем tab на исходный URL
            // без cache-buster (чтобы Chrome показал обычную ошибку соединения как при прямом заходе).
            if (isEarlySrc) {
                try { await chrome.tabs.update(tabId, { url }); } catch {}
            }
        } finally {
            toggleInProgress = false;
        }
    } catch (e) { /* storage read fail – silent */ }
}

// [v2.6.5] Три источника навигационных событий, по убыванию приоритета:
//   1. webNavigation.onBeforeNavigate (opt-in permission) – до DNS, самый быстрый
//   2. webRequest.onBeforeRequest (всегда on, покрывает main_frame) – работает в Chrome,
//      но в Opera/части Chromium приходит поздно
//   3. tabs.onUpdated (info.url) – universal fallback, включая BFCache / restore
// При granted webNavigation переключаемся: отписываемся от webRequest listener,
// чтобы не делать 2× storage.get на одну навигацию. onUpdated остаётся всегда –
// BFCache restore не вызывает ни onBeforeNavigate, ни onBeforeRequest.

// [v2.6.5 audit] Все listener'ы именованные + hasListener-гард. Без этого после нескольких
// wake/sleep SW Chrome мог бы зарегистрировать одну и ту же анонимную функцию дважды –
// каждая навигация вызывала бы maybeAutoEnableOnUrl 2-3×.
function _onBeforeRequestHandler(details) {
    if (details.type !== 'main_frame') return;
    if (details.tabId < 0) return;
    maybeAutoEnableOnUrl(details.url, 'request', details.tabId).catch(() => {});
}
function _onBeforeNavHandler(details) {
    if (details.frameId !== 0) return;
    if (details.tabId < 0) return;
    // [v2.7.6 audit Pass10] Skip Chrome speculative loading (prerender/preload) –
    // user не виден ниcobservedим nav, auto-enable не должен fire'ить DNR redirect
    // на prefetched страницу (ломает back-forward + создаёт ненужные toggles).
    // Properties added в Chrome 109+, undefined = treated false.
    if (details.documentLifecycle === 'prerender') return;
    maybeAutoEnableOnUrl(details.url, 'beforenav', details.tabId).catch(() => {});
}
function _onPermissionsAddedHandler(perms) {
    if (perms && Array.isArray(perms.permissions) && perms.permissions.indexOf('webNavigation') >= 0) {
        // [v2.7.5 audit r3] Clear `_webNavRefused` flag – раньше юзер deny'нул via popup-confirm,
        // потом разрешил вручную через chrome://extensions; popup продолжал бы skip'ать prompt
        // ('refused' = true persists). Теперь grant очищает флаг → следующий toggle ON работает
        // нормально с tier-1 listener активным.
        chrome.storage.local.remove(['_webNavRefused']).catch(() => {});
        attachEarlyNavListener();
    }
}
// [v2.6.5 audit] Если юзер снял webNavigation через chrome://extensions – снимаем tier-1
// listener и возвращаем tier-2 (webRequest). Иначе auto-enable деградирует до tier-3
// (tabs.onUpdated), который срабатывает уже после старта TCP – пользователь ждёт таймаут.
function _onPermissionsRemovedHandler(perms) {
    if (!perms || !Array.isArray(perms.permissions)) return;
    // [v2.7.0 fix F53] При revoke `management` очищаем кэш конфликт-листа – без этого
    // popup показывал бы stale данные из vpnConflictList после отзыва permission.
    if (perms.permissions.indexOf('management') >= 0) {
        // [v2.8.2 vpn-conflict-block] Также очищаем vpnConflictBlocked – без management
        // не можем больше детектировать конфликты, поэтому unblock UI (серверный ASN-фильтр
        // в request-trial.php остаётся как fallback защита).
        try { chrome.storage.local.remove(['vpnConflictList', 'vpnConflictLastSeen', 'vpnConflictBlocked']).catch(() => {}); } catch {}
        logDiag('management', 'permission_removed', {});
    }
    if (perms.permissions.indexOf('webNavigation') < 0) return;
    try { chrome.webNavigation.onBeforeNavigate.removeListener(_onBeforeNavHandler); } catch {}
    if (!chrome.webRequest.onBeforeRequest.hasListener(_onBeforeRequestHandler)) {
        try {
            chrome.webRequest.onBeforeRequest.addListener(
                _onBeforeRequestHandler,
                { urls: ['http://*/*', 'https://*/*'], types: ['main_frame'] }
            );
        } catch {}
    }
    logDiag('autoEnable', 'early_listener_off', {});
}
function _onTabsUpdatedHandler(tabId, info) {
    if (!info.url) return;
    // [v2.6.5 audit r6] ВСЕГДА трактуем onUpdated с url как early-source (с about:blank
    // перехватом). Предыдущая версия гейтила на `info.status === 'loading'`, но в
    // Yandex Browser status-поле либо не 'loading', либо приходит слишком поздно –
    // геэйт никогда не срабатывал, auto-enable активировался только после TCP-таймаута.
    // Worst case для BFCache restore – мелкое мерцание таба; защита от повторов:
    // debounce 30с per-domain + toggleInProgress + skip_vpnon + ~30мс about:blank flash.
    maybeAutoEnableOnUrl(info.url, 'nav_early', tabId).catch(() => {});
}
async function _onTabsActivatedHandler(info) {
    try {
        const tab = await chrome.tabs.get(info.tabId);
        if (tab && tab.url) maybeAutoEnableOnUrl(tab.url, 'switch', info.tabId).catch(() => {});
    } catch { /* tab gone or no permission for private tab */ }
}

if (!chrome.webRequest.onBeforeRequest.hasListener(_onBeforeRequestHandler)) {
    chrome.webRequest.onBeforeRequest.addListener(
        _onBeforeRequestHandler,
        { urls: ['http://*/*', 'https://*/*'], types: ['main_frame'] }
    );
}

function attachEarlyNavListener() {
    if (!chrome.webNavigation || !chrome.webNavigation.onBeforeNavigate) return;
    if (chrome.webNavigation.onBeforeNavigate.hasListener(_onBeforeNavHandler)) return;
    try {
        chrome.webNavigation.onBeforeNavigate.addListener(_onBeforeNavHandler);
        // onBeforeNavigate покрывает все main_frame – снимаем дублирующий webRequest listener.
        try { chrome.webRequest.onBeforeRequest.removeListener(_onBeforeRequestHandler); } catch {}
        logDiag('autoEnable', 'early_listener_on', {});
    } catch (e) {
        logDiag('autoEnable', 'early_listener_err', { msg: (e && e.message) ? String(e.message).slice(0, 80) : '?' });
    }
}
// Если permission уже выдан – поднимаем listener при старте SW.
chrome.permissions.contains({ permissions: ['webNavigation'] }).then(function(has) {
    if (has) attachEarlyNavListener();
}).catch(function() {});
// При выдаче permission в runtime – поднимаем сразу.
if (chrome.permissions && chrome.permissions.onAdded && !chrome.permissions.onAdded.hasListener(_onPermissionsAddedHandler)) {
    chrome.permissions.onAdded.addListener(_onPermissionsAddedHandler);
}
if (chrome.permissions && chrome.permissions.onRemoved && !chrome.permissions.onRemoved.hasListener(_onPermissionsRemovedHandler)) {
    chrome.permissions.onRemoved.addListener(_onPermissionsRemovedHandler);
}

// Universal fallback – BFCache restore и прочие кейсы, когда ни onBeforeNavigate,
// ни onBeforeRequest не fires. Без about:blank (страница уже отрисована), только reload.
if (!chrome.tabs.onUpdated.hasListener(_onTabsUpdatedHandler)) {
    chrome.tabs.onUpdated.addListener(_onTabsUpdatedHandler);
}
if (!chrome.tabs.onActivated.hasListener(_onTabsActivatedHandler)) {
    chrome.tabs.onActivated.addListener(_onTabsActivatedHandler);
}
