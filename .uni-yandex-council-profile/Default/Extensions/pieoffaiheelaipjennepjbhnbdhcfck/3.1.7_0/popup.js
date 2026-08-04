let timerInterval = null;
let cachedTranslations = null;
let _cachedTranslationsVersion = null; // [v2.6.3] stamp для invalidation на update
let cachedProxyList = null;
let updateRequiredFlag = false; // [v2.5.8]
let illegalExtIdFlag = false;   // [v2.5.8]
let _proxyListFetchError = null; // [v2.8.4] 'network' | 'server' | null – детализация «Нет серверов» (читается из storage)
let serverUserCounts = {};
let isVpnOn = false;
let _newsAutoSwitched = false; // [v2.7.3] защита от повторного auto-switch в одной сессии popup
let _latestVersionRequested = false; // [v2.7.4] one-shot trigger checkLatestVersion → SW per popup open
// [v2.7.3] Free-юзерам запрещено подключение к серверам с нагрузкой >= 75 (тот же порог
// что даёт оранжевое предупреждение). Premium – без ограничений. Порог согласован с SW
// (service_worker.js константа FREE_LOAD_LIMIT) и с badge-рендером (строки 1694, 2630).
const FREE_LOAD_LIMIT = 75;
// [v3.0.3] Порог ПРЕДУПРЕЖДЕНИЯ о повышенной средней нагрузке (баннер «Возможно повышенная
// нагрузка»). Ниже порога блокировки (75 = пик): предупреждаем заранее, на 60.
const LOAD_WARN_AVG = 60;

// [v3.0.3] Страны с жёсткой интернет-цензурой / частыми блокировками, где exit-нода может
// терять доступ к YouTube/Instagram (и соцсетям). Метка-предупреждение в выборе сервера.
// Расширяемо: добавь ISO-2 код (UPPERCASE). Текущий минимум: Китай, КНДР, Иран, Туркменистан,
// Эритрея, ЦАР, Таджикистан, Россия, Сирия, Судан, Южный Судан, Турция, Пакистан, Казахстан.
const GEO_RESTRICTED_COUNTRIES = ['CN','KP','IR','TM','ER','CF','TJ','RU','SY','SD','SS','TR','PK','KZ'];
function isGeoRestricted(country){
    if (!country) return false;
    return GEO_RESTRICTED_COUNTRIES.indexOf(String(country).toUpperCase().trim()) >= 0;
}

// [v3.0.3] Страны, чьи сервера имеют ОБЩИЙ (на всех пользователей) лимит трафика → при исчерпании
// временно пропадают из списка и возвращаются позже. Это НЕ личный лимит юзера. Метка-предупреждение
// в выборе сервера (тот же принцип, что geoBlock). Расширяемо: добавь ISO-2 код.
const GEO_TRAFFIC_COUNTRIES = ['EE','JP','FI'];
function isTrafficLimited(country){
    if (!country) return false;
    return GEO_TRAFFIC_COUNTRIES.indexOf(String(country).toUpperCase().trim()) >= 0;
}

// [v2.8.1] Стабильный ключ серверной статистики – host:port. Заменил старые fN/pN
// (позиционные индексы), которые ломались при перетасовке n_proxies.txt.
function _serverKey(p) {
    return p && p.host && p.port ? (String(p.host) + ':' + String(p.port)) : '';
}

// [v2.8.5] Compact server labels in "Select server": "No.N" / "* No.N" / "(lock) No.N".
// Words "Server"/"Premium server" dropped - they duplicate the section header.
function _freeServerLabel(idx){ return '№' + (idx + 1); }
function _premServerLabel(idx, unlocked){ return (unlocked ? '⭐' : '🔒') + ' №' + (idx + 1); }

// [v2.8.5] host:port -> {cls,text} from the ping results of the last server check
// (Premium tab -> "Server checker"). checkerLastResults.ping.results is keyed by the
// positional f{i}/p{i}, so we match by the stored hp (host:port), not by index.
function _buildPingMap(checkerLastResults){
    var m = {};
    var clr = checkerLastResults;
    if (clr && clr.ping && clr.ping.results) {
        Object.keys(clr.ping.results).forEach(function(k){
            var r = clr.ping.results[k];
            if (r && r.hp && r.text) m[r.hp] = { cls: r.cls || '', text: r.text };
        });
    }
    return m;
}

// [v2.8.5] host:port → ms (число) из последней ping-проверки – для режима сортировки «По пингу».
// Неудачные/таймаут-пинги пропускаются (sortServers уводит их вниз как Infinity).
var _pingSortMap = null;
function _buildPingSortMap(pingMap){
    var m = {};
    if (pingMap) Object.keys(pingMap).forEach(function(hp){
        var ms = parseInt(pingMap[hp] && pingMap[hp].text, 10);
        if (!isNaN(ms) && ms >= 0) m[hp] = ms;
    });
    return m;
}
// [v2.8.5] true, если пользователь хотя бы раз прогонял ping-проверку серверов.
function _hasCheckerPingData(checkerLastResults){
    var p = checkerLastResults && checkerLastResults.ping;
    return !!(p && p.results && Object.keys(p.results).length > 0);
}

// [v2.9.2 critical fix] Auto-select смотрит ТОЛЬКО `serverPings` (writes bulk-ping),
// а UI server-list смотрит `checkerLastResults.ping.results` (writes server-checker
// в Premium-tab). Эти 2 store не синкаются обратно: если юзер пинговал через
// «Проверка серверов» вместо bulk-ping – pickBestServer не видит этих пингов.
// Merge: берём оба источника, на конфликт по host:port побеждает более свежий (max ts).
function _mergePingSources(serverPings, checkerLastResults){
    var merged = {};
    if (checkerLastResults && checkerLastResults.ping && checkerLastResults.ping.results) {
        Object.keys(checkerLastResults.ping.results).forEach(function(k){
            var r = checkerLastResults.ping.results[k];
            if (!r || !r.hp) return;
            // r.text формата "<ms> ms"; r.ts – timestamp
            var ms = parseInt(r.text, 10);
            if (isNaN(ms) || ms <= 0) return;
            merged[r.hp] = { ms: ms, ts: r.ts || 0 };
        });
    }
    if (serverPings && typeof serverPings === 'object' && !Array.isArray(serverPings)) {
        Object.keys(serverPings).forEach(function(hp){
            var sp = serverPings[hp];
            if (!sp || typeof sp.ms !== 'number' || sp.ms <= 0) return;
            var existing = merged[hp];
            if (!existing || (Number(sp.ts) || 0) > (Number(existing.ts) || 0)) {
                merged[hp] = { ms: sp.ms, ts: sp.ts || 0 };
            }
        });
    }
    return merged;
}

// [v2.7.3] ~22 callback'а chrome.storage.local.set в popup.js теперь начинаются с
// inline-проверки chrome.runtime.lastError (QuotaExceededError / transient storage fails).
// До 2.7.3 ошибки молча проглатывались → UI пересчитывал состояние на основе незаписанных данных.

// [v2.8.7] Multi-domain API fallback – клон того что в service_worker.js (без import/export
// между popup и SW). Active-domain хранится в chrome.storage.local._apiActiveDomain – shared
// с SW: если SW переключился на fallback, popup на следующем запросе подхватит то же.
// [v3.0.0] Новая инфраструктура – список ДОЛЖЕН совпадать с API_DOMAINS в service_worker.js.
// balancing.apiget.ru намеренно НЕ здесь (только для ссылок) – см. коммент в service_worker.js.
const API_DOMAINS = ['https://api.bot-support.ru', 'https://n1.bot-support.ru', 'https://g1.bot-support.ru', 'https://api.unkill.ru', 'https://n1.unkill.ru', 'https://g1.unkill.ru', 'https://api.sibirlife.ru', 'https://n1.sibirlife.ru', 'https://g1.sibirlife.ru', 'https://api.1150.ru', 'https://n1.1150.ru', 'https://g1.1150.ru', 'https://api.foofle.ru', 'https://n1.foofle.ru', 'https://g1.foofle.ru'];
const API_ACTIVE_KEY = '_apiActiveDomain';
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
async function apiFetch(path, opts) {
    const domains = await _getApiDomainsByPriority();
    let lastErr = null;
    for (let i = 0; i < domains.length; i++) {
        const d = domains[i];
        try {
            const resp = await fetch(d + path, opts);
            if (resp.status < 500) {
                await _persistActiveApiDomain(d);
                return resp;
            }
            lastErr = new Error('HTTP ' + resp.status + ' from ' + d);
        } catch (e) { lastErr = e; }
    }
    throw lastErr || new Error('All API domains unreachable');
}

// [v2.6.5] UTM helpers – analytics for site purchases
const SITE_PAYMENT_URL = 'https://balancing.apiget.ru/AnonVPN/lk/premium-access-payment/';
function siteUrl(medium) {
    var v = (chrome.runtime.getManifest && chrome.runtime.getManifest().version) || '';
    return SITE_PAYMENT_URL + '?utm_source=ext&utm_medium=' + encodeURIComponent(medium) + '&utm_campaign=v' + v;
}
function upsellUrl(medium) {
    return chrome.runtime.getURL('premium-upsell.html') + '?utm_medium=' + encodeURIComponent(medium);
}

// [v2.6.5] Единые URL Telegram-бота. Если бот переедет – правим только здесь.
// HTML держит те же URL как fallback (на случай если JS не успел до клика),
// JS при init переписывает href в актуальные – DRY на стороне JS.
const TG_BOT_HANDLE = '@exp_AnonVPN_bot';
const TG_URLS = {
    web:    'https://web.telegram.org/k/#' + TG_BOT_HANDLE,
    direct: 'https://t.me/'                + TG_BOT_HANDLE.slice(1),
};

// v2.4.2: device_id
function getDeviceId() {
    return new Promise(resolve => {
        chrome.storage.local.get(['uid'], data => {
            // [v2.7.4 audit r6] Regex validation на stored uid (parity с SW UID_VALID_RE F34).
            // Storage corruption (manual edit / quota partial write) могла оставить malformed uid;
            // popup using его в support iframe params + HMAC-style server log → malformed identifier.
            if (data.uid && /^u_[0-9a-z]+_[0-9a-z]+$/.test(data.uid)) { resolve(data.uid); return; }
            // [v2.7.0 fix F43 + v2.7.3 audit] Proper 40-bit base36 encoding – см. getUID в SW.
            const r = crypto.getRandomValues(new Uint8Array(5));
            let n = 0;
            for (let i = 0; i < 5; i++) n = n * 256 + r[i];
            const rand = n.toString(36).padStart(8, '0');
            const uid = 'u_' + Date.now().toString(36) + '_' + rand;
            chrome.storage.local.set({ uid }, () => {if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] uid save failed:",chrome.runtime.lastError.message);} resolve(uid);});
        });
    });
}

// [v2.8.2 Этап Б hardware FP] Собирает hardware-стабильный fingerprint для anti-abuse в trial/recover.
// Сигналы устойчивы к смене IP (другой VPN) И к переустановке расширения (никакого storage):
//   - Canvas – text rendering peculiarities GPU+OS+font-rendering stack
//   - WebGL – UNMASKED_RENDERER/VENDOR (имя GPU)
//   - AudioContext – DSP компрессор-pipeline + sample-rate hardware quirks
//   - screen.{width,height,devicePixelRatio} – display hw
//   - timezone – host OS timezone
//   - languages – Chrome lang list (стабильна per-install OS)
//   - hardwareConcurrency, deviceMemory, platform – host CPU/RAM/OS
// Каждый компонент isolated try/catch – если 1 fails, остальные дают entropy.
// Результат – sha256(parts.join('||')), 64 hex chars. Меняется только при смене железа/OS.
async function collectHardwareFp() {
    var parts = [];
    // 1. Canvas
    try {
        var c = document.createElement('canvas');
        c.width = 200; c.height = 50;
        var ctx = c.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillStyle = '#f60';
        ctx.fillRect(125, 1, 62, 20);
        ctx.fillStyle = '#069';
        ctx.fillText('AnonVPN_FP_test_😀', 2, 15);
        parts.push('canvas:' + c.toDataURL().slice(-100));
    } catch (e) { parts.push('canvas:err'); }
    // 2. WebGL
    try {
        var gl = document.createElement('canvas').getContext('webgl') || document.createElement('canvas').getContext('experimental-webgl');
        if (gl) {
            var dbg = gl.getExtension('WEBGL_debug_renderer_info');
            var rend = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
            var vend = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
            parts.push('webgl:' + (vend || '') + '|' + (rend || ''));
        } else parts.push('webgl:none');
    } catch (e) { parts.push('webgl:err'); }
    // 3. Audio (OfflineAudioContext)
    try {
        var AC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
        if (AC) {
            var ac = new AC(1, 44100, 44100);
            var osc = ac.createOscillator();
            osc.type = 'triangle';
            osc.frequency.value = 1000;
            var compressor = ac.createDynamicsCompressor();
            osc.connect(compressor);
            compressor.connect(ac.destination);
            osc.start(0);
            var buf = await ac.startRendering();
            var sample = 0;
            var data = buf.getChannelData(0);
            for (var i = 4500; i < 5000; i++) sample += Math.abs(data[i]);
            parts.push('audio:' + sample.toFixed(8));
        } else parts.push('audio:none');
    } catch (e) { parts.push('audio:err'); }
    // 4. Screen
    parts.push('screen:' + (screen.width || 0) + 'x' + (screen.height || 0) + '@' + (window.devicePixelRatio || 1));
    // 5. Timezone
    try { parts.push('tz:' + Intl.DateTimeFormat().resolvedOptions().timeZone); }
    catch (e) { parts.push('tz:' + new Date().getTimezoneOffset()); }
    // 6. Languages
    parts.push('langs:' + (navigator.languages ? navigator.languages.join(',') : navigator.language || ''));
    // 7. Hardware
    parts.push('hw:' + (navigator.hardwareConcurrency || 0) + '|' + (navigator.deviceMemory || 0) + '|' + (navigator.platform || ''));
    // SHA-256 hex
    // [v2.8.2 audit-2] try/catch на TextEncoder + digest. Раньше unguarded – fail отбрасывал
    // весь FP collect (catch в getClientFp), даунгрейд proto=2 → proto=1. Теперь явный path.
    try {
        var enc = new TextEncoder().encode(parts.join('||'));
        var buf2 = await crypto.subtle.digest('SHA-256', enc);
        var bytes = new Uint8Array(buf2);
        var hex = '';
        for (var i = 0; i < bytes.length; i++) hex += (bytes[i] < 16 ? '0' : '') + bytes[i].toString(16);
        return hex;
    } catch (e) {
        try { console.warn('[AnonVPN] FP digest fail:', e); } catch (_) {}
        return '';
    }
}

// In-popup-session cache. FP стабилен – повторный сбор лишний.
// При reopen popup – функция запустится заново (memory сброшен).
let _clientFpPromise = null;
function getClientFp() {
    if (_clientFpPromise) return _clientFpPromise;
    _clientFpPromise = collectHardwareFp().catch(function(e){
        // [v2.8.2 Этап Б] Сбор FP fail (например WebGL отключён в strict-privacy mode) – возвращаем
        // пустую строку. SW решит: если пусто – fallback на proto=1 (без client_fp).
        try { console.warn('[AnonVPN] FP collect fail:', e); } catch (_) {}
        return '';
    });
    return _clientFpPromise;
}

document.addEventListener('DOMContentLoaded', () => {

const $ = id => document.getElementById(id);
const accountModuleTitle = $('accountModuleTitle');
const statusLabel = $('statusLabel');
const accountStatus = $('accountStatus');
const expireLabel = $('expireLabel');
const premiumKeyInput = $('premiumKey');
const activateBtn = $('activateKey');
const premiumDateBlock = $('premiumDateBlock');
const premiumDateSpan = $('premiumDate');
const resetPremiumBtn = $('resetPremiumBtn');
const premiumMessage = $('premiumMessage');
const tgText = $('tgText');
const stars = document.querySelectorAll(".star");
const feedbackForm = $("feedback-form");
const submitButton = $("submit-feedback");
const editButton = $("edit-feedback");
const ratingInput = $("rating-value");
const feedbackTextarea = $("feedback");
const emailInput = $("email");
const toggle = $('proxyToggle');
const vpnToggleBtn = $('vpnToggleBtn');
const vpnStatusText = $('vpnStatusText');
const languageSelect = $('language');
const proxySelect = $('proxy-select');
const buyPremiumBtn = $('buyPremiumBtn');
const buyPremiumModal = $('buyPremiumModal');
const versionSpan = $("version");
const tabMain = $('tabMain');
const tabPremium = $('tabPremium');
const tabNews = $('tabNews');
const newsContainer = $('newsContainer');
const sysMsgContainer = $('sysMsgContainer');
const newsLoading = $('newsLoading');
const newsEmpty = $('newsEmpty');

// v2.4.3: Modal references
const serverBtnLabel = $('serverBtnLabel');
const langBtnLabel = $('langBtnLabel');
const langBtnFlag = $('langBtnFlag');
const langBtnText = $('langBtnText');

function updateLangBtn(code){
    if(langBtnText) langBtnText.textContent=LANG_NAMES[code]||code;
    if(langBtnFlag){
        var fc=LANG_FLAGS[code];
        langBtnFlag.src=fc?'flags/'+fc+'.svg':'';
        langBtnFlag.alt=code;
        langBtnFlag.style.display=fc?'':'none';
    }
}
// [v2.7.0 fix F55] `checkerServerBtnLabel` – orphan reference без соответствия в popup.html,
// осиротел после UI-рефакторинга до 2.7.0; `$('X')` возвращал null, переменная никогда не
// использовалась. Удаляем чтобы не сбивать будущие аудиты и не замусоривать scope.
const checkerSiteBtnLabel = $('checkerSiteBtnLabel');

// ═══ Country data ═══
var FLAG_MAP = {
    'US':'us','USA':'us','RU':'ru','DE':'de','NL':'nl','GB':'gb','UK':'gb',
    'FR':'fr','CA':'ca','JP':'jp','SG':'sg','AU':'au','SE':'se','FI':'fi',
    'CH':'ch','AT':'at','PL':'pl','CZ':'cz','RO':'ro','BG':'bg','HU':'hu',
    'UA':'ua','KZ':'kz','TR':'tr','IN':'in','BR':'br','KR':'kr','HK':'hk',
    'TW':'tw','IT':'it','ES':'es','PT':'pt','IE':'ie','DK':'dk','NO':'no',
    'IL':'il','AE':'ae','ZA':'za','MX':'mx','AR':'ar','CL':'cl','CO':'co',
    'LV':'lv','LT':'lt','EE':'ee','IS':'is','MD':'md','RS':'rs','HR':'hr',
    'SK':'sk','SI':'si','BE':'be','LU':'lu','GR':'gr','CY':'cy','MT':'mt','BY':'by','AM':'am'
};
// [v3.0.1] Фоллбэк на lowercase-код страны если кода нет в FLAG_MAP (FLAG_MAP теперь
// только для алиасов UK→gb, USA→us). Бандл флагов покрывает все 117 стран proxylin
// (наш единственный источник прокси) → новая страна-сервер НЕ требует релиза ради флага.
function getFlagFile(code){if(!code)return '';var c=FLAG_MAP[code.toUpperCase()]||code.toLowerCase();return 'flags/'+c+'.svg';}
function getFlagImg(code,large){
    var f=getFlagFile(code);
    if(!f) return null;
    var img=document.createElement('img');
    // [v3.0.1] hide broken-image если флаг отсутствует (страна вне бандла)
    img.onerror=function(){this.onerror=null;this.style.display='none';};
    img.src=f;img.className=large?'flag-img flag-img-lg':'flag-img';
    img.alt=code.toUpperCase();
    img.title=getCountryName(code);
    // [v2.7.1 fix F121] Lazy-load flags – server modal создаёт ~130 flag SVGs
    // (free+premium ~65 каждый). Без lazy все загружаются immediately on modal open,
    // блокируя render + bandwidth. loading="lazy" defers offscreen images.
    img.loading='lazy';
    return img;
}
var COUNTRY_NAME={
    'US':'United States','USA':'United States','RU':'Russia','DE':'Germany','NL':'Netherlands',
    'GB':'United Kingdom','UK':'United Kingdom','FR':'France','CA':'Canada','JP':'Japan',
    'SG':'Singapore','AU':'Australia','SE':'Sweden','FI':'Finland','CH':'Switzerland',
    'AT':'Austria','PL':'Poland','CZ':'Czech Republic','RO':'Romania','BG':'Bulgaria',
    'HU':'Hungary','UA':'Ukraine','KZ':'Kazakhstan','TR':'Turkey','IN':'India',
    'BR':'Brazil','KR':'South Korea','HK':'Hong Kong','TW':'Taiwan','IT':'Italy',
    'ES':'Spain','PT':'Portugal','IE':'Ireland','DK':'Denmark','NO':'Norway',
    'IL':'Israel','AE':'UAE','ZA':'South Africa','MX':'Mexico','AR':'Argentina',
    'CL':'Chile','CO':'Colombia','LV':'Latvia','LT':'Lithuania','EE':'Estonia',
    'IS':'Iceland','MD':'Moldova','RS':'Serbia','HR':'Croatia','SK':'Slovakia',
    'SI':'Slovenia','BE':'Belgium','LU':'Luxembourg','GR':'Greece','CY':'Cyprus','MT':'Malta','BY':'Belarus','AM':'Armenia'
};
var COUNTRY_NAME_RU={
    'US':'США','USA':'США','RU':'Россия','DE':'Германия','NL':'Нидерланды',
    'GB':'Великобритания','UK':'Великобритания','FR':'Франция','CA':'Канада','JP':'Япония',
    'SG':'Сингапур','AU':'Австралия','SE':'Швеция','FI':'Финляндия','CH':'Швейцария',
    'AT':'Австрия','PL':'Польша','CZ':'Чехия','RO':'Румыния','BG':'Болгария',
    'HU':'Венгрия','UA':'Украина','KZ':'Казахстан','TR':'Турция','IN':'Индия',
    'BR':'Бразилия','KR':'Южная Корея','HK':'Гонконг','TW':'Тайвань','IT':'Италия',
    'ES':'Испания','PT':'Португалия','IE':'Ирландия','DK':'Дания','NO':'Норвегия',
    'IL':'Израиль','AE':'ОАЭ','ZA':'ЮАР','MX':'Мексика','AR':'Аргентина',
    'CL':'Чили','CO':'Колумбия','LV':'Латвия','LT':'Литва','EE':'Эстония',
    'IS':'Исландия','MD':'Молдова','RS':'Сербия','HR':'Хорватия','SK':'Словакия',
    'SI':'Словения','BE':'Бельгия','LU':'Люксембург','GR':'Греция','CY':'Кипр','MT':'Мальта','BY':'Беларусь','AM':'Армения'
};
// [v3.0.1] Intl.DisplayNames – локализованное название страны для ЛЮБОГО кода
// (встроено в Chrome 81+, у нас min 109). Новая страна-сервер получает название
// автоматически, без хардкода и релиза. Формат кэшируется по языку (модал серверов
// зовёт getCountryName ~130 раз за открытие).
var _regionFmtCache={};
function _regionFmt(lang){
    if(_regionFmtCache[lang]!==undefined) return _regionFmtCache[lang];
    var f=null;
    try{ if(typeof Intl!=='undefined' && Intl.DisplayNames) f=new Intl.DisplayNames([lang||'en'],{type:'region'}); }catch(e){}
    _regionFmtCache[lang]=f;
    return f;
}
function getCountryName(code){
    if(!code) return '';
    var c=code.toUpperCase();
    var lang=getLang();
    // 1. Хардкод-маппинг – короткие удобные названия (США, ОАЭ, ЮАР) для частых стран.
    if(lang==='ru' && COUNTRY_NAME_RU[c]) return COUNTRY_NAME_RU[c];
    if(COUNTRY_NAME[c]) return COUNTRY_NAME[c];
    // 2. Intl.DisplayNames – для ЛЮБОЙ другой страны (Армения, Грузия, Узбекистан…) без релиза.
    var fmt=_regionFmt(lang);
    if(fmt){ try{ var n=fmt.of(c); if(n && n.toUpperCase()!==c) return n; }catch(e){} }
    // 3. код как есть
    return c;
}

// Language flag codes
var LANG_FLAGS = {ru:'ru',en:'gb',de:'de',fr:'fr',es:'es',pt:'br',zh:'cn',ja:'jp',ko:'kr',it:'it',nl:'nl',pl:'pl',tr:'tr',ar:'ae',hi:'in',vi:'vn',th:'th',id:'id',sv:'se',am:'et',bg:'bg',bn:'bd',ca:'es',cs:'cz',da:'dk',el:'gr',et:'ee',fa:'ir',fi:'fi',fil:'ph',gu:'in',he:'il',hr:'hr',hu:'hu',kn:'in',lt:'lt',lv:'lv',ml:'in',mr:'in',ms:'my',no:'no',ro:'ro',sk:'sk',sl:'si',sr:'rs',sw:'ke',ta:'in',te:'in'};
var LANG_NAMES = {ru:'Русский',en:'English',de:'Deutsch',fr:'Français',es:'Español',pt:'Português',zh:'中文',ja:'日本語',ko:'한국어',it:'Italiano',nl:'Nederlands',pl:'Polski',tr:'Türkçe',ar:'العربية',hi:'हिन्दी',vi:'Tiếng Việt',th:'ไทย',id:'Bahasa Indonesia',sv:'Svenska',am:'አማርኛ',bg:'Български',bn:'বাংলা',ca:'Català',cs:'Čeština',da:'Dansk',el:'Ελληνικά',et:'Eesti',fa:'فارسی',fi:'Suomi',fil:'Filipino',gu:'ગુજરાતી',he:'עברית',hr:'Hrvatski',hu:'Magyar',kn:'ಕನ್ನಡ',lt:'Lietuvių',lv:'Latviešu',ml:'മലയാളം',mr:'मराठी',ms:'Bahasa Melayu',no:'Norsk',ro:'Română',sk:'Slovenčina',sl:'Slovenščina',sr:'Српски',sw:'Kiswahili',ta:'தமிழ்',te:'తెలుగు'};

let newsLoaded = false;

// ═══ FAVORITES ═══
var favoriteServers = [];
// [v2.7.1 fix F138] Array.isArray – corrupted storage (object вместо массива) ломал .indexOf вызовы
function loadFavorites(cb){chrome.storage.local.get(['favoriteServers'],function(d){favoriteServers=Array.isArray(d.favoriteServers)?d.favoriteServers:[];if(cb)cb();});}
function isFavoriteProxy(proxy){return proxy && favoriteServers.indexOf(proxy.host+':'+proxy.port)>=0;}
// [v3.1.2] Tooltip звезды избранного (восстановлен — раньше был, потом пропал). Динамический.
function _favTitle(active){ return active ? t('favRemove','Убрать из избранного') : t('favAdd','Добавить в избранное'); }
function toggleFavoriteProxy(proxy){
    var id=proxy.host+':'+proxy.port, idx=favoriteServers.indexOf(id);
    if(idx>=0) favoriteServers.splice(idx,1); else favoriteServers.push(id);
    // [v2.7.1 fix F128] callback с lastError – fire-and-forget без guard терял quota errors молча
    chrome.storage.local.set({favoriteServers:favoriteServers}, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;} void chrome.runtime.lastError; });
}

// [v2.5.9] Per-server exclusion from auto-select pool
var autoSelectExcluded = [];
function loadAutoSelectExcluded(cb){
    chrome.storage.local.get(['excludedFromAutoSelect'],function(d){
        // [v2.7.1 fix F139] Array.isArray – см. F138
        autoSelectExcluded = Array.isArray(d.excludedFromAutoSelect) ? d.excludedFromAutoSelect : [];
        if(cb) cb();
    });
}
function isExcludedFromAutoSelect(proxy){
    // [v2.8.2 audit-2] Array.isArray guard – без него storage corruption (autoSelectExcluded
    // = null/string) → indexOf throw → callsite (renderProxySelect/buildServerModalList) crash.
    if (!proxy || !Array.isArray(autoSelectExcluded)) return false;
    return autoSelectExcluded.indexOf(proxy.host+':'+proxy.port) >= 0;
}
function toggleAutoSelectExclude(proxy){
    // [v2.8.2 audit-3 F18] Array.isArray guard на write path. Read path (isExcludedFromAutoSelect)
    // уже guarded – symmetric protection. Без guard'а corruption (autoSelectExcluded=null) → indexOf throw.
    if (!Array.isArray(autoSelectExcluded)) autoSelectExcluded = [];
    if (!proxy || !proxy.host || !proxy.port) return;
    var id = proxy.host+':'+proxy.port, idx = autoSelectExcluded.indexOf(id);
    if(idx>=0) autoSelectExcluded.splice(idx,1); else autoSelectExcluded.push(id);
    // [v2.7.1 fix F129] callback с lastError – см. F128
    chrome.storage.local.set({excludedFromAutoSelect: autoSelectExcluded}, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;} void chrome.runtime.lastError; });
}

// ═══ MODAL SYSTEM ═══
function openModal(id){ var m=$(id); if(m) m.classList.add('active'); }
function closeModal(id){
    var m=$(id);
    if(!m) return;
    m.classList.remove('active');
    // [v2.7.0 fix F40] Освобождаем iframe src при закрытии support-modal, чтобы iframe
    // не держал https://balancing.apiget.ru/AnonVPN/lk/... connection после close (память + network).
    // Re-open openSupportChat/FaqModal проставит src заново.
    if (id === 'supportModal') { var f=$('supportFaqFrame'); if (f) f.src = ''; }
    if (id === 'supportChatModal') { var c=$('supportChatFrame'); if (c) { c.src = ''; if (c.dataset) delete c.dataset.lastUrl; } }
    // [v3.1.3] Останавливаем опрос статуса фоновой проверки при закрытии выбора сервера
    // (закрытие крестиком/оверлеем/ESC – все пути идут через closeModal).
    if (id === 'serverModal') { _ghostStatusStop(); _hideServerSitesTip(); } // [v3.1.7] прячем висящую подсказку сайтов
}

// [v3.1.3] Статус фоновой проверки скорости в шапке модалки «Выбор сервера»:
// «Идёт проверка…» (SW гоняет очередь) / «До проверки: 00:37» (отсчёт до alarm-тика) /
// «Пауза: ВПН включён». Опрос SW раз в 2с (заодно держит SW живым, пока модалка открыта →
// очередь пингуется без пауз на усыпление), локальная перерисовка отсчёта – каждую секунду.
var _ghostStatusTimer = null;
var _ghostStatusData = null;
function _ghostStatusRender(){
    var el = $('ghostPingStatus'); if (!el) return;
    var d = _ghostStatusData;
    var txt = '';
    if (d && d.vpnOn) txt = t('ghostPausedVpn', 'Пауза: ВПН включён');
    else if (d && d.running) txt = t('ghostChecking', 'Идёт проверка…');
    else if (d && d.nextAt) {
        var s = Math.max(0, Math.ceil((d.nextAt - Date.now()) / 1000));
        var mm = Math.floor(s / 60), ss = s % 60;
        var timeStr = (mm < 10 ? '0' : '') + mm + ':' + (ss < 10 ? '0' : '') + ss;
        txt = t('ghostNextCheck', 'До проверки: {time}').replace('{time}', timeStr);
    }
    el.textContent = txt;
    el.title = txt; // полный текст при обрезке ellipsis на длинных локализациях
}
function _ghostStatusPoll(kick){
    try {
        chrome.runtime.sendMessage({ action: 'ghostPingStatus', kick: !!kick }, function(resp){
            if (chrome.runtime && chrome.runtime.lastError) return; // SW перезапускается – дождёмся следующего опроса
            if (resp && resp.ok) { _ghostStatusData = resp; _ghostStatusRender(); }
        });
    } catch (e) {}
}
function _ghostStatusStart(){
    _ghostStatusStop();
    _ghostStatusPoll(true); // kick: будим цикл сразу при открытии списка, не дожидаясь alarm
    var n = 0;
    _ghostStatusTimer = setInterval(function(){
        n++;
        if (n % 2 === 0) _ghostStatusPoll(false);
        _ghostStatusRender();
    }, 1000);
}
function _ghostStatusStop(){
    if (_ghostStatusTimer) { clearInterval(_ghostStatusTimer); _ghostStatusTimer = null; }
    _ghostStatusData = null;
}

// Close buttons
document.querySelectorAll('.modal-close').forEach(function(btn){
    var target=btn.getAttribute('data-close');
    if(target) btn.addEventListener('click',function(){closeModal(target);});
});
// Overlay click
document.querySelectorAll('.modal-overlay').forEach(function(ov){
    // [v2.7.0 fix F40.1] Вызываем closeModal(ov.id) вместо прямого classList.remove,
    // чтобы отрабатывала F40-очистка iframe.src для support-modal (иначе iframe.src
    // остаётся при клике-overlay → memory leak + висит network-соединение на anon-vpn.ru).
    ov.addEventListener('click',function(e){if(e.target===ov) closeModal(ov.id);});
});
// [v2.7.0 fix F59+F77] Escape key закрывает активную модалку ИЛИ settings-drawer.
// F77 добавил покрытие settings-overlay – F59 изначально смотрел только на
// `.modal-overlay.active` и юзер не мог закрыть настройки клавиатурой.
document.addEventListener('keydown', function(e){
    if (e.key !== 'Escape') return;
    var active = document.querySelector('.modal-overlay.active');
    if (active && active.id) {
        // [v2.7.6 audit Pass13] Escape на importConfirmModal – clear pending state.
        // Без cleanup'а stale `_pendingImport` оставался бы set'нутым (хотя popup-scope
        // защищает от cross-session leak, в рамках одной сессии было бы нечисто).
        if (active.id === 'importConfirmModal') { try { _pendingImport = null; } catch(_) {} }
        e.preventDefault(); closeModal(active.id); return;
    }
    var settingsOv = $('settingsOverlay');
    if (settingsOv && settingsOv.classList.contains('active')) { e.preventDefault(); closeSettings(); }
});

// ═══ TABS ═══
// [v2.6.5 audit] Единый handler с ветками per-tab – раньше было ДВА отдельных forEach
// по `.tab-btn` (second – в секции «Premium tab init»), оба вешали listener на одни и те же
// 3 элемента. Клик на Premium → дубль-работа + лишние storage.get.
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => {
            b.classList.remove('active');
            // [v2.7.1 fix F84] aria-selected синхронизируется с .active-классом. Раньше
            // при клике табы меняли только classList, aria-selected оставался с HTML-defaults
            // (main=true, остальные=false) → скринридеры объявляли неверный "selected"-таб.
            b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
        });
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        $('tab-' + btn.dataset.tab).classList.add('active');
        if (btn.dataset.tab === 'news' && !newsLoaded) { loadNews(); newsLoaded = true; }
        if (btn.dataset.tab === 'premium') { updatePremiumTabLock(); loadExclusions(); loadAdBlockerState(); loadAutoEnable(); }
    });
});

// ═══ TRANSLATE ═══
// [v2.5.8 audit] Sentinel-ключ: если его нет в кэше – кэш устарел, перезагружаем.
// [v2.6.3] Дополнительно проверяем cachedTranslationsVersion – переводы могут
// меняться без добавления новых ключей (правки текстов), sentinel это не ловит.
function isTranslationsCacheCurrent(tr) {
    // [v2.7.0 fix F38 + F38.1] sentinel расширен для инвалидации старых кэшей 2.6.x –
    // автоEnablePermDenied (F31) + connectionError/deviceChanged/premiumExpired/connectionTimeout
    // активно используются в UI, без них старый юзер видит en-fallback при отсутствии ключей.
    return !!(tr && tr.en
        && tr.en.illegalVersionBanner && tr.en.autoSelectServer && tr.en.sessionExpiredTitle
        && tr.en.adBlockerTitle && tr.en.tryTrialLabel && tr.en.recoverPremiumLabel
        && tr.en.trialMainCtaTitle && tr.en.timerUrgencyText && tr.en.autoEnableTitle
        && tr.en.autoEnableNotifMsg && tr.en.webNavPermPrompt && tr.en.autoEnablePermDenied
        && tr.en.connectionError && tr.en.deviceChanged && tr.en.premiumExpired
        && tr.en.connectionTimeout && tr.en.autoEnableInvalidDomain
        // [v2.7.6 audit Pass9] Sentinel updated to freeBlockedUpsell (newest key in
        // 2.7.3 free-server-lock feature, position 248/248) – was freeBlockedTitle
        // which doesn't catch cache-staleness for users who already have *Title but
        // missing *Upsell key.
        && tr.en.freeBlockedTitle && tr.en.freeBlockedUpsell
        && tr.en.offlineError
        // [v2.7.1 fix F105] Sentinel ловит race между popup-open и SW init –
        // если юзер откроет popup ДО STALE_KEYS wipe (или wipe failed на quota),
        // sentinel mismatch → forced re-fetch → fresh translations с новым ключом.
        // [v2.7.1 fix F147] Обновлено на toggleBusy (новейший добавленный ключ из F123) –
        // CLAUDE.md паттерн: sentinel = newest-added key.
        && tr.en.storageLimitExceeded
        && tr.en.toggleBusy
        // [v2.7.6] Sentinel updated to feat_backup (newest key after backup moved
        // to Premium-only zone, position 264/264).
        && tr.en.backupImportSummary
        && tr.en.feat_backup
        // [v2.7.3] freeBlockedTitle – добавлен в free-server-lock feature.
        && tr.en.freeBlockedTitle
        // [v2.8.0] rateLimitTitle – bot-detection ban banner (новейший ключ position 268/268).
        && tr.en.rateLimitTitle
        && tr.en.rateLimitTextUntil
        // [v2.8.0] account-link feature (newest keys, position 281/281). Sentinel
        // обновлён до accountUnlinkConfirm (последний добавленный) – это инвалидирует
        // кэш для юзеров которые откроют popup впервые после update на 2.8.0.
        && tr.en.accountSection
        && tr.en.accountUnlinkConfirm
        // [v2.8.0] supportChatTitle – newest of 13 keys добавленных в этом round'е
        // (sortMode/checkBtnShort/stopping/disableVpnForCheck/etc.). Sentinel закрывает
        // edge case для юзеров с partial cached переводом (старая структура без этих keys).
        && tr.en.supportChatTitle
        // [v2.8.0] premiumOrVerifiedOnly – новый lock-message для checker (Premium ИЛИ verified)
        && tr.en.premiumOrVerifiedOnly
        // [v2.8.0] feat-desc для exclusions/theme cards (descriptions visible when locked)
        && tr.en.exclusionsFeatureDesc && tr.en.themeFeatureDesc
        // [v2.8.0] checker rate-limit messages + hints для free-verified юзеров
        // (ping=1/час, site=3/час – раздельные счётчики через checkerRunHistory)
        && tr.en.checkerRateLimited && tr.en.checkerFreeVerifiedHint
        && tr.en.checkerRateLimitedSite && tr.en.checkerFreeVerifiedHintSite
        // [v2.8.2] vpnConflictBlocked – newest key (position 302/302). Без проверки старый
        // кэш юзеров без vpnConflictBlocked показывал бы английский fallback вместо локали.
        && tr.en.vpnConflictBlocked
        // [v2.8.4] noServersOffline / noServersServer – детализация «Нет серверов».
        // Sentinel закрывает кэш юзеров с partial cached переводом (без новых ключей).
        && tr.en.noServersOffline && tr.en.noServersServer
        // [v2.8.5] sortByPing – режим сортировки «По пингу»; checkerWarn* – предупреждения
        // массовой проверки; checkerLockedTitle – модалка «чекер недоступен» (free без премиума/почты).
        && tr.en.sortByPing
        && tr.en.checkerWarnFree && tr.en.checkerWarnPremium
        && tr.en.checkerLockedTitle && tr.en.checkerLockedText
        && tr.en.sysKeyExpBody && tr.en.sysMarkRead
        // [v2.8.6] proxyControlTitle – баннер «прокси перехвачен другой программой»
        && tr.en.proxyControlTitle
        // [v2.8.8] bypassRuLabel + bypassRuHint – toggle и hover-подсказка для .ru/.рф bypass.
        && tr.en.bypassRuLabel && tr.en.bypassRuHint
        // [v3.1.1] Уведомления о конце сессии (настройки + текст warn-уведомления)
        // + переводимый текст verify-баннера (раньше hardcoded ru).
        && tr.en.notifTimerSoon && tr.en.notifyEndLabel && tr.en.notifySoonLabel
        && tr.en.accountVerifyBannerText
        // [v2.9.1] setupTitle/setupSub/metricByLoad/metricByPing/metricBoth/setupDoneBtn/
        // setupRunPingsLabel/bulkPingProgress/bulkPingDone – setup wizard + bulk-ping UI.
        // bulkPingDone – newest sentinel.
        && tr.en.metricByLoad && tr.en.metricByPing && tr.en.metricBoth && tr.en.bulkPingDone
        // [v3.0.1] diagnostics i18n – 51 ключ (вердикты/шаги/метки/статусы).
        && tr.en.fullDiagLabel && tr.en.diagV_all_ok_m && tr.en.diagRateLimited && tr.en.metricRecommended
        // [v3.0.3] гео-ограничения (метка YouTube/Instagram в выборе сервера).
        && tr.en.geoBlockTitle && tr.en.geoBlockText
        // [v3.0.3] уведомление rescue + статус «подбираем» + метка «не отвечает». newest sentinel.
        && tr.en.ipBrokenTitle && tr.en.ipBrokenSwitched && tr.en.ipRescuing && tr.en.ipBrokenMark && tr.en.ipBrokenManual
        // [v3.0.3] предупреждение про общий лимит трафика (EE/JP/FI) + финальная no-server модалка.
        && tr.en.trafficTitle && tr.en.trafficText && tr.en.noServerTitle && tr.en.noServerText
        // [v3.0.3] модалка «как обновить вручную» (11 ключей). newest sentinel.
        && tr.en.updateHelpTitle && tr.en.updateHelpCopied && tr.en.updateHelpBtnAria
        // [v3.0.5] мастер первичной настройки (ключ/проверка/готово + хоткей-уведомление). newest sentinel.
        && tr.en.setupKeyPrompt && tr.en.setupCheckPrompt && tr.en.setupHotkeyText
        // [v3.0.5] уведомление о смене недоступного сервера. newest sentinel.
        && tr.en.staleSwitchText
        && tr.en.setupSkipDanger
        // [v3.1.2] tooltip звезды избранного. newest sentinel.
        && tr.en.favRemove
        // [v3.1.3] статус фоновой проверки в шапке выбора сервера. newest sentinel.
        && tr.en.ghostNextCheck
        // [v3.1.4] вердикт «прокси перехвачен» + список найденных VPN. newest sentinel.
        && tr.en.diagV_proxy_hijacked_m
        && tr.en.diagOtherVpnsFound
        && tr.en.serverBrokenTitle // [v3.1.6] подсказки в выборе сервера
        // [v3.1.7] автоподбор сервера для сайта + подсказка проверенных сайтов при наведении
        // + тумблер подсказки в настройках + кнопка чата пользователей. newest sentinel.
        && tr.en.autoPickBtnLabel && tr.en.siteHitsHead && tr.en.siteHintsToggleLabel && tr.en.communityChatLabel);
}

// [v2.7.1 fix F88] _translateAllInFlight – защита от interleave DOM mutations при
// быстром en→ru→de: первый fetch ещё в полёте → второй clicks – оба applyTranslations
// в разных языках перемешивали 200+ setText-вызовов. Guard drops duplicate лишь во
// время fetch-окна (~100мс на холодном cache); cache-hit всё равно sync.
var _translateAllInFlight = false;
function translateAll(lang) {
    var extVersion = chrome.runtime.getManifest().version;
    if (cachedTranslations && isTranslationsCacheCurrent(cachedTranslations) && _cachedTranslationsVersion === extVersion) {
        applyTranslations(lang, cachedTranslations);
        return;
    }
    if (_translateAllInFlight) return;
    _translateAllInFlight = true;
    // Кэш отсутствует или устарел – грузим с диска.
    // [v2.6.3] cache:'no-store' + версионный cache-buster – Chrome агрессивно кеширует
    // `fetch(runtime.getURL)` внутри процесса; без этих мер dev-правки translations.json
    // не подхватываются даже после reload расширения.
    fetch(chrome.runtime.getURL('translations.json') + '?v=' + extVersion, { cache: 'no-store', signal: AbortSignal.timeout(5000) })
        .then(res => { if (!res.ok) throw new Error('http ' + res.status); return res.json(); })
        .then(translations => {
            cachedTranslations = translations;
            _cachedTranslationsVersion = extVersion;
            // [v2.7.1 fix F115] Chain storage.set перед applyTranslations – без `return`
            // promise был fire-and-forget; popup-close mid-microtask терял write на disk
            // → SW restart → next popup open читал stale storage → forced re-fetch.
            // Awaiting гарантирует persist перед DOM mutation.
            return chrome.storage.local.set({ cachedTranslationsData: translations, cachedTranslationsVersion: extVersion })
                .catch(() => {})
                .then(() => applyTranslations(lang, translations));
        })
        // [v2.5.8 audit] Без catch popup завис бы если файл переводов битый.
        // Минимальный fallback: пустые переводы → сработают inline-фоллбэки в setText/t().
        .catch(() => { applyTranslations(lang, {}); })
        .finally(() => { _translateAllInFlight = false; });
}

function applyTranslations(lang, translations) {
    // [v2.6.2 audit] Two-tier fallback: язык → английский → hardcoded.
    // Раньше: для не-ru/en юзеров новые ключи (которых нет в их языке) → undefined → setText игнорировал → оставался HTML default (русский). Теперь ключ обязательно резолвится через en, если он там есть.
    const _trLang = translations[lang] || translations['en'] || {};
    const _trEn = translations['en'] || {};
    const tr = new Proxy({}, {
        get: function(_, key) {
            return (key in _trLang) ? _trLang[key] : _trEn[key];
        }
    });
    // RTL support
    var isRTL = (lang === 'ar' || lang === 'he' || lang === 'fa');
    document.body.dir = isRTL ? 'rtl' : 'ltr';
    document.documentElement.lang = lang;

    setText('proxyToggleLabel', tr.proxyToggleLabel);
    setText('languageLabel', tr.languageLabel);
    setText('feedbackTitle', tr.feedbackTitle);
    setText('serverSelectTitle', (tr.serverItem || 'Server') + ": ");
    if (buyPremiumBtn) buyPremiumBtn.textContent = tr.buyPremiumButton || 'Buy Premium';
    var _abBtn=$('accountBuyBtn'); if(_abBtn) _abBtn.textContent=tr.buyPremiumButton||'Buy Premium';
    setText('buyModalTitle', tr.buyModalTitle || 'Buy Premium');
    setText('buyModalText', tr.buyModalText || '');
    setText('buyModalAction', tr.buyModalAction || '');
    setText('buyModalActionSite', tr.buyModalActionSite || 'Buy on website');
    setText('supportBtnText', tr.supportButton || 'Support');
    setText('communityChatText', tr.communityChatLabel || 'User chat');
    setText('privacyBtn', tr.privacyPolicy || 'Privacy Policy');
    setText('vpnLockedBannerText', tr.vpnLockedBanner || 'Server selection and premium settings are locked. Disable VPN to change them.');
    setText('vpnLockedBannerPremiumText', tr.vpnLockedBanner || 'Server selection and premium settings are locked. Disable VPN to change them.');
    setText('vpnConflictBannerTitle', tr.vpnConflictTitle || 'Other active VPN extensions detected');
    setText('vpnConflictBannerHint', tr.vpnConflictHint || 'Disable them in chrome://extensions to avoid connection problems.');
    setText('proxyControlBannerTitle', tr.proxyControlTitle || 'Proxy is controlled by another program');
    setText('proxyControlBannerHint', tr.proxyControlHint || 'VPN is on, but traffic bypasses AnonVPN. Open chrome://extensions, disable other VPN/proxy extensions, then turn the VPN on again.');
    setText('settingsConflictTitle', tr.settingsConflictTitle || 'VPN conflicts');
    setText('settingsConflictHint', tr.settingsConflictHint || 'Check for other active VPN extensions that may interfere');
    setText('checkVpnConflictLabel', tr.checkVpnConflictBtn || 'Check');
    setText('loadWarningBannerTitle', tr.loadWarningTitle || 'Servers may be experiencing elevated load');
    setText('loadWarningBannerText', tr.loadWarningText || 'Speed and stability may be affected. Premium unlocks access to less loaded servers.');
    setText('loadWarningBuyBtn', tr.loadWarningBuyBtn || 'Get Premium');
    setText('loadWarningTrialBtn', tr.loadWarningTrialBtn || 'Free trial in Telegram');
    setText('sessionExpiredTitle', tr.sessionExpiredTitle || 'Session has ended');
    setText('sessionExpiredText', tr.sessionExpiredText || 'Your 1-hour VPN session ended. Premium removes the time limit.');
    var _sepb = $('sessionExpiredPremiumBtn'); if (_sepb) _sepb.textContent = tr.sessionExpiredPremiumBtn || 'Premium';
    var _setb = $('sessionExpiredTrialBtn'); if (_setb) _setb.textContent = tr.sessionExpiredTrialBtn || 'Trial';
    var _sedb = $('sessionExpiredDetailsBtn'); if (_sedb) _sedb.textContent = tr.sessionExpiredDetailsBtn || 'Details';
    setText('overloadConfirmTitle', tr.overloadConfirmTitle || 'Elevated server load');
    (function(){
        var el = $('overloadConfirmText'); if (!el) return;
        var tmpl = tr.overloadConfirmText || 'The selected server may be experiencing elevated load ({n} users). Connection may be slower than usual. Continue?';
        var prevCount = ($('overloadConfirmCount') && $('overloadConfirmCount').textContent) || '–';
        // [v2.6.5 audit] DOM API – никаких innerHTML, CWS-сканеры не помечают, fallback-шаблон не
        // даёт вложенного <b id="overloadConfirmCount"> (раньше hardcoded-фаллбэк уже содержал
        // обёртку, а код добавлял ещё одну → двойной id).
        renderOverloadConfirmText(el, tmpl, prevCount);
    })();
    var _oy = $('overloadConfirmYes'); if (_oy) _oy.textContent = tr.overloadConfirmYes || 'Connect';
    var _on = $('overloadConfirmNo'); if (_on) _on.textContent = tr.overloadConfirmNo || 'Cancel';
    // [v2.7.3] freeBlockedModal – free-юзер на перегруженном сервере
    setText('freeBlockedTitle', tr.freeBlockedTitle || 'Server unavailable');
    setText('freeBlockedText', tr.freeBlockedText || 'This server is overloaded. Without Premium you can only connect to servers with low load. Activate Premium to connect to any server without restrictions.');
    var _fbc = $('freeBlockedCancel'); if (_fbc) _fbc.textContent = tr.freeBlockedCancel || 'Close';
    var _fbu = $('freeBlockedUpsell'); if (_fbu) _fbu.textContent = tr.freeBlockedUpsell || 'Activate Premium';
    // [v2.8.5] checkerLockedModal – кнопки переиспользуют freeBlocked*-строки.
    setText('checkerLockedTitle', tr.checkerLockedTitle || 'Server check unavailable');
    setText('checkerLockedText', tr.checkerLockedText || 'Server checking is available with Premium or a verified email. Verify your email in the extension settings (free) or get Premium.');
    var _clc = $('checkerLockedClose'); if (_clc) _clc.textContent = tr.freeBlockedCancel || 'Close';
    var _clu = $('checkerLockedUpsell'); if (_clu) _clu.textContent = tr.freeBlockedUpsell || 'Activate Premium';
    // [v3.1.6] Легенда обозначений + предупреждения при выборе сервера (для тех, кто не понимает значков)
    setText('serverLegendTitle', tr.serverLegendTitle || 'What the icons mean');
    setText('serverLegendPing', tr.serverLegendPing || 'The number next to a server is its response speed (ping). Green is fast, red is slow.');
    setText('serverLegendBroken', tr.serverLegendBroken || 'A cross means the server is not responding or failed the check. You will not be able to connect to it.');
    setText('serverLegendPending', tr.serverLegendPending || 'If there is no speed icon, the server is still being checked. Wait a couple of seconds.');
    setText('serverLegendUsers', tr.serverLegendUsers || 'The person icon shows how many people are on the server now. The more there are, the higher the load.');
    setText('serverLegendGeo', tr.serverLegendGeo || 'The triangle warns that the server country may have restrictions or outages.');
    setText('serverLegendFav', tr.serverLegendFav || 'The star adds the server to favorites and pins it to the top of the list.');
    setText('serverLegendExclude', tr.serverLegendExclude || 'Minus removes the server from automatic selection, plus brings it back.');
    setText('serverLegendGotIt', tr.serverLegendGotIt || 'Got it');
    setText('serverNoPingTitle', tr.serverNoPingTitle || 'Check still in progress');
    setText('serverNoPingText', tr.serverNoPingText || 'This server has no speed check result yet, it may still be checking. It is better to wait a few seconds. Connect anyway?');
    setText('serverNoPingConnect', tr.serverNoPingConnect || 'Connect');
    setText('serverNoPingCancel', tr.serverPickCancel || 'Cancel');
    setText('serverBrokenTitle', tr.serverBrokenTitle || 'Server not responding');
    setText('serverBrokenText', tr.serverBrokenText || 'This server failed the check: it is not responding and does not ping. You most likely will not be able to connect to it. Better choose another server.');
    setText('serverBrokenConnectAnyway', tr.serverBrokenConnectAnyway || 'Connect anyway');
    setText('serverBrokenChooseOther', tr.serverBrokenChooseOther || 'Choose another');
    var _slb = $('serverLegendBtn'); if (_slb) _slb.setAttribute('aria-label', tr.serverLegendTitle || 'What the icons mean');
    // [v2.7.6] Backup section + import confirm modal
    setText('settingsBackupTitle', tr.settingsBackupTitle || 'Backup');
    setText('settingsBackupHint', tr.settingsBackupHint || 'Save settings and site lists to transfer them to another browser');
    setText('exportSettingsLabel', tr.exportSettingsBtn || 'Export');
    setText('importSettingsLabel', tr.importSettingsBtn || 'Import');
    setText('importConfirmTitle', tr.importConfirmTitle || 'Confirm import');
    setText('importConfirmText', tr.importConfirmText || 'Current settings will be replaced. Premium key and statistics are not affected.');
    var _icy = $('importConfirmYes'); if (_icy) _icy.textContent = tr.importConfirmYes || 'Import';
    var _icn = $('importConfirmNo'); if (_icn) _icn.textContent = tr.confirmNo || 'Cancel';
    setText('serverModalTitle', tr.selectServer || 'Select server');
    setText('serverStatusLinkLabel', tr.serverStatusLink || 'Server status');
    setText('autoSelLabel', tr.autoSelectServer || 'Auto-select server');
    setText('autoSelScopeAll', tr.autoSelectScopeAll || 'All');
    setText('autoSelScopeFree', tr.autoSelectScopeFree || 'Standard');
    setText('autoSelScopePrem', tr.autoSelectScopePremium || 'Premium');
    updateAutoSelScopeText();
    // [audit fix critical] Method-dropdown items + setup-modal labels – обновляем здесь
    // синхронно при смене языка. Раньше hardcoded HTML «Комбо/По нагрузке/По скорости»
    // не переводился до user-click. setText игнорирует пустые/falsy → fallback держит HTML.
    setText('autoSelMethodPing', tr.metricByPing || 'By speed');
    setText('autoSelMethodBoth', tr.metricBoth || 'Combo');
    // [v3.0.5] Мастер первичной настройки – переводы шагов (и здесь, и при открытии в _showSetupMetricModal)
    setText('setupKeyPrompt', tr.setupKeyPrompt || 'Have a premium key? Paste it to remove all time limits. No key – just skip, the VPN works for free too.');
    setText('setupKeySkip', tr.setupKeySkip || 'I have no key – skip →');
    setText('setupPremiumOkText', tr.setupPremiumOk || 'Premium is active ✓ – no time limits.');
    setText('setupCheckPrompt', tr.setupCheckPrompt || 'Now we’ll pick a working server so the VPN works right away. The check takes about 2 minutes.');
    setText('setupCheckWarnText', tr.setupCheckWarn || 'Without this you may land on a slow or non-working server.');
    setText('setupStartCheck', tr.setupStartCheck || 'Start the check');
    setText('setupCheckSkip', tr.setupCheckSkip || 'Skip the check →');
    setText('setupDoneText', tr.setupDoneText || 'All set! Close this window and press “Turn on VPN”.');
    setText('setupFinishBtn', tr.setupFinishBtn || 'Great');
    var _smt = $('setupMetricTitle'); if (_smt && tr.setupTitle) _smt.textContent = tr.setupTitle;
    var _sms = $('setupMetricSub'); if (_sms && tr.setupSub) _sms.textContent = tr.setupSub;
    // Также пере-применяем dropdown text (selected method label) – учитывает isPremium + pings.
    try { updateAutoSelMethodText(); } catch (_) {}
    // Refresh tooltips on existing "-" buttons in the server modal (if open)
    document.querySelectorAll('#serverModalList .modal-item-exclude').forEach(function(el){
        var isExc = el.classList.contains('excluded');
        el.title = isExc
            ? (tr.includeInAutoSelect || 'Include in auto-select')
            : (tr.excludeFromAutoSelect || 'Exclude from auto-select');
    });
    setText('langModalTitle', tr.selectLanguage || 'Select language');
    setText('checkerModalTitle', tr.checkerTitle ? tr.checkerTitle.replace(/^🔍\s*/,'') : 'Server check');
    setText('checkerIntroHint', tr.checkerIntroHint || 'Measure speed and site availability through each server.');
    // [v2.7.1 fix F110] EN fallback symmetric с остальным кодом – non-RU юзеры не должны
    // видеть русский текст при отсутствии translation key.
    var _occm = $('openCheckerModal'); if (_occm) _occm.textContent = tr.openCheckerBtn || 'Open checker';
    var _cab = $('checkAllBtn'); if (_cab) _cab.textContent = tr.checkAll || 'Check all';
    var _apb = $('autoPickBtn'); if (_apb) _apb.textContent = tr.autoPickBtnLabel || '🎯 Find best';
    setText('autoPickTabText', tr.autoPickTabLabel || 'Site not opening? Pick a server');
    setText('autoPickNoTabTitle', tr.autoPickNoTabTitle || 'Open a website first');
    setText('autoPickNoTabText', tr.autoPickNoTab || 'There is no website in the active tab. Open the site you need and click the button again.');
    var _antok = $('autoPickNoTabOk'); if (_antok) _antok.textContent = tr.serverLegendGotIt || 'Got it';
    setText('checkerSiteModalTitle', tr.checkerSite || 'Target site');

    if (accountModuleTitle) accountModuleTitle.textContent = tr.account || 'Account';
    if (statusLabel) statusLabel.textContent = tr.status || 'Status';
    if (expireLabel) expireLabel.textContent = tr.expires || 'Expires';
    if (premiumKeyInput) premiumKeyInput.placeholder = tr.activationKey || 'Activation key';
    if (resetPremiumBtn) resetPremiumBtn.textContent = tr.logout || 'Logout';
    if (tgText) tgText.textContent = tr.buyPremium || 'Buy Premium: ';
    if (tabMain) tabMain.textContent = tr.tabMain || 'Main';
    if (tabPremium) {
        var _pb=tabPremium.querySelector('.news-badge');
        tabPremium.textContent=tr.tabPremium||'Premium';
        if(_pb)tabPremium.appendChild(_pb);
    }
    // [v2.6.2] One-click trial + recovery button labels
    setText('tryTrialLabel', tr.tryTrialLabel || 'Получить 3 дня Premium бесплатно');
    setText('recoverPremiumLabel', tr.recoverPremiumLabel || 'Восстановить мой Premium');
    // [v2.6.3] Main-tab trial CTA copy
    setText('trialMainCtaTitle', tr.trialMainCtaTitle || '3 дня Premium бесплатно');
    setText('trialMainCtaSub', tr.trialMainCtaSub || 'Один клик, без регистрации');
    setText('trialMainCtaBtnLabel', tr.trialMainCtaBtn || 'Активировать');
    // [v2.6.3] Timer urgency CTA + usage stats copy
    setText('timerUrgencyText', tr.timerUrgencyText || 'Не хотите попробовать?');
    setText('timerUrgencyBtnLabel', tr.timerUrgencyBtn || '3 дня Premium');
    setText('premiumBenefitsTitle',tr.premiumBenefitsTitle); setText('feat_servers',tr.feat_servers);
    setText('feat_checker',tr.feat_checker); setText('feat_exclusions',tr.feat_exclusions);
    setText('feat_unlimited',tr.feat_unlimited);
    setText('feat_theme', tr.feat_theme || '🎨 Custom color scheme');
    setText('feat_adblock', tr.feat_adblock || '🛑 Ad & tracker blocker');
    setText('feat_autoenable', tr.feat_autoenable || '🚀 Auto-enable VPN for favorite sites');
    // [v2.7.6] Backup feature item в Premium-features list
    setText('feat_backup', tr.feat_backup || '💾 Settings backup & restore');
    setText('premiumOnlyBackup', tr.premiumOnly);
    setText('checkerTitle',tr.checkerTitle);
    setText('modePingLabel',tr.modePing||'Proxy speed');
    setText('modeSiteLabel',tr.modeSite||'Site access');
    // [v2.6.2] checkerServerLabel/checkerSiteLabel removed with old single-server UI
    setText('exclusionsTitle',tr.exclusionsTitle); setText('exclusionsHint',tr.exclusionsHint);
    // [v2.8.0] feat-desc выводится на самой карточке (видим даже когда заблокировано)
    setText('exclusionsFeatureDesc', tr.exclusionsFeatureDesc || 'Black or white site list: VPN turns on only where needed.');
    setText('themeFeatureDesc', tr.themeFeatureDesc || '17 color themes for extension appearance.');
    setText('modeBlacklistLabel',tr.modeBlacklist); setText('modeWhitelistLabel',tr.modeWhitelist);
    // [v2.8.0] checker – отдельный ключ premiumOrVerifiedOnly т.к. fix также unlocks при verified-email
    setText('premiumOnlyChecker', tr.premiumOrVerifiedOnly || tr.premiumOnly);
    setText('premiumOnlyExcl',tr.premiumOnly);
    setText('premiumOnlyTheme',tr.premiumOnly);
    // [v2.8.8] bypass .ru/.рф toggle (Main tab, under server-picker) + hover-подсказка
    setText('bypassRuLabel', tr.bypassRuLabel || "Don't use VPN on .ru / .рф sites");
    var _bru = $('bypassRuRow');
    if (_bru) _bru.setAttribute('title', tr.bypassRuHint || "So Russian sites don't notice you're using a VPN. Foreign sites still go through the VPN as usual.");
    // [v3.1.1] Настройки уведомлений о конце free-сессии
    setText('notifySectionTitle', tr.notifySectionTitle || 'Notifications');
    setText('notifyEndLabel', tr.notifyEndLabel || 'Notify when the free session ends');
    setText('notifySoonLabel', tr.notifySoonLabel || 'Warn 5 minutes before the session ends');
    setText('serverListSectionTitle', tr.serverListSectionTitle || 'Server list');
    setText('siteHintsToggleLabel', tr.siteHintsToggleLabel || 'Show checked sites on hover over a server');
    setText('adBlockerTitle', tr.adBlockerTitle || '🛑 Ad & tracker blocker');
    setText('adBlockerLabel', tr.adBlockerLabel || 'Block known trackers and ads');
    setText('adBlockerHint', tr.adBlockerHint || 'Blocks ads and trackers on websites you visit.');
    setText('premiumOnlyAdBlock', tr.premiumOnly);
    // [v2.6.4] Auto-enable for sites
    setText('autoEnableTitle', tr.autoEnableTitle || '🚀 Auto-enable for sites');
    setText('autoEnableLabel', tr.autoEnableLabel || 'Enable VPN automatically');
    setText('autoEnableHint', tr.autoEnableHint || 'VPN turns on when you visit sites from the list. Disable manually.');
    setText('autoEnableModalTitle', tr.autoEnableTitle || '🚀 Auto-enable for sites');
    setText('autoEnableModalHint', tr.autoEnableModalHint || 'VPN turns on automatically when you visit any of these sites.');
    // [v2.7.1 fix F110] EN fallback symmetric с остальным кодом.
    var _oab=$('openAutoEnableModal'); if(_oab) _oab.textContent = tr.autoEnableConfigure || 'Configure list';
    setText('premiumOnlyAutoEnable', tr.premiumOnly);
    setText('themeTitle', tr.themeTitle || '🎨 Color scheme');
    setText('exclModalTitle', tr.exclusionsTitle);
    setText('exclBlackTitle', tr.modeBlacklist); setText('exclWhiteTitle', tr.modeWhitelist);
    // [v2.6.2] checkerBtn element removed (replaced by openCheckerModal launcher + checkAllBtn)
    var _ei=$('blacklistInput'); if(_ei) _ei.placeholder=tr.exclusionPlaceholder||'example.com';
    var _ei2=$('whitelistInput'); if(_ei2) _ei2.placeholder=tr.exclusionPlaceholder||'example.com';
    var _csOpt=document.querySelector('#checker-site option[value="custom"]'); if(_csOpt) _csOpt.textContent=tr.customSite||'Custom...';
    var _oeb=$('openExclusionsModal'); if(_oeb) _oeb.textContent=tr.configLists||'Configure lists';
    var _ctw=$('copyToWhiteBtn'); if(_ctw) _ctw.title=tr.copyToWhite||'Copy to whitelist';
    var _ctb=$('copyToBlackBtn'); if(_ctb) _ctb.title=tr.copyToBlack||'Copy to blacklist';
    updatePremiumTabLock();
    if (tabNews) {
        const badge = tabNews.querySelector('.news-badge');
        tabNews.textContent = tr.tabNews || 'News';
        if (badge) tabNews.appendChild(badge);
    }

    if (feedbackTextarea) feedbackTextarea.placeholder = tr.feedbackPlaceholder;
    if (emailInput) emailInput.placeholder = tr.emailOptional || tr.emailPlaceholder || 'Email (optional)';
    if (submitButton) submitButton.textContent = tr.submitFeedback;
    if (editButton) editButton.textContent = tr.editReview;

    // Re-render server list with new labels
    if (cachedProxyList && cachedProxyList.length > 0) renderProxySelect(cachedProxyList);
    updatePremiumUI();
    if (isVpnOn) setVpnFieldsLocked(true);
    updateVpnButtonUI(isVpnOn);
    // [v2.6.2 audit] Обновить текст update-баннера если он виден
    applyUpdateAvailableBanner();
    // Update excl counts
    updateExclSummary();

    // Update theme preview name
    var curTheme = THEMES.filter(function(t){return t.id===currentThemeId;})[0];
    var pn=$('themePreviewName');
    if(pn && curTheme) pn.textContent=getThemeLabel(curTheme);
    setText('themeModalTitle', tr.themeTitle ? tr.themeTitle.replace(/^🎨\s*/,'') : 'Color scheme');
    var otb=$('openThemeModal'); if(otb) otb.textContent=tr.selectTheme||'Choose theme';
    // Settings drawer
    setText('settingsTitle', tr.settingsTitle || 'Settings');
    setText('statsTitle', tr.statsTitle || 'Statistics');
    setText('statTotalTimeLabel', tr.statTotalTime || 'Total time');
    setText('statSessionsLabel', tr.statSessions || 'Sessions');
    setText('statTopServerLabel', tr.statTopServer || 'Top server');
    setText('supportModalTitle', tr.supportModalTitle || 'Support');
    setText('openSupportPageLabel', tr.openSupportPage || 'Support page');
    setText('openSupportChatLabel', tr.openSupportChat || 'Support chat');
    setText('supportFaqTitle', tr.supportFaqTitle || 'FAQ');
    setText('settingsDiagTitle', tr.settingsDiagTitle || 'Diagnostics');
    setText('settingsDiagHint', tr.settingsDiagHint || 'Run a check or copy the log for support');
    setText('fullDiagLabel', tr.fullDiagLabel || 'Full diagnostics');
    setText('diagCopyResultLabel', tr.diagCopyResultLabel || 'Copy check result');
    setText('copyDiagLabel', tr.copyDiagLabel || 'Copy log');
    setText('settingsCacheTitle', tr.settingsCacheTitle || 'Cache & data');
    setText('settingsCacheHint', tr.settingsCacheHint || 'Clearing cache may help if the extension is not working properly');
    setText('clearCacheLabel', tr.clearCache || 'Clear cache');
    var _sb=$('openSettingsBtn'); if(_sb) _sb.title=tr.settingsTitle||'Settings';
    // [v2.8.0] Account-link section + verify banner translations.
    setText('accountSection', tr.accountSection || 'Account');
    setText('accountUnlinkedHint', tr.accountUnlinkedHint || 'Not linked');
    setText('accountLinkBtnLabel', tr.accountLinkBtn || 'Link');
    setText('accountUnlinkBtnLabel', tr.accountUnlinkBtn || 'Unlink');
    setText('accountRegisterLink', tr.accountRegisterLink || 'Register in your account');
    setText('accountVerifyBanner_title', tr.accountVerifyBanner || 'Verify e-mail');
    // [v3.1.1] Текст баннера теперь переводится (раньше hardcoded ru в popup.html для всех языков).
    setText('accountVerifyBanner_text', tr.accountVerifyBannerText || 'With a verified email, sessions last 60 minutes instead of 30 – reconnects are unlimited.');
    setText('accountVerifyBanner_btn', tr.accountVerifyBtn || 'Verify');
    var _aci = $('accountCodeInput'); if (_aci && tr.accountLinkPlaceholder) _aci.setAttribute('placeholder', tr.accountLinkPlaceholder);
    // (confirmYes, confirmNo, clearCacheConfirm – used dynamically via t())
}

function setText(id, text) { const el = $(id); if (el && text) el.textContent = text; }
function getLang() { return languageSelect ? languageSelect.value : (typeof detectBrowserLang === 'function' ? detectBrowserLang() : 'en'); }
// [v2.6.4 audit] Two-tier fallback – mirrors applyTranslations Proxy logic. Without the en
// pass, non-ru/en users see hardcoded Russian fallbacks for keys not yet translated into
// their language (e.g. auto-enable, sortBy*) even when the key exists in en.
function t(key, fallback) {
    const all = cachedTranslations;
    if (!all) return fallback || key;
    const tr = all[getLang()];
    if (tr && tr[key]) return tr[key];
    const en = all['en'];
    if (en && en[key]) return en[key];
    return fallback || key;
}

// ═══ NOTIFICATIONS ═══
let statusMessageTimer = null;
function showStatusMessage(text, isError, where) {
    // where: 'vpn' → vpnMessage, 'premium' → premiumKeyMessage, default → auto-detect
    var target;
    if (where === 'vpn') {
        target = $('vpnMessage');
    } else if (where === 'premium') {
        target = $('premiumKeyMessage');
    } else {
        var premKeyMsg = $('premiumKeyMessage');
        var premTab = $('tab-premium');
        target = (premKeyMsg && premTab && premTab.classList.contains('active')) ? premKeyMsg : premiumMessage;
    }
    if (!target) return;
    if (statusMessageTimer) clearTimeout(statusMessageTimer);
    target.textContent = text;
    target.style.color = isError ? "#f44336" : "var(--accent)";
    statusMessageTimer = setTimeout(() => { target.textContent = ""; statusMessageTimer = null; }, 5000);
}

// [v2.8.1 audit] escapeHtml убран – был dead code (0 callers; renderRichTextSafe используется
// для всех translation HTML rendering).

// [v2.6.5] Render text that may contain <b>...</b> (и только их) без innerHTML –
// defense-in-depth на случай, если перевод случайно попадёт в кэш с неочищенным тегом.
// Всё остальное – plain text через createTextNode.
function renderRichTextSafe(el, tmpl) {
    if (!el) return;
    el.textContent = '';
    if (typeof tmpl !== 'string' || tmpl === '') return;
    // [v2.6.5 audit r3] `i`-flag – чтобы `<B>...</B>` (uppercase в переводе) тоже работал
    // как `<b>`, а не оставался plain text.
    const re = /<b>([\s\S]*?)<\/b>/gi;
    let last = 0, m;
    while ((m = re.exec(tmpl)) !== null) {
        if (m.index > last) el.appendChild(document.createTextNode(tmpl.slice(last, m.index)));
        const b = document.createElement('b');
        b.textContent = m[1];
        el.appendChild(b);
        last = re.lastIndex;
    }
    if (last < tmpl.length) el.appendChild(document.createTextNode(tmpl.slice(last)));
}

// [v2.6.5 audit] Для overloadConfirm (модалка «нагрузка»): в tmpl может быть `{n}` либо
// `<b id="overloadConfirmCount">{n}</b>` (hardcoded-fallback). Нормализуем, затем собираем DOM:
// один <b id="overloadConfirmCount"> вокруг числа, остальное – plain text. Защита и от XSS
// (никаких innerHTML), и от случайно-вложенных <b> (раньше fallback давал вложенные id).
function renderOverloadConfirmText(el, tmpl, count) {
    if (!el) return;
    el.textContent = '';
    if (typeof tmpl !== 'string') return;
    var plain = tmpl.replace(/<b[^>]*>\{n\}<\/b>/gi, '{n}');
    var parts = plain.split('{n}');
    if (parts[0]) el.appendChild(document.createTextNode(parts[0]));
    var b = document.createElement('b');
    b.id = 'overloadConfirmCount';
    b.textContent = String(count);
    el.appendChild(b);
    // [v2.6.5 audit r2] join – если будущий перевод внесёт два {n}, склеиваем хвост через
    // literal {n} вместо silent-drop trailing segment.
    if (parts.length > 1) {
        var tail = parts.slice(1).join('{n}');
        if (tail) el.appendChild(document.createTextNode(tail));
    }
}

// ═══ PREMIUM RECHECK ═══
function recheckPremiumFromServer() {
    if (isVpnOn) {
        chrome.storage.local.get(['isPremium', 'expiresAt', 'language'], d => {
            updatePremiumUIDisplay(!!d.isPremium, d.expiresAt, d.language || 'en');
        });
        return;
    }
    chrome.storage.local.get(['isPremium', 'premiumKey', 'language'], (data) => {
        const lang = data.language || 'en';
        if (!data.isPremium || !data.premiumKey) return;
        getDeviceId().then(deviceId => {
            apiFetch('/AnonVPN/check-key.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: data.premiumKey, device_id: deviceId }),
                signal: AbortSignal.timeout(15000)
            })
            .then(res => {
                // [v2.6.5 audit] res.ok check – 500/503/HTML-страница ошибки от CDN → JSON.parse
                // теперь пройдёт если тело валидный JSON без .valid → премиум снимается без причины.
                if (!res.ok) throw new Error('http ' + res.status);
                return res.json();
            })
            .then(result => {
                // [v2.6.5 audit r3] Строгое сравнение – compromised-сервер мог бы прислать
                // `valid: "yes"` / `valid: 1` и активировать premium через truthy-check.
                if (result.valid === true) {
                    // [v2.8.2 audit-5 F33] String() coercion на server response – symmetric с
                    // activateKey path (line ~1029). Защита от non-string type (number/null/object)
                    // от compromised server, иначе regex в updatePremiumUIDisplay throws.
                    var expAtStr = String(result.expires_at || '');
                    // [v3.1.1 audit] Type-guard expires_timestamp перед persist (инвариант CLAUDE.md:
                    // ВСЕ activation-пути валидируют Number.isFinite>0 – этот recheck-путь пропускал).
                    // Compromised/buggy сервер → string/null/Infinity не попадёт в storage.
                    var _expTs = Number(result.expires_timestamp);
                    if (!Number.isFinite(_expTs) || _expTs <= 0) { updatePremiumUIDisplay(true, expAtStr, lang); return; }
                    chrome.storage.local.set({
                        isPremium: true, expiresAt: expAtStr, expires_timestamp: _expTs
                    }, () => {
                        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                        updatePremiumUIDisplay(true, expAtStr, lang);
                        // [v2.8.5 fix] НЕ шлём 'premiumActivated'. recheckPremiumFromServer
                        // вызывается при КАЖДОМ открытии popup и доходит сюда ТОЛЬКО для
                        // уже-премиум юзера (guard выше: `if(!data.isPremium||!data.premiumKey)return`).
                        // SW-обработчик premiumActivated делает remove(['selectedProxy']) –
                        // это поведение перехода free→premium. На re-check уже-активного
                        // премиума он стирал выбранный вручную сервер на КАЖДОМ открытии popup
                        // (renderProxySelect потом видел !selected и перезаписывал авто-выбором).
                        // Премиум уже активен → ad-blocker DNR и badge уже в premium-состоянии,
                        // sync не нужен. Настоящие активации (ввод ключа, trial, recover) шлют
                        // premiumActivated сами – там wipe selectedProxy корректен.
                    });
                } else {
                    chrome.storage.local.remove(['isPremium', 'expiresAt', 'expires_timestamp', 'premiumKey'], () => {
                        const msg = result.reason === 'device_changed'
                            ? t('deviceChanged', 'Premium activated on another device')
                            : t('premiumExpired', 'Premium expired');
                        showStatusMessage(msg, true);
                        updatePremiumUIDisplay(false, null, lang);
                        loadProxies();
                    });
                }
            })
            .catch(() => {
                chrome.storage.local.get(['expiresAt'], c => { updatePremiumUIDisplay(true, c.expiresAt, lang); });
            });
        });
    });
}

// ═══ PREMIUM UI ═══
function updatePremiumUI() {
    chrome.storage.local.get(['isPremium', 'expiresAt', 'language'], d => {
        updatePremiumUIDisplay(!!d.isPremium, d.expiresAt, d.language || 'en');
    });
}

function updatePremiumUIDisplay(isPremium, expiresAt, lang) {
    timerIsPremium = !!isPremium;
    if (accountStatus) {
        // [v2.8.2 audit-7 F39] Premium – бренд, оставляем. Free → t('statusFree') для локализации.
        accountStatus.textContent = isPremium ? "Premium" : t('statusFree', 'Free');
        // [v2.8.1 audit] Free badge через CSS vars (--badge-free-bg/fg) – раньше hardcoded
        // #e8eaed/#555 нечитаемы на theme-dark. Vars defined в popup.css :root + theme-dark override.
        accountStatus.style.cssText = isPremium
            ? 'background:var(--accent-lt);color:var(--accent-dk);'
            : 'background:var(--badge-free-bg);color:var(--badge-free-fg);';
    }
    var accountBuyBtn = $('accountBuyBtn');
    if (isPremium) {
        // [v2.6.3 audit] Остановить free-countdown interval – Premium = unlimited.
        // Иначе interval продолжает тикать до естественного decrement'а до 0 (CPU waste).
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        if (premiumDateBlock) premiumDateBlock.style.display = 'flex';
        if (resetPremiumBtn) resetPremiumBtn.style.display = 'inline-block';
        if (accountBuyBtn) accountBuyBtn.style.display = 'none';
        if (expiresAt && premiumDateSpan) {
            try {
                // [v2.7.1 fix F91] Defensive UTC anchor: если сервер случайно вернул
                // expires_at без 'Z' suffix (CLAUDE.md v2.6.2 mandates gmdate('...\Z'),
                // но прошлые версии PHP backend имели bug с date(...) . 'Z'), парсинг
                // через `new Date('2026-04-21T12:00:00')` интерпретируется как ЛОКАЛЬНОЕ
                // время → display смещён на TZ-разницу. Принудительно добавляем 'Z'.
                // [v2.7.1 fix F94] Расширенный regex: 2-digit offset `+03` тоже теперь
                // matches → не append 'Z' → не получаем "+03Z" Invalid Date. F91 ловил
                // только `+03:00` / `+0300`, минус edge-cases.
                let isoStr = expiresAt.replace(' ', 'T');
                if (!/Z$|[+-]\d{2}(:?\d{2})?$/.test(isoStr)) isoStr += 'Z';
                const date = new Date(isoStr);
                if (isNaN(date.getTime())) throw new Error('invalid_date');
                const localeMap = {ru:'ru-RU',en:'en-US',zh:'zh-CN',es:'es-ES',de:'de-DE',fr:'fr-FR',pt:'pt-BR'};
                const loc = localeMap[lang] || 'en-US';
                // [v2.7.1 fix F118] Display in user's local TZ instead of UTC. Раньше
                // юзер в Moscow видел «15:00 UTC» вместо ожидаемого «18:00 MSK» – UX
                // confusion. expiresAt parsed as UTC (F91/F94), но display должен быть local.
                const dp = date.toLocaleDateString(loc, { day: 'numeric', month: 'long', year: 'numeric' });
                const tp = date.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit', hour12: false });
                premiumDateSpan.textContent = dp.replace(/\s*г\.?\s*$/, '') + ', ' + tp;
            } catch(e) { premiumDateSpan.textContent = expiresAt; }
        }
        updateTimerDisplay(999999);
    } else {
        if (premiumDateBlock) premiumDateBlock.style.display = 'none';
        if (resetPremiumBtn) resetPremiumBtn.style.display = 'none';
        if (accountBuyBtn) accountBuyBtn.style.display = 'inline-block';
    }
    // [v2.6.3] Обновить Trial-CTA/badge при любом изменении premium-state
    updateTrialMainCta(isPremium);
}

// [v2.6.3] Module-var: trial уже исчерпан (trialAlreadyIssued или isPremium).
// Блокирует ВСЕ trial-CTA (main card, shimmer, urgency, stats).
// [v2.8.4] Возвращает локализованный текст для пустого списка серверов с детализацией причины:
//  navigator.onLine === false ИЛИ proxyListFetchError === 'network' → «Нет интернета»
//  proxyListFetchError === 'server' → «Сервер недоступен»
//  иначе (свежая установка ещё ни разу не fetch'ала) → общий «Нет серверов»
function noServersText() {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        return t('noServersOffline', 'No internet connection. Check your connection and try again.');
    }
    if (_proxyListFetchError === 'network') {
        return t('noServersOffline', 'No internet connection. Check your connection and try again.');
    }
    if (_proxyListFetchError === 'server') {
        return t('noServersServer', 'Server temporarily unavailable. Try again in a minute.');
    }
    return t('noServers', 'No servers available. Try again later.');
}

// trialCtaDismissed блокирует ТОЛЬКО main card + shimmer – контекстные
// CTA (urgency при <=10 мин, stats при активном использовании) продолжают работать.
// [v2.6.3 audit] null = ещё не проверено. updateTimerUrgency показывает urgency ТОЛЬКО
// при явном === false – защита от micro-flash у trialAlreadyIssued-юзеров до первого
// updateTrialMainCta (async storage read).
var _trialExhausted = null;

// [v2.6.3] Main-tab Trial CTA – главная точка конверсии free→premium.
// Card + shimmer скрываются при dismiss ИЛИ exhaustion. Urgency/Stats – только exhaustion.
function updateTrialMainCta(isPremium) {
    var cta = $('trialMainCta');
    var tabPrem = $('tabPremium');
    updateCommunityChatVisibility(); // [v3.1.7] чат виден только тем, кто насидел с ВПН ≥1ч (независимо от premium)
    if (isPremium) {
        _trialExhausted = true; // premium – никаких trial-CTA
        // [v2.7.0 fix F22] Clear free-tier countdown immediately – иначе interval
        // продолжает тикать ~100ms до того как updatePremiumUIDisplay вызовет clearInterval.
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        if (cta) cta.hidden = true;
        if (tabPrem) tabPrem.classList.remove('tab-btn-goldshine');
        updateTimerUrgency();
        updateUsageStatsHint(true);
        return;
    }
    chrome.storage.local.get(['trialCtaDismissed', 'trialAlreadyIssued'], function(d){
        var dismissed = !!d.trialCtaDismissed;
        var exhausted = !!d.trialAlreadyIssued;
        _trialExhausted = exhausted;
        // [v3.0.0] Trial исчерпан → скрываем и premium-tab кнопку #tryTrialBtn (симметрично
        // main-CTA). Вызывается при загрузке popup и в callback всех 3 already_issued-веток,
        // поэтому одна точка покрывает и «после сообщения», и persistence при reopen.
        var _ttBtn = $('tryTrialBtn');
        if (_ttBtn && exhausted) _ttBtn.style.display = 'none';
        var hideMainCta = dismissed || exhausted;
        if (cta) cta.hidden = hideMainCta;
        if (tabPrem) tabPrem.classList.toggle('tab-btn-goldshine', !hideMainCta);
        updateTimerUrgency();
        updateUsageStatsHint(false);
    });
}

// [v2.6.3] Urgency CTA под таймером – контекстная: показывается только при timer<=10 мин.
// Игнорирует trialCtaDismissed (юзер хочет видеть напоминание в момент истечения),
// скрывается только при exhaustion.
var _currentTimerSecs = 0;
function updateTimerUrgency() {
    var urg = $('timerUrgency');
    if (!urg) return;
    var show = !timerIsPremium
        && _currentTimerSecs > 0
        && _currentTimerSecs <= 600
        && _trialExhausted === false; // явно false, не null
    urg.hidden = !show;
}

// [v2.6.3] Usage stats hint – контекстная: показывается только активным free-юзерам.
// Тоже игнорирует dismiss (dismiss = "позже", а статистика актуальна независимо).
// [audit] Скрываем пока _trialExhausted === null (storage ещё не прочитан) –
// pessimistic default защищает от flash у exhausted-юзеров.
function updateUsageStatsHint(isPremium) {
    var el = $('usageStatsHint');
    if (!el) return;
    if (isPremium || _trialExhausted !== false) { el.hidden = true; return; }
    chrome.storage.local.get(['vpnStats'], function(d){
        var stats = d.vpnStats || {};
        var daily = stats.dailySeconds || {};
        var cutoff = new Date(Date.now() - 30*86400000).toISOString().split('T')[0];
        var sec30 = 0;
        for (var date in daily) { if (date >= cutoff) sec30 += daily[date] || 0; }
        // Показываем только если юзер реально пользуется (>= 1 час за 30 дней)
        if (sec30 < 3600) { el.hidden = true; return; }
        var hours = Math.max(1, Math.round(sec30 / 3600));
        var reconnects = Math.max(1, Math.ceil(sec30 / 3600)); // ~1 переподключение на каждый час
        var txt = $('usageStatsText');
        if (txt) {
            var tpl = t('usageStatsText', 'За 30 дней: <b>{h} ч</b> VPN, <b>{r}</b> переподключений из-за лимита 60 мин');
            // [v2.6.5 audit] renderRichTextSafe вместо innerHTML – CWS-сканеры флагают
            // `innerHTML = <translation>` даже для bundled-строк.
            renderRichTextSafe(txt, tpl.replace('{h}', String(hours)).replace('{r}', String(reconnects)));
        }
        el.hidden = false;
    });
}

// [v3.1.7] Кнопка «Чат пользователей» видна: Premium — сразу (оплатил, не «сброд»); free — только
// тем, кто суммарно провёл с включённым ВПН ≥1 час (vpnStats.totalSeconds). Отсекает случайных/абузеров.
// Скрыта по умолчанию (inline display:none в HTML) до подтверждения — без вспышки у новичков.
function updateCommunityChatVisibility(){
    var el = $('communityChatBtn'); if (!el) return;
    chrome.storage.local.get(['vpnStats', 'isPremium'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) return;
        var s = (d.vpnStats && typeof d.vpnStats === 'object' && !Array.isArray(d.vpnStats)) ? d.vpnStats : {};
        var total = Number(s.totalSeconds || 0) || 0;
        el.style.display = (d.isPremium || total >= 3600) ? '' : 'none';
    });
}

// ═══ ACTIVATE KEY ═══
// [v2.7.1 fix F104] Enter в input триггерит activate – input не в <form>, без этого
// Enter был бы no-op и юзер должен был бы тянуться к кнопке мышью.
premiumKeyInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !activateBtn?.disabled) {
        e.preventDefault();
        activateBtn?.click();
    }
});
// [v2.7.5 audit r3] In-flight guard – race против concurrent activate clicks.
// Симметрично _trialInFlight/_recoverInFlight в SW. Без него double-click шлёт
// 2 параллельных fetch – server idempotent OK, но client UX confusing.
let _activateInFlight = false;
activateBtn?.addEventListener('click', () => {
    // [v2.7.1 fix F113] Раньше silent return – после F104 user pressed Enter и
    // не получал feedback. Показываем status, иначе UX тупик.
    if (isVpnOn) {
        showStatusMessage(t('disableVpnFirst', 'Disable VPN to manage premium'), true);
        return;
    }
    if (_activateInFlight) return;
    const key = premiumKeyInput.value.trim();
    if (key.length < 5) { showStatusMessage(t('keyTooShort', 'Key is too short'), true); return; }
    // [v2.7.5 audit r3] Format validation – premium keys обычно alphanumeric+hyphens
    // 16-64 chars. Раньше только length>=5, server rejected на network round-trip.
    // Pre-validate улучшает UX (мгновенный feedback на typo) + reduces server load.
    if (!/^[A-Za-z0-9-]{16,64}$/.test(key)) {
        showStatusMessage(t('keyTooShort', 'Invalid key format'), true);
        return;
    }
    _activateInFlight = true;
    activateBtn.disabled = true;
    getDeviceId().then(deviceId => {
        apiFetch('/AnonVPN/check-key.php', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, device_id: deviceId, activate: true }),
            signal: AbortSignal.timeout(15000)
        })
        .then(res => {
            // [v2.6.5 audit] res.ok check – см. комментарий в recheckPremiumFromServer.
            if (!res.ok) throw new Error('http ' + res.status);
            return res.json();
        })
        .then(data => {
            // [v2.6.5 audit r3] Строгое сравнение – см. коммент выше.
            if (data.valid === true) {
                // [v2.6.7 audit] Defense-in-depth: strict type-check expires_timestamp.
                // Compromised-server мог бы прислать "infinity"/строку – тогда NaN-сравнения в
                // checkPremiumExpiration дают premium без истечения. Режектим битый ответ.
                const expTs = Number(data.expires_timestamp);
                if (!Number.isFinite(expTs) || expTs <= 0) {
                    showStatusMessage(t('invalidKey', 'Invalid key'), true);
                    return;
                }
                // [v2.7.1 fix F108] Quota-guard на popup-side activateKey path –
                // symmetric с F90 в SW recoverPremium/requestTrial. Callback-style
                // .set без try/catch + chrome.runtime.lastError неловимый throw на
                // QuotaExceededError → callback не fires → UI обновляется БЕЗ persist
                // → premium теряется на SW restart. Switch на await + try/catch.
                (async () => {
                    try {
                        await chrome.storage.local.set({
                            isPremium: true, premiumKey: key,
                            expiresAt: String(data.expires_at || ''), expires_timestamp: expTs
                        });
                        showStatusMessage(t('activated', 'Activated!'));
                        updatePremiumUI(); updatePremiumTabLock();
                        chrome.runtime.sendMessage({ action: 'premiumActivated' }).catch(()=>{});
                        if (!isVpnOn) loadProxies();
                    } catch (e) {
                        showStatusMessage(t('storageLimitExceeded', 'Storage full. Clear cache in Settings → Diagnostics.'), true);
                    }
                })();
            } else {
                const reasonMessages = {
                'key_not_found_or_expired': t('keyNotFoundOrExpired', 'Key not found or expired'),
                'device_changed': t('deviceChanged', 'Premium activated on another device')
            };
            showStatusMessage(reasonMessages[data.reason] || t('invalidKey', 'Invalid key'), true);
            }
        })
        .catch(() => { showStatusMessage(t('connectionError', 'Connection error'), true); })
        .finally(() => {
            activateBtn.disabled = false;
            _activateInFlight = false;  // [v2.7.5 audit r3] release in-flight mutex
        });
    }).catch(function(e){
        // [v2.7.4 audit r4] getDeviceId() rejection (rare storage failure / crypto fail) –
        // без .catch button stuck disabled forever (нет finally на верхнем уровне).
        console.warn('[AnonVPN] getDeviceId failed in activateKey:', e);
        activateBtn.disabled = false;
        _activateInFlight = false;  // [v2.7.5 audit r3] release in-flight mutex
        showStatusMessage(t('connectionError', 'Connection error'), true);
    });
});

// [v2.6.2] One-click trial activation – отправляет запрос в SW, получает 3 дня Premium.
// [v2.6.3] isVpnOn check убран: SW теперь бесшовно активирует trial при VPN on
// (см. requestTrial handler – `wasOn` logic, не трогает selectedProxy и не переподключается).
$('tryTrialBtn')?.addEventListener('click', function(){
    var btn = this;
    var lbl = $('tryTrialLabel');
    var origLbl = lbl ? lbl.textContent : '';
    btn.disabled = true;
    if (lbl) lbl.textContent = t('trialActivating', 'Активируем...');

    // [v2.7.1 fix F119] Safety timeout – если SW crash или callback never fires,
    // button stuck disabled forever. 20s safety net (15s SW timeout + buffer).
    var _trialResponded = false;
    // [v2.8.2 audit-3 F20] Расширен с 20s → 35s. На медленных GPU collectHardwareFp + AudioContext
    // могут занять до 18s. SW fetch timeout 15s after FP. Total worst-case ~33s. Старые 20s резали
    // активный flow → trial выдавался на сервере но UI показывал «Ошибка соединения». User confused.
    var _trialResetTimer = setTimeout(function(){
        if (_trialResponded) return;
        _trialResponded = true;
        btn.disabled = false;
        if (lbl) lbl.textContent = origLbl;
        showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'premium');
    }, 35000);
    // [v2.8.2 Этап Б] Сбор client FP (Canvas+WebGL+Audio+...) для anti-abuse в SW.
    // Async: ждём FP, потом отправляем. SW при empty FP fallback'ает на proto=1.
    getClientFp().then(function(_clientFp){
    chrome.runtime.sendMessage({ action: 'requestTrial', clientFp: _clientFp || '' }, function(res){
        if (_trialResponded) return;
        _trialResponded = true;
        clearTimeout(_trialResetTimer);
        btn.disabled = false;
        if (lbl) lbl.textContent = origLbl;

        if (chrome.runtime.lastError || !res) {
            showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'premium');
            return;
        }

        if (!res.ok) {
            var reason = res.reason || 'error';
            var msg;
            var showTgHint = false;
            if (reason === 'already_issued') {
                msg = t('trialAlreadyIssued', 'Trial уже использован. Купите Premium для продолжения.');
                // [v2.6.3] Скрываем Main-CTA навсегда – юзер уже использовал свой trial
                chrome.storage.local.set({ trialAlreadyIssued: true }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;} updateTrialMainCta(false); });
            } else if (reason === 'datacenter_ip' || reason === 'suspicious' || reason === 'subnet_rate_limit') {
                msg = t('trialViaTg', 'Получите trial через Telegram-бота');
                showTgHint = true;
            } else if (reason === 'network_error') {
                msg = t('trialNetworkError', 'Нет связи. Попробуйте позже');
            } else if (reason === 'clock') {
                msg = t('trialClockError', 'Часы расходятся с сервером. Проверьте время');
            } else if (reason === 'storage_quota_exceeded') {
                // [v2.8.0] Симметрия с recoverPremium handler – SW returns этот reason при
                // storage.set rejection. Раньше попадал в else «Ошибка активации», что misleading.
                msg = t('storageLimitExceeded', 'Хранилище переполнено. Очистите кэш в Настройках.');
            } else if (reason === 'bad_server_response') {
                // [v2.8.0] Symmetric с recoverPremium – server returned malformed/incomplete response
                msg = t('trialServerError', 'Ошибка активации. Попробуйте позже');
            } else if (reason === 'vpn_conflict') {
                // [v2.8.2 audit-2] SW отказал из-за активного другого VPN – symmetric с toggleProxy handler.
                msg = t('vpnConflictBlocked', 'Disable other VPN extensions first');
            } else {
                msg = t('trialServerError', 'Ошибка активации. Попробуйте позже');
            }
            showStatusMessage(msg, true, 'premium');
            // Если рекомендован TG – подчёркиваем fallback-ссылку
            if (showTgHint) {
                var tgLink = $('premiumTrialHint');
                if (tgLink) {
                    tgLink.style.background = 'var(--accent-lt)';
                    tgLink.style.borderColor = 'var(--accent)';
                    tgLink.style.fontWeight = '700';
                }
            }
            return;
        }
        // Успех: SW broadcast 'premiumActivated' → popup listener сделает loadProxies,
        // тут только status message + быстрый UI sync (updatePremiumUI/Tab – очень дёшево).
        var days = res.days_granted || 3;
        showStatusMessage('🎉 ' + (t('trialActivated', 'Premium активирован на {d} дн.') || '').replace('{d}', days), false, 'premium');
        updatePremiumUI();
        updatePremiumTabLock();
        hideSessionExpiredBanner(true);
    });
    }); // close getClientFp().then
});

// [v2.6.3] Main-tab Trial CTA handler – отдельный от премиум-таб кнопки, но делегирует на тот же flow.
// UX: click → activating... → success hides CTA, fail либо показывает ошибку, либо ставит trialAlreadyIssued
// и скрывает CTA навсегда. isVpnOn check убран – SW делает бесшовную активацию при VPN on.
$('trialMainCtaBtn')?.addEventListener('click', function(){
    var btn = this;
    var lbl = $('trialMainCtaBtnLabel');
    var origLbl = lbl ? lbl.textContent : '';
    btn.disabled = true;
    if (lbl) lbl.textContent = t('trialActivating', 'Активируем...');
    // [v2.7.6 audit Pass13+14] F119-pattern: 20sec safety timeout на случай SW kill mid-flight.
    // Без guard'а callback не сработает → btn навсегда disabled. Identical к tryTrialBtn.
    // Pass14 fix: clearTimeout + status message – симметрия с tryTrialBtn line 928-934.
    var _trialMainResponded = false;
    // [v2.8.2 audit-3 F20] См. комментарий в tryTrialBtn – symmetric extension до 35s.
    var _trialMainResetTimer = setTimeout(function(){
        if (_trialMainResponded) return;
        _trialMainResponded = true;
        btn.disabled = false;
        if (lbl) lbl.textContent = origLbl;
        showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'main');
    }, 35000);

    // [v2.8.2 Этап Б] Сбор client FP (Canvas+WebGL+Audio+...) для anti-abuse в SW.
    // Async: ждём FP, потом отправляем. SW при empty FP fallback'ает на proto=1.
    getClientFp().then(function(_clientFp){
    chrome.runtime.sendMessage({ action: 'requestTrial', clientFp: _clientFp || '' }, function(res){
        if (_trialMainResponded) return;
        _trialMainResponded = true;
        clearTimeout(_trialMainResetTimer);
        btn.disabled = false;
        if (lbl) lbl.textContent = origLbl;

        if (chrome.runtime.lastError || !res) {
            showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'main');
            return;
        }
        if (!res.ok) {
            var reason = res.reason || 'error';
            var msg;
            if (reason === 'already_issued') {
                msg = t('trialAlreadyIssued', 'Trial уже использован. Купите Premium для продолжения.');
                // Больше не показываем CTA – юзер уже использовал свой шанс
                chrome.storage.local.set({ trialAlreadyIssued: true }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                    updateTrialMainCta(false);
                });
            } else if (reason === 'datacenter_ip' || reason === 'suspicious' || reason === 'subnet_rate_limit') {
                msg = t('trialViaTg', 'Получите trial через Telegram-бота');
            } else if (reason === 'network_error') {
                msg = t('trialNetworkError', 'Нет связи. Попробуйте позже');
            } else if (reason === 'clock') {
                msg = t('trialClockError', 'Часы расходятся с сервером. Проверьте время');
            } else if (reason === 'vpn_conflict') {
                msg = t('vpnConflictBlocked', 'Disable other VPN extensions first');
            } else {
                msg = t('trialServerError', 'Ошибка активации. Попробуйте позже');
            }
            showStatusMessage(msg, true, 'main');
            return;
        }
        var days = res.days_granted || 3;
        showStatusMessage('🎉 ' + (t('trialActivated', 'Premium активирован на {d} дн.') || '').replace('{d}', days), false, 'main');
        updatePremiumUI();
        updatePremiumTabLock();
        hideSessionExpiredBanner(true);
    });
    }); // close getClientFp().then
});

// [v2.6.3] Dismiss: юзер не хочет trial сейчас – прячем CTA и запоминаем решение.
// Badge на табе Премиум тоже пропадает. Не показываем повторно (только после reinstall).
$('trialMainCtaDismiss')?.addEventListener('click', function(e){
    e.stopPropagation();
    chrome.storage.local.set({ trialCtaDismissed: true }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
        updateTrialMainCta(false);
    });
});

// [v2.6.3] Urgency CTA под таймером – появляется ТОЛЬКО когда VPN on (<=10 мин до конца).
// В отличие от других trial-CTA НЕ требуем выключать VPN: SW сам переподключит к премиум-серверу
// в рамках activation flow (~1 сек). Суть urgency = "не хочу reconnect'а через 60 мин" → бесшовный переход.
$('timerUrgencyBtn')?.addEventListener('click', function(){
    var btn = this;
    btn.disabled = true;
    // [v2.7.6 audit Pass13+14] F119-pattern safety timeout – symmetric с tryTrialBtn.
    // Pass14 fix: clearTimeout + status message – без них cleared timeout оставался armed
    // в очереди event loop'а до 20с после успешного callback'а.
    var _timerUrgResponded = false;
    // [v2.8.2 audit-3 F20] См. комментарий в tryTrialBtn – extension до 35s.
    var _timerUrgResetTimer = setTimeout(function(){
        if (_timerUrgResponded) return;
        _timerUrgResponded = true;
        btn.disabled = false;
        showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'main');
    }, 35000);
    // [v2.8.2 Этап Б] Сбор client FP (Canvas+WebGL+Audio+...) для anti-abuse в SW.
    // Async: ждём FP, потом отправляем. SW при empty FP fallback'ает на proto=1.
    getClientFp().then(function(_clientFp){
    chrome.runtime.sendMessage({ action: 'requestTrial', clientFp: _clientFp || '' }, function(res){
        if (_timerUrgResponded) return;
        _timerUrgResponded = true;
        clearTimeout(_timerUrgResetTimer);
        btn.disabled = false;
        if (chrome.runtime.lastError || !res) {
            showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'main'); return;
        }
        if (!res.ok) {
            var reason = res.reason || 'error';
            if (reason === 'already_issued') {
                chrome.storage.local.set({ trialAlreadyIssued: true }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;} updateTrialMainCta(false); });
                showStatusMessage(t('trialAlreadyIssued','Trial уже использован. Купите Premium.'), true, 'main');
            } else if (reason === 'vpn_conflict') {
                showStatusMessage(t('vpnConflictBlocked','Disable other VPN extensions first'), true, 'main');
            } else {
                showStatusMessage(t('trialServerError','Ошибка активации. Попробуйте позже'), true, 'main');
            }
            return;
        }
        var days = res.days_granted || 3;
        showStatusMessage('🎉 ' + (t('trialActivated','Premium активирован на {d} дн.')||'').replace('{d}', days), false, 'main');
        updatePremiumUI();
        updatePremiumTabLock();
        hideSessionExpiredBanner(true);
    });
    }); // close getClientFp().then
});

// [v2.6.3] Usage stats – клик ведёт на Premium-таб (там Trial CTA, фичи, и кнопка купить).
// Не активируем trial сразу – юзер может хотеть разобраться.
$('usageStatsHint')?.addEventListener('click', function(){
    var tabBtn = $('tabPremium');
    if (tabBtn) tabBtn.click();
});

// [v2.6.3] Clickable Premium locks – каждый lock-оверлей на Premium-табе открывает upsell-страницу.
// Контекстная sell: юзер кликнул на lock конкретной фичи → в upsell может увидеть её описание.
// [v2.8.0 a11y] role="button" + tabindex + keydown – keyboard-only юзер мог только с мышью открыть
// upsell. Screen-reader теперь announce'ит как button. Enter/Space – также активируют.
['checkerLock','exclusionsLock','adBlockerLock','autoEnableLock','themeLock','backupLock'].forEach(function(id){
    var el = $(id);
    if (!el) return;
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    function activate(){
        var medium = 'lock_' + id.replace(/Lock$/, '').toLowerCase();
        chrome.tabs.create({ url: upsellUrl(medium) }).catch(() => {});
    }
    el.addEventListener('click', activate);
    el.addEventListener('keydown', function(e){
        // [v2.8.0] stopPropagation для consistency с codebase pattern (modal-close pattern)
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); activate(); }
    });
});

// Reset premium features to defaults
function resetPremiumFeatures(){
    applyTheme('default');
    chrome.storage.local.set({colorTheme:'default', excludedDomains:[], exclusionsMode:'blacklist'}, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
}

// [v2.6.2] Logout с confirm-модалкой – защита от случайного клика при активном Premium.
// [v2.7.1 fix F112] Добавлен `proxyListFetchAt` (v2.6.9 TTL) – без него после logout
// stale timestamp блокировал свежий fetch на 5 мин (cache-hit + TTL gate). Switch на
// async/await с try/catch – callback-style глотал quota errors.
async function _doLogout() {
    try {
        // [v2.7.6 audit Pass13] Добавлен `lastHeartbeatAt` (v2.6.10 TTL) – symmetric с
        // proxyListFetchAt (F112). Без него stale heartbeat-timestamp переживал logout
        // → следующая premium-активация после re-login блокировала первый heartbeat
        // на ~4.5 мин (TTL guard видел свежий timestamp от прошлого юзера).
        // [v2.8.5 fix] accountVerified/accountEmail НЕ удаляем при logout из Premium.
        // Привязка почты – ОТДЕЛЬНАЯ функция (даёт 60-мин сессии бесплатно), не зависит
        // от Premium. Раньше [v2.8.0 audit r2] их сносили здесь → после истечения Premium
        // почта «отвязывалась», сессии падали 60→30 мин. Отвязка почты – только явной
        // кнопкой «Отвязать» (unlinkAccount), которая ещё и дёргает server-side endpoint.
        await chrome.storage.local.remove(['isPremium', 'expiresAt', 'expires_timestamp', 'premiumKey', 'selectedProxy', 'proxyList', 'proxyListEnc', 'proxyListFetchAt', 'lastHeartbeatAt']);
    } catch (e) {
        showStatusMessage(t('storageLimitExceeded', 'Storage full. Clear cache in Settings → Diagnostics.'), true);
        return;
    }
    updatePremiumUI(); updatePremiumTabLock();
    resetPremiumFeatures();
    // [v2.6.6 audit] null-guard для консистентности с остальными clearInterval-сайтами (575, 1631, 1636)
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    const timerEl = $("timer");
    if (timerEl) { timerEl.textContent = ''; timerEl.classList.remove("timer-active"); }
    // [v2.8.1 audit] Correct message name – это logout, не activation. SW handler для
    // premiumDeactivated revoke'ит DNR ad-blocker; storage.onChanged тоже подхватит, но
    // explicit message – defense in depth.
    chrome.runtime.sendMessage({ action: 'premiumDeactivated', reason: 'logout' }).catch(()=>{});
    if (!isVpnOn) loadProxies();
    showStatusMessage(t('loggedOut', 'Logged out'));
}
resetPremiumBtn?.addEventListener('click', () => {
    if (isVpnOn) return;
    // Показываем confirm только если premium реально активен (есть expiresAt)
    chrome.storage.local.get(['isPremium', 'expiresAt', 'language'], function(d){
        if (!d.isPremium || !d.expiresAt) { _doLogout(); return; }
        var titleEl = $('logoutConfirmTitle');
        var textEl = $('logoutConfirmText');
        var noBtn = $('logoutConfirmNo');
        var yesBtn = $('logoutConfirmYes');
        var expEl = $('logoutConfirmExpires');
        if (titleEl) titleEl.textContent = t('logoutConfirmTitle', 'Точно выйти?');
        if (noBtn) noBtn.textContent = t('overloadConfirmNo', 'Отмена');
        if (yesBtn) yesBtn.textContent = t('logoutConfirmYes', 'Выйти');
        // Format expires date
        try {
            // [v2.7.4 audit r4] Z-suffix validation (parity с updatePremiumUIDisplay F94).
            // Если server вернул "2026-04-25T12:00:00" без Z – JS парсит как local TZ.
            // Premium expires display showed wrong time на user TZ ≠ server TZ.
            var rawExp = String(d.expiresAt || '').replace(' ', 'T');
            if (rawExp && !/Z$|[+-]\d{2}(:?\d{2})?$/.test(rawExp)) rawExp += 'Z';
            var date = new Date(rawExp);
            // [v2.7.5 audit r3] localeMap consistent с updatePremiumUIDisplay (popup.js:692).
            // Раньше hardcoded ru-RU/en-US – для 46 langs Premium expiry display падал в en-US.
            var localeMap = {ru:'ru-RU',en:'en-US',zh:'zh-CN',es:'es-ES',de:'de-DE',fr:'fr-FR',pt:'pt-BR'};
            var loc = localeMap[d.language] || (d.language || 'en');
            // [v2.7.1 fix F118] См. updatePremiumUIDisplay – display в local TZ.
            var dp = date.toLocaleDateString(loc, { day: 'numeric', month: 'long', year: 'numeric' });
            var tp = date.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit', hour12: false });
            if (expEl) expEl.textContent = dp.replace(/\s*г\.?\s*$/, '') + ', ' + tp;
        } catch(e) { if (expEl) expEl.textContent = d.expiresAt; }
        // Bind handlers (single-shot replace)
        if (yesBtn) yesBtn.onclick = function(){
            closeModal('logoutConfirmModal');
            // [v2.8.5 fix R5] Перепроверка VPN – юзер мог включить VPN (Alt+Shift+V)
            // пока модалка открыта; logout при активном VPN оставляет рассинхрон
            // (proxyEnabled=true, а selectedProxy/isPremium стёрты). Симметрично
            // проверке при клике (выше) и recoverPremiumBtn.
            if (isVpnOn) { showStatusMessage(t('vpnDisabledHint', 'Отключите VPN'), true, 'premium'); return; }
            _doLogout();
        };
        if (noBtn) noBtn.onclick = function(){ closeModal('logoutConfirmModal'); };
        openModal('logoutConfirmModal');
    });
});

// [v2.6.2] Recovery – восстанавливает активный ключ из БД для случая "случайно вышел".
$('recoverPremiumBtn')?.addEventListener('click', function(){
    if (isVpnOn) {
        showStatusMessage(t('vpnDisabledHint', 'Отключите VPN для восстановления'), true, 'premium');
        return;
    }
    var btn = this;
    var lbl = $('recoverPremiumLabel');
    var orig = lbl ? lbl.textContent : '';
    btn.disabled = true;
    if (lbl) lbl.textContent = t('recovering', 'Проверяем...');

    // [v2.7.1 fix F119] Safety timeout – see tryTrialBtn handler.
    var _recoverResponded = false;
    // [v2.8.2 audit-3 F20] См. комментарий в tryTrialBtn – extension до 35s для FP collect.
    var _recoverResetTimer = setTimeout(function(){
        if (_recoverResponded) return;
        _recoverResponded = true;
        btn.disabled = false;
        if (lbl) lbl.textContent = orig;
        showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'premium');
    }, 35000);
    // [v2.8.2 audit-2 F7] Симметрия с requestTrial: собрать hardware FP перед recover.
    // SW handler принимает clientFp в payload, шлёт proto=2 → server использует Tier 1.5
    // (recovery by client_fp_hash) если uid не нашёл активный Premium.
    getClientFp().then(function(_clientFp){
    chrome.runtime.sendMessage({ action: 'recoverPremium', clientFp: _clientFp || '' }, function(res){
        if (_recoverResponded) return;
        _recoverResponded = true;
        clearTimeout(_recoverResetTimer);
        btn.disabled = false;
        if (lbl) lbl.textContent = orig;

        if (chrome.runtime.lastError || !res) {
            showStatusMessage(t('connectionError', 'Ошибка соединения'), true, 'premium');
            return;
        }
        if (!res.ok) {
            var reason = res.reason || 'error';
            var msg;
            if (reason === 'no_active_premium') {
                msg = t('recoverNoActive', 'Активного Premium не найдено для этого устройства');
            } else if (reason === 'ambiguous_fingerprint') {
                msg = t('recoverAmbiguous', 'Несколько устройств в вашей сети использовали Premium. Восстановление через поддержку.');
            } else if (reason === 'network_error') {
                msg = t('trialNetworkError', 'Нет связи. Попробуйте позже');
            } else if (reason === 'clock') {
                msg = t('trialClockError', 'Часы расходятся с сервером. Проверьте время');
            } else if (reason === 'storage_quota_exceeded') {
                // [v2.8.0] SW reports `storage_quota_exceeded` – раньше попадало в else-fallback
                // как «Не удалось восстановить» что misleading. Reuse существующий ключ.
                msg = t('storageLimitExceeded', 'Хранилище переполнено. Очистите кэш в Настройках.');
            } else if (reason === 'bad_server_response') {
                // [v2.8.0] Server returned malformed/incomplete response – generic «попробуйте позже»
                msg = t('recoverError', 'Не удалось восстановить. Попробуйте позже');
            } else if (reason === 'vpn_conflict') {
                // [v2.8.2 audit-2] symmetric с trial.
                msg = t('vpnConflictBlocked', 'Disable other VPN extensions first');
            } else {
                msg = t('recoverError', 'Не удалось восстановить. Попробуйте позже');
            }
            showStatusMessage(msg, true, 'premium');
            return;
        }
        // SW broadcast 'premiumActivated' → popup listener сделает loadProxies сам.
        showStatusMessage('🔓 ' + t('recoverSuccess', 'Premium восстановлен'), false, 'premium');
        updatePremiumUI();
        updatePremiumTabLock();
        hideSessionExpiredBanner(true);
    });
    }); // close getClientFp().then
});

// ═══ FEEDBACK ═══
chrome.storage.local.get(['feedback_text', 'feedback_email', 'feedback_rating'], fbData => {
    if (fbData.feedback_text) feedbackTextarea.value = fbData.feedback_text;
    if (fbData.feedback_email) emailInput.value = fbData.feedback_email;
    if (fbData.feedback_rating) {
        ratingInput.value = fbData.feedback_rating;
        setStars(fbData.feedback_rating);
        if (fbData.feedback_rating <= 3) { feedbackForm.style.display = "block"; submitButton.style.display = "none"; editButton.style.display = "inline-block"; toggleForm(true); }
    }
});

stars.forEach((star, index) => {
    star.addEventListener("mouseover", () => { stars.forEach((s, i) => s.classList.toggle("hover", i <= index)); });
    star.addEventListener("mouseout", () => { stars.forEach(s => s.classList.remove("hover")); });
    const activate = () => {
        const value = index + 1;
        ratingInput.value = value;
        chrome.storage.local.set({ feedback_rating: value }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);}});
        stars.forEach((s, i) => s.setAttribute('aria-checked', i === index ? 'true' : 'false'));
        setStars(value);
        if (value <= 3) { feedbackForm.style.display = "block"; submitButton.style.display = "inline-block"; editButton.style.display = "none"; toggleForm(false); }
        else { window.open("https://chromewebstore.google.com/detail/pieoffaiheelaipjennepjbhnbdhcfck/reviews", "_blank", "noopener,noreferrer"); }
    };
    star.addEventListener("click", activate);
    // [v2.7.3] Клавиатурная навигация по radiogroup: Enter/Space выбирает,
    // ArrowLeft/Right перемещает focus + tabindex (roving tabindex, ARIA pattern).
    star.addEventListener("keydown", (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); return; }
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            const next = stars[Math.min(index + 1, stars.length - 1)];
            stars.forEach(s => s.setAttribute('tabindex', '-1'));
            next.setAttribute('tabindex', '0');
            next.focus();
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            const prev = stars[Math.max(index - 1, 0)];
            stars.forEach(s => s.setAttribute('tabindex', '-1'));
            prev.setAttribute('tabindex', '0');
            prev.focus();
        }
    });
});

// [v2.7.6] Собираем расширенный контекст для саппорта – версия, premium-state, vpn-state,
// recent diag log, locale, user-agent. Без этого support получает голый feedback-text и
// должен ходить вручную выяснять что у юзера. Cap 8000 байт на сервере, JSON-validation.
// Privacy: НЕ собираем IP (сервер сам видит из request), browsing history, cookies. uid –
// ID для tracking ответов, не identifying real user.
function _collectFeedbackMetadata() {
    return new Promise(function(resolve){
        try {
            chrome.storage.local.get(['uid','isPremium','trialAlreadyIssued','language','proxyEnabled','selectedProxy','vpnStats','autoEnableEnabled','autoEnableDomains','adBlockerEnabled','exclusionsMode','blacklistDomains','whitelistDomains','colorTheme','autoSelectScope','vpnConflictList','diagnosticLog','expires_timestamp'], function(d){
                try {
                    var activeTabBtn = document.querySelector('.tab-btn.active');
                    var activeTab = (activeTabBtn && activeTabBtn.dataset && activeTabBtn.dataset.tab) || 'main';
                    var server = '';
                    if (d.proxyEnabled && d.selectedProxy) {
                        server = String(d.selectedProxy.host || '') + ':' + String(d.selectedProxy.port || '');
                    }
                    var stats = d.vpnStats || {};
                    var tzName = '';
                    try { tzName = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch(_) {}
                    var meta = {
                        uid: String(d.uid || '').slice(0, 64),
                        version: chrome.runtime.getManifest().version,
                        is_premium: !!d.isPremium,
                        premium_expires_ts: Number(d.expires_timestamp) || 0,
                        trial_used: !!d.trialAlreadyIssued,
                        lang_ui: ((chrome.i18n && chrome.i18n.getUILanguage && chrome.i18n.getUILanguage()) || '').slice(0, 16),
                        lang_app: String(d.language || '').slice(0, 16),
                        vpn_state: d.proxyEnabled ? 'on' : 'off',
                        vpn_server: server.slice(0, 64),
                        vpn_seconds_total: Number(stats.totalSeconds || 0) || 0,
                        sessions_total: Number(stats.totalSessions || 0) || 0,
                        auto_enable_on: d.autoEnableEnabled === true,
                        auto_enable_count: Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains.length : 0,
                        ad_blocker_on: d.adBlockerEnabled === true,
                        excl_mode: String(d.exclusionsMode || ''),
                        excl_black_count: Array.isArray(d.blacklistDomains) ? d.blacklistDomains.length : 0,
                        excl_white_count: Array.isArray(d.whitelistDomains) ? d.whitelistDomains.length : 0,
                        color_theme: String(d.colorTheme || '').slice(0, 32),
                        auto_select_scope: String(d.autoSelectScope || ''),
                        vpn_conflicts_count: Array.isArray(d.vpnConflictList) ? d.vpnConflictList.length : 0,
                        tab_active: activeTab,
                        // [v2.7.6 audit pass15] Truncate UA до 192 chars + дроп длинных
                        // build-string'ов снижает fingerprint surface (browser+OS achievable
                        // в первых ~150 char типичного UA).
                        user_agent: String(navigator.userAgent || '').slice(0, 192),
                        platform: String(navigator.platform || '').slice(0, 64),
                        languages: Array.isArray(navigator.languages) ? navigator.languages.slice(0, 5) : [],
                        tz_offset: new Date().getTimezoneOffset(),
                        tz_name: String(tzName).slice(0, 48),
                        screen: (Number(screen.width)||0) + 'x' + (Number(screen.height)||0),
                        online: navigator.onLine !== false,
                        // Последние 25 diag-events – даёт картину "что произошло перед feedback".
                        // Полный лог cap 100 (sw _logDiagQueue ring buffer) – 25 покрывает 1-3 минуты активности.
                        // [v2.7.6 audit pass15] Privacy: SW logDiag в auto-enable / toggle / blocked
                        // путях кладёт `host`/`from`/`ext` поля с user-visited hostname'ами или
                        // proxy-host. Через feedback metadata это leak'ало бы browsing history.
                        // Sanitize: keep timestamp/category/event, дроп .data полей с PII.
                        recent_diag: Array.isArray(d.diagnosticLog) ? d.diagnosticLog.slice(-25).map(function(e){
                            if (!e || typeof e !== 'object') return e;
                            var clean = { t: e.t, c: e.c, e: e.e };
                            if (e.d && typeof e.d === 'object') {
                                // Whitelist: безопасные numeric/enum/version/error поля. Дропаем
                                // host/dom/targetHost/from/ext/src – могут содержать user-visited
                                // URL hostnames или extension ID (PII-leak risk через support).
                                // err/fatal проверены: логируются только net::ERR_* коды и proxy
                                // status, не URL. days/users/fIdx – public server stats.
                                var safeKeys = [
                                    'count', 'status', 'ageMs', 'minVer', 'current', 'reason',
                                    'msg', 'offsetSec', 'skew', 'ver', 'serverTs', 'clientTs',
                                    'latest', 'ms',
                                    // [v2.7.6 audit /audit-extension] добавлены non-PII поля
                                    'days', 'users', 'fIdx', 'version', 'prev', 'cur',
                                    'err', 'fatal', 'ts', 'ur', 'ill', 'listLen'
                                ];
                                var d2 = {};
                                for (var k in e.d) {
                                    if (safeKeys.indexOf(k) >= 0) d2[k] = e.d[k];
                                }
                                clean.d = d2;
                            }
                            return clean;
                        }) : []
                    };
                    resolve(meta);
                } catch(e) { resolve({ _meta_err: String((e && e.message) || '').slice(0, 80) }); }
            });
        } catch(e) { resolve({ _meta_err: 'outer:' + String((e && e.message) || '').slice(0, 80) }); }
    });
}

feedbackForm?.addEventListener("submit", e => {
    e.preventDefault();
    // [v2.6.0] parseInt с radix 10 + isNaN guard: без этого `NaN` проходит валидацию
    // (NaN < 1 → false, NaN > 5 → false), сервер получает мусорное значение.
    const rating = parseInt(ratingInput.value, 10);
    const feedback = feedbackTextarea.value.trim();
    const email = emailInput.value.trim();
    if (!feedback || isNaN(rating) || rating < 1 || rating > 5) { showStatusMessage(t('rateAndReview', 'Please rate and write a review.'), true); return; }
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showStatusMessage(t('emailRequired', 'Please enter a valid email.'), true); return; }
    submitButton.disabled = true; feedbackTextarea.disabled = true; emailInput.disabled = true;
    _collectFeedbackMetadata().then(function(meta){
        var metaJson = '';
        try { metaJson = JSON.stringify(meta); } catch(_) { metaJson = ''; }
        // Безопасность: cap размер на клиенте (сервер тоже cap'ит до 8000), чтобы не делать
        // огромные POST'ы при corrupted diagnosticLog
        if (metaJson.length > 7800) metaJson = JSON.stringify({ _truncated: true, version: meta.version, uid: meta.uid });
        return apiFetch("/AnonVPN/submit-feedback.php", {
            method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: 'rating='+rating+'&feedback='+encodeURIComponent(feedback)+'&email='+encodeURIComponent(email)+'&metadata='+encodeURIComponent(metaJson),
            signal: AbortSignal.timeout(15000)
        });
    })
    .then(res => { if (!res.ok) throw new Error(); chrome.storage.local.set({ feedback_text: feedback, feedback_email: email }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);}}); submitButton.style.display = "none"; editButton.style.display = "inline-block"; toggleForm(true); })
    .catch(() => { showStatusMessage(t('sendError', 'Send error.'), true); submitButton.disabled = false; feedbackTextarea.disabled = false; emailInput.disabled = false; });
});

editButton?.addEventListener("click", () => { toggleForm(false); submitButton.style.display = "inline-block"; editButton.style.display = "none"; });
function setStars(value) { stars.forEach((s, i) => s.classList.toggle("selected", i < value)); }
function toggleForm(state) { feedbackTextarea.disabled = state; emailInput.disabled = state; submitButton.disabled = state; }

// ═══ PROXIES + SERVER STATS ═══
function fetchServerStats() {
    return apiFetch('/AnonVPN/stats/server-stats.json?t=' + Date.now(), { cache: 'no-store', signal: AbortSignal.timeout(8000) })
        .then(res => { if (!res.ok) throw new Error('http ' + res.status); return res.json(); })
        .then(data => { if (data && typeof data === 'object') {
            serverUserCounts = data;
            // [v3.0.2] Кэшируем статистику + таймстамп (TTL 30 мин в refreshServerStats) – чтобы
            // фетчить не чаще раза в полчаса при popup-open / disconnect / открытии модалки выбора.
            chrome.storage.local.set({ cachedServerStats: serverUserCounts, cachedServerStatsAt: Date.now() }, function(){
                if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);}
            });
            // [v2.8.5] Stats догрузились – обновляем кнопку сервера (счётчик 👤 был 0 до этого).
            if (typeof updateServerBtnLabel === 'function') { try { updateServerBtnLabel(); } catch(_){} }
        } })
        .catch(() => {});
}

// [v2.6.2] Soft-баннер «Доступна новая версия» (информационный, не блокирует работу).
// SW пишет в storage.updateAvailable строку версии (напр. "2.6.3"), popup показывает баннер
// с кнопкой «Обновить» (ведёт в CWS) и крестиком (dismissed для этой версии).
// Клиентский semver-compare – защита от stale-флага (SW не успел очистить после апдейта).
function _cmpSemver(a, b){
    var pa = String(a).split('.').map(function(n){ return parseInt(n,10); });
    var pb = String(b).split('.').map(function(n){ return parseInt(n,10); });
    for (var i = 0; i < 3; i++) {
        var ai = isFinite(pa[i]) ? pa[i] : 0;
        var bi = isFinite(pb[i]) ? pb[i] : 0;
        if (ai > bi) return 1;
        if (ai < bi) return -1;
    }
    return 0;
}
function applyUpdateAvailableBanner(){
    var banner = $('updateAvailableBanner');
    if (!banner) return;
    function _renderFromStorage(){
        chrome.storage.local.get(['updateAvailable','updateAvailableDismissed','updateRequired','illegalExtId'], function(d){
            // Если уже показан hard-баннер (updateRequired/illegalExtId) – не дублируем
            if (d.updateRequired || d.illegalExtId) { banner.setAttribute('hidden',''); return; }
            var latest = d.updateAvailable;
            if (!latest || typeof latest !== 'string' || !/^\d+\.\d+\.\d+$/.test(latest)) {
                banner.setAttribute('hidden',''); return;
            }
            // [v2.6.2 audit] Двойная защита: если latest ≤ текущей версии – это stale-флаг
            // от предыдущей версии. Прячем, ничего не показываем. SW асинхронно очистит storage.
            var ext = chrome.runtime.getManifest().version;
            if (_cmpSemver(latest, ext) <= 0) { banner.setAttribute('hidden',''); return; }
            // Пользователь dismissed эту конкретную версию – не показываем пока не выйдет новее
            if (d.updateAvailableDismissed === latest) { banner.setAttribute('hidden',''); return; }
            var txtEl = $('updateAvailableText');
            var tmpl = t('updateAvailableBanner', 'Доступна новая версия {v}');
            if (txtEl) txtEl.textContent = tmpl.replace('{v}', latest);
            var btnEl = $('updateAvailableBtn');
            if (btnEl) btnEl.textContent = t('updateNow', 'Обновить');
            var helpBtn = $('updateHelpBtn');
            if (helpBtn) helpBtn.textContent = t('updateHelpBtnAria', 'Как обновить вручную');
            banner.removeAttribute('hidden');
        });
    }
    // [v2.7.4] Триггерим SW-side checkLatestVersion один раз на popup open. SW делает fetch
    // latest.json + storage.set, потом sendResponse – после ack читаем storage. Повторные
    // вызовы applyUpdateAvailableBanner (смена языка, dismiss) идут сразу из storage без
    // лишних hits на сервер. Game flow: open popup → 1 hit (vs прежние десятки в день).
    if (_latestVersionRequested) { _renderFromStorage(); return; }
    _latestVersionRequested = true;
    try {
        chrome.runtime.sendMessage({ action: 'checkLatestVersion' }, function(){
            // lastError возможен если SW killed mid-flight – игнорируем, читаем storage всё равно
            if (chrome.runtime.lastError) { /* noop */ }
            _renderFromStorage();
        });
    } catch (_) {
        _renderFromStorage();
    }
}
$('updateAvailableBtn')?.addEventListener('click', function(){
    var btn = this;
    var origText = btn.textContent;
    function openCwsFallback(){
        chrome.tabs.create({ url: 'https://chromewebstore.google.com/detail/pieoffaiheelaipjennepjbhnbdhcfck' }).catch(() => {});
    }
    btn.disabled = true;
    btn.textContent = t('checking', 'Проверяем…');
    try {
        chrome.runtime.requestUpdateCheck(function(status){
            if (chrome.runtime.lastError) {
                btn.disabled = false; btn.textContent = origText;
                // Unpacked / нет update_url / сеть – просто открываем страницу в CWS
                openCwsFallback();
                return;
            }
            if (status === 'update_available') {
                // Chrome скачал обновление – перезагружаем extension, чтобы применить.
                // SW после reload восстановит VPN-состояние из storage (proxyEnabled).
                btn.textContent = t('updating', 'Обновляем…');
                setTimeout(function(){ chrome.runtime.reload(); }, 400);
            } else if (status === 'throttled') {
                btn.disabled = false; btn.textContent = origText;
                showStatusMessage(t('updateCheckThrottled', 'Chrome ограничил проверки. Попробуйте через пару минут.'), true);
            } else {
                // 'no_update' – обновление анонсировано, но CWS ещё не раздаёт (например, в ревью).
                btn.disabled = false; btn.textContent = origText;
                showStatusMessage(t('updateNotYetPublished', 'Обновление пока не раздаётся Chrome Web Store. Попробуйте позже.'), false);
                openCwsFallback();
            }
        });
    } catch (e) {
        btn.disabled = false; btn.textContent = origText;
        openCwsFallback();
    }
});
$('updateAvailableClose')?.addEventListener('click', function(){
    chrome.storage.local.get(['updateAvailable'], function(d){
        if (d.updateAvailable) {
            chrome.storage.local.set({ updateAvailableDismissed: d.updateAvailable }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                applyUpdateAvailableBanner();
            });
        }
    });
});

// [v2.5.8] Баннер блокировки: либо «нужно обновление», либо «нелегальная версия»
// [v3.0.3] Статические обработчики кнопок критичных баннеров (updateBanner + rateLimit).
// Раньше onclick ставился внутри apply*Banner ТОЛЬКО при показе → если баннер показан иначе
// (или apply не отработал), кнопка молчала. Теперь привязка постоянная (как у updateAvailableBtn,
// который работает), состояние читаем при клике.
$('updateBannerBtn')?.addEventListener('click', function(){
    var officialUrl = 'https://chromewebstore.google.com/detail/pieoffaiheelaipjennepjbhnbdhcfck';
    chrome.storage.local.get(['illegalExtId', 'updateUrl'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) { chrome.tabs.create({ url: officialUrl }).catch(() => {}); return; }
        // Нелегальная копия → официальная установка из CWS (ручное обновление не поможет).
        if (d && d.illegalExtId) { chrome.tabs.create({ url: officialUrl }).catch(() => {}); return; }
        // updateRequired → updateUrl с сервера (https-only валидация против phishing), иначе CWS.
        var safe = officialUrl;
        if (d && typeof d.updateUrl === 'string') {
            try { var p = new URL(d.updateUrl); if (p.protocol === 'https:') safe = p.origin + p.pathname + p.search; } catch (e) {}
        }
        chrome.tabs.create({ url: safe }).catch(() => {});
    });
});
$('rateLimitBtn')?.addEventListener('click', function(){
    var fb = 'https://balancing.apiget.ru/AnonVPN/lk/premium-access-payment/?utm_source=ext&utm_medium=rate_limit';
    var url = (typeof upsellUrl === 'function') ? upsellUrl('rate_limit') : fb;
    try { chrome.tabs.create({ url: url || fb }).catch(() => {}); } catch (e) { chrome.tabs.create({ url: fb }).catch(() => {}); }
});

function applyUpdateBanner() {
    const banner = $('updateBanner');
    if (!banner) return;
    chrome.storage.local.get(['updateRequired', 'minVersion', 'updateUrl', 'illegalExtId', 'proxyListFetchError'], d => {
        updateRequiredFlag = !!d.updateRequired;
        illegalExtIdFlag = !!d.illegalExtId;
        _proxyListFetchError = (d.proxyListFetchError === 'network' || d.proxyListFetchError === 'server') ? d.proxyListFetchError : null;
        const txtEl = $('updateBannerText');
        const btnEl = $('updateBannerBtn');
        // [v3.0.3] Кнопка «как обновить вручную»: видна только для updateRequired (нелегальной
        // копии нужна офиц. установка – ручное обновление через chrome://extensions не поможет).
        const manualRow = $('updateBannerManualRow');
        const helpBtn2 = $('updateHelpBtn2');
        if (helpBtn2) helpBtn2.textContent = t('updateHelpBtnAria', 'Как обновить вручную');
        const officialUrl = 'https://chromewebstore.google.com/detail/pieoffaiheelaipjennepjbhnbdhcfck';

        if (d.illegalExtId) {
            // Нелегальная копия расширения – приоритет выше чем update
            if (txtEl) txtEl.textContent = t('illegalVersionBanner', 'Illegal version. Install the official extension from the Chrome Web Store.');
            if (btnEl) btnEl.textContent = t('getOfficial', 'Official');
            if (manualRow) manualRow.hidden = true; // ручное обновление не относится к нелегальной копии
            banner.hidden = false;
            // [v3.0.3] onclick больше тут не ставим – кнопка имеет статический listener (см. ниже),
            // читающий illegalExtId/updateUrl при клике. Так кнопка работает всегда (раньше onclick
            // ставился только при показе через applyUpdateBanner → при ином показе кнопка молчала).
        } else if (d.updateRequired) {
            const tmpl = t('updateRequiredBanner', 'Update required: please install version {v} or newer');
            const minV = d.minVersion || '';
            if (txtEl) txtEl.textContent = minV ? tmpl.replace('{v}', minV) : t('updateRequiredShort', 'Update required');
            if (btnEl) btnEl.textContent = t('updateNow', 'Update');
            if (manualRow) manualRow.hidden = false; // показать «как обновить вручную»
            banner.hidden = false;
            // [v3.0.3] onclick – в статическом listener ниже (читает updateUrl при клике).
        } else {
            banner.hidden = true;
        }
    });
}

// [v2.8.0] applyRateLimitBanner – показ баннера для rate_limited бана.
// Симметрично applyUpdateBanner, но отдельный banner-элемент (не блокирует update-баннер).
// Кнопка Premium открывает upsell с UTM medium=rate_limit (для аналитики conversion).
var _rateLimitExpiryTimer = null;
function applyRateLimitBanner() {
    const banner = $('rateLimitBanner');
    if (!banner) return;
    // [round 12] Очищаем pending timer от предыдущего вызова – иначе stale callback
    // мог fire через старый rateLimitedUntil после storage-clear.
    if (_rateLimitExpiryTimer) { clearTimeout(_rateLimitExpiryTimer); _rateLimitExpiryTimer = null; }
    chrome.storage.local.get(['rateLimited', 'rateLimitedReason', 'rateLimitedUntil', 'isPremium'], d => {
        // [v2.8.0 audit] Premium юзеров не баним по cron-фильтру (premium=0), но defense-in-depth:
        // если флаг rateLimited всё-таки оказался true у Premium-юзера (corrupted storage,
        // legacy state с прошлой версии), не показываем банер – Premium-сессии безлимитны.
        if (!d.rateLimited || d.isPremium) {
            banner.hidden = true;
            return;
        }
        const titleEl = $('rateLimitTitle');
        const textEl = $('rateLimitText');
        const btnEl = $('rateLimitBtn');
        if (titleEl) titleEl.textContent = t('rateLimitTitle', 'Превышен лимит активности');
        // Текст: показываем until если есть, иначе обобщённое сообщение
        let bodyText = t('rateLimitText', 'Доступ временно ограничен. Premium снимает все лимиты.');
        if (d.rateLimitedUntil && typeof d.rateLimitedUntil === 'string') {
            // until в формате 'YYYY-MM-DD HH:MM:SS' UTC от сервера
            // [v2.8.0 audit r7] typeof === 'string' guard – без него `.replace()` на number/object
            // throws, перехватывается outer try/catch, но diag-log полезнее explicit type-check.
            try {
                const dt = new Date(d.rateLimitedUntil.replace(' ', 'T') + 'Z');
                if (!isNaN(dt.getTime())) {
                    // [round 12] Время истекло – скрываем баннер, не дожидаясь следующего
                    // heartbeat-clear от сервера (~5 мин окно). Прячем сразу после expiry.
                    const msUntilExpiry = dt.getTime() - Date.now();
                    if (msUntilExpiry <= 0) {
                        banner.hidden = true;
                        return;
                    }
                    // Schedule auto-hide через 1 sec после expiry – на случай если SW
                    // ещё не успел сделать heartbeat-clear к этому моменту. Cap 24h
                    // против setTimeout overflow (max ~24.8d signed int32 ms).
                    if (msUntilExpiry < 24 * 3600 * 1000) {
                        _rateLimitExpiryTimer = setTimeout(applyRateLimitBanner, msUntilExpiry + 1000);
                    }
                    const localStr = dt.toLocaleString();
                    bodyText = t('rateLimitTextUntil', 'Доступ ограничен до {until}. Premium снимает все лимиты.').replace('{until}', localStr);
                }
            } catch {}
        }
        if (textEl) textEl.textContent = bodyText;
        if (btnEl) btnEl.textContent = t('rateLimitPremiumBtn', 'Premium');
        banner.hidden = false;
        // [v3.0.3] onclick – в статическом listener ниже (всегда привязан).
    });
}

// [v2.6.0] Счётчик повторов loadProxies в рамках одного открытия popup.
// Защищает от «пустого» списка при транзиентной ошибке SW/сети – даём второй шанс
// через ~1500ms, прежде чем показать «No servers». Сбрасывается на proxyStateChanged
// и прочих событиях, инициирующих новый цикл загрузки списка.
var _loadProxiesRetried = false;
function resetLoadProxiesRetry() { _loadProxiesRetried = false; }

// [v3.0.2] TTL-актуализация статистики серверов (нагрузка по host:port). Кэш 30 мин – fetch не
// чаще раза в полчаса. onUpdate() зовётся после загрузки кэша И после свежего fetch (idempotent
// re-render, callsite'ы re-entrancy-guarded). Триггеры: открытие popup, отключение от сервера,
// открытие модалки выбора. Решает: в час пик «первый» сервер показывался свободным по устаревшему
// кэшу (а реально перегружен) → все валились на него.
var SERVER_STATS_TTL_MS = 30 * 60 * 1000;
function refreshServerStats(onUpdate) {
    chrome.storage.local.get(['cachedServerStats','cachedServerStatsAt'], function(d){
        if (d.cachedServerStats && typeof d.cachedServerStats === 'object' && !Array.isArray(d.cachedServerStats)) {
            var _sc = d.cachedServerStats, _keys = Object.keys(_sc);
            if (_keys.length && _keys.some(function(k){ return /^[fp]\d+$/.test(k); })) {
                // [v2.8.1] legacy fN/pN ключи → wipe; следующий fetch наполнит host:port
                serverUserCounts = {};
                chrome.storage.local.remove(['cachedServerStats','cachedServerStatsAt']);
            } else {
                serverUserCounts = _sc;
            }
        }
        if (onUpdate) { try { onUpdate(); } catch(_){} }
        var age = Date.now() - (Number(d.cachedServerStatsAt) || 0);
        if (age >= 0 && age < SERVER_STATS_TTL_MS && serverUserCounts && Object.keys(serverUserCounts).length > 0) return; // кэш свежий
        // onUpdate уже отработал с кэшем выше – при сбое fetch глушим (рендер уже был, unhandled
        // rejection не нужен). При успехе перерисовываем свежими данными.
        fetchServerStats().then(function(){ if (onUpdate) { try { onUpdate(); } catch(_){} } }).catch(function(){});
    });
}

function loadProxies() {
    // [v3.0.2] Список из SW + TTL-актуализация статистики через refreshServerStats (кэш 30 мин).
    // Раньше: при VPN ON статистика бралась ТОЛЬКО из кэша (устаревала → перегруженный сервер
    // показывался свободным); при VPN OFF фетчилась каждый раз без кэша. Теперь единообразно.
    chrome.runtime.sendMessage({ action: 'getProxies' }, response => {
        if (chrome.runtime.lastError) { handleEmptyProxiesResponse(); return; } // [audit] SW мог упасть
        const list = (response && response.proxies) ? response.proxies : [];
        if (list.length === 0) { handleEmptyProxiesResponse(); return; }
        cachedProxyList = list;
        refreshServerStats(function(){ renderProxySelect(cachedProxyList); });
    });
}

// [v2.6.0] Реакция на пустой ответ от SW:
//   1. Если подняты updateRequired/illegalExtId – реальная блокировка, рендерим сразу.
//   2. Если уже есть непустой cachedProxyList – оставляем, не затираем транзиентным сбоем.
//   3. Первый раз в сессии popup – повторяем через 1500ms (SW может ещё подгружать).
//   4. После повторного пустого ответа – рендерим пустое состояние («No servers»).
function handleEmptyProxiesResponse() {
    chrome.storage.local.get(['updateRequired', 'illegalExtId'], function(d){
        if (d.updateRequired || d.illegalExtId) {
            renderProxySelect([]);
            return;
        }
        if (Array.isArray(cachedProxyList) && cachedProxyList.length > 0) {
            // Уже есть рабочий список – ничего не трогаем
            return;
        }
        if (_loadProxiesRetried) {
            renderProxySelect([]);
            return;
        }
        _loadProxiesRetried = true;
        setTimeout(function(){ loadProxies(); }, 1500);
    });
}

// [v2.5.9] Elevated-load warning – average free-server load ≥ LOAD_WARN_AVG triggers upgrade banner.
// [v3.0.3] Порог снижен 75→60: 75 = уже пик (порог блокировки), предупреждаем раньше.
// Shown only for free users with valid stats. Recomputed on every renderProxySelect.
function checkHighLoadWarning() {
    var banner = $('loadWarningBanner');
    if (!banner) return;
    chrome.storage.local.get(['isPremium'], function(d){
        if (d.isPremium) { banner.setAttribute('hidden',''); return; }
        if (!Array.isArray(cachedProxyList) || cachedProxyList.length === 0) { banner.setAttribute('hidden',''); return; }
        var freeList = cachedProxyList.filter(function(p){return p.type!=='premium';});
        if (freeList.length === 0) { banner.setAttribute('hidden',''); return; }
        var total = 0, counted = 0;
        for (var i = 0; i < freeList.length; i++) {
            var key = _serverKey(freeList[i]);
            if (key && typeof serverUserCounts[key] === 'number') {
                total += serverUserCounts[key];
                counted++;
            }
        }
        if (counted === 0) { banner.setAttribute('hidden',''); return; }
        var avg = total / counted;
        if (avg >= LOAD_WARN_AVG) banner.removeAttribute('hidden');
        else banner.setAttribute('hidden','');
    });
}

// [v2.6.2] Режим сортировки списка серверов.
// Варианты: 'load' (default) – flat по нагрузке ascending (меньше users – выше);
// 'index' – оригинальный порядок от сервера (№1, №2, ...);
// 'country' – страны по коду alphabetical, внутри – по idx.
// Excluded-из-автовыбора всегда в конце независимо от режима.
// Кэшируется в памяти popup на время сессии, читается/пишется в chrome.storage.local.serverSortMode.
var _currentSortMode = 'load';
function loadSortMode(cb){
    chrome.storage.local.get(['serverSortMode'], function(d){
        var m = d.serverSortMode;
        if (m !== 'index' && m !== 'country' && m !== 'ping') m = 'load';
        _currentSortMode = m;
        if (cb) cb(m);
    });
}

// [v2.6.2] Сортирует items ({proxy, idx}) согласно текущему режиму.
// idx сохраняется – label «US №3» остаётся «US №3», меняется только порядок отрисовки.
// Исключённые из автовыбора серверы всегда в конце независимо от режима.
function sortServers(items, type, mode){
    if (!Array.isArray(items) || items.length === 0) return items;
    mode = mode || _currentSortMode || 'load';
    // Делим на активные и excluded – excluded всегда ниже
    var active = [], excluded = [];
    items.forEach(function(it){
        (isExcludedFromAutoSelect(it.proxy) ? excluded : active).push(it);
    });
    var sortActive = function(arr){
        if (mode === 'index') {
            return arr.slice().sort(function(a,b){ return a.idx - b.idx; });
        }
        if (mode === 'country') {
            return arr.slice().sort(function(a,b){
                var ca = (a.proxy && a.proxy.country) || 'ZZ';
                var cb = (b.proxy && b.proxy.country) || 'ZZ';
                if (ca !== cb) return ca < cb ? -1 : 1;
                return a.idx - b.idx;
            });
        }
        if (mode === 'ping') {
            // [v2.8.5] Сортировка по последнему измеренному пингу (по возрастанию).
            // Серверы без результата пинга – вниз. Нет данных вообще → fallback на 'load'.
            if (_pingSortMap && Object.keys(_pingSortMap).length) {
                return arr.slice().sort(function(a,b){
                    var pa = _pingSortMap[_serverKey(a.proxy)]; if (typeof pa !== 'number') pa = Infinity;
                    var pb = _pingSortMap[_serverKey(b.proxy)]; if (typeof pb !== 'number') pb = Infinity;
                    if (pa !== pb) return pa - pb;
                    return a.idx - b.idx;
                });
            }
        }
        // 'load' – плоская сортировка по user-count ascending (без группировки по стране)
        return arr.slice().sort(function(a,b){
            var la = serverUserCounts[_serverKey(a.proxy)] || 0;
            var lb = serverUserCounts[_serverKey(b.proxy)] || 0;
            if (la !== lb) return la - lb;
            return a.idx - b.idx; // tiebreak для стабильности
        });
    };
    return sortActive(active).concat(sortActive(excluded));
}

// UI: текст кнопки + подсветка выбранного item в dropdown
function updateSortModeUI(){
    var txt = $('sortModeText');
    var drop = $('sortModeDropdown');
    var mode = _currentSortMode || 'load';
    var labels = {
        load: t('sortByLoad', 'По нагрузке'),
        index: t('sortByIndex', 'По номеру'),
        country: t('sortByCountry', 'По стране'),
        ping: t('sortByPing', 'По пингу')
    };
    if (txt) txt.textContent = labels[mode] || labels.load;
    if (drop) {
        drop.classList.remove('open');
        drop.querySelectorAll('.sort-mode-item').forEach(function(it){
            it.classList.toggle('selected', it.getAttribute('data-mode') === mode);
            var m = it.getAttribute('data-mode');
            if (m && labels[m]) it.textContent = labels[m];
        });
    }
    var labelEl = $('sortModeLabel');
    if (labelEl) labelEl.textContent = t('sortMode', 'Сортировка:');
    // [v3.1.2] «По скорости» приглушаем ТОЛЬКО пока нет пингов вообще (ни ghost-ping, ни ручная
    // проверка). Ghost наполняет за пару минут → обычно пункт активен почти сразу.
    var pingItem = $('sortModePing');
    if (pingItem) {
        chrome.storage.local.get(['checkerLastResults','serverPings'], function(d){
            var hasGhost = d && d.serverPings && typeof d.serverPings==='object' &&
                Object.keys(d.serverPings).some(function(k){ var r=d.serverPings[k]; return r && typeof r.ms==='number' && r.ms>0; });
            var hasPings = hasGhost || _hasCheckerPingData(d && d.checkerLastResults);
            pingItem.classList.toggle('needs-ping', !hasPings);
        });
    }
}

$('sortModeBtn')?.addEventListener('click', function(e){
    e.stopPropagation();
    var drop = $('sortModeDropdown');
    if (drop) drop.classList.toggle('open');
});
// [v2.8.5] Применяет режим сортировки: сохраняет в storage + перерисовывает список.
function _applySortMode(mode){
    _currentSortMode = mode;
    chrome.storage.local.set({ serverSortMode: mode }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
        updateSortModeUI();
        buildServerModalList(); // перерисовать открытый список
    });
}
document.querySelectorAll('#sortModeDropdown .sort-mode-item').forEach(function(item){
    var activate = function(){
        var mode = item.getAttribute('data-mode');
        if (!mode) return;
        var drop = $('sortModeDropdown'); if (drop) drop.classList.remove('open');
        // [v2.8.5] «По пингу» требует прогнанной проверки серверов. Если её ещё не было –
        // закрываем «Выбор сервера» и открываем «Проверку серверов».
        // [v3.1.2] «По скорости» доступна ВСЕМ без премиума и без ручной проверки: ghost-ping
        // наполняет пинги в фоне для всех. Раньше free-юзеру тут показывали premium-предупреждение
        // (checkerLockedModal), а premium/verified кидали в «Проверку серверов». Теперь просто
        // применяем сортировку – если пингов ещё мало (первые минуты после установки), беспинговые
        // серверы уходят вниз, ghost догоняет и список пересортируется сам.
        _applySortMode(mode);
    };
    item.addEventListener('click', function(e){ e.stopPropagation(); activate(); });
    // [v2.7.3] клавиатурная активация (role="menuitem" + tabindex=0 в HTML)
    item.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); activate(); }
    });
});
// Клик вне dropdown – закрыть
document.addEventListener('click', function(e){
    var drop = $('sortModeDropdown');
    var btn = $('sortModeBtn');
    if (!drop || !drop.classList.contains('open')) return;
    if (drop.contains(e.target) || (btn && btn.contains(e.target))) return;
    drop.classList.remove('open');
});

// [v2.5.9] Auto-select helper – returns { proxy, selectIdx } for the least-loaded server
// matching the given scope. selectIdx is the index within proxySelect options (free first, then premium).
// Respects per-server exclusions (autoSelectExcluded).
// [v2.9.1] Расширено: method ('load'|'ping'|'both') + pings ({host:port:{ms,ts}}).
// Симметрично SW pickBestServer. Backward-compat: без method/pings = old behavior (load).
function pickBestServerLocal(list, scope, isPremium, method, pings) {
    if (!Array.isArray(list) || list.length === 0) return null;
    pings = (pings && typeof pings === 'object' && !Array.isArray(pings)) ? pings : {};
    method = (method === 'ping' || method === 'both') ? method : 'load';
    var PING_TTL_MS = 24 * 60 * 60 * 1000;
    var now = Date.now();
    var freeList = list.filter(function(p){return p.type!=='premium';});
    var premList = list.filter(function(p){return p.type==='premium';});
    var pool;
    if (!isPremium) pool = freeList;
    else if (scope === 'premium') pool = premList.length ? premList : freeList;
    else if (scope === 'all') pool = list; // [audit fix critical] parity с SW: list (не freeList.concat – порядок отличался)
    else pool = freeList.length ? freeList : list; // [audit fix critical] parity с SW: 'free' fallback на list, не premList
    pool = pool.filter(function(p){ return !isExcludedFromAutoSelect(p); });
    // [v3.0.3] Пропускаем недавно-сломанные (✕) серверы – синхронно с SW-автовыбором. Иначе визуал
    // авто-выбора встаёт на ✕-сервер, который реальный коннект (SW) всё равно пропустит → рассинхрон.
    pool = pool.filter(function(p){ return !(_brokenServersMap && _brokenServersMap[p.host + ':' + p.port]); });
    if (pool.length === 0) return null;
    // [v3.0.4] Random tie-break (parity с SW pickBestServer): при равных score (пустые stats – у всех
    // load=0) не берём детерминированно pool[0], иначе все без нагрузки садятся на первый сервер списка.
    // selectIdx считается через freeList/premList.indexOf(p) → от порядка pool не зависит, шафл безопасен.
    for (var _s = pool.length - 1; _s > 0; _s--) { var _r = Math.floor(Math.random() * (_s + 1)); var _t = pool[_s]; pool[_s] = pool[_r]; pool[_r] = _t; }
    // [v3.1.2] Scoring вынесен в под-функцию – прогоняем сначала на избранных, затем на полном пуле.
    function _pickFrom(candidates){
        var best = null, bestScore = Infinity, bestSelectIdx = -1;
        for (var i = 0; i < candidates.length; i++) {
            var p = candidates[i], users, selectIdx, sk;
            sk = _serverKey(p);
            if (p.type === 'premium') {
                var pIdx = premList.indexOf(p);
                users = serverUserCounts[sk] || 0;
                selectIdx = freeList.length + pIdx;
            } else {
                var fIdx = freeList.indexOf(p);
                users = serverUserCounts[sk] || 0;
                selectIdx = fIdx;
            }
            if (!isPremium && p.type !== 'premium' && users >= FREE_LOAD_LIMIT) continue;
            var ms = Infinity;
            if (sk && pings[sk] && typeof pings[sk].ms === 'number' && pings[sk].ms > 0 &&
                typeof pings[sk].ts === 'number' && (now - pings[sk].ts) < PING_TTL_MS) {
                ms = pings[sk].ms;
            }
            var score;
            if (method === 'ping') {
                if (!Number.isFinite(ms)) continue;
                score = ms;
            } else if (method === 'both') {
                var usersN = users / FREE_LOAD_LIMIT;
                // [2026-06-29] Штраф +100 беспинговому: пинганутые впереди (score<2), среди беспинговых – по нагрузке.
                if (!Number.isFinite(ms)) score = usersN + 100;
                else score = 0.5 * usersN + 0.5 * (Math.min(ms, 1500) / 600);
            } else {
                score = users;
            }
            if (score < bestScore) { bestScore = score; best = p; bestSelectIdx = selectIdx; }
        }
        return best ? { proxy: best, selectIdx: bestSelectIdx } : null;
    }
    // [v3.1.2] Приоритет избранных (parity с SW pickBestServer): если у юзера есть избранные,
    // сначала выбираем лучший из тех избранных, что попали в pool. Если среди них никто не подошёл –
    // из полного пула (fallback обязателен, иначе юзер с перегруженными избранными без сервера).
    if (Array.isArray(favoriteServers) && favoriteServers.length) {
        var _favSet = {};
        for (var _fi = 0; _fi < favoriteServers.length; _fi++) _favSet[favoriteServers[_fi]] = 1;
        var favPool = pool.filter(function(p){ return _favSet[p.host + ':' + p.port]; });
        if (favPool.length) {
            var favPick = _pickFrom(favPool);
            if (favPick) return favPick;
        }
    }
    return _pickFrom(pool);
}

var _renderProxySelectSeq = 0;
function renderProxySelect(list) {
    // [v2.5.9] Authoritative state sync: cachedProxyList всегда отражает текущий state
    // proxySelect. Иначе получали рассинхрон «Сервер: –» + полный список в модалке,
    // когда SW возвращал [] (error/empty), а cachedProxyList сохранял старые данные.
    // [v2.8.5 fix R2] Re-entrancy guard – renderProxySelect зовётся из ~7 мест; два
    // конкурентных вызова раньше дублировали <option> в proxySelect (clear синхронно +
    // append в async storage.get callback). Устаревший вызов выходит до append.
    var _rpsSeq = ++_renderProxySelectSeq;
    var safeList = Array.isArray(list) ? list : [];
    cachedProxyList = safeList;
    proxySelect.innerHTML = '';
    // [v2.5.8] Пустой список – показываем понятное сообщение и блокируем select
    if (safeList.length === 0) {
        // [v2.5.9] Reset button label – иначе держит stale данные от прошлого успешного рендера
        if (serverBtnLabel) {
            serverBtnLabel.textContent = '–';
            var _pe = serverBtnLabel.parentElement;
            if (_pe) {
                _pe.title = '';
                var _oldWarn = _pe.querySelector('.server-btn-warn');
                if (_oldWarn) _oldWarn.remove();
            }
        }
        const opt = document.createElement('option');
        if (illegalExtIdFlag) {
            opt.textContent = t('illegalVersionShort', 'Illegal version');
        } else if (updateRequiredFlag) {
            opt.textContent = t('updateRequiredShort', 'Update required');
        } else {
            opt.textContent = noServersText();
        }
        opt.value = ''; // [v2.5.9] explicit empty – иначе DOM берёт textContent как value
        opt.disabled = true;
        opt.selected = true;
        proxySelect.appendChild(opt);
        proxySelect.disabled = true;
        // [v2.5.9] Также надо перепроверить load-warning banner (скрыть – нечего показывать)
        checkHighLoadWarning();
        return;
    }
    proxySelect.disabled = false;
    chrome.storage.local.get(['selectedProxy', 'isPremium', 'autoSelectServer', 'autoSelectScope', 'autoSelectMethod', 'serverPings', 'checkerLastResults', 'cachedServerStats'], data => {
        if (_rpsSeq !== _renderProxySelectSeq) return; // superseded by a newer renderProxySelect
        // [v3.1.2] Восстанавливаем счётчик юзеров из кэша, если serverUserCounts ещё пуст:
        // перерисовка от обновления пингов (ghost/bulk) может прийти раньше refreshServerStats,
        // иначе метка [👤 N] у серверов пропадает.
        if ((!serverUserCounts || !Object.keys(serverUserCounts).length) && data.cachedServerStats
            && typeof data.cachedServerStats==='object' && !Array.isArray(data.cachedServerStats)) {
            serverUserCounts = data.cachedServerStats;
        }
        const selected = data.selectedProxy;
        const isPremium = !!data.isPremium;
        const autoOn = data.autoSelectServer !== false; // default true
        const autoScope = isPremium ? (data.autoSelectScope || 'free') : 'free';
        // [v2.9.1] Auto-method
        const autoMethod = (data.autoSelectMethod === 'ping' || data.autoSelectMethod === 'both') ? data.autoSelectMethod : 'ping';
        // [v2.9.2 critical fix] Merge оба источника пингов (bulk-ping + checker-tab).
        const autoPings = _mergePingSources(data.serverPings, data.checkerLastResults);

        const freeList = list.filter(p => p.type !== 'premium');
        const premList = list.filter(p => p.type === 'premium');
        var selIdx = -1;

        // [v2.6.2] Порядок отрисовки согласно _currentSortMode (load/index/country).
        // Оригинальный idx сохраняется (№3 остаётся №3 в label), меняется только позиция.
        const freeSorted = sortServers(freeList.map((p,i) => ({proxy:p, idx:i})), 'f');
        const premSorted = sortServers(premList.map((p,i) => ({proxy:p, idx:i})), 'p');

        freeSorted.forEach(function(item){
            const proxy = item.proxy, idx = item.idx;
            const opt = document.createElement('option');
            opt.value = 'f' + idx;
            const statsKey = _serverKey(proxy);
            const users = serverUserCounts[statsKey] || 0;
            const usersStr = users > 0 ? ' [\u{1F464} ' + users + ']' : '';
            // [v2.8.5] Compact label "No.N" (+ load count for free servers).
            opt.textContent = _freeServerLabel(idx) + usersStr;
            if (selected && selected.host === proxy.host && String(selected.port) === String(proxy.port)) { opt.selected = true; selIdx = idx; }
            if (proxy.country) opt.title = getCountryName(proxy.country);
            proxySelect.appendChild(opt);
        });

        premSorted.forEach(function(item){
            const proxy = item.proxy, idx = item.idx;
            const opt = document.createElement('option');
            opt.value = 'p' + idx;
            // [v2.8.5] Premium label "* No.N" / "(lock) No.N" + load count.
            const statsKey = _serverKey(proxy);
            const users = serverUserCounts[statsKey] || 0;
            const usersStr = users > 0 ? ' [\u{1F464} ' + users + ']' : '';
            if (isPremium) {
                opt.textContent = _premServerLabel(idx, true) + usersStr;
                opt.className = 'premium-option';
            } else {
                opt.textContent = _premServerLabel(idx, false) + usersStr;
                opt.disabled = true;
                opt.className = 'premium-option locked';
            }
            if (selected && selected.host === proxy.host && String(selected.port) === String(proxy.port) && isPremium) opt.selected = true;
            if (proxy.country) opt.title = getCountryName(proxy.country);
            proxySelect.appendChild(opt);
        });

        // [v2.5.9] Авто-выбор сервера при открытии popup.
        // VPN off + autoSelect on → всегда пере-выбираем (чтобы пользователь видел актуальный лучший сервер).
        // VPN off + autoSelect off + нет selectedProxy → подстраховка: выбираем разумное значение один раз.
        // VPN on → не трогаем, иначе storage.onChanged в SW переподключит прокси.
        if (!isVpnOn) {
            var shouldPick = autoOn || !selected;
            if (shouldPick && list.length > 0) {
                // [v2.9.1] Передаём method+pings (только когда autoOn – иначе режим load)
                var picked = pickBestServerLocal(list, autoOn ? autoScope : 'free', isPremium,
                    autoOn ? autoMethod : 'load', autoOn ? autoPings : {});
                // [v2.9.1] ping/both без свежих пингов → fallback на load
                if (!picked && autoOn && autoMethod !== 'load') {
                    picked = pickBestServerLocal(list, autoScope, isPremium, 'load', {});
                }
                if (picked) {
                    var sameAsCurr = selected && selected.host === picked.proxy.host && String(selected.port) === String(picked.proxy.port);
                    // [v2.6.2] Используем реальный index после сортировки, не picked.selectIdx
                    var _oi = findSelectIndexByProxy(picked.proxy);
                    if (_oi >= 0) proxySelect.selectedIndex = _oi;
                    if (!sameAsCurr) {
                        chrome.storage.local.set({ selectedProxy: picked.proxy }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;} updateServerBtnLabel(); });
                    }
                }
            }
        }

        // Update button label
        updateServerBtnLabel();
        // Disable toggle if no servers
        if (toggle && !isVpnOn) toggle.disabled = (list.length === 0);
        // [v2.5.9] Recheck high-load warning (stats + proxy list now ready)
        checkHighLoadWarning();
    });
}

var _btnLabelSeq = 0;
function updateServerBtnLabel() {
    if (!serverBtnLabel || !proxySelect) return;
    var opt = proxySelect.options[proxySelect.selectedIndex];
    if (!opt) return;
    var mySeq = ++_btnLabelSeq;
    serverBtnLabel.textContent = '';
    var key = opt.value;
    var proxy = resolveProxyByKey(key);
    // [v2.8.5] Кнопка сервера = тот же вид, что строка в «Выборе сервера»:
    // флаг + чистый лейбл (№/⭐) + плашка-счётчик 👤 + плашка пинга (если есть).
    var btnText = opt.textContent.split(' [')[0];
    if (proxy && proxy.country) {
        var img = getFlagImg(proxy.country);
        if (img) serverBtnLabel.appendChild(img);
        var sp = document.createElement('span');
        sp.textContent = ' ' + btnText;
        serverBtnLabel.appendChild(sp);
        serverBtnLabel.parentElement.title = getCountryName(proxy.country);
    } else {
        var sp0 = document.createElement('span');
        sp0.textContent = btnText;
        serverBtnLabel.appendChild(sp0);
        serverBtnLabel.parentElement.title = '';
    }
    // [v2.8.5] Старый отдельный значок ⚠ убран – нагрузку показывает сама плашка-счётчик
    // (warn-классы, как в списке серверов).
    var oldWarn = serverBtnLabel.parentElement.querySelector('.server-btn-warn');
    if (oldWarn) oldWarn.remove();
    // [v2.7.4 audit r6] Defensive guard на пустой/некорректный key.
    if (!key || (key[0] !== 'f' && key[0] !== 'p')) return;
    var statsKey = _serverKey(proxy);
    var users = statsKey ? (serverUserCounts[statsKey] || 0) : 0;
    // Счётчик 👤 – те же классы, что в списке (.modal-item-badge + warn).
    if (users > 0) {
        var badge = document.createElement('span');
        badge.className = 'modal-item-badge';
        badge.textContent = '\u{1F464} ' + users;
        if (users >= 100) badge.classList.add('badge-warn', 'badge-warn-high');
        else if (users >= FREE_LOAD_LIMIT) badge.classList.add('badge-warn', 'badge-warn-medium');
        serverBtnLabel.appendChild(badge);
    }
    // Пинг – та же плашка, что в списке (.modal-item-ping). checkerLastResults из
    // storage async; seq-guard – устаревший вызов не дублирует плашку.
    chrome.storage.local.get(['checkerLastResults'], function(d){
        if (mySeq !== _btnLabelSeq || !statsKey) return;
        var pi = _buildPingMap(d && d.checkerLastResults)[statsKey];
        if (pi && pi.text) {
            var pe = document.createElement('span');
            pe.className = 'modal-item-ping ' + (pi.cls || '');
            pe.textContent = pi.text;
            serverBtnLabel.appendChild(pe);
        }
    });
}

proxySelect?.addEventListener('change', () => {
    if (proxySelect.disabled || !cachedProxyList) return;
    var val = proxySelect.value;
    var proxyObj = resolveProxyByKey(val);
    if (!proxyObj) return;
    chrome.storage.local.get(['isPremium'], d => {
        if (proxyObj.type === 'premium' && !d.isPremium) {
            chrome.storage.local.get(['selectedProxy'], prev => {
                if (prev.selectedProxy) {
                    for (let i = 0; i < proxySelect.options.length; i++) {
                        var p = resolveProxyByKey(proxySelect.options[i].value);
                        if (p && p.host === prev.selectedProxy.host && String(p.port) === String(prev.selectedProxy.port)) {
                            proxySelect.selectedIndex = i; break;
                        }
                    }
                }
            });
            return;
        }
        // [v2.7.0 fix F64] При ручном выборе сервера автоматически выключаем auto-select,
        // иначе SW.maybeAutoSelectServer на следующем toggle-on перезатрёт выбор юзера
        // лист-лоаднейшим сервером (per CLAUDE.md: «Manual server pick auto-disables auto-select»).
        chrome.storage.local.set({ selectedProxy: proxyObj, autoSelectServer: false }, function(){
            if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
        });
        updateServerBtnLabel();
    });
});

// [v2.6.2] Найти option-index в proxySelect по host:port (актуально после сортировки,
// когда pickBestServerLocal.selectIdx перестал совпадать с реальной позицией).
function findSelectIndexByProxy(proxy){
    if (!proxy || !proxySelect) return -1;
    for (var i = 0; i < proxySelect.options.length; i++) {
        var p = resolveProxyByKey(proxySelect.options[i].value);
        if (p && p.host === proxy.host && String(p.port) === String(proxy.port)) return i;
    }
    return -1;
}

function resolveProxyByKey(key) {
    // [v2.8.1 audit] Array.isArray guard – corrupted storage / race window with empty fetch
    // могут оставить cachedProxyList=undefined или non-array, и .filter() throws TypeError.
    if (!Array.isArray(cachedProxyList) || !key) return null;
    var type = key.charAt(0) === 'p' ? 'premium' : 'free';
    var idx = parseInt(key.substring(1), 10);
    var filtered = cachedProxyList.filter(function(p) { return type === 'premium' ? p.type === 'premium' : p.type !== 'premium'; });
    return filtered[idx] || null;
}

function updateVpnButtonUI(on) {
    if (vpnToggleBtn) {
        vpnToggleBtn.textContent = on ? t('turnOff', 'Выключить ВПН') : t('turnOn', 'Включить ВПН');
        vpnToggleBtn.className = 'vpn-toggle-btn ' + (on ? 'vpn-btn-on' : 'vpn-btn-off');
    }
    if (vpnStatusText) {
        vpnStatusText.textContent = on ? t('vpnOn', 'Включен') : t('vpnOff', 'Выключен');
        vpnStatusText.className = on ? 'vpn-status-on' : 'vpn-status-off';
    }
}

function setVpnFieldsLocked(locked) {
    const hint = locked ? t('vpnDisabledHint', 'Turn off VPN to change this setting') : '';
    // [v2.7.0 fix F65] tryTrialBtn убран из locked – seamless trial-activation per v2.6.3:
    // SW handler использует wasOn-логику (см. sw:requestTrial), если VPN on – сессия
    // продолжается без reconnect, только снимается 60-мин таймер. Блокировать кнопку =
    // лишить главную конверсионную точку CTA активного юзера. activateBtn и recoverPremiumBtn
    // остаются заблокированными – активация ключа/восстановление требуют VPN off.
    var els = [premiumKeyInput, activateBtn, resetPremiumBtn, $('recoverPremiumBtn')];
    els.forEach(function(el) {
        if (!el) return;
        el.disabled = locked; el.title = hint;
        if (locked) el.classList.add('vpn-locked');
        else el.classList.remove('vpn-locked');
    });
    // Modal open buttons
    var btns = [$('openServerModal'),$('openCheckerModal')];
    btns.forEach(function(b){ if(!b) return; if(locked){b.classList.add('vpn-locked');b.title=hint;}else{b.classList.remove('vpn-locked');b.title='';} });
    // [v2.5.9] Warning banner
    var banner = $('vpnLockedBanner');
    if (banner) {
        if (locked) banner.removeAttribute('hidden');
        else banner.setAttribute('hidden', '');
    }
    // [v3.1.1] Дубль баннера на вкладке «Премиум»: поле ключа заблокировано там же,
    // а основной vpnLockedBanner живёт в «Главной» и с «Премиума» не виден.
    var bannerPrem = $('vpnLockedBannerPremium');
    if (bannerPrem) {
        if (locked) bannerPrem.removeAttribute('hidden');
        else bannerPrem.setAttribute('hidden', '');
    }
}

// ═══ TIMER ═══
let timerIsPremium = false;
// [v3.1.1] Счётчик длительности безлимитной сессии: SW уже пишет vpnStats.currentSessionStart
// при каждом подключении (recordSessionStart, для статистики) – popup только читает и тикает.
// Отдельный интервал (_unlimInterval), НЕ timerInterval: премиум-ветки чистят timerInterval
// (updatePremiumUIDisplay и др.) и убили бы тикер. Жизненный цикл – целиком в startLocalTimer.
let _unlimStartTs = null;
let _unlimInterval = null;
function _fmtElapsed(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    return h + ':' + String(m).padStart(2, '0') + ':' + String(ss).padStart(2, '0');
}
function updateTimerDisplay(seconds) {
    const timerEl = $("timer");
    if (!timerEl) return;
    _currentTimerSecs = seconds; // [v2.6.3] для updateTimerUrgency
    if (timerIsPremium) { timerEl.textContent = t('unlimited', 'Unlimited Access') + (_unlimStartTs ? ' · ⏱ ' + _fmtElapsed(Date.now() - _unlimStartTs) : ''); timerEl.classList.add("timer-active"); }
    else if (seconds > 0) { const m = Math.floor(seconds/60), s = seconds%60; timerEl.textContent = t('disconnectIn','Disconnect in: ')+m+':'+s.toString().padStart(2,'0'); timerEl.classList.add("timer-active"); }
    else { timerEl.textContent = ''; timerEl.classList.remove("timer-active"); }
    updateTimerUrgency();
}

function startLocalTimer() {
    // [v2.6.5 audit] Clearinterval ДО sendMessage – иначе два быстрых proxyStateChanged:true
    // могут создать два интервала (второй запущен до того, как первый coll-бэк отработал clear).
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    // [v3.1.1] Сброс тикера безлимитной сессии – пересоздаётся ниже, если premium + VPN ON.
    // prevStart сохраняем: при transient-сбое SW (усыплён → lastError) восстановим тикер
    // с последнего известного старта, а не потеряем счётчик до следующего успешного вызова.
    var _prevUnlimStart = _unlimStartTs;
    if (_unlimInterval) { clearInterval(_unlimInterval); _unlimInterval = null; }
    _unlimStartTs = null;
    chrome.runtime.sendMessage({ action: "getRemainingTime" }, res => {
        // [v2.6.5 audit] lastError read – если SW усыплён на момент sendMessage, res===undefined
        // и Chrome пишет warning «Unchecked runtime.lastError». Читаем, подавляем.
        if (chrome.runtime.lastError || !res || !res.secondsLeft) {
            // [v3.1.1] SW не ответил – восстанавливаем прежний тикер безлимита (если был):
            // сон SW ≠ выключенный VPN, последнее известное состояние лучше пустого.
            if (_prevUnlimStart && timerIsPremium) {
                _unlimStartTs = _prevUnlimStart;
                updateTimerDisplay(999999);
                _unlimInterval = setInterval(function() { updateTimerDisplay(999999); }, 1000);
            }
            return;
        }
        let remaining = res.secondsLeft;
        updateTimerDisplay(remaining);
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        if (remaining > 500000) {
            // [v3.1.1] Безлимит (premium): «сколько уже подключён». Источник – vpnStartedAt
            // (переживает SW-рестарты; vpnStats.currentSessionStart обнуляется initialize→
            // recordSessionEnd на каждом cold-wake SW даже при живом VPN – счётчик пропадал).
            // Fallback на vpnStats.currentSessionStart – для сессии, начатой до апдейта.
            chrome.storage.local.get(['vpnStartedAt', 'vpnStats', 'proxyEnabled'], function(d) {
                if (chrome.runtime && chrome.runtime.lastError) return;
                var st = (typeof d.vpnStartedAt === 'number' && d.vpnStartedAt > 0)
                    ? d.vpnStartedAt
                    : ((d.vpnStats && typeof d.vpnStats === 'object' && !Array.isArray(d.vpnStats)) ? d.vpnStats.currentSessionStart : null);
                // санити: число, в прошлом, не старше 30 дней (защита от clock-skew/corruption)
                var ok = d.proxyEnabled && typeof st === 'number' && st > 0 && st <= Date.now() + 60000 && (Date.now() - st) < 30 * 86400e3;
                _unlimStartTs = ok ? st : null;
                updateTimerDisplay(999999);
                if (_unlimInterval) { clearInterval(_unlimInterval); _unlimInterval = null; }
                if (_unlimStartTs) _unlimInterval = setInterval(function() { updateTimerDisplay(999999); }, 1000);
            });
            return;
        }
        timerInterval = setInterval(() => {
            remaining--;
            updateTimerDisplay(remaining);
            if (remaining <= 0) { clearInterval(timerInterval); timerInterval = null; updateTimerDisplay(0); }
        }, 1000);
    });
}

// ═══ [v2.6.2] CURRENT IP / FLAG ═══
// Источник: api.ipify.org (только IP). Страна: при VPN ON – из выбранного сервера
// (selectedProxy.country), при VPN OFF – ipinfo.io/{ip}/country (ISO-2).
// ipify НЕ в bypass – при VPN ON показывает exit-IP прокси, при VPN OFF – реальный.
// [v3.0.2] ipinfo.io больше НЕ дёргается при VPN ON: запрос шёл через прокси → ipinfo.io
// видел ОБЩИЙ IP сервера (сотни юзеров за ним) → 429 rate-limit на всех. Страна сервера
// известна локально (его CC) – мгновенно и точнее.
// Кэш на 60 сек, чтобы не дёргать на каждый toggle/reload popup.
var _ipInfoCache = null; // { ip, country, ts, vpnOn }
var _ipRetryTimer = null; // [v2.6.5 audit] trackedretry – отмена при быстром toggle
// [v3.0.3] Rescue-состояние + карта сломанных серверов. `brokenServers` – общий storage-key с SW
// (SW пишет при сломе туннеля; popup читает для метки «не работает» в списке + триггерит rescue).
var _tunnelRescueInFlight = false;
var _brokenServersMap = {};
function _refreshBrokenServers(cb){
    chrome.storage.local.get(['brokenServers'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) { if (cb) cb(); return; }
        var bs = (d.brokenServers && typeof d.brokenServers === 'object' && !Array.isArray(d.brokenServers)) ? d.brokenServers : {};
        var now = Date.now(), m = {};
        for (var k in bs) { if (now - bs[k] <= 5 * 60 * 1000) m[k] = true; }
        _brokenServersMap = m;
        if (cb) cb();
    });
}
_refreshBrokenServers();
// [v3.0.3] Inline-спиннер в IP-блоке: вкл во время резолва IP / подбора рабочего сервера.
function _ipSpin(on){
    var s = $('vpnIpSpinner');
    if (!s) return;
    if (on) s.removeAttribute('hidden'); else s.setAttribute('hidden', '');
}
// [v3.0.3] Снять спиннер «Connecting…» из #timer (на терминалах toggle). Текст не трогаем –
// на success его перетрёт updateTimer (textContent), на failure остаётся как раньше.
function _clearConnectSpinner(){
    var te = $('timer'); if (!te) return;
    var sp = te.querySelector('.inline-spinner'); if (sp) sp.remove();
}
// [v3.1.4 hotfix] Достать exit-IP через прокси: HTTPS И HTTP ipify ПАРАЛЛЕЛЬНО, первый валидный.
// На Kiwi/Android (и, возможно, macOS) HTTPS-fetch через прокси-CONNECT из extension-страницы не
// получает Proxy-Authorization → падает даже на живом туннеле. Итог до фикса: loadIpInfo не мог
// достать IP → «Сервер не отвечает, подбираем рабочий…» крутилось бесконечно (SW-проба уже чинена
// отдельно, но popup сам фейлился). HTTP-GET через прокси авторизуется надёжно. Промис → IP|null.
function _popupFetchExitIp(timeoutMs){
    timeoutMs = timeoutMs || 8000;
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
function loadIpInfo(force, _retry){
    var box = $('vpnIpInfo'), txt = $('vpnIpText'), flag = $('vpnIpFlag');
    if (!box || !txt || !flag) return;
    // [v3.0.3] Во время rescue не дёргаем ipify (SW переключает серверы) – показываем статус.
    if (_tunnelRescueInFlight && !_retry) {
        box.removeAttribute('hidden');
        _ipSpin(true);
        txt.textContent = t('ipRescuing', 'Сервер не отвечает, подбираем рабочий…');
        flag.style.display = 'none';
        return;
    }
    var nowMs = Date.now();
    if (!force && _ipInfoCache && (nowMs - _ipInfoCache.ts < 60000) && _ipInfoCache.vpnOn === isVpnOn) {
        renderIpInfo(_ipInfoCache.ip, _ipInfoCache.country);
        return;
    }
    if (_ipRetryTimer) { clearTimeout(_ipRetryTimer); _ipRetryTimer = null; }
    box.removeAttribute('hidden');
    _ipSpin(true);
    txt.textContent = '…';
    flag.style.display = 'none';
    _popupFetchExitIp(8000)
        .then(function(ip){
            if (!ip) throw new Error('no_ip');
            // [v3.0.2] VPN ON → страну берём из выбранного сервера (его код страны), а НЕ из
            // ipinfo.io: тот через прокси видит ОБЩИЙ IP сервера → 429 на всех юзеров за ним.
            // Локально мгновенно и точнее (это страна, которую юзер выбрал).
            if (isVpnOn) {
                return new Promise(function(resolve){
                    chrome.storage.local.get(['selectedProxy'], function(s){
                        var cc = (s && s.selectedProxy && s.selectedProxy.country) ? String(s.selectedProxy.country).trim().toUpperCase().slice(0,2) : '';
                        if (!/^[A-Z]{2}$/.test(cc)) cc = '';
                        _ipInfoCache = { ip: ip, country: cc, ts: nowMs, vpnOn: isVpnOn };
                        renderIpInfo(ip, cc);
                        resolve();
                    });
                });
            }
            // VPN OFF → реальный (уникальный) IP, ipinfo.io rate-limit'ит крайне редко.
            return fetch('https://ipinfo.io/' + encodeURIComponent(ip) + '/country', { cache: 'no-store', signal: AbortSignal.timeout(8000) })
                .then(function(r){ if (!r.ok) throw new Error('http ' + r.status); return r.text(); })
                .catch(function(){ return ''; })
                .then(function(c){
                    var country = String(c||'').trim().toUpperCase().slice(0,2);
                    if (!/^[A-Z]{2}$/.test(country)) country = '';
                    _ipInfoCache = { ip: ip, country: country, ts: nowMs, vpnOn: isVpnOn };
                    renderIpInfo(ip, country);
                });
        })
        .catch(function(){
            // [v2.6.2] Retry once after 1500ms – proxy may still be warming up on toggle-ON
            if (!_retry) {
                _ipRetryTimer = setTimeout(function(){ _ipRetryTimer = null; loadIpInfo(true, true); }, 1500);
                return;
            }
            flag.style.display = 'none';
            // [v3.0.3] Туннель сломан (ipify не прошёл дважды). При VPN ON просим SW подобрать
            // рабочий сервер + показываем понятный статус (не молчаливое «IP недоступен»).
            if (isVpnOn && !_tunnelRescueInFlight) {
                _tunnelRescueInFlight = true;
                chrome.storage.local.get(['autoSelectServer'], function(_ad){
                    // авто-выбор ВКЛ → «подбираем»; ВЫКЛ (ручной закреп) → SW не переключит, сразу «смените вручную».
                    var _auto = !(_ad && _ad.autoSelectServer === false);
                    // [v3.0.3] Авто: «подбираем…» со спиннером в IP-зоне.
                    // Ручной: НЕ дублируем инструкцию здесь – её ОДИН раз покажет #vpnMessage над
                    // кнопкой (broadcast tunnel_manual из swDisconnectVpn). IP-зона остаётся в
                    // loading-состоянии и резолвится в реальный IP после disconnect
                    // (proxyStateChanged → loadIpInfo через 500мс). Раньше тот же текст мелькал
                    // и в IP-зоне, и над кнопкой – пользователь видел дубль.
                    txt.textContent = _auto ? t('ipRescuing', 'Сервер не отвечает, подбираем рабочий…') : '…';
                    _ipSpin(true);
                    chrome.runtime.sendMessage({ action: 'rescueTunnel' }, function(resp){
                        _tunnelRescueInFlight = false;
                        if (chrome.runtime && chrome.runtime.lastError) { _ipSpin(false); txt.textContent = t('ipUnknown', 'IP unavailable'); return; }
                        if (resp && resp.busy) { setTimeout(function(){ loadIpInfo(true); }, 2000); return; } // ещё ищет → спиннер крутится
                        if (resp && resp.ok) { loadIpInfo(true); return; } // нашли рабочий → покажем новый IP (спиннер снимет renderIpInfo)
                        // ok:false → SW выключил ВПН; proxyStateChanged-обработчик покажет баннер-пояснение + реальный IP.
                        _ipSpin(false);
                    });
                });
            } else {
                _ipSpin(false);
                txt.textContent = t('ipUnknown', 'IP unavailable');
            }
        });
}
// [v2.6.5 audit] При toggle OFF – сбрасываем cache и pending retry, чтобы не перекрыть
// актуальный IP старым результатом из inflight-запроса.
function clearIpInfoCache(){
    _ipInfoCache = null;
    if (_ipRetryTimer) { clearTimeout(_ipRetryTimer); _ipRetryTimer = null; }
}
function renderIpInfo(ip, country){
    var txt = $('vpnIpText'), flag = $('vpnIpFlag');
    if (!txt || !flag) return;
    _ipSpin(false); // [v3.0.3] IP получен – снять спиннер
    if (country) {
        var fc = (typeof FLAG_MAP !== 'undefined' && FLAG_MAP[country]) ? FLAG_MAP[country] : country.toLowerCase();
        // [v2.6.2] Fallback for rare countries without an SVG in flags/ – hide broken-image icon
        flag.onerror = function(){ this.onerror = null; this.style.display = 'none'; };
        flag.src = 'flags/' + fc + '.svg';
        flag.alt = country;
        flag.style.display = '';
        txt.textContent = ip + ' • ' + getCountryName(country);
    } else {
        flag.style.display = 'none';
        txt.textContent = ip;
    }
}

// ═══ NEWS ═══
function getNewsText(item, field) {
    const lang = getLang();
    return item[field + '_' + lang] || item[field + '_en'] || item[field + '_ru'] || item[field] || '';
}

function renderNewsItems(news) {
    newsContainer.innerHTML = '';
    // [v2.6.5 audit] Полный DOM-билд вместо innerHTML-сборки. Данные эскейпились, но CWS-сканеры
    // помечают паттерн innerHTML=<server-data>. Этот вариант и читается проще.
    news.forEach(item => {
        const div = document.createElement('div'); div.className = 'news-item';
        const title = getNewsText(item, 'title');
        const body = getNewsText(item, 'body');
        const linkText = getNewsText(item, 'link_text') || t('readMore', 'Read more');
        if (item.date) {
            const d = document.createElement('div'); d.className = 'news-item-date';
            d.textContent = String(item.date);
            div.appendChild(d);
        }
        if (title) {
            const h = document.createElement('div'); h.className = 'news-item-title';
            h.textContent = String(title);
            div.appendChild(h);
        }
        if (body) {
            const b = document.createElement('div'); b.className = 'news-item-body';
            String(body).split('\n').forEach((line, i) => {
                if (i > 0) b.appendChild(document.createElement('br'));
                b.appendChild(document.createTextNode(line));
            });
            div.appendChild(b);
        }
        if (item.link && /^https?:\/\//i.test(item.link)) {
            // [v2.6.5 audit r2] Defense-in-depth: реконструируем URL без userinfo – иначе
            // `https://evil@good.com/path` прошёл бы regex и в адресной строке показал `evil@`
            // (потенциальный phishing при compromised-apiget.ru).
            let safeHref = null;
            try {
                const parsed = new URL(item.link);
                if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
                    safeHref = parsed.origin + parsed.pathname + parsed.search;
                }
            } catch {}
            if (safeHref) {
                const a = document.createElement('a');
                a.href = safeHref;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.className = 'news-item-link';
                a.textContent = String(linkText);
                div.appendChild(a);
            }
        }
        newsContainer.appendChild(div);
    });
}

function loadNews() {
    // [v2.8.5] Системные сообщения (окончание ключа + админ-сообщения) – независимо от
    // состояния VPN: keyexp считается локально, getUserMessages идёт на apiget.ru (BYPASS_LIST).
    loadSystemMessages();
    if (isVpnOn) {
        if (newsContainer.children.length > 0) return;
        chrome.storage.local.get(['cachedNews'], d => {
            if (Array.isArray(d.cachedNews) && d.cachedNews.length > 0) {
                if (newsLoading) newsLoading.style.display = 'none';
                if (newsEmpty) newsEmpty.style.display = 'none';
                renderNewsItems(d.cachedNews);
            } else {
                if (newsLoading) newsLoading.style.display = 'none';
                if (newsEmpty) {
                    var vpnNewsHint = {
                        ru:'Отключите VPN для загрузки новостей', en:'Turn off VPN to load news',
                        zh:'关闭VPN以加载新闻', es:'Desactiva la VPN para cargar noticias',
                        de:'VPN ausschalten um Nachrichten zu laden', fr:'Désactivez le VPN pour charger les actualités',
                        pt:'Desligue a VPN para carregar notícias'
                    };
                    newsEmpty.textContent = vpnNewsHint[getLang()] || vpnNewsHint.en;
                    newsEmpty.style.display = 'block';
                }
            }
        });
        return;
    }
    if (newsLoading) newsLoading.style.display = 'block';
    if (newsEmpty) newsEmpty.style.display = 'none';
    newsContainer.innerHTML = '';
    apiFetch('/AnonVPN/stats/news.json?t=' + Date.now(), { cache: 'no-store', signal: AbortSignal.timeout(10000) })
        .then(res => { if (!res.ok) throw new Error('http ' + res.status); return res.json(); })
        .then(news => {
            if (newsLoading) newsLoading.style.display = 'none';
            if (!Array.isArray(news) || news.length === 0) {
                if (newsEmpty) { newsEmpty.textContent = t('noNews', 'No news'); newsEmpty.style.display = 'block'; }
                return;
            }
            // [v2.7.5 audit r3] Cap 50 items – без cap server compromise / runaway feed
            // могут забить storage.local quota (10 MB). 50 items × ~2 KB = ~100 KB max.
            // [v2.7.5 audit r4] Cap also applied к render – раньше storage capped, render full.
            var cappedNews = news.slice(0, 50);
            chrome.storage.local.set({ cachedNews: cappedNews }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);}});
            renderNewsItems(cappedNews);
            if (news[0] && news[0].timestamp) chrome.storage.local.set({ lastNewsTime: news[0].timestamp }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);}});
            const badge = tabNews.querySelector('.news-badge');
            if (badge) badge.remove();
        })
        .catch(() => {
            if (newsLoading) newsLoading.style.display = 'none';
            if (newsContainer.children.length === 0) {
                chrome.storage.local.get(['cachedNews'], d => {
                    if (Array.isArray(d.cachedNews) && d.cachedNews.length > 0) { renderNewsItems(d.cachedNews); }
                    else { if (newsEmpty) { newsEmpty.textContent = t('newsLoadError', 'Error'); newsEmpty.style.display = 'block'; } }
                });
            }
        });
}

function checkNewsBadge() {
    if (isVpnOn) return;
    apiFetch('/AnonVPN/stats/news.json', { signal: AbortSignal.timeout(10000) })
        .then(res => { if (!res.ok) throw new Error('http ' + res.status); return res.json(); })
        .then(news => {
            if (!Array.isArray(news) || !news.length) return;
            chrome.storage.local.get(['lastNewsTime'], d => {
                const lastSeen = d.lastNewsTime || 0;
                if ((news[0]?.timestamp || 0) > lastSeen) {
                    if (tabNews && !tabNews.querySelector('.news-badge')) {
                        const b = document.createElement('span'); b.className = 'news-badge'; b.textContent = 'NEW'; tabNews.appendChild(b);
                    }
                    // [v2.7.3] Async fallback для auto-switch: покрывает сценарии где
                    // instant-switch при init не сработал (cachedNews пустой после wipe
                    // на update – `cachedNews` в STALE_KEYS, или fresh install без
                    // предыдущего визита на вкладку Новости). Срабатывает ОДИН раз за
                    // сессию popup'а, и только если юзер всё ещё на Main вкладке
                    // (не успел сам переключиться на Premium/News до fetch callback).
                    if (!_newsAutoSwitched && !isVpnOn && tabNews) {
                        var mainTab = document.querySelector('.tab-btn[data-tab="main"]');
                        if (mainTab && mainTab.classList.contains('active')) {
                            _newsAutoSwitched = true;
                            tabNews.click();
                        }
                    }
                }
            });
        }).catch(() => {});
}

// ═══ [v2.8.5] СИСТЕМНЫЕ СООБЩЕНИЯ ═══
// Предупреждение об окончании Premium-ключа (считается клиентом) + адресные сообщения
// от администратора (грузятся через SW getUserMessages). Рендерятся отдельным контейнером
// #sysMsgContainer ВВЕРХУ вкладки «Новости», над обычными новостями.
//
// Read-модель:
//  • keyexp – «увидено» (seenSysMsgIds) при рендере вкладки «Новости».
//  • admin  – «прочитано» ТОЛЬКО по кнопке «Прочитано» (readAdminMsgIds + read-receipt
//    на сервер). Пока есть непрочитанное админ-сообщение, popup при открытии переключается
//    на «Новости» (см. checkSysMsgBadge).
var _sysMsgItems = null; // кэш на сессию popup: [{id, kind, ...}]

// Клиентское предупреждение об истечении Premium-ключа по expires_timestamp.
function _buildKeyExpiryItem(d) {
    if (!d || !d.isPremium) return null;
    var expTs = Number(d.expires_timestamp);
    if (!isFinite(expTs) || expTs <= 0) return null;
    var leftSec = expTs - Math.floor(Date.now() / 1000);
    var DAY = 86400;
    if (leftSec > 3 * DAY) return null;   // ещё рано напоминать
    if (leftSec < -DAY) return null;      // истёк давно – больше не показываем
    if (leftSec <= 0) {
        return { id: 'keyexp_expired', kind: 'keyexp',
                 title: t('sysKeyExpiredTitle', 'Срок Premium истёк'),
                 body: t('sysKeyExpBody', 'Продлите Premium, чтобы пользоваться премиум-серверами без ограничений.') };
    }
    // id с днём-бакетом → бейдж NEW появляется заново при каждом приближении (3→2→1 день).
    var days = Math.max(1, Math.min(3, Math.ceil(leftSec / DAY)));
    return { id: 'keyexp_d' + days, kind: 'keyexp',
             title: t('sysKeyExpTitle', 'Premium скоро закончится'),
             body: t('sysKeyExpBody', 'Продлите Premium, чтобы пользоваться премиум-серверами без ограничений.') };
}

// «Нужно внимание»: непрочитанное админ-сообщение ИЛИ ещё неувиденный keyexp.
function _sysMsgNeedsAttention(items, seenIds) {
    if (!Array.isArray(items)) return false;
    return items.some(function(it){
        if (it.kind === 'admin') return !it.acknowledged;
        return seenIds.indexOf(it.id) < 0; // keyexp
    });
}

// Собирает системные сообщения: keyexp (клиент) + админ-сообщения (SW getUserMessages).
// readAdminMsgIds отправляются вместе с запросом – сервер пере-подтверждает read_at
// (idempotent), это чинит потерянные read-receipt'ы при следующем открытии popup.
function fetchSystemMessages(cb) {
    chrome.storage.local.get(['isPremium', 'expires_timestamp', 'readAdminMsgIds'], function(d){
        var items = [];
        try { var ke = _buildKeyExpiryItem(d); if (ke) items.push(ke); } catch (_e) {}
        var readIds = Array.isArray(d.readAdminMsgIds) ? d.readAdminMsgIds : [];
        var done = false;
        var finish = function(){
            if (done) return; done = true;
            _sysMsgItems = items;
            if (cb) cb(items);
        };
        try {
            chrome.runtime.sendMessage({ action: 'getUserMessages', readIds: readIds }, function(res){
                if (chrome.runtime && chrome.runtime.lastError) { finish(); return; }
                if (res && res.ok && Array.isArray(res.messages)) {
                    res.messages.forEach(function(m){
                        if (!m || (typeof m.id !== 'number' && typeof m.id !== 'string')) return;
                        var num = Number(m.id);
                        // «прочитано» = сервер вернул read:1 ИЛИ id в локальном readAdminMsgIds.
                        var ack = (m.read === 1 || m.read === true)
                                  || (isFinite(num) && readIds.indexOf(num) >= 0);
                        items.push({ id: 'adm_' + m.id, msgId: num, kind: 'admin',
                                     title: String(m.title || ''), body: String(m.body || ''),
                                     acknowledged: ack });
                    });
                }
                finish();
            });
        } catch (_e) { finish(); }
    });
}

// Рендер системных сообщений в #sysMsgContainer. DOM-build (textContent), без innerHTML –
// CWS-сканеры помечают innerHTML=<данные>; админ-текст идёт через textContent (анти-XSS).
function renderSystemMessages(items) {
    if (!sysMsgContainer) return;
    sysMsgContainer.innerHTML = '';
    if (!Array.isArray(items)) return;
    items.forEach(function(it){
        var div = document.createElement('div');
        div.className = 'news-item news-item-system' + (it.kind === 'keyexp' ? ' sys-keyexp' : ' sys-admin');
        var h = document.createElement('div'); h.className = 'news-item-title';
        h.textContent = (it.kind === 'keyexp' ? '⏳ ' : '\u{1F4E2} ') + String(it.title || '');
        div.appendChild(h);
        if (it.body) {
            var b = document.createElement('div'); b.className = 'news-item-body';
            String(it.body).split('\n').forEach(function(line, i){
                if (i > 0) b.appendChild(document.createElement('br'));
                b.appendChild(document.createTextNode(line));
            });
            div.appendChild(b);
        }
        if (it.kind === 'keyexp') {
            var a = document.createElement('a');
            a.href = '#'; a.className = 'news-item-link';
            a.textContent = t('sysRenewBtn', 'Продлить Premium');
            a.addEventListener('click', function(e){
                e.preventDefault();
                try { chrome.tabs.create({ url: upsellUrl('key_expiry') }); } catch (_e) {}
            });
            div.appendChild(a);
        } else if (it.kind === 'admin') {
            // Кнопка «Прочитано». Пока не нажата – popup продолжит переключаться на «Новости».
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'sys-read-btn' + (it.acknowledged ? ' done' : '');
            btn.textContent = '✓ ' + t('sysMarkRead', 'Прочитано');
            btn.disabled = !!it.acknowledged;
            if (!it.acknowledged) {
                btn.addEventListener('click', function(){
                    btn.disabled = true;
                    btn.classList.add('done');
                    _markAdminMsgRead(it);
                });
            }
            div.appendChild(btn);
        }
        sysMsgContainer.appendChild(div);
    });
}

// Отметка админ-сообщения прочитанным: локально (readAdminMsgIds) + read-receipt серверу.
function _markAdminMsgRead(it) {
    if (!it || it.kind !== 'admin' || it.acknowledged) return;
    it.acknowledged = true; // it – ссылка на элемент _sysMsgItems, кэш обновляется
    var mid = it.msgId;
    chrome.storage.local.get(['readAdminMsgIds'], function(d){
        var arr = Array.isArray(d.readAdminMsgIds) ? d.readAdminMsgIds.slice() : [];
        if (isFinite(mid) && arr.indexOf(mid) < 0) arr.push(mid);
        if (arr.length > 200) arr = arr.slice(arr.length - 200);
        chrome.storage.local.set({ readAdminMsgIds: arr }, function(){
            if (chrome.runtime && chrome.runtime.lastError) { console.warn("[AnonVPN] storage.set failed:", chrome.runtime.lastError.message); }
        });
    });
    // Немедленный read-receipt серверу (fire-and-forget; продублируется на след. открытии
    // popup через fetchSystemMessages – на случай если этот запрос не дошёл).
    if (isFinite(mid)) {
        try {
            chrome.runtime.sendMessage({ action: 'getUserMessages', readIds: [mid] }, function(){
                void (chrome.runtime && chrome.runtime.lastError);
            });
        } catch (_e) {}
    }
    // Если больше нет системных сообщений, требующих внимания – снять бейдж NEW.
    chrome.storage.local.get(['seenSysMsgIds'], function(d){
        var seen = Array.isArray(d.seenSysMsgIds) ? d.seenSysMsgIds : [];
        if (!_sysMsgNeedsAttention(_sysMsgItems, seen)) {
            var bdg = tabNews && tabNews.querySelector('.news-badge');
            if (bdg) bdg.remove();
        }
    });
}

// Помечает keyexp-сообщения увиденными (seenSysMsgIds). Админ-сообщения НЕ трогает –
// они «прочитываются» только кнопкой «Прочитано».
function _markKeyexpSeen(items) {
    if (!Array.isArray(items)) return;
    var ke = items.filter(function(it){ return it.kind === 'keyexp'; });
    if (!ke.length) return;
    chrome.storage.local.get(['seenSysMsgIds'], function(d){
        var seen = Array.isArray(d.seenSysMsgIds) ? d.seenSysMsgIds.slice() : [];
        var changed = false;
        ke.forEach(function(it){ if (seen.indexOf(it.id) < 0) { seen.push(it.id); changed = true; } });
        if (seen.length > 100) seen = seen.slice(seen.length - 100);
        if (changed) chrome.storage.local.set({ seenSysMsgIds: seen }, function(){
            if (chrome.runtime && chrome.runtime.lastError) { console.warn("[AnonVPN] storage.set failed:", chrome.runtime.lastError.message); }
        });
    });
}

// Вызывается при открытии вкладки «Новости»: рендер + отметка keyexp увиденными.
function loadSystemMessages() {
    var go = function(items){ renderSystemMessages(items); _markKeyexpSeen(items); };
    if (_sysMsgItems) go(_sysMsgItems);
    else fetchSystemMessages(go);
}

// Бейдж NEW + авто-переход на «Новости», если есть системное сообщение, требующее внимания
// (непрочитанное админ-сообщение или новый keyexp-бакет).
function checkSysMsgBadge() {
    fetchSystemMessages(function(items){
        if (!Array.isArray(items) || !items.length) return;
        chrome.storage.local.get(['seenSysMsgIds'], function(d){
            var seen = Array.isArray(d.seenSysMsgIds) ? d.seenSysMsgIds : [];
            if (!_sysMsgNeedsAttention(items, seen)) return;
            if (tabNews && !tabNews.querySelector('.news-badge')) {
                var b = document.createElement('span');
                b.className = 'news-badge'; b.textContent = 'NEW';
                tabNews.appendChild(b);
            }
            // Авто-переход на «Новости». Общий флаг _newsAutoSwitched с news.json-переключением
            // (1 раз за сессию popup). Только если юзер ещё на «Главной». Без !isVpnOn-гейта.
            if (!_newsAutoSwitched && tabNews) {
                var mainTab = document.querySelector('.tab-btn[data-tab="main"]');
                if (mainTab && mainTab.classList.contains('active')) {
                    _newsAutoSwitched = true;
                    tabNews.click();
                }
            }
        });
    });
}

// ═══ EVENT HANDLERS ═══

// [v2.5.9] Returns the free/premium list index of `proxy` in cachedProxyList (or -1)
function getServerLoadFor(proxy) {
    if (!proxy || !Array.isArray(cachedProxyList)) return null;
    var freeList = cachedProxyList.filter(function(p){return p.type!=='premium';});
    var premList = cachedProxyList.filter(function(p){return p.type==='premium';});
    // [v2.7.3 fix] Port в raw proxyList приходит как number ИЛИ string (sw:1257
    // `typeof p.port === 'number' || 'string'`). После JSON-roundtrip через storage
    // может измениться тип. Строгое `===` сравнение фейлило → функция возвращала null →
    // `load >= 75` false → confirm-диалог перегрузки не показывался. SW уже использует
    // `String() === String()` (sw:1480, 2022); делаем симметрично в popup.
    var pPort = String(proxy.port);
    var idx;
    // [v2.8.1] cachedServerStats indexed by host:port – match достаточно по host+port.
    var _sk = _serverKey(proxy);
    if (!_sk) return null;
    if (proxy.type === 'premium') {
        for (idx = 0; idx < premList.length; idx++) {
            if (premList[idx].host === proxy.host && String(premList[idx].port) === pPort) {
                return serverUserCounts[_sk] || 0;
            }
        }
    } else {
        for (idx = 0; idx < freeList.length; idx++) {
            if (freeList[idx].host === proxy.host && String(freeList[idx].port) === pPort) {
                return serverUserCounts[_sk] || 0;
            }
        }
    }
    return null;
}

// [v2.5.9] Predicts which server SW will actually use on toggle ON.
// Mirrors maybeAutoSelectServer logic in service_worker.js.
function predictConnectServer(cb) {
    chrome.storage.local.get(['autoSelectServer','autoSelectScope','isPremium','selectedProxy'], function(d){
        var autoOn = d.autoSelectServer !== false;
        var isPrem = !!d.isPremium;
        if (autoOn && Array.isArray(cachedProxyList) && cachedProxyList.length) {
            var scope = isPrem ? (d.autoSelectScope || 'free') : 'free';
            var picked = pickBestServerLocal(cachedProxyList, scope, isPrem);
            if (picked) { cb(picked.proxy); return; }
        }
        cb(d.selectedProxy || null);
    });
}

// [v2.5.9] Actual VPN connect/disconnect flow – extracted so overload confirmation can gate it.
function performVpnToggle() {
    // [v2.5.9] User manually toggling → dismiss session-expired banner and clear flag
    if (!isVpnOn) hideSessionExpiredBanner(true);
    vpnToggleBtn.disabled = true;
    vpnToggleBtn.classList.add('loading');
    var timerEl = $('timer');
    var connecting = !isVpnOn;
    if (timerEl && connecting) {
        // [v3.0.3] Спиннер + «Connecting…» через DOM (без innerHTML – не триггерим CWS-сканер).
        // На success перетрётся updateTimer (textContent), на failure снимется _clearConnectSpinner().
        timerEl.textContent = '';
        var _cspin = document.createElement('span');
        _cspin.className = 'inline-spinner';
        timerEl.appendChild(_cspin);
        timerEl.appendChild(document.createTextNode(t('connecting', 'Connecting...')));
        /* CSP: color in CSS */
        timerEl.classList.add('timer-active');
    }

    // [v2.7.0 fix F29] Hard timeout 12 sec – SW может умереть mid-handler без отправки
    // response (MV3 lifecycle). Без этого callback never fires → button stays loading
    // forever. 12 сек = SW timeout 10s + 2s margin.
    var _toggleResponded = false;
    var _toggleTimer = setTimeout(function(){
        if (_toggleResponded) return;
        _toggleResponded = true;
        vpnToggleBtn.disabled = false;
        vpnToggleBtn.classList.remove('loading');
        _clearConnectSpinner(); // [v3.0.3] timeout-терминал – снять спиннер «Connecting…»
        if (timerEl && !isVpnOn) timerEl.classList.remove('timer-active');
        // [v2.7.0 fix F72] Различаем «нет интернета» и «proxy недоступен». navigator.onLine
        // false = юзер реально offline → показать соответствующее сообщение вместо
        // «Try another server» (который бесполезен при отсутствии сети).
        if (typeof navigator !== 'undefined' && navigator.onLine === false) {
            showStatusMessage(t('offlineError', 'Device is offline. Check your internet connection.'), true, 'vpn');
        } else {
            showStatusMessage(t('connectionTimeout', 'Connection timeout. Try another server.'), true, 'vpn');
        }
    }, 12000);
    chrome.runtime.sendMessage({ action: 'toggleProxy' }, res => {
        if (_toggleResponded) return;
        _toggleResponded = true;
        clearTimeout(_toggleTimer);
        vpnToggleBtn.disabled = false;
        vpnToggleBtn.classList.remove('loading');
        _clearConnectSpinner(); // [v3.0.3] ответ-терминал – снять спиннер (на success его и так перетрёт отсчёт)
        if (chrome.runtime.lastError || !res || res.error) {
            if(timerEl && !isVpnOn){timerEl.classList.remove('timer-active');}
            if(res && res.error === 'timeout') {
                // [v2.7.0 fix F72] См. выше – «offline» приоритетнее «timeout» в UI.
                if (typeof navigator !== 'undefined' && navigator.onLine === false) {
                    showStatusMessage(t('offlineError','Device is offline. Check your internet connection.'), true, 'vpn');
                } else {
                    showStatusMessage(t('connectionTimeout','Connection timeout. Try another server.'), true, 'vpn');
                }
            } else if (res && res.error === 'storage_quota_exceeded') {
                // [v2.7.1 fix F93] Storage quota exceeded – направляем юзера на Clear Cache.
                showStatusMessage(t('storageLimitExceeded','Storage full. Clear cache in Settings → Diagnostics.'), true, 'vpn');
            } else if (res && res.error === 'busy') {
                // [v2.7.1 fix F120] SW занят (concurrent toggle) – graceful retry hint
                // вместо generic «error». Юзер видит «уже подключаемся, подождите».
                showStatusMessage(t('toggleBusy','Подождите завершения предыдущего действия'), true, 'vpn');
            } else if (res && res.error === 'ping_active') {
                // [v2.7.4 audit r6] Pinger активен в SW – toggle отвергнут до завершения проверки.
                // Раньше попадало в silent default → юзер не понимает почему toggle не сработал.
                showStatusMessage(t('toggleBusy','Подождите завершения предыдущего действия'), true, 'vpn');
            } else if (res && res.error === 'vpn_conflict') {
                // [v2.8.2 vpn-conflict-block] SW отказал из-за активного другого VPN – баннер
                // уже показан выше, дополнительно подсвечиваем причину.
                // CLAUDE.md: hardcoded fallback на английском (non-ru/en юзеры видят его).
                showStatusMessage(t('vpnConflictBlocked','Disable other VPN extensions first'), true, 'vpn');
            }
            return;
        }
        toggle.checked = res.proxyEnabled;
        isVpnOn = res.proxyEnabled;
        updateVpnButtonUI(res.proxyEnabled);
        setVpnFieldsLocked(res.proxyEnabled);
        if (res.proxyEnabled) {
            startLocalTimer();
            // [v2.6.2] IP changed – force-refresh after a small delay so proxy is fully primed
            clearIpInfoCache();
            setTimeout(function(){ loadIpInfo(true); }, 800);
            // [v2.5.9] SW may have auto-picked a different server – sync the "Сервер:" label.
            chrome.storage.local.get(['selectedProxy'], function(d){
                if (!d.selectedProxy || !proxySelect) return;
                for (var i = 0; i < proxySelect.options.length; i++) {
                    var p = resolveProxyByKey(proxySelect.options[i].value);
                    if (p && p.host === d.selectedProxy.host && String(p.port) === String(d.selectedProxy.port)) {
                        proxySelect.selectedIndex = i;
                        updateServerBtnLabel();
                        break;
                    }
                }
            });
        } else {
            if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
            updateTimerDisplay(0);
            // [v2.6.2] IP changed back to real – refresh
            clearIpInfoCache();
            setTimeout(function(){ loadIpInfo(true); }, 500);
            loadProxies(); recheckPremiumFromServer(); checkNewsBadge();
            if (newsLoaded) {
                newsLoaded = false;
                const newsTab = document.querySelector('.tab-btn[data-tab="news"]');
                if (newsTab && newsTab.classList.contains('active')) { loadNews(); newsLoaded = true; }
            }
        }
    });
}

// [v2.5.9] Overload confirmation modal – uses a module-level callback slot so
// click-handlers can be registered ONCE on DOMContentLoaded (no per-call addEventListener
// which previously leaked when user dismissed via overlay-click without firing cleanup).
// Two levels: high (≥100) – red/critical, medium (75–99) – orange/elevated.
var _overloadConfirmCb = null;

function _overloadConfirmResolve(result) {
    var cb = _overloadConfirmCb;
    _overloadConfirmCb = null;
    closeModal('overloadConfirmModal');
    if (cb) cb(result);
}

function showOverloadConfirm(load, cb) {
    var isHigh = load >= 100;
    var modal = $('overloadConfirmModal');
    var box = modal && modal.querySelector('.overload-confirm-box');
    if (box) {
        box.classList.toggle('overload-confirm-high', isHigh);
        box.classList.toggle('overload-confirm-medium', !isHigh);
    }
    var titleEl = $('overloadConfirmTitle');
    var textEl = $('overloadConfirmText');
    if (titleEl) {
        titleEl.textContent = isHigh
            ? t('overloadConfirmTitleHigh', 'Critical server load')
            : t('overloadConfirmTitle', 'Elevated server load');
    }
    if (textEl) {
        var tmpl = isHigh
            ? t('overloadConfirmTextHigh', 'The selected server is overloaded ({n} users). Connection may be unstable. Continue anyway?')
            : t('overloadConfirmText', 'The selected server may be experiencing elevated load ({n} users). Connection may be slower than usual. Continue?');
        // [v2.6.5 audit] DOM API вместо innerHTML – см. комментарий в applyTranslations.
        renderOverloadConfirmText(textEl, tmpl, load);
    }
    // If a previous cb is still pending (shouldn't normally happen), resolve as cancelled
    if (_overloadConfirmCb) {
        var prev = _overloadConfirmCb;
        _overloadConfirmCb = null;
        try { prev(false); } catch {}
    }
    _overloadConfirmCb = cb;
    openModal('overloadConfirmModal');
}

// [v2.5.9] Single registered handlers (once per DOMContentLoaded) – no leak.
$('overloadConfirmYes')?.addEventListener('click', function(){ _overloadConfirmResolve(true); });
$('overloadConfirmNo')?.addEventListener('click', function(){ _overloadConfirmResolve(false); });
document.querySelector('#overloadConfirmModal .modal-close')?.addEventListener('click', function(){
    // generic .modal-close handler (above) already calls closeModal; we just fire cb(false)
    var cb = _overloadConfirmCb;
    _overloadConfirmCb = null;
    if (cb) cb(false);
});

// [v3.1.6] Подтверждения при ручном выборе сервера без проверки / со сбоем проверки.
// Один общий callback (в один момент открыт только один такой диалог). Зеркалит overloadConfirm.
var _serverPickCb = null;
function _serverPickResolve(modalId, result){
    var cb = _serverPickCb; _serverPickCb = null;
    closeModal(modalId);
    if (cb) { try { cb(result); } catch(e){} }
}
function showServerNoPing(cb){
    if (_serverPickCb) { var p=_serverPickCb; _serverPickCb=null; try{p(false);}catch(e){} }
    _serverPickCb = cb; openModal('serverNoPingModal');
}
function showServerBroken(cb){
    if (_serverPickCb) { var p2=_serverPickCb; _serverPickCb=null; try{p2(false);}catch(e){} }
    _serverPickCb = cb; openModal('serverBrokenModal');
}
$('serverNoPingConnect')?.addEventListener('click', function(){ _serverPickResolve('serverNoPingModal', true); });
$('serverNoPingCancel')?.addEventListener('click', function(){ _serverPickResolve('serverNoPingModal', false); });
$('serverBrokenConnectAnyway')?.addEventListener('click', function(){ _serverPickResolve('serverBrokenModal', true); });
$('serverBrokenChooseOther')?.addEventListener('click', function(){ _serverPickResolve('serverBrokenModal', false); });
document.querySelector('#serverNoPingModal .modal-close')?.addEventListener('click', function(){ var cb=_serverPickCb; _serverPickCb=null; if(cb){try{cb(false);}catch(e){}} });
document.querySelector('#serverBrokenModal .modal-close')?.addEventListener('click', function(){ var cb=_serverPickCb; _serverPickCb=null; if(cb){try{cb(false);}catch(e){}} });
// [v3.1.6] Кнопка «?» в шапке выбора сервера → легенда обозначений (доступна всегда).
$('serverLegendBtn')?.addEventListener('click', function(){ openModal('serverLegendModal'); });
// [v3.1.6] Кнопка «Понятно» в легенде: класс не .modal-close (тот = крестик), поэтому глобальный
// data-close хендлер (стр. 531) её не ловит — вешаем явно (× сверху ловится глобально).
$('serverLegendGotIt')?.addEventListener('click', function(){ closeModal('serverLegendModal'); });

// [v2.7.3] Обработчики freeBlockedModal: кнопка «Закрыть» просто закрывает модал,
// «Активировать Premium» открывает premium-upsell.html с UTM medium="server_load_block"
// для отслеживания конверсии из этого CTA-пути.
$('freeBlockedCancel')?.addEventListener('click', function(){ closeModal('freeBlockedModal'); });
$('freeBlockedUpsell')?.addEventListener('click', function(){
    closeModal('freeBlockedModal');
    window.open(upsellUrl('server_load_block'), '_blank', 'noopener,noreferrer');
});
// [v2.8.5] checkerLockedModal – показывается free-юзеру без премиума/почты при «По пингу».
$('checkerLockedClose')?.addEventListener('click', function(){ closeModal('checkerLockedModal'); });
$('checkerLockedUpsell')?.addEventListener('click', function(){
    closeModal('checkerLockedModal');
    window.open(upsellUrl('checker_locked'), '_blank', 'noopener,noreferrer');
});

// [v2.9.1] Онбординг = только setup wizard (выбор критерия auto-select + bulk-ping).
// Legacy "Как пользоваться AnonVPN" modal удалён в 2.9.1 (старый sentinel onboardingSeen
// остаётся в KNOWN_STORAGE_KEYS для обратной совместимости с уже-проставленным state,
// но больше не используется логикой).
function _maybeShowOnboarding(){
    chrome.storage.local.get(['onboardingV2Done'], function(d){
        if (!d || !d.onboardingV2Done) {
            _showSetupMetricModal();
        }
    });
}

// [v2.9.1] Setup Metric Wizard – выбор критерия авто-выбора + опциональный bulk-ping
// При выборе ping/both пинговка обязательна (без неё метод бесполезен) – checkbox
// принудительно ON и заблокирован. Для load – checkbox опционален, default OFF.
// [v2.9.1] Безопасная подстановка перевода: если t() вернул ключ (перевод не найден)
// или translations ещё не загружены – берём hardcoded fallback по языку.
function _tSafe(key, fallbackMap, defaultFallback){
    var lang = (typeof getLang === 'function' ? getLang() : 'ru') || 'ru';
    var hardcoded = (fallbackMap && fallbackMap[lang]) || (fallbackMap && fallbackMap.en) || defaultFallback;
    if (typeof t !== 'function') return hardcoded;
    var v = t(key);
    // t() возвращает сам key если перевод не найден (lang[key]→en[key]→hardcoded);
    // считаем такой результат "нет перевода" → fallback на нашу карту
    if (!v || v === key) return hardcoded;
    return v;
}
// [v3.0.5] Мастер первичной настройки (заменил выбор метода автоподбора). Шаги: ключ → проверка → готово.
// Метод автоподбора по умолчанию 'ping' (По скорости), меняется в настройках. Показ – 1 раз на open popup
// после install/update (sentinel onboardingV2Done, стирается на апдейте). Хоткей до завершения → SW шлёт
// уведомление «откройте расширение» (см. service_worker). Завершение ставит onboardingV2Done=true.
var _setupCheckActive = false; // идёт ли диагностика ИЗ мастера (чтобы ловить её broadcast'ы)
var _setupModalOpen = false;   // открыт ли мастер (для внешних хуков premiumActivated/diag)
var _setupKeyTimer = null;     // fallback-таймаут ожидания активации ключа
var _setupCheckCompleted = false; // прошёл ли юзер проверку серверов (для reportSetupDone.checkPassed; с 3.1.2 метод подбора всегда 'ping')
var _setupSkipArmed = false; // [v3.1.2] 1-й клик «Пропустить» → красное предупреждение о риске плохого пинга, 2-й → реально пропустить

function _setupGoStep(step){
    ['setupStepKey','setupStepCheck','setupStepDone'].forEach(function(id){
        var el = $(id); if (el) el.hidden = (id !== step);
    });
}
// [v3.0.5] Состояние «проверка идёт»: ПРЯЧЕМ кнопку старта + «пропустить», показываем прогресс.
// (.setup-btn имеет display:block, поэтому прячем через style.display, а не hidden-атрибут.)
function _setupShowCheckRunning(running){
    var btn=$('setupStartCheck'), skip=$('setupCheckSkip'), prog=$('setupCheckProgress');
    var prompt=$('setupCheckPrompt'), warn=$('setupCheckWarn');
    if (btn){ btn.style.display = running ? 'none' : ''; btn.disabled = false; }
    if (skip) skip.hidden = !!running;
    if (prompt) prompt.hidden = !!running;                    // на время проверки – только живые шаги, без текста
    if (warn) warn.style.display = running ? 'none' : '';      // .setup-warning display:flex → прячем через style
    if (running && prog){ prog.hidden = false; prog.style.display=''; }
}
// [v3.0.5] Возобновить показ ИДУЩЕЙ проверки в мастере (popup переоткрыт во время неё): прячем кнопку,
// восстанавливаем шаги из diagProgress. Иначе показывалась свежая кнопка, заблокированная _fullDiagRunning.
function _setupResumeCheck(progress){
    _setupCheckActive = true;
    _fullDiagRunning = true;
    _diagProgId = 'setupCheckProgress'; _diagResId = 'fullDiagResult';
    _diagBuilt = false;
    var msg=$('setupCheckMsg'); if (msg){ msg.textContent=''; msg.className='settings-result'; }
    _setupShowCheckRunning(true);
    _diagBuildSteps(); _diagBuilt = true;
    if (progress && progress.phase) _diagRenderProgress(progress.phase, progress);
    else _diagSetStep(_diagStepRow('internet'), 'active');
}
function _showSetupMetricModal(){
    var modal = $('setupMetricModal'); if (!modal) return;
    // i18n (если ключа нет в translations – остаётся дефолтный русский из HTML)
    try {
        var setIf = function(id, key){ var el = $(id); if (el && typeof t === 'function'){ var v = t(key); if (v && v !== key) el.textContent = v; } };
        setIf('setupMetricTitle', 'setupTitle');
        setIf('setupMetricSub', 'setupSub');
        setIf('setupKeyPrompt', 'setupKeyPrompt');
        setIf('setupKeySkip', 'setupKeySkip');
        setIf('setupPremiumOkText', 'setupPremiumOk');
        setIf('setupCheckPrompt', 'setupCheckPrompt');
        setIf('setupCheckWarnText', 'setupCheckWarn');
        setIf('setupStartCheck', 'setupStartCheck');
        setIf('setupCheckSkip', 'setupCheckSkip');
        setIf('setupDoneText', 'setupDoneText');
        setIf('setupFinishBtn', 'setupFinishBtn');
        // [v3.1.5 audit i2] убран мёртвый t('premiumKeyPlaceholder') — ключа нет ни в одном из 48 языков
        // (гвард всегда глотал), placeholder берётся из HTML. Если нужна локализация — добавить ключ в 48 langs.
    } catch(_){}
    // Уже Premium → шаг ключа не нужен: скрываем его, стартуем с проверки, показываем плашку «Premium активен».
    chrome.storage.local.get(['isPremium','diagRunning','diagProgress','diagLastResult'], function(d){
        d = d || {};
        var isPrem = !!d.isPremium;
        var okText = $('setupPremiumOkText'); if (okText) okText.hidden = !isPrem;
        _setupModalOpen = true;
        var now = Date.now();
        // Проверка идёт (popup переоткрыт во время неё) → возобновляем её показ, а не рисуем свежую
        // кнопку (её заблокировал бы _fullDiagRunning от _diagRecover). Завершилась пока закрыт → «Готово».
        var running = d.diagRunning && (now - (d.diagRunning.ts||0) < 5*60*1000);
        var doneWhileClosed = !running && d.diagLastResult && d.diagLastResult.ts && (now - d.diagLastResult.ts < 5*60*1000);
        if (running){
            _setupGoStep('setupStepCheck');
            _setupResumeCheck(d.diagProgress);
        } else if (doneWhileClosed){
            _setupCheckCompleted = true; // проверка завершилась пока popup был закрыт → дефолт 'ping'
            _setupApplyDoneOutcome(d.diagLastResult);
            _setupGoStep('setupStepDone');
        } else {
            _setupGoStep(isPrem ? 'setupStepCheck' : 'setupStepKey');
        }
        openModal('setupMetricModal');
    });
}
// Завершение: метод по умолчанию 'ping', снимаем sentinel (→ больше не показываем + SW снимет хоткей-гейт).
function _setupFinish(){
    _setupModalOpen = false;
    _setupCheckActive = false; _diagProgId = 'fullDiagProgress'; _diagResId = 'fullDiagResult'; // сброс состояния мастера
    // [v3.1.2] ВСЕГДА 'ping' – даже при пропуске проверки. Раньше пропуск → 'load' (по нагрузке
    // вслепую), что давало 30.8% churn <10мин у пропустивших (анализ аудитории 3.1.1: слепой
    // подбор мог дать сервер, недоступный у юзера → «не включается» → удаляют). Теперь ghost-ping
    // наполняет пинги в фоне сам (3 сервера/5мин), поэтому 'ping' осмыслен и без ручной проверки:
    // первые минуты пингов ещё мало → pickBestServer сам делает fallback на 'load' (регресса нет),
    // а через 5-10 мин подбор идёт по свежим RTT. serverSortMode тоже 'ping' → список отсортирован.
    // Затем ПЕРЕ-ПОДБИРАЕМ сервер – иначе на главной оставался ✗-сервер (авто-пик во время
    // диагностики шёл по 'load', method ещё не выставлен). reAutoPickAndRefresh исключает битые.
    var _m = 'ping';
    chrome.storage.local.set({ autoSelectMethod: _m, serverSortMode: _m, onboardingV2Done: true }, function(){
        if (chrome.runtime && chrome.runtime.lastError){ console.warn('[AnonVPN] setup save fail:', chrome.runtime.lastError.message); closeModal('setupMetricModal'); return; }
        try { _currentSortMode = _m; } catch(_){}
        try { if (typeof applyAutoSelectUI === 'function') applyAutoSelectUI(); } catch(_){}
        try { updateAutoSelMethodText(); } catch(_){}
        try { if (typeof updateSortModeUI === 'function') updateSortModeUI(); } catch(_){}
        try { if (typeof reAutoPickAndRefresh === 'function') reAutoPickAndRefresh(); } catch(_){}
        closeModal('setupMetricModal');
        // [v3.1.1] Сигнал серверу о завершении первичной настройки (SW шлёт ОДИН раз при первой
        // установке – для воронки install→setup). checkPassed = прошёл проверку серверов (не пропустил);
        // workingServers = сколько рабочих нашлось (0 = не смог подключиться → риск удаления).
        try {
            var _ws = 0;
            try { var _v = (typeof _lastDiagResult !== 'undefined' && _lastDiagResult && typeof computeDiagVerdict === 'function') ? computeDiagVerdict(_lastDiagResult) : null; _ws = _v ? (_v.working | 0) : 0; } catch (_e) {}
            chrome.runtime.sendMessage({ action: 'reportSetupDone', payload: { checkPassed: !!_setupCheckCompleted, workingServers: _ws } }, function () { if (chrome.runtime && chrome.runtime.lastError) { /* SW asleep – ok, best-effort */ } });
        } catch (_e) {}
    });
}
// Успех активации ключа во время мастера. Детектим по storage.onChanged isPremium→true (см. listener
// ниже), а НЕ по premiumActivated – то сообщение шлёт сам popup и своим onMessage не ловится. Идемпотентно.
function _setupOnPremiumActivated(){
    if (!_setupModalOpen) return;
    var keyStep = $('setupStepKey');
    if (!keyStep || keyStep.hidden) return; // не на шаге ключа – игнор (уже прошли дальше)
    if (_setupKeyTimer){ clearTimeout(_setupKeyTimer); _setupKeyTimer = null; }
    var msg = $('setupKeyMsg');
    if (msg){ msg.textContent = _tSafe('setupKeyOk', { ru:'Premium активирован ✓', en:'Premium activated ✓' }, 'Premium activated'); msg.className='settings-result show ok'; }
    var okText = $('setupPremiumOkText'); if (okText) okText.hidden = false;
    setTimeout(function(){ _setupGoStep('setupStepCheck'); }, 1000);
}
// Хук: прогресс/финиш/ошибка диагностики, когда она запущена ИЗ мастера.
// Прогресс-шаги рисует сам _diagRenderProgress прямо в setupCheckProgress (_diagProgId) – отдельного
// хука прогресса не нужно. Здесь – только финиш/ошибка: вернуть цель diag на настроечную + перейти дальше.
// [v3.0.5] Текст/иконка шага «Готово» по РЕЗУЛЬТАТУ проверки: если рабочих серверов нет – честно
// показываем причину (вердикт диагностики, локализован), а не «всё готово».
// [v3.1.1] Проверка конфликтов в мастере первичной настройки: установленные VPN/proxy-расширения
// показываем как ПОДСКАЗКУ (не блок). Новый юзер сразу знает, что другой VPN может перехватывать
// трафик – частая причина «включил AnonVPN, а IP реальный». Пусто/скрыто, если конфликтов нет или
// нет доступа к списку расширений (management). Кнопки НЕ блокирует.
function _setupCheckConflicts(){
    var el = $('setupConflictWarn');
    if (!el) return;
    el.hidden = true;
    try {
        hasManagementPermission(function(has){
            if (!has) return;
            enumerateProxyExtensions(function(list){
                if (!list || !list.length) return;
                var names = list.map(function(e){ return e.name; }).join(', ');
                var pre = _tSafe('setupConflictPre', { ru:'⚠ Обнаружены другие VPN-расширения: ', en:'⚠ Other VPN extensions detected: ' }, 'Other VPN detected: ');
                var suf = _tSafe('setupConflictSuf', { ru:'. Держите их выключенными, пока пользуетесь AnonVPN – иначе они могут перехватывать трафик, и ваш IP не сменится.', en:'. Keep them off while using AnonVPN – otherwise they may intercept traffic and your IP won’t change.' }, '');
                el.textContent = pre + names + suf;
                el.hidden = false;
            });
        });
    } catch (_) {}
}
function _setupApplyDoneOutcome(R){
    var v = (R && typeof computeDiagVerdict === 'function') ? computeDiagVerdict(R) : null;
    var good = !v || ((v.code === 'all_ok' || v.code === 'partial') && (v.working||0) > 0);
    var txt = $('setupDoneText'), icon = document.querySelector('#setupStepDone .setup-done-check');
    var fbtn = $('setupFinishBtn'), retry = $('setupRetryBtn');
    if (good){
        if (icon){ icon.textContent = '✓'; icon.classList.remove('setup-done-warn'); }
        if (txt) txt.textContent = _tSafe('setupDoneText', { ru:'Всё готово! Закройте это окно и нажмите «Включить ВПН».', en:'All set! Close this window and press “Turn on VPN”.' }, 'All set!');
        if (fbtn) fbtn.textContent = _tSafe('setupFinishBtn', { ru:'Отлично', en:'Great' }, 'Great');
        if (retry) retry.hidden = true;
    } else {
        if (icon){ icon.textContent = '⚠'; icon.classList.add('setup-done-warn'); }
        var vmsg = '';
        try { if (v && v.code && typeof t === 'function'){ var raw = t('diagV_'+v.code+'_m'); if (raw && raw !== 'diagV_'+v.code+'_m') vmsg = raw.replace('{working}', String(v.working||0)).replace('{total}', String(v.total||0)).replace('{until}',''); } } catch(_){}
        var generic = _tSafe('setupDoneFail', { ru:'Рабочих серверов сейчас не нашлось – возможно, их блокирует провайдер или антивирус. Попробуйте позже или смените сеть (моб. интернет/Wi-Fi).', en:'No working servers right now – they may be blocked by your ISP or antivirus. Try again later or switch your network (mobile/Wi-Fi).' }, 'No working servers right now.');
        if (txt) txt.textContent = vmsg || generic;
        // Не «Отлично» на ошибке: закрыть + предложить повтор.
        if (fbtn) fbtn.textContent = _tSafe('setupCloseBtn', { ru:'Закрыть', en:'Close' }, 'Close');
        if (retry){ retry.textContent = _tSafe('setupRetryBtn', { ru:'Попробовать снова', en:'Try again' }, 'Try again'); retry.hidden = false; }
    }
    _setupCheckConflicts();
}
// Пропуск проверки: нейтральный итог (не успех и не ошибка).
function _setupApplyDoneSkipped(){
    var txt = $('setupDoneText'), icon = document.querySelector('#setupStepDone .setup-done-check');
    var fbtn = $('setupFinishBtn'), retry = $('setupRetryBtn');
    if (icon){ icon.textContent = '✓'; icon.classList.remove('setup-done-warn'); }
    if (txt) txt.textContent = _tSafe('setupDoneSkipped', { ru:'Настройка завершена. Нажмите «Включить ВПН». Если не подключится – запустите проверку серверов в настройках.', en:'Setup complete. Press “Turn on VPN”. If it doesn’t connect, run the server check in settings.' }, 'Setup complete.');
    if (fbtn) fbtn.textContent = _tSafe('setupFinishBtn', { ru:'Отлично', en:'Great' }, 'Great');
    if (retry) retry.hidden = true;
    _setupCheckConflicts();
}
function _setupOnDiagDone(){
    if (!_setupCheckActive) return;
    _setupCheckActive = false;
    _setupCheckCompleted = true; // проверка пройдена → дефолт 'ping'
    _diagProgId = 'fullDiagProgress'; _diagResId = 'fullDiagResult'; // вернуть цель для диагностики из настроек
    _setupApplyDoneOutcome(_lastDiagResult);
    setTimeout(function(){ _setupGoStep('setupStepDone'); }, 600);
}
function _setupOnDiagError(){
    if (!_setupCheckActive) return;
    _setupCheckActive = false;
    _diagProgId = 'fullDiagProgress'; _diagResId = 'fullDiagResult';
    var msg = $('setupCheckMsg'), prog = $('setupCheckProgress');
    _setupShowCheckRunning(false); // вернуть кнопку «Начать проверку» + «Пропустить»
    if (prog){ prog.style.display='none'; prog.innerHTML=''; prog.hidden = true; }
    if (msg){ msg.textContent = _tSafe('setupCheckErr', { ru:'Проверка не удалась – можно пропустить.', en:'Check failed – you can skip.' }, 'Check failed'); msg.className='settings-result show err'; }
}

// ── Обвязка мастера ──
$('setupMetricClose')?.addEventListener('click', function(){ _setupModalOpen = false; closeModal('setupMetricModal'); });
// Шаг «ключ»: OK → переиспользуем основную активацию (premiumKey/activateKey); успех придёт broadcast'ом premiumActivated.
$('setupKeyActivate')?.addEventListener('click', function(){
    var inp = $('setupKeyInput'); var v = (inp && inp.value || '').trim();
    var msg = $('setupKeyMsg');
    if (!v){ if (msg){ msg.textContent = _tSafe('setupKeyEmpty', { ru:'Введите ключ или пропустите', en:'Enter a key or skip' }, 'Enter a key'); msg.className='settings-result show err'; } return; }
    var main = $('premiumKey'), mainBtn = $('activateKey');
    if (main && mainBtn){
        main.value = v;
        if (msg){ msg.textContent = _tSafe('setupKeyChecking', { ru:'Проверяем ключ…', en:'Checking the key…' }, 'Checking…'); msg.className='settings-result show'; }
        mainBtn.click();
        // Успех придёт через storage.onChanged (isPremium→true) → _setupOnPremiumActivated. Fallback-таймаут
        // на случай неверного ключа/сети: активация не поднимет isPremium → показываем «не удалось».
        if (_setupKeyTimer) clearTimeout(_setupKeyTimer);
        _setupKeyTimer = setTimeout(function(){
            _setupKeyTimer = null;
            var m2 = $('setupKeyMsg');
            if (m2){ m2.textContent = _tSafe('setupKeyFail', { ru:'Не удалось активировать. Проверьте ключ или пропустите.', en:'Activation failed. Check the key or skip.' }, 'Activation failed'); m2.className='settings-result show err'; }
        }, 12000);
    }
});
$('setupKeyInput')?.addEventListener('keydown', function(e){ if (e.key === 'Enter'){ e.preventDefault(); $('setupKeyActivate')?.click(); } });
$('setupKeySkip')?.addEventListener('click', function(){ _setupGoStep('setupStepCheck'); });
// Шаг «проверка»: полная диагностика с прогрессом в мастере. Скип → готово.
function _setupRunCheck(){
    var msg = $('setupCheckMsg');
    if (isVpnOn){ if (msg){ msg.textContent = _tSafe('diagTurnOffVpn', { ru:'Сначала выключите ВПН', en:'Turn off VPN first' }, 'Turn off VPN first'); msg.className='settings-result show err'; } return; }
    if (_fullDiagRunning) return;
    _setupCheckActive = true;
    _fullDiagRunning = true; _diagFinished = false; _diagConn = 0; _diagBuilt = false;
    // [v3.0.5] Наводим diag-рендер на контейнер мастера → те же ЖИВЫЕ шаги (интернет→API→серверы→сайты),
    // что и полная диагностика. Вердикт уходит в (скрытый) settings-блок; в мастере – шаги + переход «Готово».
    _diagProgId = 'setupCheckProgress'; _diagResId = 'fullDiagResult';
    if (msg){ msg.textContent=''; msg.className='settings-result'; }
    _setupShowCheckRunning(true); // прячем кнопку старта + «пропустить», показываем прогресс
    _diagBuildSteps(); _diagBuilt = true; _diagSetStep(_diagStepRow('internet'), 'active'); // сразу показать шаги, как в настройках
    chrome.runtime.sendMessage({ action:'runFullDiagnosis' }, function(resp){
        if (chrome.runtime && chrome.runtime.lastError) return;
        if (resp && resp.error){ _setupOnDiagError(); return; }
        if (resp && resp.ok && resp.result){ _setupOnDiagDone(); } // обычно приходит broadcast'ом diagDone
    });
}
$('setupStartCheck')?.addEventListener('click', _setupRunCheck);
// «Попробовать снова» на шаге результата (проверка не нашла рабочих) → назад к проверке + запуск.
$('setupRetryBtn')?.addEventListener('click', function(){ _setupGoStep('setupStepCheck'); _setupRunCheck(); });
$('setupCheckSkip')?.addEventListener('click', function(){
    // [v3.1.2] 1-й клик — КРАСНОЕ предупреждение про плохой пинг для региона. Пропуск проверки →
    // autoSelectMethod='ping' (метод «по нагрузке» убран в 3.1.3), пинги догоняет ghost-ping в фоне.
    if (!_setupSkipArmed){
        _setupSkipArmed = true;
        var _w = $('setupCheckWarn'); if (_w) _w.classList.add('danger');
        var _wt = $('setupCheckWarnText');
        if (_wt){ var _dv = (typeof t==='function') ? t('setupSkipDanger') : ''; _wt.textContent = (_dv && _dv!=='setupSkipDanger') ? _dv : 'Велика вероятность попасть на сервер с плохим пингом для вашего региона — ВПН будет медленным. Рекомендуем пройти проверку.'; }
        var _sk = $('setupCheckSkip'); if (_sk){ var _cv = (typeof t==='function') ? t('setupSkipConfirm') : ''; _sk.textContent = (_cv && _cv!=='setupSkipConfirm') ? _cv : 'Всё равно пропустить →'; }
        return;
    }
    // Пропуск: отвязываем мастер от проверки (SW-диагностика доработает в фоне) + нейтральный итог.
    _setupCheckActive = false; _setupCheckCompleted = false; // пропущена → _setupFinish ставит 'ping'
    _diagProgId = 'fullDiagProgress'; _diagResId = 'fullDiagResult';
    _setupApplyDoneSkipped();
    _setupGoStep('setupStepDone');
});
$('setupFinishBtn')?.addEventListener('click', _setupFinish);
// [v3.0.5] Успех активации ключа в мастере ловим по storage.onChanged (isPremium→true): основная
// активация шлёт premiumActivated через runtime.sendMessage, но СВОЙ же onMessage его не получает.
chrome.storage.onChanged.addListener(function(changes, area){
    if (area !== 'local' || !changes.isPremium) return;
    if (changes.isPremium.newValue === true) { try { _setupOnPremiumActivated(); } catch(_){} }
});

// [v2.9.1] Bulk-ping: запускает SW handler bulkPingTopServers, показывает прогресс-индикатор.
// Прогресс приходит через chrome.runtime.onMessage (bulkPingProgress / bulkPingDone).
// [audit fix high-3] Если SW уже пингует (ping_busy) – не дублируем индикатор-start;
// просто ничего не делаем (прогресс уже придёт broadcast'ами от текущего run).
function _startBulkPing(){
    var ind = $('bulkPingProgress');
    var txt = $('bulkPingProgressText');
    var bar = $('bulkPingBarFill');
    if (ind) ind.hidden = false;
    if (txt) txt.textContent = _tSafe('bulkPingStarting', { ru:'Запускаем проверку…', en:'Starting check…' }, 'Starting check…');
    if (bar) bar.style.width = '0%';
    chrome.runtime.sendMessage({action:'bulkPingTopServers'}, function(res){
        if (chrome.runtime.lastError || !res) {
            if (txt) txt.textContent = _tSafe('bulkPingError', { ru:'Не получилось запустить проверку', en:'Could not start the check' }, 'Check failed');
            setTimeout(function(){ if (ind) ind.hidden = true; }, 3000);
            return;
        }
        if (res.error === 'ping_busy') {
            // SW уже пингует – не показываем error, индикатор останется, broadcast'ы догонят.
            return;
        }
        if (res.error === 'premium_required') {
            // [v2.9.1] Free-юзер пытается re-run. Показываем premium-prompt с upsell.
            // [audit fix high] Click на индикатор открывает Premium tab – раньше юзер
            // видел сообщение «только с Premium» без понятного next-action.
            if (txt) txt.textContent = _tSafe('bulkPingPremiumRequired', {
                ru:'Повторная проверка серверов – только с Premium',
                en:'Re-checking servers requires Premium'
            }, 'Premium required');
            if (ind) {
                ind.style.cursor = 'pointer';
                ind.title = _tSafe('buyPremiumButton', { ru:'Купить Premium', en:'Buy Premium' }, 'Buy Premium');
                var upsellClick = function(){
                    try {
                        var tab = $('tab-premium-btn') || document.querySelector('[data-tab="premium"]');
                        if (tab) tab.click();
                    } catch(_){}
                    if (ind) { ind.hidden = true; ind.style.cursor = ''; ind.removeAttribute('title'); }
                    ind && ind.removeEventListener('click', upsellClick);
                };
                ind.addEventListener('click', upsellClick);
            }
            setTimeout(function(){
                if (ind) {
                    ind.hidden = true;
                    ind.style.cursor = '';
                    ind.removeAttribute('title');
                    // [audit fix should] Очистка listener'а – иначе при multiple premium_required
                    // в одном popup-сеансе на ind накапливаются upsellClick handlers.
                    try { ind.removeEventListener('click', upsellClick); } catch(_){}
                }
            }, 6000);
            return;
        }
        if (res.error) {
            if (txt) txt.textContent = _tSafe('bulkPingError', { ru:'Не получилось запустить проверку', en:'Could not start the check' }, 'Check failed');
            setTimeout(function(){ if (ind) ind.hidden = true; }, 3000);
            return;
        }
        // started:true – прогресс придёт broadcast'ом
    });
}
// [audit fix high-4] При init popup'а проверяем – может в SW сейчас идёт bulk-ping.
// Storage bulkPingProgress={done,total,ts} ставится SW на каждой итерации, чистится
// на done. Если есть свежий (≤5 мин – bulk не может идти дольше) – показываем индикатор.
function _restoreBulkPingProgressIfRunning(){
    chrome.storage.local.get(['bulkPingProgress'], function(d){
        if (!d || !d.bulkPingProgress) return;
        var p = d.bulkPingProgress;
        if (typeof p.done !== 'number' || typeof p.total !== 'number') return;
        var age = Date.now() - (Number(p.ts) || 0);
        if (age > 10 * 60 * 1000) return; // [audit fix high] TTL 10 мин – bulk-ping всех free может занять 5-7 мин; 5-мин TTL был слишком жёстким
        var ind = $('bulkPingProgress');
        var txt = $('bulkPingProgressText');
        var bar = $('bulkPingBarFill');
        if (!ind || !txt || !bar) return;
        ind.hidden = false;
        var template = _tSafe('bulkPingProgress', { ru:'Проверяем серверы: {done} из {total}', en:'Checking servers: {done} of {total}' }, 'Checking: {done}/{total}');
        var label = template.replace('{done}', String(p.done)).replace('{total}', String(p.total));
        txt.textContent = label;
        var pct = p.total > 0 ? Math.round((p.done / p.total) * 100) : 0;
        bar.style.width = pct + '%';
    });
}
setTimeout(_restoreBulkPingProgressIfRunning, 100);
// Слушаем broadcast от SW
chrome.runtime.onMessage.addListener(function(msg){
    if (!msg || !msg.action) return;
    if (msg.action === 'bulkPingProgress') {
        var ind = $('bulkPingProgress');
        var txt = $('bulkPingProgressText');
        var bar = $('bulkPingBarFill');
        if (!ind || !txt || !bar) return;
        ind.hidden = false;
        var template = _tSafe('bulkPingProgress', { ru:'Проверяем серверы: {done} из {total}', en:'Checking servers: {done} of {total}' }, 'Checking: {done}/{total}');
        var label = template.replace('{done}', String(msg.done || 0)).replace('{total}', String(msg.total || 0));
        txt.textContent = label;
        var pct = msg.total > 0 ? Math.round((msg.done / msg.total) * 100) : 0;
        bar.style.width = pct + '%';
    } else if (msg.action === 'bulkPingDone') {
        var ind = $('bulkPingProgress');
        var txt = $('bulkPingProgressText');
        var bar = $('bulkPingBarFill');
        if (txt) txt.textContent = _tSafe('bulkPingDone', { ru:'Готово!', en:'Done!' }, 'Done!');
        if (bar) bar.style.width = '100%';
        setTimeout(function(){ if (ind) ind.hidden = true; }, 2500);
        // [v2.9.2 critical fix] КРИТИЧЕСКИЙ FIX: после bulk-ping завершения нужно re-pick
        // сервер, иначе UI остаётся со старым load-fallback'ом, пинги в storage есть,
        // но используются только при следующем reopen popup'а. Юзер видит "Готово!" +
        // тот же сервер что был при load → "не работает". Forced re-pick через
        // reAutoPickAndRefresh + перерендер dropdown через updateAutoSelMethodText.
        try { if (typeof reAutoPickAndRefresh === 'function') reAutoPickAndRefresh(); } catch(_){}
        try { updateAutoSelMethodText(); } catch(_){}
        // Перерендер server-select с новыми пингами в подписях (если он отображается).
        try { resetLoadProxiesRetry(); loadProxies(); } catch(_){}
    }
});
// Overlay click (outside the box) – generic handler removes 'active'; we fire cb(false)
$('overloadConfirmModal')?.addEventListener('click', function(e){
    if (e.target === this) {
        var cb = _overloadConfirmCb;
        _overloadConfirmCb = null;
        if (cb) cb(false);
    }
});

// VPN toggle button click
vpnToggleBtn?.addEventListener('click', () => {
    // Block if no servers available
    if (!isVpnOn && (!cachedProxyList || cachedProxyList.length === 0)) {
        showStatusMessage(noServersText(), true, 'vpn');
        return;
    }
    // [v2.5.9] Disconnect path – no confirmation
    if (isVpnOn) { performVpnToggle(); return; }
    // [v2.5.9] Connecting – warn if predicted server has elevated load (≥75 users)
    predictConnectServer(function(proxy){
        var load = getServerLoadFor(proxy);
        if (load !== null && load >= 75) {
            showOverloadConfirm(load, function(confirmed){
                if (confirmed) performVpnToggle();
            });
            return;
        }
        performVpnToggle();
    });
});

// [v2.7.1 fix F122] Multi-popup sync: на MacOS пользователь может открыть popup в
// двух окнах одновременно. Когда один меняет VPN/Premium state, второй showed stale UI
// до manual close+reopen. Storage.onChanged listener ловит критичные изменения и
// обновляет UI без ожидания broadcast от SW (broadcasts не достигают closed popup).
chrome.storage.onChanged.addListener(function(changes, area){
    if (area !== 'local') return;
    try {
        if (changes.proxyEnabled && typeof changes.proxyEnabled.newValue === 'boolean') {
            var newState = changes.proxyEnabled.newValue;
            if (isVpnOn !== newState) {
                isVpnOn = newState;
                if (toggle) toggle.checked = newState;
                updateVpnButtonUI(newState);
                setVpnFieldsLocked(newState);
            }
            // [v2.8.6] ВПН включился/выключился → перепроверить, кто владеет прокси.
            // Небольшая задержка – chrome.proxy.settings.set в SW мог ещё не устаканиться.
            setTimeout(function(){ try { checkProxyControl(); } catch (e) {} }, 800);
        }
        if (changes.isPremium) {
            // [v2.8.5 fix R4] Premium активирован → скрыть баннер «сессия закончилась»
            // (у Premium нет лимита 30/60-мин; checkSessionExpiredBannerOnInit чистит флаг
            // для Premium при следующем открытии – здесь покрываем popup, открытый в момент
            // активации Premium).
            if (changes.isPremium.newValue === true) { try { hideSessionExpiredBanner(true); } catch {} }
            updatePremiumUI();
            updatePremiumTabLock();
        }
        // [v2.7.4 audit] Multi-popup sync для soft update-banner: popup A pingует SW
        // checkLatestVersion → SW записывает updateAvailable → popup B (открыт параллельно)
        // должен показать баннер без reopen. Также покрывает dismiss-сценарий через другую
        // popup-инстанцию (хотя dismiss уже writes updateAvailableDismissed напрямую).
        if (changes.updateAvailable || changes.updateAvailableDismissed) {
            applyUpdateAvailableBanner();
        }
        // [v3.1.5 audit] hard update-required / illegal-ext баннер: soft 200-envelope путь в SW пишет
        // updateRequired в storage БЕЗ sendMessage → открытый popup не показывал баннер до reopen.
        // Крепим на onChanged (симметрично applyRateLimitBanner ниже).
        if (changes.updateRequired || changes.illegalExtId) {
            try { applyUpdateBanner(); } catch (e) {}
        }
        // [v2.7.4 audit r2] sessionExpired sync: SW writes flag на VPN_ALARM expiry (60-мин mark
        // после free-VPN-on). Edge case: popup открыт когда таймер срабатывает → без listener
        // banner не показывался до reopen. Покрывает + clear на dismiss из другого popup.
        if (changes.sessionExpired) {
            if (changes.sessionExpired.newValue) checkSessionExpiredBannerOnInit();
            else hideSessionExpiredBanner(false);
        }
        // [v2.8.0] rate-limit ban state – multi-popup sync
        if (changes.rateLimited || changes.rateLimitedReason || changes.rateLimitedUntil) {
            applyRateLimitBanner();
        }
        // [v2.8.4] proxyListFetchError – live-sync детализации «Нет серверов».
        // Если popup открыт во время фейла fetch'а в SW – обновляем in-memory флаг и,
        // если на экране пустой select, перерисовываем с актуальным текстом.
        if (changes.proxyListFetchError) {
            var nv = changes.proxyListFetchError.newValue;
            _proxyListFetchError = (nv === 'network' || nv === 'server') ? nv : null;
            if (typeof renderProxySelect === 'function' && Array.isArray(cachedProxyList) && cachedProxyList.length === 0) {
                try { renderProxySelect(cachedProxyList); } catch {}
            }
        }
        // [v2.8.0] Account-link state sync – popup A links → popup B updates.
        if (changes.accountVerified || changes.accountEmail || changes.isPremium || changes.sessionExpired) {
            try { applyAccountLinkUI(); } catch {}
        }
        // [v2.8.0] accountVerified change → пере-render premium-tab locks (checker
        // открывается verified-юзеру даже без Premium).
        if (changes.accountVerified) {
            try { updatePremiumTabLock(); } catch {}
        }
        // [v2.7.5 audit r3] Multi-popup sync для autoEnableEnabled и adBlockerEnabled –
        // без этого popup A toggle premium feature → popup B показывает stale switch state
        // до reload. Toggle также reapplies через applyPremiumState в SW для adBlocker.
        if (changes.autoEnableEnabled) {
            var aeSwitch = $('autoEnableToggle');
            if (aeSwitch) aeSwitch.checked = !!changes.autoEnableEnabled.newValue;
        }
        // [v2.8.1 audit] Multi-popup sync для списка доменов: popup A удалил → popup B
        // должен перерендерить модалку и счётчик. Без этого при открытой в обоих popup'ах
        // модалке юзер видел в B stale-список даже после reopen B-modal (storage.get
        // в loadAutoEnable читает свежий, но если B-modal уже открыт – без sync не обновится).
        if (changes.autoEnableDomains) {
            var aeNew = Array.isArray(changes.autoEnableDomains.newValue) ? changes.autoEnableDomains.newValue : [];
            try { renderAutoEnableList(aeNew); } catch {}
            try { updateAutoEnableCount(aeNew.length); } catch {}
        }
        // [v2.8.1 audit] Multi-popup sync для тем оформления – popup A меняет тему,
        // popup B без sync остаётся в старой палитре до reopen. applyTheme идемпотентен.
        if (changes.colorTheme && typeof changes.colorTheme.newValue === 'string') {
            // [v3.1.1] Whitelist по THEMES – симметрично init (6386): импорт настроек с мусорным
            // значением иначе вешает класс `theme-<мусор>` на body (безвредно, но DOM-мусор).
            var _nt = THEMES.some(function(t){ return t.id === changes.colorTheme.newValue; })
                ? changes.colorTheme.newValue : 'default';
            try { applyTheme(_nt); } catch {}
        }
        // [v2.8.1 audit] Sync списков исключений + режима. Если modal exclusions открыт
        // в popup B – re-render списков; счётчик в основном UI обновляется всегда.
        if (changes.blacklistDomains) {
            try {
                var blNew = Array.isArray(changes.blacklistDomains.newValue) ? changes.blacklistDomains.newValue : [];
                if ($('exclusionsModal')?.classList.contains('active')) renderExclList('blacklistItems', blNew, 'black');
                updateExclSummary();
            } catch {}
        }
        if (changes.whitelistDomains) {
            try {
                var wlNew = Array.isArray(changes.whitelistDomains.newValue) ? changes.whitelistDomains.newValue : [];
                if ($('exclusionsModal')?.classList.contains('active')) renderExclList('whitelistItems', wlNew, 'white');
                updateExclSummary();
            } catch {}
        }
        if (changes.exclusionsMode) {
            try { updateExclModeUI(); updateExclSummary(); } catch {}
        }
        // [v2.8.1 audit] favoriteServers + serverSortMode – popup A меняет, popup B
        // без sync видит stale ⭐/сортировку в server-modal. Пересобираем только если modal открыт.
        if (changes.favoriteServers) {
            try {
                favoriteServers = Array.isArray(changes.favoriteServers.newValue) ? changes.favoriteServers.newValue : [];
                if ($('serverModal')?.classList.contains('active')) buildServerModalList();
            } catch {}
        }
        // [v3.0.3] brokenServers (SW пометил сломанный туннель) → обновить карту + метку в списке.
        if (changes.brokenServers) {
            try {
                _refreshBrokenServers(function(){
                    if ($('serverModal') && $('serverModal').classList.contains('active')) buildServerModalList();
                });
            } catch (e) {}
        }
        if (changes.serverSortMode) {
            // [v2.8.5 fix R4] Multi-popup sync: popup A сменил сортировку → синхронизировать
            // _currentSortMode, иначе buildServerModalList в ЭТОМ popup отрисует список
            // СТАРЫМ режимом (sortServers/updateSortModeUI читают _currentSortMode).
            try {
                _currentSortMode = changes.serverSortMode.newValue || 'load';
                if ($('serverModal')?.classList.contains('active')) { updateSortModeUI(); buildServerModalList(); }
            } catch {}
        }
        if (changes.adBlockerEnabled) {
            var abSwitch = $('adBlockerToggle');
            // [v2.7.6] === true (default OFF) – symmetric с loadAdBlockerState.
            if (abSwitch) abSwitch.checked = (changes.adBlockerEnabled.newValue === true);
        }
        // [v2.7.6 audit Pass6] vpnConflictList sync – popup A после grant `management`
        // permission делает scan и пишет vpnConflictList; popup B без sync не обновляет
        // banner. Multi-popup edge case (rare, но F122 design goal – sync всех known keys).
        if (changes.vpnConflictList) {
            try { silentVpnConflictCheck(); } catch {}
        }
        // [v2.8.2 vpn-conflict-block] Multi-popup sync блок-флага: popup A детектировал
        // конфликт → SW и popup A заблокировали кнопки → popup B без sync остался unlocked.
        if (changes.vpnConflictBlocked) {
            try { applyVpnConflictBlock(changes.vpnConflictBlocked.newValue ? [{name:'_'}] : []); } catch {}
        }
        // [v2.7.6 audit Pass9] autoSelectScope multi-popup sync – popup A toggle premium →
        // SW writes autoSelectScope='all' → popup B без sync продолжает показывать old scope
        // в dropdown «Область авто-выбора» до reopen. updateServerBtnLabel чтобы UI отразить
        // новые available servers.
        if (changes.autoSelectScope) {
            try { updateServerBtnLabel(); } catch {}
            try { updateAutoSelMethodText(); } catch {} // [audit fix] scope влияет на pool – пересчитываем hasFresh
        }
        // [audit fix critical] Multi-popup sync для v2.9.1+ keys: autoSelectMethod, serverPings,
        // bulkPingProgress. Без листенеров popup A запускает bulk-ping → popup B держит stale
        // disabled-state у dropdown пока юзер не закроет/откроет popup.
        if (changes.autoSelectMethod || changes.serverPings) {
            try { updateAutoSelMethodText(); } catch {}
            // [v2.9.2 critical fix] Пинги обновились (multi-popup sync ИЛИ другой источник –
            // bulk-ping завершился в SW параллельно) → re-pick сервер, иначе UI держит старый
            // load-fallback выбор. На случай, если bulkPingDone broadcast не пришёл (popup
            // в другом окне открыт после bulk завершён) – этот handler покрывает edge case.
            if (changes.serverPings) {
                // [v3.1.2] Пинги обновились → re-pick авто-выбор + перерисовать пинги в UI из КЭША.
                // НЕ loadProxies: ghost пишет serverPings по одному серверу (каждые ~1.5с) → loadProxies
                // дёргал бы server-stats.json на КАЖДЫЙ пинг. Состав серверов и нагрузка от пинга не
                // меняются → сетевой фетч не нужен, рисуем из cachedProxyList/serverUserCounts.
                try { if (typeof reAutoPickAndRefresh === 'function') reAutoPickAndRefresh(); } catch(_){}
                try { if (Array.isArray(cachedProxyList) && cachedProxyList.length) renderProxySelect(cachedProxyList); } catch(_){}
                try { if ($('serverModal') && $('serverModal').classList.contains('active')) buildServerModalList(); } catch(_){}
            }
        }
        if (changes.bulkPingProgress) {
            try {
                var bpNew = changes.bulkPingProgress.newValue;
                if (bpNew && typeof bpNew.done === 'number' && typeof bpNew.total === 'number') {
                    var ind = $('bulkPingProgress');
                    var txt = $('bulkPingProgressText');
                    var bar = $('bulkPingBarFill');
                    if (ind && txt && bar) {
                        ind.hidden = false;
                        var tpl = _tSafe('bulkPingProgress', { ru:'Проверяем серверы: {done} из {total}', en:'Checking servers: {done} of {total}' }, 'Checking: {done}/{total}');
                        txt.textContent = tpl.replace('{done}', String(bpNew.done)).replace('{total}', String(bpNew.total));
                        var pct = bpNew.total > 0 ? Math.round((bpNew.done / bpNew.total) * 100) : 0;
                        bar.style.width = pct + '%';
                    }
                } else if (bpNew === undefined || bpNew === null) {
                    // SW cleared progress (done). Hide indicator.
                    var indD = $('bulkPingProgress');
                    if (indD) indD.hidden = true;
                }
            } catch {}
        }
        // [v2.8.0 round 15] excludedFromAutoSelect sync – SW делает first-install apply
        // (KR/TW/TR/JP) или другой popup toggle'ит «−/+» → этот popup без листенера показывает
        // stale UI до reopen. Reload module-var и re-render server modal если он open.
        if (changes.excludedFromAutoSelect) {
            try {
                autoSelectExcluded = Array.isArray(changes.excludedFromAutoSelect.newValue)
                    ? changes.excludedFromAutoSelect.newValue : [];
                // server modal – пересобираем список с актуальными «−/+» маркерами
                if (typeof buildServerModalList === 'function') buildServerModalList();
            } catch {}
        }
        // [v2.7.5 audit Pass5] Multi-popup sync: language change in popup A должен
        // re-rendern UI в popup B без reload. До этого фикса второй popup продолжал
        // показывать старый язык до закрытия/reopen. translateAll сам обновит select+UI.
        if (changes.language && changes.language.newValue && typeof changes.language.newValue === 'string') {
            try { translateAll(changes.language.newValue); } catch {}
        }
        // [v2.7.5 audit Pass5] selectedProxy sync – popup B должен обновить server-button
        // label когда popup A выбрал другой сервер. updateServerBtnLabel читает свежий
        // cached state и применяет к UI.
        if (changes.selectedProxy) {
            try {
                // [v3.0.3] Внешняя смена selectedProxy (SW-rescue сменил битый сервер на рабочий) –
                // синкаем НАТИВНЫЙ proxySelect, иначе updateServerBtnLabel читает старый selectedIndex
                // и кнопка/селектор показывают прежний сервер. Затем лейбл + подсветка в модалке.
                var _np = changes.selectedProxy.newValue;
                if (_np && _np.host && typeof findSelectIndexByProxy === 'function' && proxySelect) {
                    var _idx = findSelectIndexByProxy(_np);
                    if (_idx >= 0) proxySelect.selectedIndex = _idx;
                }
                updateServerBtnLabel();
                if ($('serverModal') && $('serverModal').classList.contains('active')) buildServerModalList();
            } catch {}
        }
    } catch (e) {
        // [v2.7.5 audit r3] Логируем ошибку listener'а вместо silent swallow – debugging
        console.warn('[AnonVPN] storage.onChanged handler error:', e);
    }
});

languageSelect?.addEventListener('change', () => {
    const lang = languageSelect.value;
    chrome.storage.local.set({ language: lang }, () => {
        // [v2.7.5 audit r3] lastError check (F147 pattern). Quota exceed silent
        // → UI updated but storage not persisted → next popup open reverts.
        if (chrome.runtime && chrome.runtime.lastError) {
            console.warn("[AnonVPN] storage.set failed:", chrome.runtime.lastError.message);
            return;
        }
        translateAll(lang);
        // Rebuild server names with new language
        if (cachedProxyList) renderProxySelect(cachedProxyList);
        buildServerModalList();
        // [v2.6.2] checkerModal rebuild if open
        if ($('checkerModal')?.classList.contains('active')) buildCheckerList();
        if (newsLoaded) {
            newsLoaded = false;
            const nt = document.querySelector('.tab-btn[data-tab="news"]');
            if (nt && nt.classList.contains('active')) { loadNews(); newsLoaded = true; }
        }
    });
});

chrome.runtime.onMessage.addListener((msg, sender) => {
    // [v2.7.6 audit pass17] Defense-in-depth sender validation. Manifest НЕ содержит
    // `externally_connectable` → other extensions не могут слать messages, но defensive
    // pattern symmetric с SW-side guard (sw:2536) – если manifest изменится в будущем,
    // popup сразу останется защищённым от spoofed messages.
    if (sender && sender.id && sender.id !== chrome.runtime.id) return false;
    // [v3.0.5] Прогресс перебора серверов при rescue → «подбираем рабочий… (N)» в IP-зоне, чтобы
    // длинный перебор (до тайм-бюджета 2.5мин на silent-DPI) не выглядел зависшим спиннером.
    if (msg.action === 'rescueProgress') {
        try {
            var _rt = $('vpnIpText');
            if (_rt && isVpnOn) _rt.textContent = t('ipRescuing', 'Сервер не отвечает, подбираем рабочий…') + ' (' + (msg.tried || 0) + ')';
        } catch (_e) {}
        return;
    }
    if (msg.action === 'serverSwitched') {
        // [v3.0.5] Выбранный сервер исчез → SW переключил на другой (+системное уведомление). Обновляем кнопку/список.
        try { updateServerBtnLabel(); } catch(_){}
        try { resetLoadProxiesRetry(); loadProxies(); } catch(_){}
        return;
    }
    if (msg.action === "proxyStateChanged") {
        toggle.checked = msg.proxyEnabled;
        isVpnOn = msg.proxyEnabled;
        setVpnFieldsLocked(msg.proxyEnabled);
        updateVpnButtonUI(msg.proxyEnabled);
        // [v2.6.2] State flipped externally (alarm timer / SW) – IP must be refreshed
        clearIpInfoCache();
        setTimeout(function(){ loadIpInfo(true); }, 500);
        if (msg.proxyEnabled) {
            // [v3.1.1] Внешнее включение (Alt+Shift+V при открытом popup): запустить
            // отображение таймера сразу – раньше countdown/счётчик безлимита появлялся
            // только при следующем открытии popup. startLocalTimer идемпотентен.
            startLocalTimer();
        }
        if (!msg.proxyEnabled) {
            if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
            // [v3.1.1] Остановить счётчик безлимитной сессии – иначе через секунду
            // updateTimerDisplay перерисует уже очищенный #timer.
            if (_unlimInterval) { clearInterval(_unlimInterval); _unlimInterval = null; }
            _unlimStartTs = null;
            const timerEl = $("timer");
            if (timerEl) { timerEl.textContent = ''; timerEl.classList.remove("timer-active"); }
            resetLoadProxiesRetry(); loadProxies(); recheckPremiumFromServer(); checkNewsBadge();
            // [v2.5.9] Если disconnect по таймеру – показать sticky-баннер
            if (msg.reason === 'timer') {
                showSessionExpiredBanner();
            }
            // [v2.7.0 fix F18.1] Keyboard shortcut (Alt+Shift+V) – показать error-сообщение
            // если toggle failed. SW broadcast'ит proxyStateChanged с reason='timeout'/'error'.
            // Без этого юзер нажимает shortcut и не видит почему ничего не произошло.
            if (msg.reason === 'timeout') {
                showStatusMessage(t('connectionTimeout', 'Connection timeout. Try another server.'), true, 'vpn');
            } else if (msg.reason === 'error') {
                showStatusMessage(t('connectionError', 'Connection error. Try again.'), true, 'vpn');
            } else if (msg.reason === 'server_overloaded_free') {
                // [v2.7.3] SW заблокировал toggle – free-юзер на перегруженном сервере.
                openFreeBlockedModal();
            } else if (msg.reason === 'tunnel_manual') {
                // [v3.0.3] Ручной закреп битого сервера – ВПН выключен SW. Пояснение в баннер
                // (vpnIpText покажет реальный IP – не конфликтуем).
                showStatusMessage(t('ipBrokenManual', 'Выбранный сервер не отвечает. Выберите другой или включите «Автовыбор сервера».'), true, 'vpn');
            } else if (msg.reason === 'tunnel_no_server' || msg.reason === 'no_server_available') {
                // [v3.0.3] Не удалось подключиться ни к одному серверу:
                //  - tunnel_no_server: rescue перебрал все, рабочих нет (ВПН выключен);
                //  - no_server_available: автовыбор не нашёл сервер ДО коннекта (все ≥75/сломаны/исключены).
                // Финальная модалка (прочнее баннера) + действия (кэш/диагностика/поддержка).
                openNoServerModal();
            }
        }
    }
    if (msg.action === "updateRequired") {
        // [v2.5.8] SW сообщил, что версия заблокирована – обновляем UI
        applyUpdateBanner();
        resetLoadProxiesRetry(); loadProxies(); // перерисовать селект (там тоже сменится сообщение)
    }
    if (msg.action === "proxyListUpdated") {
        // [v2.9.2 critical fix] SW сделал defensive refresh (premium-mismatch) и пришли
        // premium-сервера. Перерисуем server-list + auto-select – иначе юзер видит stale UI
        // до повторного reopen popup'а.
        resetLoadProxiesRetry();
        loadProxies();
        try { if (typeof reAutoPickAndRefresh === 'function') reAutoPickAndRefresh(); } catch(_){}
    }
    if (msg.action === "illegalExtId") {
        // [v2.5.8] SW сообщил, что копия расширения нелегальна
        applyUpdateBanner();
        resetLoadProxiesRetry(); loadProxies();
    }
    if (msg.action === "rateLimited") {
        // [v2.8.0] SW сообщил, что юзер забанен bot-detection'ом
        applyRateLimitBanner();
        resetLoadProxiesRetry(); loadProxies();
    }
    if (msg.action === "premiumActivated") { resetLoadProxiesRetry(); loadProxies(); hideSessionExpiredBanner(true); try { _setupOnPremiumActivated(); } catch(_){} }
    if (msg.action === "premiumDeactivated") {
        updatePremiumUI(); resetLoadProxiesRetry(); loadProxies(); updatePremiumTabLock();
        resetPremiumFeatures();
        if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
        // [v3.1.1] Счётчик безлимитной сессии больше не актуален (premium слетел).
        if (_unlimInterval) { clearInterval(_unlimInterval); _unlimInterval = null; }
        _unlimStartTs = null;
        const timerEl = $("timer");
        updateVpnButtonUI(false);
        if (timerEl) { timerEl.textContent = ''; timerEl.classList.remove("timer-active"); }
        const deactivateMsg = msg.reason === 'device_changed'
            ? t('deviceChanged', 'Premium activated on another device')
            : t('premiumExpired', 'Premium expired, proxy disabled');
        showStatusMessage(deactivateMsg, true);
    }
});

// ═══════════════════════════════════════
// ═══ v2.5.9: AUTO-SELECT SERVER    ═══
// ═══════════════════════════════════════
// State: autoSelectServer (default true), autoSelectScope ('all'|'free'|'premium', default 'free').
// Scope selector (gear) is visible only for premium users.

function getAutoSelectState(cb){
    chrome.storage.local.get(['autoSelectServer','autoSelectScope','isPremium'], function(d){
        var enabled = d.autoSelectServer !== false; // default true
        var scope = d.autoSelectScope || 'free';
        var isPrem = !!d.isPremium;
        if (!isPrem) scope = 'free'; // free users locked to 'free'
        cb(enabled, scope, isPrem);
    });
}

function updateAutoSelScopeText(){
    var el = $('autoSelScopeText'); if (!el) return;
    getAutoSelectState(function(enabled, scope){
        var label;
        if (scope === 'all') label = t('autoSelectScopeAll','All');
        else if (scope === 'premium') label = t('autoSelectScopePremium','Premium');
        else label = t('autoSelectScopeFree','Free');
        el.textContent = label;
    });
}

function applyAutoSelectUI(){
    var toggleEl = $('autoSelToggle');
    var gear = $('autoSelScopeBtn');
    var bar = document.querySelector('.auto-sel-bar');
    var drop = $('autoSelScopeDropdown');
    if (!toggleEl || !bar) return;
    getAutoSelectState(function(enabled, scope, isPrem){
        toggleEl.checked = enabled;
        bar.classList.toggle('disabled', !enabled);
        if (gear) {
            if (isPrem) gear.removeAttribute('hidden');
            else gear.setAttribute('hidden','');
            gear.disabled = !enabled;
        }
        if (drop) {
            drop.classList.remove('open');
            drop.querySelectorAll('.auto-sel-scope-item').forEach(function(it){
                it.classList.toggle('selected', it.getAttribute('data-scope') === scope);
            });
        }
        updateAutoSelScopeText();
        // [v2.9.1] Method label/highlight тоже обновляется
        try { updateAutoSelMethodText(); } catch(_){}
        // [v2.9.1] disable method-btn если auto-select выключен
        var mb = $('autoSelMethodBtn');
        if (mb) mb.disabled = !enabled;
    });
}

// ═══════════════════════════════════════
// ═══ v2.4.3: SERVER MODAL           ═══
// ═══════════════════════════════════════
$('openServerModal')?.addEventListener('click', function(){
    if(isVpnOn) return;
    applyAutoSelectUI();
    updateSortModeUI();
    buildServerModalList();
    openModal('serverModal');
    // [v3.1.6] Первое открытие выбора сервера → показываем легенду обозначений (много юзеров не
    // понимают значков). Один раз: sentinel serverLegendSeen (KNOWN, не STALE). Дальше — кнопка «?».
    chrome.storage.local.get(['serverLegendSeen'], function(d){
        if (!d.serverLegendSeen) {
            setTimeout(function(){ openModal('serverLegendModal'); }, 400);
            chrome.storage.local.set({ serverLegendSeen: true }, function(){ if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;} });
        }
    });
    _ghostStatusStart(); // [v3.1.3] статус фоновой проверки в шапке (+будим ghost-цикл)
    // [v3.0.2] Актуализируем статистику нагрузки при открытии выбора серверов (TTL 30 мин) и
    // перерисовываем список свежими данными. Иначе в час пик первый сервер виден свободным по
    // устаревшему кэшу, и все подключаются к нему (160+ на одном сервере).
    refreshServerStats(function(){ if ($('serverModal') && $('serverModal').classList.contains('active')) buildServerModalList(); });
});

// Re-run auto-pick and refresh UI (button label + modal highlights)
function reAutoPickAndRefresh(){
    if (isVpnOn || !cachedProxyList || cachedProxyList.length === 0) return;
    // [v2.9.1] Читаем method+serverPings – popup-side выбор должен совпадать с SW.
    chrome.storage.local.get(['autoSelectServer','autoSelectScope','isPremium','autoSelectMethod','serverPings','checkerLastResults'], function(d){
        if (d.autoSelectServer === false) return;
        var isPrem = !!d.isPremium;
        var scope = isPrem ? (d.autoSelectScope || 'free') : 'free';
        var method = (d.autoSelectMethod === 'ping' || d.autoSelectMethod === 'both') ? d.autoSelectMethod : 'ping';
        // [v2.9.2 critical fix] Merge оба источника пингов – симметрия с renderProxySelect (popup.js:2403).
        // Без merge: смена scope/method триггерила reAutoPickAndRefresh, тот видел только bulk-ping
        // (serverPings), премиум-пинги из «Проверка серверов» (checkerLastResults) терялись →
        // все 32 premium-сервера skipped:'no_ping', picked=null → fallback на load → юзер видит
        // не самый быстрый сервер, а тот что по нагрузке.
        var pings = _mergePingSources(d.serverPings, d.checkerLastResults);
        var picked = pickBestServerLocal(cachedProxyList, scope, isPrem, method, pings);
        // [v2.9.1] ping-mode без свежих пингов → fallback на load (симметрично SW)
        if (!picked && method !== 'load') picked = pickBestServerLocal(cachedProxyList, scope, isPrem, 'load', {});
        if (!picked) return;
        // [v2.6.2] Реальный index после сортировки
        var _oi = findSelectIndexByProxy(picked.proxy);
        if (_oi >= 0) proxySelect.selectedIndex = _oi;
        chrome.storage.local.set({ selectedProxy: picked.proxy }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            updateServerBtnLabel();
            // Refresh modal list highlighting without rebuilding (smooth)
            var container = $('serverModalList');
            if (container && $('serverModal')?.classList.contains('active')) {
                // [v2.6.2] Preserve scroll: buildServerModalList recreates DOM,
                // resetting scrollTop to 0 – feels broken on exclude/include click.
                var savedScroll = container.scrollTop;
                buildServerModalList();
                setTimeout(function(){
                    if (container) container.scrollTop = savedScroll;
                }, 50);
            }
        });
    });
}

$('autoSelToggle')?.addEventListener('change', function(){
    var on = this.checked;
    chrome.storage.local.set({ autoSelectServer: on }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
        applyAutoSelectUI();
        if (on) reAutoPickAndRefresh();
    });
});

$('autoSelScopeBtn')?.addEventListener('click', function(e){
    e.stopPropagation();
    var drop = $('autoSelScopeDropdown');
    if (drop) drop.classList.toggle('open');
});

document.querySelectorAll('#autoSelScopeDropdown .auto-sel-scope-item').forEach(function(item){
    var activate = function(){
        var scope = item.getAttribute('data-scope');
        chrome.storage.local.set({ autoSelectScope: scope }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            applyAutoSelectUI();
            reAutoPickAndRefresh();
        });
    };
    item.addEventListener('click', function(e){ e.stopPropagation(); activate(); });
    // [v2.7.3] клавиатурная активация (role="menuitem" + tabindex=0 в HTML)
    item.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); activate(); }
    });
});

// [v2.9.1] Method dropdown (load/ping/both) – зеркало scope dropdown.
function updateAutoSelMethodText(){
    var el = $('autoSelMethodText'); if (!el) return;
    // [audit fix critical] Читаем isPremium + cachedProxyList – для premium-юзеров считаем
    // пинги только на серверах их пула (если scope=premium – premium-only, иначе всё).
    // Раньше: для premium с пингами только на premium-серверах + scope=premium hasFresh
    // мог быть = 0 (если пинговались только free), и ping/both дисаблились.
    chrome.storage.local.get(['autoSelectMethod','serverPings','isPremium','autoSelectScope','checkerLastResults'], function(d){
        var m = (d.autoSelectMethod === 'ping' || d.autoSelectMethod === 'both') ? d.autoSelectMethod : 'ping';
        // [v2.9.2 critical fix] Merge оба источника пингов – иначе hasFresh false, когда юзер пинговал в checker-tab
        var pings = _mergePingSources(d.serverPings, d.checkerLastResults);
        var isPremium = !!d.isPremium;
        var scope = (d.autoSelectScope === 'premium' || d.autoSelectScope === 'all') ? d.autoSelectScope : 'free';
        var now = Date.now();
        var TTL = 24*60*60*1000;
        // Строим Set ключей серверов в пуле (по типу/scope) – пинги считаем только по ним.
        var poolKeys = null;
        var list = Array.isArray(cachedProxyList) ? cachedProxyList : null;
        if (list && list.length) {
            poolKeys = new Set();
            list.forEach(function(p){
                if (!p || !p.host || !p.port) return;
                var isPrem = p.type === 'premium';
                var include = false;
                if (!isPremium) include = !isPrem;
                else if (scope === 'premium') include = isPrem;
                else if (scope === 'all') include = true;
                else include = !isPrem; // 'free' default for premium too
                if (include) poolKeys.add(p.host + ':' + p.port);
            });
        }
        var freshCount = 0;
        Object.keys(pings).forEach(function(k){
            if (poolKeys && !poolKeys.has(k)) return;
            var p = pings[k];
            if (p && typeof p.ms === 'number' && p.ms > 0 && typeof p.ts === 'number' && (now - p.ts) < TTL) freshCount++;
        });
        var hasFresh = freshCount > 0;
        var label;
        if (m === 'ping') label = _tSafe('metricByPing', { ru:'По скорости', en:'By speed' }, 'By speed');
        else if (m === 'both') label = _tSafe('metricBoth', { ru:'Комбо', en:'Combo' }, 'Combo');
        else label = _tSafe('metricByLoad', { ru:'По нагрузке', en:'By load' }, 'By load');
        el.textContent = label;
        // [v2.9.1] Disabled items без свежих пингов
        // [v2.9.2] Также обновляем текст items через i18n (раньше hardcoded в HTML)
        var drop = $('autoSelMethodDropdown');
        if (drop) {
            drop.querySelectorAll('.auto-sel-method-item').forEach(function(it){
                var md = it.getAttribute('data-method');
                // Локализованный текст из i18n
                var itemLabel;
                if (md === 'load') itemLabel = _tSafe('metricByLoad', { ru:'По нагрузке', en:'By load' }, 'By load');
                else if (md === 'ping') itemLabel = _tSafe('metricByPing', { ru:'По скорости', en:'By speed' }, 'By speed');
                else if (md === 'both') itemLabel = _tSafe('metricBoth', { ru:'Комбо', en:'Combo' }, 'Combo');
                if (itemLabel) it.textContent = itemLabel;
                var disabled = !hasFresh && (md === 'ping' || md === 'both');
                it.classList.toggle('disabled', disabled);
                it.setAttribute('aria-disabled', disabled ? 'true' : 'false');
                if (disabled) {
                    it.title = _tSafe('methodDisabledNoPings', {
                        ru:'Нет данных проверки – сначала запустите проверку серверов',
                        en:'No ping data – run server check first'
                    }, 'No ping data');
                } else {
                    it.removeAttribute('title');
                }
            });
        }
        // Подсветка selected пункта
        var drop = $('autoSelMethodDropdown');
        if (drop) {
            drop.querySelectorAll('.auto-sel-method-item').forEach(function(it){
                it.classList.toggle('selected', it.getAttribute('data-method') === m);
            });
        }
    });
}

$('autoSelMethodBtn')?.addEventListener('click', function(e){
    e.stopPropagation();
    var drop = $('autoSelMethodDropdown');
    if (drop) drop.classList.toggle('open');
});

document.querySelectorAll('#autoSelMethodDropdown .auto-sel-method-item').forEach(function(item){
    var activate = function(){
        var m = item.getAttribute('data-method');
        // [v3.1.2] Больше НЕ запускаем массовую проверку (bulk-ping / полоса сверху) при выборе
        // метода. Раньше это был единственный способ добыть пинги; теперь их наполняет ghost-ping
        // в фоне (3 сервера/5мин). Disabled-пункт (нет пингов для scope) тоже просто выбирает метод –
        // pickBestServer сам сделает fallback на нагрузку, пока ghost догоняет. Ручной bulk-ping
        // остаётся доступен в «Проверке серверов» (Premium-tab) как явное действие.
        chrome.storage.local.set({ autoSelectMethod: m }, function(){
            if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            updateAutoSelMethodText();
            var drop = $('autoSelMethodDropdown'); if (drop) drop.classList.remove('open');
            reAutoPickAndRefresh();
        });
    };
    item.addEventListener('click', function(e){ e.stopPropagation(); activate(); });
    item.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); activate(); }
    });
});

// Outside-click – закрыть оба dropdown'а (scope + method)
document.addEventListener('click', function(){
    var d1 = $('autoSelMethodDropdown'); if (d1) d1.classList.remove('open');
});

// При первом отрисовке UI – обновим method label
setTimeout(function(){ try { updateAutoSelMethodText(); } catch(_){} }, 50);

// Close scope dropdown when clicking elsewhere in the modal
document.addEventListener('click', function(e){
    var drop = $('autoSelScopeDropdown');
    var btn = $('autoSelScopeBtn');
    if (!drop || !drop.classList.contains('open')) return;
    if (drop.contains(e.target) || (btn && btn.contains(e.target))) return;
    drop.classList.remove('open');
});

var _buildServerModalSeq=0;
function buildServerModalList(){
    // [v2.8.1 audit] Array.isArray guard – defense vs corrupted state.
    var container=$('serverModalList'); if(!container||!Array.isArray(cachedProxyList)) return;
    // [v2.8.5 fix] Re-entrancy guard: смена сортировки триггерит buildServerModalList дважды
    // (set-callback + storage.onChanged). Раньше DOM-clear был синхронным сверху, а render –
    // в async storage.get callback → два вызова интерливились и список УДВАИВАЛСЯ. Теперь
    // clear+render оба в callback, устаревший вызов (mySeq != _buildServerModalSeq) выходит.
    var mySeq=++_buildServerModalSeq;
    var lang=getLang(), trans=cachedTranslations||{};
    var sL=(trans[lang]&&trans[lang].serverItem)||'Server';
    var pL=(trans[lang]&&trans[lang].premiumServer)||'Premium server';
    var freeList=cachedProxyList.filter(function(p){return p.type!=='premium';});
    var premList=cachedProxyList.filter(function(p){return p.type==='premium';});

    var freeItems=freeList.map(function(p,i){return {proxy:p,idx:i};});
    var premItems=premList.map(function(p,i){return {proxy:p,idx:i};});

    chrome.storage.local.get(['selectedProxy','isPremium','checkerLastResults','serverPings','cachedServerStats','siteCheckByServer','serverSiteHintsEnabled'],function(d){
        if(mySeq!==_buildServerModalSeq) return; // superseded by a newer rebuild – не дублируем DOM
        container.innerHTML='';
        var sel=d.selectedProxy, isPrem=!!d.isPremium;
        // [v3.1.7] Данные для подсказки при наведении: накопитель проверок «Доступность сайта» по серверам
        // (host:port → {siteHost:{cls,text,ts}}) ПЛЮС последняя проверка из checkerLastResults.site —
        // чтобы подсказка работала сразу после автоподбора, даже если накопитель ещё пуст (первый запуск).
        // Тумблер в настройках (serverSiteHintsEnabled, default ON) полностью отключает подсказку.
        var _siteHintsOn = (d.serverSiteHintsEnabled !== false);
        var _siteHitsMap = (_siteHintsOn && d.siteCheckByServer && typeof d.siteCheckByServer==='object' && !Array.isArray(d.siteCheckByServer)) ? d.siteCheckByServer : {};
        try {
            var _cs = _siteHintsOn && d.checkerLastResults && d.checkerLastResults.site;
            if (_cs && _cs.results && _cs.target) {
                var _csHost=''; try{_csHost=new URL(_cs.target).hostname;}catch(e){_csHost=String(_cs.target||'');}
                if (_csHost) Object.keys(_cs.results).forEach(function(k){
                    var r=_cs.results[k]; if(!r || !r.hp) return;
                    var b=(_siteHitsMap[r.hp] && typeof _siteHitsMap[r.hp]==='object') ? _siteHitsMap[r.hp] : {};
                    var newTs=Number(r.ts)||Number(_cs.ts)||Date.now();
                    if(!b[_csHost] || newTs >= (Number(b[_csHost].ts)||0)) b[_csHost]={cls:r.cls, text:r.text, ts:newTs};
                    _siteHitsMap[r.hp]=b;
                });
            }
        } catch(_){}
        // При закрытии/пересборке списка прячем висящую подсказку.
        if(!container._sitesTipBound){ container._sitesTipBound=1; container.addEventListener('scroll',function(){ _hideServerSitesTip(); }); }
        // [v3.1.2] Восстанавливаем счётчик юзеров из кэша, если глобальный serverUserCounts ещё пуст:
        // перерисовка от обновления пингов (ghost/bulk) может прийти РАНЬШЕ, чем refreshServerStats
        // заполнит serverUserCounts → иначе у всех серверов показалось бы «0 юзеров».
        if ((!serverUserCounts || !Object.keys(serverUserCounts).length) && d.cachedServerStats
            && typeof d.cachedServerStats==='object' && !Array.isArray(d.cachedServerStats)) {
            serverUserCounts = d.cachedServerStats;
        }
        var pingMap=_buildPingMap(d.checkerLastResults);
        // [v3.1.2] Ghost-пинги в списке серверов: раньше карта строилась ТОЛЬКО из ручной
        // проверки (checkerLastResults) – фоновые замеры (serverPings: ghost-ping + bulk-ping)
        // в UI не отображались вовсе. Мержим по свежести: ghost-запись перекрывает чекерную,
        // только если её ts новее (спец-метки чекера типа «✓» не затираются старым ghost'ом).
        try {
            var _mrg=_mergePingSources(d.serverPings, d.checkerLastResults);
            Object.keys(_mrg).forEach(function(hp){
                var mm=_mrg[hp];
                var sp=d.serverPings && d.serverPings[hp];
                if (sp && typeof sp.ms==='number' && sp.ms>0 && mm.ms===sp.ms && (Number(mm.ts)||0)===(Number(sp.ts)||0)) {
                    pingMap[hp]={cls:pingCls(sp.ms), text:sp.ms+' ms'};
                }
            });
            // [v3.1.2] Визуал для не ответивших: ghost пометил сервер fail и валидного пинга нет →
            // показываем «✕» (красный), иначе такой сервер остался бы вообще без индикатора.
            if (d.serverPings && typeof d.serverPings==='object') {
                Object.keys(d.serverPings).forEach(function(hp){
                    var sp=d.serverPings[hp];
                    var cur=pingMap[hp];
                    var hasValid = cur && parseInt(cur.text,10) > 0;
                    if (sp && sp.fail && !hasValid) pingMap[hp]={cls:'fail', text:'✕'};
                });
            }
        } catch(_){}
        _pingSortMap=_buildPingSortMap(pingMap);
        var favLabel=t('favorites','Favorites');
        // [v2.7.3] free-юзер + free-сервер + u>=FREE_LOAD_LIMIT → blocked. Premium не затронут.
        function isBlockedForFree(users, isPremItem){ return !isPrem && !isPremItem && users >= FREE_LOAD_LIMIT; }

        // Collect favorites from both lists
        var favItems=[];
        freeItems.forEach(function(item){
            if(isFavoriteProxy(item.proxy)) favItems.push({proxy:item.proxy,idx:item.idx,key:'f'+item.idx,label:_freeServerLabel(item.idx),statsKey:_serverKey(item.proxy),isPremItem:false,locked:false});
        });
        premItems.forEach(function(item){
            if(isFavoriteProxy(item.proxy)) favItems.push({proxy:item.proxy,idx:item.idx,key:'p'+item.idx,label:_premServerLabel(item.idx,isPrem),statsKey:_serverKey(item.proxy),isPremItem:true,locked:!isPrem});
        });

        // Render favorites section
        if(favItems.length){
            var secFav=document.createElement('div');secFav.className='modal-section-label modal-section-fav';
            secFav.textContent='★ '+favLabel;container.appendChild(secFav);
            // [v3.1.2] Избранное тоже сортируется по выбранному режиму (по скорости/нагрузке/…).
            // Раньше рендерилось в порядке добавления, игнорируя «Сортировку». idx добавлен выше –
            // нужен sortServers для index/country и как tiebreak.
            var favSorted = sortServers(favItems, 'fav');
            favSorted.forEach(function(fi){
                var users=serverUserCounts[fi.statsKey]||0;
                var isSel=sel&&sel.host===fi.proxy.host&&String(sel.port)===String(fi.proxy.port)&&(!fi.isPremItem||isPrem);
                var blocked=isBlockedForFree(users, fi.isPremItem);
                var el=createServerModalItem(fi.proxy,fi.key,fi.label,users,isSel,fi.isPremItem,fi.locked,blocked,pingMap[fi.statsKey],_siteHitsMap[fi.statsKey]);
                el.setAttribute('data-fav','1');
                container.appendChild(el);
            });
        }

        // [v2.6.2] Порядок согласно _currentSortMode (free и premium сортируются отдельно).
        // idx остаётся оригинальным (№3 остаётся №3 в label).
        var freeSorted = sortServers(freeItems, 'f');
        var premSorted = sortServers(premItems, 'p');

        // [v2.8.5] \u041F\u043E\u0440\u044F\u0434\u043E\u043A \u0441\u0435\u043A\u0446\u0438\u0439 \u043F\u043E \u0442\u0430\u0440\u0438\u0444\u0443: premium-\u044E\u0437\u0435\u0440\u0443 \u043F\u0440\u0435\u043C\u0438\u0443\u043C-\u0441\u0435\u0440\u0432\u0435\u0440\u044B \u043F\u0435\u0440\u0432\u044B\u043C\u0438,
        // free-\u044E\u0437\u0435\u0440\u0443 \u2014 \u0431\u0435\u0441\u043F\u043B\u0430\u0442\u043D\u044B\u0435 \u043F\u0435\u0440\u0432\u044B\u043C\u0438. \u0421\u0438\u043C\u043C\u0435\u0442\u0440\u0438\u0447\u043D\u043E buildCheckerList.
        function _renderFreeBlock(){
            if(freeSorted.length){
                var secLabel=document.createElement('div');secLabel.className='modal-section-label';
                secLabel.textContent=sL;container.appendChild(secLabel);
            }
            freeSorted.forEach(function(item){
                var proxy=item.proxy, idx=item.idx;
                var key='f'+idx;
                var statsKey=_serverKey(proxy);
                var users=serverUserCounts[statsKey]||0;
                var isSel=sel&&sel.host===proxy.host&&String(sel.port)===String(proxy.port);
                var blocked=isBlockedForFree(users, false);
                var el=createServerModalItem(proxy,key,_freeServerLabel(idx),users,isSel,false,false,blocked,pingMap[statsKey],_siteHitsMap[statsKey]);
                container.appendChild(el);
            });
        }
        function _renderPremBlock(){
            if(premSorted.length){
                var secLabel2=document.createElement('div');secLabel2.className='modal-section-label';
                secLabel2.textContent='\u2B50 '+pL;container.appendChild(secLabel2);
            }
            premSorted.forEach(function(item){
            var proxy=item.proxy, idx=item.idx;
            var key='p'+idx;
            var statsKey=_serverKey(proxy);
            var users=serverUserCounts[statsKey]||0;
            var isSel=sel&&sel.host===proxy.host&&String(sel.port)===String(proxy.port)&&isPrem;
            var locked=!isPrem;
            var label=_premServerLabel(idx,isPrem);
            // Premium-item \u0434\u043b\u044f \u043d\u0435-premium \u044e\u0437\u0435\u0440\u0430 \u0443\u0436\u0435 \u0432 locked-\u0440\u0435\u0436\u0438\u043c\u0435 (premium-lock flow), \u0431\u043b\u043e\u043a \u043f\u043e \u043d\u0430\u0433\u0440\u0443\u0437\u043a\u0435 \u043d\u0435 \u043d\u0443\u0436\u0435\u043d.
            var el=createServerModalItem(proxy,key,label,users,isSel,true,locked,false,pingMap[statsKey],_siteHitsMap[statsKey]);
            container.appendChild(el);
        });
        }
        if(isPrem){ _renderPremBlock(); _renderFreeBlock(); }
        else      { _renderFreeBlock(); _renderPremBlock(); }
    });
}

var _rebuildFavSeq=0;
function rebuildFavoritesSection(container){
    // [v2.8.5 fix R1] Re-entrancy guard – symmetric с buildServerModalList. Sync-remove
    // (ниже) + async-insert (в storage.get callback): два конкурентных вызова (быстрые
    // клики по ⭐) интерливились → секция «Избранное» ДУБЛИРОВАЛАСЬ. Устаревший вызов
    // выходит в callback'е до вставки.
    var mySeq=++_rebuildFavSeq;
    // Remove existing favorites section (header + items)
    var oldHeader=container.querySelector('.modal-section-fav');
    if(oldHeader) oldHeader.remove();
    container.querySelectorAll('.modal-list-item[data-fav="1"]').forEach(function(el){el.remove();});

    // Also sync star state in main list items
    container.querySelectorAll('.modal-list-item:not([data-fav])').forEach(function(el){
        var key=el.getAttribute('data-key');
        var proxy=resolveProxyByKey(key);
        var star=el.querySelector('.modal-item-fav');
        if(star&&proxy){ var _sa=isFavoriteProxy(proxy); star.classList.toggle('active',_sa); star.title=_favTitle(_sa); }
    });

    // Collect current favorites
    // [v2.8.1 audit] Array.isArray guard.
    if(!Array.isArray(cachedProxyList)) return;
    var freeList=cachedProxyList.filter(function(p){return p.type!=='premium';});
    var premList=cachedProxyList.filter(function(p){return p.type==='premium';});
    chrome.storage.local.get(['selectedProxy','isPremium','checkerLastResults'],function(d){
        if(mySeq!==_rebuildFavSeq) return; // superseded by a newer rebuild – не дублируем секцию
        var sel=d.selectedProxy, isPrem=!!d.isPremium;
        var pingMap=_buildPingMap(d.checkerLastResults);
        var favItems=[];
        freeList.forEach(function(p,i){
            if(isFavoriteProxy(p)) favItems.push({proxy:p,key:'f'+i,label:_freeServerLabel(i),statsKey:_serverKey(p),isPremItem:false,locked:false});
        });
        premList.forEach(function(p,i){
            if(isFavoriteProxy(p)) favItems.push({proxy:p,key:'p'+i,label:_premServerLabel(i,isPrem),statsKey:_serverKey(p),isPremItem:true,locked:!isPrem});
        });

        if(!favItems.length) return;

        // Insert favorites section at the top
        var header=document.createElement('div');
        header.className='modal-section-label modal-section-fav';
        header.textContent='★ '+t('favorites','Favorites');

        var firstChild=container.firstChild;
        container.insertBefore(header,firstChild);

        favItems.forEach(function(fi){
            var users=serverUserCounts[fi.statsKey]||0;
            var isSel=sel&&sel.host===fi.proxy.host&&String(sel.port)===String(fi.proxy.port)&&(!fi.isPremItem||isPrem);
            // [v2.7.3] free-юзер + free-сервер + u>=FREE_LOAD_LIMIT → блок
            var blocked=!isPrem && !fi.isPremItem && users >= FREE_LOAD_LIMIT;
            var el=createServerModalItem(fi.proxy,fi.key,fi.label,users,isSel,fi.isPremItem,fi.locked,blocked,pingMap[fi.statsKey]);
            el.setAttribute('data-fav','1');
            el.classList.add('fav-animate');
            container.insertBefore(el,header.nextSibling?findNextSection(container,header):null);
        });

        // Re-insert fav items after header in order
        var favEls=container.querySelectorAll('.modal-list-item[data-fav="1"]');
        var afterHeader=header.nextSibling;
        favEls.forEach(function(el){ container.insertBefore(el,afterHeader); afterHeader=el.nextSibling; });
    });
}

function findNextSection(container,afterEl){
    var sib=afterEl.nextSibling;
    while(sib){
        if(sib.classList&&sib.classList.contains('modal-section-label')&&!sib.classList.contains('modal-section-fav')) return sib;
        sib=sib.nextSibling;
    }
    return null;
}

function createServerModalItem(proxy,key,label,users,isSelected,isPremItem,isLocked,isFreeBlocked,pingInfo,siteHits){
    var div=document.createElement('div');
    // [v2.7.3] isFreeBlocked – free-юзер на перегруженном (u>=75) free-сервере. Визуально
    // приглушён + замок, клик → #freeBlockedModal (не selection). Отдельно от isLocked
    // (который premium-lock для не-premium юзеров).
    div.className='modal-list-item'+(isSelected?' selected':'')+(isLocked?' disabled':'')+(isPremItem?' premium-item':'')+(isFreeBlocked?' free-blocked':'');
    div.setAttribute('data-key',key);

    var main=document.createElement('div');main.className='modal-item-main';
    if(proxy.country){
        var img=getFlagImg(proxy.country,true);
        if(img) main.appendChild(img);
        div.title=getCountryName(proxy.country);
    }
    var txt=document.createElement('span');txt.textContent=label;main.appendChild(txt);
    div.appendChild(main);

    // [v3.0.3] Метка возможных гео-ограничений (YouTube/Instagram) для стран с жёсткой цензурой.
    // Клик → модалка-пояснение; stopPropagation – чтобы клик по метке не выбирал сервер.
    if(proxy.country && isGeoRestricted(proxy.country)){
        var geo=document.createElement('span');
        geo.className='modal-item-geowarn';
        geo.textContent='⚠';
        geo.setAttribute('role','button');
        geo.setAttribute('tabindex','0');
        geo.title=t('geoBlockTitle','Возможны ограничения');
        geo.setAttribute('aria-label',geo.title);
        var _openGeo=function(e){ if(e&&e.stopPropagation)e.stopPropagation(); openGeoBlockModal(proxy.country); };
        geo.addEventListener('click',_openGeo);
        geo.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); _openGeo(e); } });
        div.appendChild(geo);
    }

    // [v3.0.3] Метка «общий лимит трафика – сервер может временно пропасть» (EE/JP/FI). Клик → модалка.
    if (proxy.country && isTrafficLimited(proxy.country)) {
        var trf = document.createElement('span');
        trf.className = 'modal-item-trafficwarn';
        trf.textContent = '⚠';
        trf.setAttribute('role','button');
        trf.setAttribute('tabindex','0');
        trf.title = t('trafficTitle', 'Возможны перебои');
        trf.setAttribute('aria-label', trf.title);
        var _openTrf = function(e){ if(e&&e.stopPropagation)e.stopPropagation(); openTrafficModal(proxy.country); };
        trf.addEventListener('click', _openTrf);
        trf.addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); _openTrf(e); } });
        div.appendChild(trf);
    }

    // [v3.0.3] Метка «сервер не отвечает» (туннель недавно ломался – brokenServers). Как fail-проверка.
    var _bkey = proxy.host + ':' + proxy.port;
    if (_brokenServersMap && _brokenServersMap[_bkey]) {
        var brk = document.createElement('span');
        brk.className = 'modal-item-broken';
        brk.textContent = '✕';
        brk.title = t('ipBrokenMark', 'Этот сервер недавно не отвечал');
        div.appendChild(brk);
    }

    // [v2.8.5] Счётчик нагрузки [👤 N] – показывается и для free, и для premium серверов.
    if(users>0){
        var badge=document.createElement('span');badge.className='modal-item-badge';
        badge.textContent='\u{1F464} '+users;
        if(users>=100) badge.classList.add('badge-warn','badge-warn-high');
        else if(users>=FREE_LOAD_LIMIT) badge.classList.add('badge-warn','badge-warn-medium');
        div.appendChild(badge);
    }
    // [v2.8.5] Server ping from the last server check (Premium tab -> "Server checker").
    if(pingInfo && pingInfo.text){
        var pingEl=document.createElement('span');
        pingEl.className='modal-item-ping '+(pingInfo.cls||'');
        pingEl.textContent=pingInfo.text;
        div.appendChild(pingEl);
    }

    // [v2.5.9] Exclude-from-auto-select button ("−" / "+")
    // Hidden for locked (premium) items since they can't be auto-selected anyway.
    if (!isLocked) {
        var excludedNow = isExcludedFromAutoSelect(proxy);
        var excl = document.createElement('span');
        excl.className = 'modal-item-exclude' + (excludedNow ? ' excluded' : '');
        excl.textContent = excludedNow ? '+' : '\u2212';
        excl.title = excludedNow
            ? t('includeInAutoSelect', 'Include in auto-select')
            : t('excludeFromAutoSelect', 'Exclude from auto-select');
        if (excludedNow) div.classList.add('auto-sel-excluded');
        excl.addEventListener('click', function(e){
            e.stopPropagation();
            toggleAutoSelectExclude(proxy);
            var nowExc = isExcludedFromAutoSelect(proxy);
            excl.textContent = nowExc ? '+' : '\u2212';
            excl.classList.toggle('excluded', nowExc);
            excl.title = nowExc
                ? t('includeInAutoSelect', 'Include in auto-select')
                : t('excludeFromAutoSelect', 'Exclude from auto-select');
            div.classList.toggle('auto-sel-excluded', nowExc);
            // Re-run auto-pick if enabled – this may change the current selection
            reAutoPickAndRefresh();
        });
        div.appendChild(excl);
    }

    // Favorite star
    var fav=document.createElement('span');
    var _favActive=isFavoriteProxy(proxy);
    fav.className='modal-item-fav'+(_favActive?' active':'');
    fav.textContent='★';
    fav.title=_favTitle(_favActive); // [v3.1.2] восстановлен tooltip звезды
    fav.addEventListener('click',function(e){
        e.stopPropagation();
        toggleFavoriteProxy(proxy);
        fav.classList.toggle('active'); // мгновенный визуальный отклик звезды
        fav.title=_favTitle(fav.classList.contains('active')); // [v3.1.2] обновить tooltip
        // [v2.8.5 fix R3] Прямой вызов rebuildFavoritesSection убран. toggleFavoriteProxy
        // пишет favoriteServers → storage.onChanged(favoriteServers) сам перестраивает
        // список через buildServerModalList (seq-guarded). Раньше rebuildFavoritesSection
        // (прямой) + buildServerModalList (через onChanged) конкурировали и могли
        // ЗАДВОИТЬ секцию «Избранное».
    });
    div.appendChild(fav);

    var check=document.createElement('span');check.className='modal-item-check';check.textContent='\u2713';
    div.appendChild(check);

    if(isFreeBlocked){
        // [v2.7.3] Free-юзер нажимает на перегруженный сервер → блок-модал с upsell'ом
        div.addEventListener('click',function(){
            openFreeBlockedModal();
        });
    } else if(isLocked){
        // [v2.7.4 audit r6] Premium-сервер для Free-юзера – клик ведёт на upsell.
        // До этого клик проваливался без feedback (UX trap: visually disabled но clickable).
        div.addEventListener('click',function(){
            chrome.tabs.create({ url: upsellUrl('server_modal_lock') }).catch(() => {});
        });
    } else if(!isLocked){
        div.addEventListener('click',function(){
            function _doPick(){
                // [v2.5.9] Manual pick pins the server and disables auto-select.
                chrome.storage.local.set({ autoSelectServer: false }, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                    applyAutoSelectUI();
                });
                // Set native select
                proxySelect.value=key;
                proxySelect.dispatchEvent(new Event('change'));
                updateServerBtnLabel();
                // Update visual
                document.querySelectorAll('#serverModalList .modal-list-item').forEach(function(it){it.classList.remove('selected');});
                div.classList.add('selected');
                setTimeout(function(){closeModal('serverModal');},150);
            }
            // [v3.1.6] Подсказки для тех, кто не понимает обозначений: крестик (не отвечает / не
            // прошёл проверку) → окно «не удастся подключиться»; нет пинга (проверка не завершена)
            // → подтверждение «подождать / подключиться всё равно». Рабочий сервер выбирается сразу.
            var _isBroken = (pingInfo && pingInfo.cls==='fail') || (_brokenServersMap && _brokenServersMap[_bkey]);
            var _hasPing = pingInfo && pingInfo.text && parseInt(pingInfo.text,10) > 0;
            if (_isBroken) {
                showServerBroken(function(ok){ if(ok) _doPick(); });
            } else if (!_hasPing) {
                showServerNoPing(function(ok){ if(ok) _doPick(); });
            } else {
                _doPick();
            }
        });
    }
    // [v3.1.7] Подсказка при наведении: какие проверенные сайты открывались на ЭТОМ сервере,
    // с их состоянием и временем последней проверки (цвет = свежесть). Данные — накопитель
    // siteCheckByServer (пополняется после каждой проверки «Доступность сайта»).
    if (siteHits && typeof siteHits==='object' && Object.keys(siteHits).length) {
        div.classList.add('has-site-hits');
        div.addEventListener('mouseenter', function(){ _showServerSitesTip(div, siteHits, label); });
        div.addEventListener('mouseleave', _hideServerSitesTip);
    }
    return div;
}

// [v3.1.7] Единая плавающая подсказка (один элемент на весь список — паттерн _overloadConfirmCb).
var _siteTipEl=null;
function _ensureSiteTip(){
    if(_siteTipEl) return _siteTipEl;
    var el=document.createElement('div'); el.className='site-hover-tip'; el.style.display='none';
    el.setAttribute('role','tooltip');
    (document.body||document.documentElement).appendChild(el); _siteTipEl=el; return el;
}
// Свежесть проверки → цветовой класс: <15 мин зелёный, <2 ч жёлтый, старше — серый.
function _siteHitFreshCls(ts){
    var age=Date.now()-(Number(ts)||0);
    if(age<0) return 'stale';
    if(age<15*60*1000) return 'fresh';
    if(age<2*60*60*1000) return 'recent';
    return 'stale';
}
// Короткое «когда проверяли»: «только что», «N мин», «N ч», «N дн» (без сторонних либ и без 48-язык. единиц —
// используем короткие суффиксы из переводов с fallback).
function _siteHitAgeText(ts){
    var age=Date.now()-(Number(ts)||0); if(age<0) age=0;
    var m=Math.floor(age/60000);
    if(m<1) return t('siteHitJustNow','<1 мин.');
    if(m<60) return m+' '+t('siteHitMin','мин');
    var h=Math.floor(m/60); if(h<24) return h+' '+t('siteHitHour','ч');
    return Math.floor(h/24)+' '+t('siteHitDay','дн');
}
function _showServerSitesTip(row, hits, srvLabel){
    var el=_ensureSiteTip();
    while(el.firstChild) el.removeChild(el.firstChild);
    var head=document.createElement('div'); head.className='site-hover-tip-head';
    head.textContent=t('siteHitsHead','Проверенные сайты'); el.appendChild(head);
    var hosts=Object.keys(hits).sort(function(a,b){ return (Number(hits[b].ts)||0)-(Number(hits[a].ts)||0); });
    hosts.forEach(function(h){
        var r=hits[h]||{};
        var rowEl=document.createElement('div'); rowEl.className='site-hover-tip-row';
        var nm=document.createElement('span'); nm.className='site-hover-tip-host'; nm.textContent=h; rowEl.appendChild(nm);
        var st=document.createElement('span'); st.className='site-hover-tip-state '+(r.cls||'');
        st.textContent=(r.cls==='fail')?'✕':(r.text||'✓'); rowEl.appendChild(st);
        var tm=document.createElement('span'); tm.className='site-hover-tip-time '+_siteHitFreshCls(r.ts);
        tm.textContent=_siteHitAgeText(r.ts); rowEl.appendChild(tm);
        el.appendChild(rowEl);
    });
    el.style.display='block';
    // Позиционируем слева от строки; если места нет — справа; затем жёстко клэмпим в окно по обеим осям.
    var rect=row.getBoundingClientRect();
    var tw=el.offsetWidth, th=el.offsetHeight;
    var left=rect.left-tw-8;
    if(left<4) left=rect.right+8;
    left=Math.max(4, Math.min(left, window.innerWidth-tw-4));
    var top=Math.max(4, Math.min(rect.top, window.innerHeight-th-4));
    el.style.top=top+'px'; el.style.left=left+'px';
}
function _hideServerSitesTip(){ if(_siteTipEl) _siteTipEl.style.display='none'; }

// [v2.7.3] Открывает модал «Сервер недоступен для Free» с переходом на premium-upsell.
// Используется при клике на free-server с u>=75 в списке выбора И при попытке toggle ON
// если SW вернул reason='server_overloaded_free' (защита от race/обхода UI-блока).
function openFreeBlockedModal() {
    openModal('freeBlockedModal');
}

// [v3.0.3] Модалка-пояснение возможных гео-ограничений. country = ISO-2. Текст с подстановкой
// локализованного названия страны (как overloadConfirm с {n}). Закрытие – × или кнопка (data-close).
function openGeoBlockModal(country){
    var cname=(typeof getCountryName==='function' ? getCountryName(country) : '')||country||'';
    var titleEl=$('geoBlockTitle');
    if(titleEl) titleEl.textContent=t('geoBlockTitle','Возможны ограничения');
    var textEl=$('geoBlockText');
    if(textEl){
        var tmpl=t('geoBlockText','В этой стране ({country}) часто ограничивают интернет – YouTube, Instagram и другие сервисы могут не открываться. При подключении к серверу этой страны вы выходите в сеть из неё, поэтому такие сервисы могут не работать. Если они нужны – выберите сервер другой страны.');
        textEl.textContent=tmpl.split('{country}').join(cname);
    }
    var btn=$('geoBlockClose');
    if(btn) btn.textContent=t('freeBlockedCancel','Закрыть');
    openModal('geoBlockModal');
}
// Кнопка «Закрыть» в geoBlockModal: класс не .modal-close (тот = крестик), поэтому глобальный
// data-close хендлер её не ловит – вешаем явно (× сверху ловится глобально).
$('geoBlockClose')?.addEventListener('click', function(){ closeModal('geoBlockModal'); });

// [v3.0.3] Модалка-пояснение про общий лимит трафика (сервер может временно пропасть). country = ISO-2.
function openTrafficModal(country){
    var cname=(typeof getCountryName==='function' ? getCountryName(country) : '')||country||'';
    var titleEl=$('trafficTitle');
    if(titleEl) titleEl.textContent=t('trafficTitle','Возможны перебои');
    var textEl=$('trafficText');
    if(textEl){
        var tmpl=t('trafficText','У серверов этой страны ({country}) есть общий лимит трафика (на всех пользователей сразу, не лично на вас). Когда он исчерпан, сервер временно пропадает из списка и возвращается позже. Если нужен стабильный сервер – выберите другую страну.');
        textEl.textContent=tmpl.split('{country}').join(cname);
    }
    var btn=$('trafficClose');
    if(btn) btn.textContent=t('freeBlockedCancel','Закрыть');
    openModal('trafficModal');
}
$('trafficClose')?.addEventListener('click', function(){ closeModal('trafficModal'); });

// [v3.0.3] Финальная модалка «не удалось подключиться ни к одному серверу» (rescue исчерпал все).
// Прочнее баннера (не перетирается перерисовкой). Кнопки ведут на существующие функции.
function openNoServerModal(){
    var titleEl=$('noServerTitle'); if(titleEl) titleEl.textContent=t('noServerTitle','Не удалось подключиться');
    var textEl=$('noServerText'); if(textEl) textEl.textContent=t('noServerText','Не удалось подключиться ни к одному серверу. Возможно, ваш провайдер блокирует подключение. Попробуйте:');
    var l1=$('noServerClearCacheLabel'); if(l1) l1.textContent=t('clearCache','Очистить кэш');
    var l2=$('noServerDiagLabel'); if(l2) l2.textContent=t('fullDiagLabel','Полная диагностика');
    var l3=$('noServerSupportLabel'); if(l3) l3.textContent=t('supportButton','Поддержка');
    openModal('noServerModal');
}
$('noServerClearCache')?.addEventListener('click', function(){
    closeModal('noServerModal');
    var sb=$('openSettingsBtn'); if(sb) sb.click();          // открыть настройки (там кэш + видно подтверждение)
    var cb=$('clearCacheBtn'); if(cb) cb.click();
});
$('noServerDiag')?.addEventListener('click', function(){
    closeModal('noServerModal');
    var sb=$('openSettingsBtn'); if(sb) sb.click();          // открыть настройки (там виден прогресс диагностики)
    var db=$('fullDiagBtn'); if(db) db.click();
});
$('noServerSupport')?.addEventListener('click', function(){
    closeModal('noServerModal');
    var spb=$('supportBtn'); if(spb) spb.click();
});

// [v3.0.3] Модалка «Как обновить вручную» (из баннера «Доступна новая версия»). Тексты ставим
// при открытии (как остальные v3.0.3-модалки). Путь chrome://extensions/ – копируемый (открыть
// chrome:// по кнопке Chrome расширению не даёт, поэтому даём скопировать).
function openUpdateHelpModal(){
    var set=function(id,key,fb){ var el=$(id); if(el) el.textContent=t(key,fb); };
    set('updateHelpTitle','updateHelpTitle','Как обновить расширение');
    set('updateHelpIntro','updateHelpIntro','Обновитесь до последней версии – это быстро.');
    set('updateHelpManual','updateHelpManual','Чтобы обновить прямо сейчас вручную:');
    set('updateHelpStep1','updateHelpStep1','Скопируйте адрес ниже, вставьте его в адресную строку браузера и нажмите Enter.');
    set('updateHelpStep2','updateHelpStep2','Включите «Режим разработчика» (переключатель вверху справа).');
    set('updateHelpStep3','updateHelpStep3','Нажмите кнопку «Обновить».');
    set('updateHelpCopyLabel','updateHelpCopy','Копировать');
    set('updateHelpNote','updateHelpNote','Удалять расширение не нужно – иначе потеряете свои настройки (и премиум-ключ, если он у вас есть).');
    set('updateHelpOkLabel','updateHelpOk','Понятно');
    openModal('updateHelpModal');
}
$('updateHelpBtn')?.addEventListener('click', openUpdateHelpModal);
$('updateHelpBtn2')?.addEventListener('click', openUpdateHelpModal); // [v3.0.3] та же модалка из критичного баннера «Требуется обновление»
$('updateHelpOkBtn')?.addEventListener('click', function(){ closeModal('updateHelpModal'); });
// Копирование chrome://extensions/ (кнопка ИЛИ сам путь). Фолбэк textarea+execCommand.
function _copyUpdateHelpPath(){
    var path='chrome://extensions/';
    var lbl=$('updateHelpCopyLabel');
    var done=function(ok){
        if(lbl) lbl.textContent = ok ? t('updateHelpCopied','Скопировано ✓') : t('diagError','Ошибка');
        setTimeout(function(){ if(lbl) lbl.textContent=t('updateHelpCopy','Копировать'); }, 1800);
    };
    (navigator.clipboard && navigator.clipboard.writeText
        ? navigator.clipboard.writeText(path)
        : Promise.reject(new Error('no clipboard'))
    ).then(function(){ done(true); }).catch(function(){
        try {
            var ta=document.createElement('textarea');
            ta.value=path; ta.style.position='fixed'; ta.style.opacity='0';
            document.body.appendChild(ta); ta.select();
            var ok=document.execCommand && document.execCommand('copy');
            document.body.removeChild(ta); done(!!ok);
        } catch(e){ done(false); }
    });
}
$('updateHelpCopyBtn')?.addEventListener('click', _copyUpdateHelpPath);
$('updateHelpPath')?.addEventListener('click', _copyUpdateHelpPath);

// ═══════════════════════════════════════
// ═══ v2.4.3: LANGUAGE MODAL         ═══
// ═══════════════════════════════════════
$('openLangModal')?.addEventListener('click', function(){
    closeSettings();
    buildLangModalList();
    openModal('langModal');
});

function buildLangModalList(){
    var container=$('langModalList'); if(!container) return;
    container.innerHTML='';
    var curLang=getLang();
    // [v2.6.0] Единый источник списка языков – LANG_FLAGS. Отсортирован: ru и en в начало,
    // далее по алфавиту, как было в хардкод-списке до 2.6.0.
    var allCodes = Object.keys(LANG_FLAGS);
    var priority = ['ru','en'];
    var rest = allCodes.filter(function(c){ return priority.indexOf(c) < 0; }).sort();
    var langs = priority.concat(rest);
    langs.forEach(function(code){
        var div=document.createElement('div');
        div.className='modal-list-item'+(code===curLang?' selected':'');
        var main=document.createElement('div');main.className='modal-item-main';
        var fc=LANG_FLAGS[code];
        if(fc){
            var flagSrc='flags/'+fc+'.svg';
            var img=document.createElement('img');img.src=flagSrc;img.className='flag-img flag-img-lg';img.alt=code;
            main.appendChild(img);
        }
        var txt=document.createElement('span');txt.textContent=LANG_NAMES[code]||code;main.appendChild(txt);
        div.appendChild(main);
        var check=document.createElement('span');check.className='modal-item-check';check.textContent='\u2713';
        div.appendChild(check);
        div.addEventListener('click',function(){
            languageSelect.value=code;
            languageSelect.dispatchEvent(new Event('change'));
            updateLangBtn(code);
            document.querySelectorAll('#langModalList .modal-list-item').forEach(function(it){it.classList.remove('selected');});
            div.classList.add('selected');
            setTimeout(function(){closeModal('langModal');},150);
        });
        container.appendChild(div);
    });
}

// ═══════════════════════════════════════
// ═══ v2.4.3: CHECKER SITE MODAL     ═══
// ═══════════════════════════════════════
$('openCheckerSiteModal')?.addEventListener('click', function(){
    buildCheckerSiteModalList();
    openModal('checkerSiteModal');
});

function buildCheckerSiteModalList(){
    var container=$('checkerSiteModalList');var sel=$('checker-site'); if(!container||!sel) return;
    container.innerHTML='';
    var curVal=sel.value;
    for(var i=0;i<sel.options.length;i++){
        (function(opt,idx){
            var div=document.createElement('div');
            div.className='modal-list-item'+(opt.value===curVal?' selected':'');
            var main=document.createElement('div');main.className='modal-item-main';
            var txt=document.createElement('span');txt.textContent=opt.textContent;main.appendChild(txt);
            div.appendChild(main);
            var check=document.createElement('span');check.className='modal-item-check';check.textContent='\u2713';
            div.appendChild(check);
            div.addEventListener('click',function(){
                sel.selectedIndex=idx;sel.dispatchEvent(new Event('change'));
                checkerSiteBtnLabel.textContent=opt.textContent;
                document.querySelectorAll('#checkerSiteModalList .modal-list-item').forEach(function(it){it.classList.remove('selected');});
                div.classList.add('selected');
                setTimeout(function(){closeModal('checkerSiteModal');},150);
            });
            container.appendChild(div);
        })(sel.options[i],i);
    }
}

// Custom site toggle
if($('checker-site')) $('checker-site').addEventListener('change',function(){
    var ci=$('checker-custom');
    if(ci){if(this.value==='custom')ci.classList.remove('hidden');else ci.classList.add('hidden');}
    if(checkerSiteBtnLabel){
        var opt=this.options[this.selectedIndex];
        if(opt) checkerSiteBtnLabel.textContent=opt.textContent;
    }
    // [v2.8.0] Persist выбранный site – restore при reopen popup
    chrome.storage.local.set({ checkerSelectedSite: this.value }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
});
// [v2.8.0] Persist custom URL value – restore при reopen popup
if($('checker-custom')) $('checker-custom').addEventListener('input', function(){
    var v = this.value || '';
    chrome.storage.local.set({ checkerCustomSite: v }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
});

// ═══════════════════════════════════════
// ═══ v2.4.3: EXCLUSIONS (split)     ═══
// ═══════════════════════════════════════
var currentExclMode = 'blacklist';

function loadExclusions(){
    chrome.storage.local.get(['blacklistDomains','whitelistDomains','exclusionsMode'],function(d){
        currentExclMode = d.exclusionsMode || 'blacklist';
        updateExclModeUI();
        renderExclList('blacklistItems', d.blacklistDomains||[], 'black');
        renderExclList('whitelistItems', d.whitelistDomains||[], 'white');
        // [v2.6.5 audit] Передаём уже прочитанные данные – без этого updateExclSummary
        // делал отдельный storage.get тех же самых ключей (2× round-trip на одно открытие).
        updateExclSummary(d);
    });
}

function updateExclSummary(preloaded){
    var apply = function(d){
        var bc=$('exclBlackCount'),wc=$('exclWhiteCount');
        // [v2.7.5 audit r3] Array.isArray guard – pattern `||[]` undefined для object-corruption
        // (objects truthy → bypass fallback → `.length` = undefined в UI render).
        var bl=Array.isArray(d.blacklistDomains)?d.blacklistDomains:[];
        var wl=Array.isArray(d.whitelistDomains)?d.whitelistDomains:[];
        var mode=d.exclusionsMode||'blacklist';
        if(bc) bc.textContent=t('modeBlacklist','Blacklist')+': '+bl.length;
        if(wc) wc.textContent=t('modeWhitelist','Whitelist')+': '+wl.length;
        // Highlight active row
        var bRow=$('exclBlackSummary'),wRow=$('exclWhiteSummary');
        if(bRow){bRow.classList.toggle('active-mode',mode==='blacklist');}
        if(wRow){wRow.classList.toggle('active-mode',mode==='whitelist');}
        // Active badge
        var badge=$('exclActiveBadge');
        if(badge){
            var enabledTxt=t('exclEnabled','Enabled');
            if(mode==='blacklist'){
                badge.textContent=enabledTxt+': ⛔ '+t('modeBlacklist','Blacklist');
                // [v2.8.1 audit] Через CSS vars вместо hardcoded – нечитаемо на theme-dark.
                badge.style.background='var(--badge-block-bg)';badge.style.color='var(--badge-block-fg)';badge.style.borderColor='var(--badge-block-brd)';
            } else {
                badge.textContent=enabledTxt+': ✅ '+t('modeWhitelist','Whitelist');
                badge.style.background='var(--accent-lt)';badge.style.color='var(--accent-dk)';badge.style.borderColor='var(--accent-100)';
            }
        }
    };
    if (preloaded) { apply(preloaded); return; }
    chrome.storage.local.get(['blacklistDomains','whitelistDomains','exclusionsMode'], apply);
}

function updateExclModeUI(){
    var bBtn=$('modeBlacklistBtn'), wBtn=$('modeWhitelistBtn'), hint=$('exclusionsHint');
    if(!bBtn||!wBtn) return;
    bBtn.classList.toggle('active', currentExclMode==='blacklist');
    wBtn.classList.toggle('active', currentExclMode==='whitelist');
    if(hint){
        hint.textContent = currentExclMode==='blacklist'
            ? t('exclHintBlack','VPN disabled on these sites')
            : t('exclHintWhite','VPN works ONLY on these sites');
    }
}

// [v2.8.1 audit] Race guard – без него double-click blacklist↔whitelist queues two
// storage.set chains → SW получает дубль exclusionsUpdated → setProxy(true) с
// возможно stale excludedDomains. _exclModeInFlight + button disable.
var _exclModeInFlight = false;
function setExclMode(mode){
    if (_exclModeInFlight) return;
    _exclModeInFlight = true;
    var _exclBtns = [$('modeBlacklistBtn'), $('modeWhitelistBtn')];
    _exclBtns.forEach(function(b){ if(b) b.disabled = true; });
    currentExclMode=mode;
    chrome.storage.local.set({exclusionsMode:mode},function(){
        if(chrome.runtime&&chrome.runtime.lastError){
            console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);
            _exclBtns.forEach(function(b){ if(b) b.disabled = false; });
            _exclModeInFlight = false;
            return;
        }
        updateExclModeUI();
        updateExclSummary();
        syncExcludedDomains();
        setTimeout(function(){
            _exclBtns.forEach(function(b){ if(b) b.disabled = false; });
            _exclModeInFlight = false;
        }, 300);
    });
}

// Sync to excludedDomains based on mode
function syncExcludedDomains(){
    var storageKey = currentExclMode==='blacklist' ? 'blacklistDomains' : 'whitelistDomains';
    chrome.storage.local.get([storageKey],function(d){
        chrome.storage.local.set({excludedDomains: d[storageKey]||[]},function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            chrome.runtime.sendMessage({action:'exclusionsUpdated'}).catch(()=>{}); // [audit] no-op .catch
        });
    });
}

function renderExclList(containerId, list, listType){
    var c=$(containerId); if(!c) return;
    c.innerHTML='';
    if(!list.length){
        // [v2.5.8 audit] DOM API вместо innerHTML+t() – переводы могут содержать спецсимволы
        var empty=document.createElement('div');
        empty.className='no-exclusions';
        empty.textContent=t('noExclusions','List is empty');
        c.appendChild(empty);
        return;
    }
    list.forEach(function(domain){
        var item=document.createElement('div');item.className='exclusion-item';
        var span=document.createElement('span');span.textContent=domain;item.appendChild(span);
        var btn=document.createElement('button');
        btn.type='button';
        btn.className='remove-excl';
        // [v2.8.1 audit] data-domain (\u043d\u0435 data-idx) \u2014 \u0443\u0441\u0442\u0440\u0430\u043d\u044f\u0435\u0442 lost-update race
        // \u043c\u0435\u0436\u0434\u0443 concurrent add/remove \u0438\u0437 \u0440\u0430\u0437\u043d\u044b\u0445 popup'\u043e\u0432 \u0438\u043b\u0438 \u0431\u044b\u0441\u0442\u0440\u044b\u0445 \u043a\u043b\u0438\u043a\u043e\u0432.
        btn.dataset.domain=domain;
        btn.dataset.list=listType;
        btn.textContent='\u2715';
        item.appendChild(btn);
        c.appendChild(item);
    });
    // [v2.7.6 audit Pass6] Per-item addEventListener \u0443\u0431\u0440\u0430\u043d \u2014 leak per-call accumulation
    // \u043f\u0440\u0438 \u043a\u0430\u0436\u0434\u043e\u043c re-render (add/remove \u0434\u043e\u043c\u0435\u043d\u0430). Single delegation listener attached once
    // \u0432 init-\u0431\u043b\u043e\u043a\u0435 popup'\u0430 \u2014 \u0441\u043c. \u043d\u0438\u0436\u0435 \u043f\u043e\u0441\u043b\u0435 init-\u0444\u0443\u043d\u043a\u0446\u0438\u0439.
}

function addExclItem(listType){
    var inputId = listType==='black' ? 'blacklistInput' : 'whitelistInput';
    var storageKey = listType==='black' ? 'blacklistDomains' : 'whitelistDomains';
    var containerId = listType==='black' ? 'blacklistItems' : 'whitelistItems';
    var input=$(inputId); var raw=(input.value||'').trim();
    if(!raw) return;
    // [v2.5.8 audit] Поддержка IDN/punycode через URL constructor (sберванк.рф → xn--80aikhbnlm.xn--p1ai)
    var domain;
    try {
        var withProto = /^https?:\/\//i.test(raw) ? raw : 'https://' + raw;
        var u = new URL(withProto);
        domain = u.hostname.toLowerCase().replace(/^www\./, '');
    } catch(e) { return; }
    // [v2.6.4 fix] Разрешаем не только доменные имена, но и localhost + IPv4.
    // Раньше `indexOf('.')<0` блокировал localhost; теперь proверяем отдельно.
    var isLocalhost = domain === 'localhost';
    var isIPv4 = /^(\d{1,3}\.){3}\d{1,3}$/.test(domain);
    var isDomain = domain.length >= 4 && domain.indexOf('.') >= 0;
    if (!domain || (!isLocalhost && !isIPv4 && !isDomain)) return;
    // [v2.7.0 fix F60] Cap длины домена – RFC 1035 макс 253; 200 даёт запас и защищает
    // от paste-bomb атаки (10KB «домен» проходит валидацию, создаёт гигантский regex
    // для DNR и ломает всю цепочку addRules в syncAutoEnableDnrRules).
    if (domain.length > 200) return;
    // [v2.7.5 audit r3] ASCII-only validation – symmetric с addAutoEnableItem (line 3233).
    // URL.hostname возвращает punycode IDN форму но + non-ASCII edge-cases возможны.
    // Без guard'а в PAC-script / DNR regex могут попасть символы ломающие RE2.
    if (!/^[a-z0-9.-]+$/.test(domain)) return;
    chrome.storage.local.get([storageKey],function(d){
        var list=Array.isArray(d[storageKey])?d[storageKey]:[];
        if(list.indexOf(domain)>=0) return;
        list.push(domain);
        var obj={}; obj[storageKey]=list;
        chrome.storage.local.set(obj,function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            renderExclList(containerId, list, listType);
            input.value='';
            updateExclSummary();
            syncExcludedDomains();
        });
    });
}

function removeExclItem(listType, domain){
    if (!domain) return;
    var storageKey = listType==='black' ? 'blacklistDomains' : 'whitelistDomains';
    var containerId = listType==='black' ? 'blacklistItems' : 'whitelistItems';
    chrome.storage.local.get([storageKey],function(d){
        // [v2.8.0 audit r2] Array.isArray guard симметрично F128-F143 pattern. Без него
        // corrupt storage (object вместо array из ручного редактирования / старого формата)
        // даст TypeError на .splice → silent catch → UI не обновится.
        var list = Array.isArray(d[storageKey]) ? d[storageKey] : [];
        // [v2.8.1 audit] removeByValue – индекс мог быть устаревшим к моменту set
        // (lost-update race с другим popup'ом или быстрым add). Идемпотентно при повторе.
        var pos = list.indexOf(domain);
        if (pos < 0) {
            renderExclList(containerId, list, listType);
            return;
        }
        list.splice(pos,1);
        var obj={}; obj[storageKey]=list;
        chrome.storage.local.set(obj,function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            renderExclList(containerId, list, listType);
            updateExclSummary();
            syncExcludedDomains();
        });
    });
}

// ═══ [v2.6.4] AUTO-ENABLE VPN (Premium feature) ═══
// Тумблер (on/off) + counter + модалка со списком. Логика auto-включения – в SW.
function loadAutoEnable(){
    chrome.storage.local.get(['autoEnableEnabled','autoEnableDomains'], function(d){
        var toggle=$('autoEnableToggle');
        if(toggle) toggle.checked = d.autoEnableEnabled !== false; // default ON
        // [v2.8.0 audit r7] Array.isArray guard симметрично F128-F143 – corrupted storage
        // (object вместо array) даст .length=undefined, Number coerce в NaN, UI broken.
        var list = Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : [];
        updateAutoEnableCount(list.length);
        renderAutoEnableList(list);
    });
}
function updateAutoEnableCount(n){
    var el = $('autoEnableCountText');
    if (!el) return;
    if (n === 0) el.textContent = t('autoEnableCount0', 'Сайтов пока нет – добавьте первый');
    else el.textContent = (t('autoEnableCountN', 'Сайтов в списке:') + ' ' + n);
}
// [v2.6.5] Запрос webNavigation permission для раннего перехвата navigation.
// Без него в Opera/некоторых Chromium auto-enable срабатывает с задержкой –
// webRequest.onBeforeRequest fires только после старта запроса.
// Идемпотентно: если permission уже выдан – silent. Если юзер отказал – флаг
// `_webNavRefused` блокирует повторный prompt (чтобы не было spam'а).
// Браузер показывает встроенный prompt с пустой строкой "Будет разрешено:" –
// это потому что у расширения уже есть `host_permissions: <all_urls>`, и для
// webNavigation браузеру нечего добавить в warning. Поэтому ДО request показываем
// объяснение – иначе юзер не понимает за что соглашается.
function ensureWebNavPermission(){
    if (!chrome.permissions || !chrome.permissions.request) return;
    chrome.permissions.contains({permissions:['webNavigation']}, function(has){
        if (has) return;
        chrome.storage.local.get(['_webNavRefused'], function(d){
            if (d._webNavRefused) return;
            var msg = t('webNavPermPrompt',
                'Для мгновенного автовключения VPN нужно дополнительное разрешение браузера. Сейчас появится системный запрос – нажмите «Разрешить» (поле «Будет разрешено» в нём может быть пустым, это нормально).');
            if (!confirm(msg)) {
                chrome.storage.local.set({_webNavRefused: true}, function(){
                    if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                });
                return;
            }
            // [v2.7.4 audit r5] Корректный lastError-check на permissions.request callback
            // (раньше комментарий говорил "storage.set failed" – copy-paste ошибка из autoEnableToggle).
            chrome.permissions.request({permissions:['webNavigation']}, function(granted){
                if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] permissions.request failed:",chrome.runtime.lastError.message);return;}
                if (!granted) chrome.storage.local.set({_webNavRefused: true}, function(){
                    if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                });
            });
        });
    });
}

// Toggle handler – моментально персистим
$('autoEnableToggle')?.addEventListener('change', function(){
    var self = this;
    var checked = !!self.checked;
    chrome.storage.local.set({ autoEnableEnabled: checked }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
    // [v2.7.0 fix F31] Если permission denied (или уже отказано ранее), revert toggle
    // обратно на OFF и показать message – иначе UI показывает ON, но фича не работает
    // (auto-enable требует webNavigation permission для tier-1 события).
    if (checked && chrome.permissions && chrome.permissions.contains) {
        chrome.permissions.contains({permissions:['webNavigation']}, function(has){
            if (has) return; // уже выдан, нет проблемы
            chrome.storage.local.get(['_webNavRefused'], function(d){
                if (d._webNavRefused) {
                    // Юзер уже отказал ранее – revert toggle, не дёргаем prompt снова
                    self.checked = false;
                    chrome.storage.local.set({ autoEnableEnabled: false }, function(){
                        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                    });
                    showStatusMessage(t('autoEnablePermDenied', 'Auto-enable требует разрешения "webNavigation". Снимите отказ в chrome://extensions/'), true, 'auto');
                    return;
                }
                // [v2.7.0 fix F31.1] Disable toggle + poll до 15 сек – медленный юзер
                // (читает confirm + browser-prompt) может не успеть с одноразовым 500ms check.
                // Раньше: setTimeout(500) часто срабатывал ДО юзерского "Allow" → false revert.
                self.disabled = true;
                ensureWebNavPermission();
                var _attempts = 0;
                var _pollId = setInterval(function(){
                    _attempts++;
                    chrome.permissions.contains({permissions:['webNavigation']}, function(stillHas){
                        if (stillHas) {
                            clearInterval(_pollId);
                            self.disabled = false;
                            return;
                        }
                        if (_attempts >= 15) { // 15-сек cap
                            clearInterval(_pollId);
                            self.disabled = false;
                            self.checked = false;
                            chrome.storage.local.set({ autoEnableEnabled: false }, function(){
                                if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                            });
                            showStatusMessage(t('autoEnablePermDenied', 'Auto-enable требует разрешения "webNavigation".'), true, 'auto');
                        }
                    });
                }, 1000);
            });
        });
    }
});
// Открытие модалки со списком
$('openAutoEnableModal')?.addEventListener('click', function(){
    loadAutoEnable(); // refresh before open
    openModal('autoEnableModal');
});
function renderAutoEnableList(list){
    var c=$('autoEnableList'); if(!c) return;
    c.innerHTML='';
    if(!list.length){
        var empty=document.createElement('div');
        empty.className='no-exclusions';
        empty.textContent=t('autoEnableEmpty','Список пуст – VPN не включается автоматически');
        c.appendChild(empty);
        // [v2.8.1 audit] обнуляем счётчик при удалении последнего домена.
        // Раньше early-return пропускал updateAutoEnableCount → юзер видел stale «Сайтов в списке: 1».
        updateAutoEnableCount(0);
        return;
    }
    list.forEach(function(domain){
        var item=document.createElement('div'); item.className='exclusion-item';
        var span=document.createElement('span'); span.textContent=domain; item.appendChild(span);
        var btn=document.createElement('button');
        btn.type='button'; btn.className='remove-excl';
        // [v2.8.1 audit] data-domain (по значению), не data-idx – устраняет lost-update race
        // между concurrent get→splice→set из multi-popup или add+delete в одном popup.
        btn.dataset.domain=domain; btn.textContent='\u2715';
        item.appendChild(btn);
        c.appendChild(item);
    });
    // [v2.7.6 audit Pass6] Per-item addEventListener \u0443\u0431\u0440\u0430\u043d \u2014 \u0441\u043c. renderExclList \u0432\u044b\u0448\u0435.
    updateAutoEnableCount(list.length);
}
function addAutoEnableItem(){
    var input=$('autoEnableInput'); if(!input) return;
    var raw=(input.value||'').trim();
    if(!raw) return;
    var domain;
    try {
        var withProto = /^https?:\/\//i.test(raw) ? raw : 'https://' + raw;
        var u = new URL(withProto);
        domain = u.hostname.toLowerCase().replace(/^www\./, '');
    } catch(e) { return; }
    // Та же валидация что для exclusions: домен / localhost / IPv4
    var isLocalhost = domain === 'localhost';
    var isIPv4 = /^(\d{1,3}\.){3}\d{1,3}$/.test(domain);
    var isDomain = domain.length >= 4 && domain.indexOf('.') >= 0;
    if (!domain || (!isLocalhost && !isIPv4 && !isDomain)) return;
    // [v2.7.0 fix F56] ASCII-only guard – в SW syncAutoEnableDnrRules фильтрует
    // `/^[a-z0-9.-]+$/` (RE2 не ест IDN). Раньше юзер вводил `пример.рф`, URL парсер
    // конвертил в punycode `xn--e1afmkfd.xn--p1ai` (ASCII – проходит), но если каким-то
    // путём стораж содержал кириллицу – DNR silently её отбрасывал, auto-enable не работал
    // без объяснений. Теперь явно отказываем при non-ASCII.
    if (!/^[a-z0-9.-]+$/.test(domain)) {
        showStatusMessage(t('autoEnableInvalidDomain', 'Only Latin letters, digits, dot and dash allowed'), true);
        return;
    }
    // [v2.7.0 fix F60] Cap длины домена – см. addExclItem выше.
    if (domain.length > 200) return;

    chrome.storage.local.get(['autoEnableDomains','blacklistDomains'], function(d){
        // [v2.7.1 fix F140] Array.isArray – corrupted storage не должна валить .indexOf/.splice
        var list = Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : [];
        if (list.indexOf(domain) >= 0) { input.value=''; return; }
        // [v2.6.5 audit] DNR-правила в SW имеют cap 500 доменов (AE_DNR_MAX_DOMAINS).
        // Сверх лимита сетевой перехват не работает – остаётся только event-based fallback
        // через webRequest/tabs.onUpdated (Yandex-сценарий сломается). Предупреждаем юзера.
        if (list.length >= 500) {
            // [v2.6.5 audit r2] hardcoded fallback по-английски, потому что `t()` возвращает
            // этот аргумент когда и user lang, и en в cachedTranslationsData отсутствуют –
            // на первом open у новых юзеров кэш ещё пуст, Russian fallback ломал UX не-ru юзеров.
            showStatusMessage(t('autoEnableMaxReached', 'Maximum of 500 domains reached'), true);
            return;
        }
        // Warn если домен в blacklist – auto-enable сильнее, но bypass blacklist'а будет конфликтовать
        // [v2.7.1 fix F141] Array.isArray – см. F140
        var blist = Array.isArray(d.blacklistDomains) ? d.blacklistDomains : [];
        if (blist.indexOf(domain) >= 0) {
            if (!confirm(t('autoEnableBlacklistConflict', 'Этот домен в списке исключений (VPN отключается). Удалить из исключений, чтобы auto-enable работало?'))) {
                // Юзер отказался – не добавляем в auto-enable (будет бесполезно)
                return;
            }
            // Убираем из blacklist
            blist.splice(blist.indexOf(domain), 1);
            chrome.storage.local.set({blacklistDomains: blist}, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
                // Refresh blacklist UI если открыт
                renderExclList('blacklistItems', blist, 'black');
                updateExclSummary();
                syncExcludedDomains();
            });
        }
        list.push(domain);
        chrome.storage.local.set({autoEnableDomains: list}, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            renderAutoEnableList(list);
            input.value='';
            ensureWebNavPermission(); // [v2.6.5] на первом добавлении домена
        });
    });
}
function removeAutoEnableItem(domain){
    if (!domain) return;
    chrome.storage.local.get(['autoEnableDomains','autoEnableHistory'], function(d){
        // [v2.7.1 fix F142] Array.isArray – см. F140
        var list = Array.isArray(d.autoEnableDomains) ? d.autoEnableDomains : [];
        // [v2.8.1 audit] removeByValue вместо splice(idx). idx-based страдал от race:
        // другой popup/SW менял список между get и set, splice бил по чужому элементу.
        var pos = list.indexOf(domain);
        if (pos < 0) {
            // [v2.8.1 audit] идемпотентность: домен уже удалён (другой popup/SW успел).
            // Просто перерендерим UI с актуальным storage state, без повторного set.
            renderAutoEnableList(list);
            return;
        }
        list.splice(pos, 1);
        // [v2.8.1 audit] чистим debounce-историю удалённого домена – иначе в storage
        // копится мусор (key=domain, value=timestamp) от уже несуществующих доменов;
        // на real-update STALE_KEYS не чистит autoEnableHistory (его нет в STALE_KEYS).
        var hist = (d.autoEnableHistory && typeof d.autoEnableHistory === 'object' && !Array.isArray(d.autoEnableHistory))
            ? d.autoEnableHistory : null;
        var setObj = { autoEnableDomains: list };
        if (hist && Object.prototype.hasOwnProperty.call(hist, domain)) {
            delete hist[domain];
            setObj.autoEnableHistory = hist;
        }
        chrome.storage.local.set(setObj, function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            renderAutoEnableList(list);
        });
    });
}
$('autoEnableAddBtn')?.addEventListener('click', addAutoEnableItem);
$('autoEnableInput')?.addEventListener('keydown', function(e){
    if (e.key === 'Enter') { e.preventDefault(); addAutoEnableItem(); }
});

// Copy buttons
$('copyToWhiteBtn')?.addEventListener('click',function(){
    chrome.storage.local.get(['blacklistDomains','whitelistDomains'],function(d){
        // [v2.7.1 fix F143] Array.isArray – corrupted storage не валит .forEach/.push
        var bl=Array.isArray(d.blacklistDomains)?d.blacklistDomains:[], wl=Array.isArray(d.whitelistDomains)?d.whitelistDomains:[];
        bl.forEach(function(dom){ if(wl.indexOf(dom)<0) wl.push(dom); });
        chrome.storage.local.set({whitelistDomains:wl},function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            renderExclList('whitelistItems',wl,'white');
            updateExclSummary(); syncExcludedDomains();
        });
    });
});
$('copyToBlackBtn')?.addEventListener('click',function(){
    chrome.storage.local.get(['blacklistDomains','whitelistDomains'],function(d){
        // [v2.7.1 fix F143] Array.isArray – см. выше
        var bl=Array.isArray(d.blacklistDomains)?d.blacklistDomains:[], wl=Array.isArray(d.whitelistDomains)?d.whitelistDomains:[];
        wl.forEach(function(dom){ if(bl.indexOf(dom)<0) bl.push(dom); });
        chrome.storage.local.set({blacklistDomains:bl},function(){if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            renderExclList('blacklistItems',bl,'black');
            updateExclSummary(); syncExcludedDomains();
        });
    });
});

$('addBlacklistBtn')?.addEventListener('click',function(){addExclItem('black');});
$('addWhitelistBtn')?.addEventListener('click',function(){addExclItem('white');});
$('blacklistInput')?.addEventListener('keydown',function(e){if(e.key==='Enter')addExclItem('black');});
$('whitelistInput')?.addEventListener('keydown',function(e){if(e.key==='Enter')addExclItem('white');});
$('modeBlacklistBtn')?.addEventListener('click',function(){setExclMode('blacklist');});
$('modeWhitelistBtn')?.addEventListener('click',function(){setExclMode('whitelist');});

// Open exclusions modal
$('openExclusionsModal')?.addEventListener('click',function(){
    loadExclusions();
    openModal('exclusionsModal');
});

// ═══════════════════════════════════════
// ═══ v2.4.3: COLOR THEME            ═══
// ═══════════════════════════════════════
var THEMES = [
    {id:'default',  label_ru:'Зелёная',      label_en:'Green'},
    {id:'blue',     label_ru:'Синяя',        label_en:'Blue'},
    {id:'purple',   label_ru:'Фиолетовая',   label_en:'Purple'},
    {id:'indigo',   label_ru:'Индиго',       label_en:'Indigo'},
    {id:'ocean',    label_ru:'Океан',        label_en:'Ocean'},
    {id:'cyan',     label_ru:'Голубая',      label_en:'Cyan'}, // [v3.1.1] было «Бирюза» – дублировало teal «Бирюзовая»; свотч #00e5ff = голубой
    {id:'teal',     label_ru:'Бирюзовая',    label_en:'Teal'},
    {id:'forest',   label_ru:'Лесная',       label_en:'Forest'},
    {id:'lime',     label_ru:'Лаймовая',     label_en:'Lime'},
    {id:'amber',    label_ru:'Янтарная',     label_en:'Amber'},
    {id:'orange',   label_ru:'Оранжевая',    label_en:'Orange'},
    {id:'red',      label_ru:'Красная',      label_en:'Red'},
    {id:'wine',     label_ru:'Вино',         label_en:'Wine'},
    {id:'pink',     label_ru:'Розовая',      label_en:'Pink'},
    {id:'brown',    label_ru:'Кофейная',     label_en:'Brown'},
    {id:'steel',    label_ru:'Стальная',     label_en:'Steel'},
    {id:'dark',     label_ru:'Тёмная',       label_en:'Dark'}
];
var currentThemeId = 'default';

function getThemeLabel(theme){
    return getLang()==='ru' ? (theme.label_ru||theme.id) : (theme.label_en||theme.id);
}

function applyTheme(name){
    THEMES.forEach(function(t){document.body.classList.remove('theme-'+t.id);});
    document.body.classList.add('theme-'+name);
    currentThemeId = name;
    // Update preview
    var ps=$('themePreviewSwatch'), pn=$('themePreviewName');
    if(ps) ps.className='theme-preview-swatch swatch-'+name;
    var theme = THEMES.filter(function(t){return t.id===name;})[0];
    if(pn && theme) pn.textContent=getThemeLabel(theme);
    // Update modal active state
    document.querySelectorAll('#themeGrid .theme-swatch').forEach(function(sw){
        sw.classList.toggle('active',sw.getAttribute('data-theme')===name);
    });
}

function buildThemeGrid(){
    var grid=$('themeGrid'); if(!grid) return;
    grid.innerHTML='';
    THEMES.forEach(function(theme){
        var btn=document.createElement('button');
        btn.type='button'; // [v3.1.1] консистентно с остальными кнопками (default submit)
        btn.className='theme-swatch'+(theme.id===currentThemeId?' active':'');
        btn.setAttribute('data-theme',theme.id);
        var fill=document.createElement('span');
        fill.className='swatch-fill swatch-'+theme.id;
        var lbl=document.createElement('span');
        lbl.className='swatch-label';
        lbl.textContent=getThemeLabel(theme);
        btn.appendChild(fill);
        btn.appendChild(lbl);
        btn.addEventListener('click',function(){
            applyTheme(theme.id);
            chrome.storage.local.set({colorTheme:theme.id}, function(){
                if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            });
        });
        grid.appendChild(btn);
    });
}

$('openThemeModal')?.addEventListener('click',function(){
    buildThemeGrid();
    openModal('themeModal');
});

// ═══════════════════════════════════════
// ═══ PREMIUM TAB                     ═══
// ═══════════════════════════════════════
function updatePremiumTabLock() {
    chrome.storage.local.get(['isPremium', 'accountVerified'], function(d) {
        var isPremium = !!d.isPremium;
        var isVerified = d.accountVerified === true;
        var locked = !isPremium;
        // [v2.8.0] Checker – unlocked для Premium ИЛИ verified-email юзеров. Юзер прошёл
        // email-verify на anon-vpn.ru → доказал владение почтой → можем дать lightweight feature.
        var checkerLocked = !isPremium && !isVerified;
        var pairs=[
            ['checkerLock','checkerContent', checkerLocked],
            ['exclusionsLock','exclusionsContent', locked],
            ['adBlockerLock','adBlockerContent', locked],
            ['autoEnableLock','autoEnableContent', locked],
            ['themeLock','themeContent', locked],
            // [v2.7.6] Резервная копия – Premium-only фича
            ['backupLock','backupContent', locked]
        ];
        pairs.forEach(function(p){
            var lk=$(p[0]),ct=$(p[1]),itemLocked=p[2];
            if(lk){if(itemLocked)lk.classList.remove('hidden');else lk.classList.add('hidden');}
            if(ct){ct.style.opacity=itemLocked?'0.4':'1';ct.style.pointerEvents=itemLocked?'none':'auto';}
        });
        // [v2.8.0] premiumPromo блок удалён из DOM – guard на $() не нужен, но keep harmless
        // Premium activate block: hide key input when premium, change button text
        var pab=$('premiumActivateBlock');
        var pib=$('premiumInputBlock');
        var bpb=$('buyPremiumBtn');
        if(pib){pib.style.display=locked?'flex':'none';}
        var trialHint=$('premiumTrialHint');
        if(trialHint){trialHint.textContent=locked?t('trialHintTg','Попробовать через Telegram'):'';trialHint.style.display=locked?'block':'none';}
        // [v2.6.2] One-click trial кнопка – только для free-юзеров
        var trialBtn=$('tryTrialBtn');
        // [v3.0.0] Скрываем trial-кнопку и при использованном trial (_trialExhausted===true),
        // не только при premium. null (storage ещё не прочитан) → показываем (free по умолчанию).
        if(trialBtn){trialBtn.style.display=(locked && _trialExhausted!==true)?'flex':'none';}
        // [v2.6.2] Recovery кнопка – тоже только для free (премиум активен → нечего восстанавливать)
        var recoverBtn=$('recoverPremiumBtn');
        if(recoverBtn){recoverBtn.style.display=locked?'flex':'none';}
        if(bpb){
            bpb.textContent=locked?t('buyPremiumButton','Купить премиум'):t('managePremium','Управление премиумом');
        }
    });
}

// ═══ PROXY CHECKER (v2.6.2 переделан: full-popup modal со списком всех серверов) ═══
var CHECKER_PATH='/AnonVPN/proxy_check.php'; // [v2.8.7] относительный путь для apiFetch
var CHECKER_API='https://apiget.ru/AnonVPN/proxy_check.php'; // legacy, не используется
// [audit] NOT a confidential secret – CRX is public, anyone can extract this value.
// Server-side rate limiting + ext_id whitelist provide real authentication.
var API_AUTH_KEY='EXT_anon_2024_v3_key';

var checkerMode = 'ping'; // 'ping' or 'site'
var _checkAllAborted = false;
var _checkAllRunning = false;

// Gradient color class: 0ms=green → 1000ms+=red
function pingCls(ms){
    if(ms<100) return 'ping-0';
    if(ms<200) return 'ping-1';
    if(ms<400) return 'ping-2';
    if(ms<600) return 'ping-3';
    if(ms<900) return 'ping-4';
    return 'ping-5';
}

function setCheckerMode(mode){
    checkerMode = mode;
    var pBtn=$('modePingBtn'), sBtn=$('modeSiteBtn');
    if(pBtn) pBtn.classList.toggle('active', mode==='ping');
    if(sBtn) sBtn.classList.toggle('active', mode==='site');
    var siteRow=$('checkerSiteRow'), customInp=$('checker-custom');
    if(siteRow) siteRow.classList.toggle('hidden', mode==='ping');
    if(mode==='ping' && customInp) customInp.classList.add('hidden');
    // [v3.1.7] Кнопка автоподбора сервера для сайта — только в site-режиме
    var apBtn=$('autoPickBtn'); if(apBtn) apBtn.classList.toggle('hidden', mode!=='site');
    // При смене режима очищаем прошлые результаты
    var list=$('checkerServerList');
    if (list) {
        list.querySelectorAll('.checker-item-result').forEach(function(r){
            r.textContent='–'; r.className='checker-item-result';
        });
    }
    // [v2.8.0] Persist выбранный mode – restore при reopen popup
    chrome.storage.local.set({ checkerMode: mode }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
}

// [v2.8.0] Restore checker UI state из storage. Mode + selected site + custom URL.
// Вызывается перед buildCheckerList в openCheckerModal click – гарантирует что DOM
// state синхронен со stored state, и _applyStoredCheckerResults видит match (site совпадает).
async function _restoreCheckerState() {
    var d = await new Promise(function(resolve){
        chrome.storage.local.get(['checkerMode', 'checkerSelectedSite', 'checkerCustomSite'], function(r){ resolve(r||{}); });
    });
    if (d.checkerMode === 'ping' || d.checkerMode === 'site') {
        checkerMode = d.checkerMode;
    }
    var sel = $('checker-site');
    if (sel && d.checkerSelectedSite) {
        // Проверяем что значение существует в options (новые версии могли переименовать)
        var found = false;
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].value === d.checkerSelectedSite) {
                sel.selectedIndex = i; found = true; break;
            }
        }
        if (found && checkerSiteBtnLabel) {
            var opt = sel.options[sel.selectedIndex];
            if (opt) checkerSiteBtnLabel.textContent = opt.textContent;
        }
    }
    var customInp = $('checker-custom');
    if (customInp && typeof d.checkerCustomSite === 'string') {
        customInp.value = d.checkerCustomSite;
    }
}
// [v2.8.0] При смене mode – переприменяем rate-limit UI (limits разные для ping/site)
// и восстанавливаем результаты последней проверки в этом mode'е (если есть).
async function _onCheckerModeChange(mode) {
    setCheckerMode(mode);
    await _applyStoredCheckerResults();
    var gate = await _checkerRateLimitGate(true);
    _applyCheckerCooldownUI(gate);
}
$('modePingBtn')?.addEventListener('click', function(){_onCheckerModeChange('ping');});
$('modeSiteBtn')?.addEventListener('click', function(){_onCheckerModeChange('site');});

// Построение списка серверов внутри checkerModal
var _buildCheckerListSeq = 0;
async function buildCheckerList(){
    var container=$('checkerServerList'); if(!container||!cachedProxyList) return;
    var tr=cachedTranslations||{}, lang=getLang();
    var sL=(tr[lang]&&tr[lang].serverItem)||'Server';
    var pL=(tr[lang]&&tr[lang].premiumServer)||'Premium server';
    var freeList=cachedProxyList.filter(function(p){return p.type!=='premium';});
    var premList=cachedProxyList.filter(function(p){return p.type==='premium';});

    // key-prefix ('p'/'f') and numbering are tied to position in premList/freeList \u2014
    // render order of the blocks does not affect keys (data-key result-restore stays safe).
    function renderPremBlock(){
        if(premList.length){
            var hdr=document.createElement('div');
            hdr.className='modal-section-label'; hdr.textContent='\u2B50 '+pL;
            container.appendChild(hdr);
        }
        premList.forEach(function(proxy,i){
            container.appendChild(createCheckerListItem(proxy, 'p'+i, pL+' \u2116'+(i+1)));
        });
    }
    function renderFreeBlock(){
        if(freeList.length){
            var hdr2=document.createElement('div');
            hdr2.className='modal-section-label'; hdr2.textContent=sL;
            container.appendChild(hdr2);
        }
        freeList.forEach(function(proxy,i){
            container.appendChild(createCheckerListItem(proxy, 'f'+i, sL+' \u2116'+(i+1)));
        });
    }
    // [v2.8.5] Block order depends on user tier:
    //  - Premium: premium servers first (he uses them) \u2014 same as before 2.8.5.
    //  - Free (incl. free-verified): free servers first \u2014 those are the ones available to him.
    // [v2.8.5 audit] Re-entrancy guard: this fn is async (awaits storage.get below).
    // Two concurrent calls (openCheckerModal + language-change rebuild) could interleave
    // and double-append. A superseded call bails after the await without touching DOM.
    var mySeq = ++_buildCheckerListSeq;
    var isPrem = await new Promise(function(resolve){
        chrome.storage.local.get(['isPremium'], function(r){ resolve(!!(r && r.isPremium)); });
    });
    if (mySeq !== _buildCheckerListSeq) return; // superseded by a newer rebuild
    container.innerHTML='';
    if(isPrem){ renderPremBlock(); renderFreeBlock(); }
    else      { renderFreeBlock(); renderPremBlock(); }
}

function createCheckerListItem(proxy, key, label){
    var div=document.createElement('div');
    div.className='checker-item';
    div.setAttribute('data-key', key);
    var main=document.createElement('div'); main.className='checker-item-main';
    if(proxy.country){
        var img=getFlagImg(proxy.country);
        if(img) main.appendChild(img);
        div.title=getCountryName(proxy.country);
    }
    var txt=document.createElement('span'); txt.textContent=label; main.appendChild(txt);
    div.appendChild(main);
    var result=document.createElement('span');
    result.className='checker-item-result'; result.textContent='–';
    div.appendChild(result);
    var btn=document.createElement('button');
    btn.type='button'; btn.className='checker-item-btn';
    btn.textContent=t('checkBtnShort', 'Проверить');
    btn.addEventListener('click', async function(){
        // [v2.8.0] Free-verified не должны попадать сюда – кнопки disabled через _applyCheckerCooldownUI.
        // Premium всегда ok=true. Defensive guard на случай race.
        var gate = await _checkerRateLimitGate();
        if (!gate.ok) return;
        // [v2.8.1] Симметрия с runCheckAll: расход фиксируем в finally – иначе если
        // popup закроется mid-fetch или throw случится между await и _recordCheckerRun,
        // free-verified юзер сможет абузить лимит (запустить → закрыть → запустить снова).
        try {
            await runSingleCheck(div);
        } finally {
            if (!gate.isPremium && gate.isVerified) {
                try { await _recordCheckerRun(checkerMode || 'ping'); } catch(_){}
                try {
                    var newGate = await _checkerRateLimitGate(true);
                    _applyCheckerCooldownUI(newGate);
                } catch(_){}
            }
        }
    });
    div.appendChild(btn);
    return div;
}

// Валидация/нормализация target URL для site-режима (возвращает string или '')
function getCheckerSiteTarget(){
    var site=$('checker-site'); if(!site) return '';
    var target=site.value;
    if(target==='custom'){
        target=($('checker-custom')||{}).value||'';
        if(!target) return '';
        if(!/^https?:\/\//i.test(target)) target='https://'+target;
        // Отсекаем javascript:, data:, мусор
        try {
            var u=new URL(target);
            if(u.protocol!=='http:'&&u.protocol!=='https:') return '';
            return u.toString();
        } catch(e) { return ''; }
    }
    return target;
}

// [v2.6.2] Блокировка всех контролов checker-модалки на время любой проверки.
// chrome.proxy.settings – singleton, параллелить ping нельзя; режим тоже не должен
// меняться посреди массовой проверки.
function setCheckerControlsDisabled(disabled){
    var container = $('checkerServerList');
    if (container) container.querySelectorAll('.checker-item-btn').forEach(function(b){ b.disabled = disabled; });
    var ids = ['modePingBtn','modeSiteBtn','openCheckerSiteModal'];
    ids.forEach(function(id){ var el = $(id); if (el) el.disabled = disabled; });
}
// [v2.6.2] Сброс всех результатов перед новым прогоном массовой проверки
function clearAllCheckerResults(){
    var container = $('checkerServerList');
    if (!container) return;
    container.querySelectorAll('.checker-item-result').forEach(function(r){
        r.className = 'checker-item-result';
        r.textContent = '–';
    });
}

// Проверка одного сервера. Возвращает Promise, резолвит по завершению.
function runSingleCheck(itemEl){
    return new Promise(function(resolve){
        if (isVpnOn) { resolve(); return; }
        var key = itemEl.getAttribute('data-key');
        var btn = itemEl.querySelector('.checker-item-btn');
        var resultEl = itemEl.querySelector('.checker-item-result');
        if (!btn || !resultEl) { resolve(); return; }
        // Блокируем всё на время проверки. Если идёт checkAll – checkAllBtn в режиме
        // «Остановить» и не должна меняться (оставляем её текущее состояние).
        var wasCheckAllRunning = _checkAllRunning;
        setCheckerControlsDisabled(true);
        var btnAll = $('checkAllBtn');
        if (!wasCheckAllRunning && btnAll) btnAll.disabled = true;
        var origLabel = btn.textContent;
        btn.textContent = '…';
        resultEl.textContent = '…';
        resultEl.className = 'checker-item-result loading';
        // [v2.8.5] Прокрутить список проверки к серверу, который проверяется сейчас.
        try { itemEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch(_){}

        function finish(cls, text){
            btn.textContent = origLabel;
            resultEl.className = 'checker-item-result ' + cls;
            resultEl.textContent = text;
            // [v2.8.0] Persist в storage – следующее открытие модалки покажет этот результат.
            // Awaited через .then – гарантия что storage.set закомитится ДО resolve outer promise.
            // Без этого: при быстром Stop+close popup pending writes могли не успеть → результаты
            // отпингованных серверов терялись.
            _saveCheckerResult(key, cls, text).then(function(){
                // Разблокируем только если мы НЕ внутри массовой проверки.
                // В runCheckAll разблокировка делается в конце цикла.
                if (!wasCheckAllRunning) {
                    setCheckerControlsDisabled(false);
                    if (btnAll) btnAll.disabled = false;
                }
                resolve();
            });
        }

        if (checkerMode === 'ping') {
            var pingDone = false;
            var pingWatchdog = setTimeout(function(){
                if (!pingDone) { pingDone = true; finish('fail', '⏱'); }
            }, 20000);
            chrome.runtime.sendMessage({action:'pingProxy', serverKey: key}, function(res){
                if (pingDone) return;
                pingDone = true;
                clearTimeout(pingWatchdog);
                if (chrome.runtime.lastError || !res || res.error) { finish('fail', '✕'); return; }
                var ping = (res.ping_ms >= 0) ? res.ping_ms : -1;
                if (ping >= 0) finish(pingCls(ping), ping + ' ms');
                else finish('fail', '✕');
            });
        } else {
            var target = getCheckerSiteTarget();
            if (!target) { finish('fail', '?'); return; }
            apiFetch(CHECKER_PATH, {
                method: 'POST',
                headers: {'Content-Type':'application/json', 'X-AnonVPN-Auth': API_AUTH_KEY},
                body: JSON.stringify({ server_key: key, target_url: target }),
                signal: AbortSignal.timeout(15000)
            })
            .then(function(r){ if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
            .then(function(data){
                if (data && data.ok) {
                    var ms = (typeof data.time_ms === 'number' && data.time_ms >= 0) ? data.time_ms : -1;
                    if (ms >= 0) finish(pingCls(ms), ms + ' ms');
                    else finish('ping-0', '✓');
                } else {
                    finish('fail', '✕');
                }
            })
            .catch(function(){ finish('fail', '✕'); });
        }
    });
}

// Последовательная проверка всех серверов (нельзя параллельно – ping меняет chrome.proxy.settings).
// Повторный клик по кнопке во время работы → остановка после текущего сервера.
// [v2.8.0] Mode-aware rate-limit для free-verified юзеров: ping=1/час, site=3/час. Premium – без лимита.
// Sliding-window: храним массив timestamps в storage.checkerRunHistory[mode]. На каждую проверку
// фильтруем массив (откидываем старше 1 часа) → если length >= limit, отказ; иначе append.
var CHECKER_RATE_WINDOW_MS = 60 * 60 * 1000; // 1 час
var CHECKER_LIMITS = { ping: 1, site: 3 };

// [v2.8.0] Storage-cache последней проверки – mode-segregated. На каждый finish() –
// мержим в нужный bucket (ping/site), не трогая другой. На openCheckerModal – load
// + apply того bucket'а который соответствует текущему mode + target.
// Структура: { ping: {ts, results:{key→{cls,text,ts}}}, site: {ts, target, results:{...}} }
// Раньше единый bucket с mode-меткой ВЫТИРАЛ другой mode при switch – bug fixed.
var _checkerStoredResults = null;

function _saveCheckerResult(key, cls, text) {
    return new Promise(function(resolve){
        if (!_checkerStoredResults || typeof _checkerStoredResults !== 'object') _checkerStoredResults = {};
        var modeKey = checkerMode || 'ping';
        if (modeKey === 'site') {
            var currentTarget = typeof getCheckerSiteTarget === 'function' ? getCheckerSiteTarget() : null;
            // Target сменился внутри site mode (Google → YouTube) – fresh bucket для нового target
            if (!_checkerStoredResults.site || _checkerStoredResults.site.target !== currentTarget) {
                _checkerStoredResults.site = { ts: Date.now(), target: currentTarget, results: {} };
            }
        } else {
            if (!_checkerStoredResults.ping || !_checkerStoredResults.ping.results) {
                _checkerStoredResults.ping = { ts: Date.now(), results: {} };
            }
        }
        // [v2.8.5] hp = host:port - stable key for showing ping in the server-select modal
        // (data-key f{i}/p{i} is positional, breaks when n_proxies.txt is rotated).
        var _hp = '';
        try { var _pp = resolveProxyByKey(key); if (_pp) _hp = _serverKey(_pp); } catch(_e){}
        _checkerStoredResults[modeKey].results[key] = { cls: cls, text: text, ts: Date.now(), hp: _hp };
        _checkerStoredResults[modeKey].ts = Date.now();
        chrome.storage.local.set({ checkerLastResults: _checkerStoredResults }, function(){
            if(chrome.runtime&&chrome.runtime.lastError){
                console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);
            }
            resolve();
        });
    });
}

// [v3.1.7] Пополняем накопитель проверок «Доступность сайта» по серверам (host:port → {siteHost:{cls,text,ts}}).
// Источник — готовый bucket _checkerStoredResults.site (у каждой записи есть hp). Храним последние
// SITE_HITS_MAX_PER_SERVER сайтов на сервер (вытесняем самые старые по ts). Подсказка при наведении на
// сервер читает эту структуру. Пишется по завершении полного прогона (автоподбор + «Проверить все» в site-режиме).
var SITE_HITS_MAX_PER_SERVER = 8;
function _foldSiteCheckByServer(siteObj){
    try {
        if (!siteObj || !siteObj.results || !siteObj.target) return;
        var host=''; try { host=new URL(siteObj.target).hostname; } catch(e){ host=String(siteObj.target||''); }
        if (!host) return;
        var now=Date.now();
        chrome.storage.local.get(['siteCheckByServer'], function(d){
            var store=(d && d.siteCheckByServer && typeof d.siteCheckByServer==='object' && !Array.isArray(d.siteCheckByServer)) ? d.siteCheckByServer : {};
            Object.keys(siteObj.results).forEach(function(k){
                var r=siteObj.results[k]; if(!r || !r.hp) return;
                var hp=r.hp;
                var bucket=(store[hp] && typeof store[hp]==='object' && !Array.isArray(store[hp])) ? store[hp] : {};
                bucket[host]={ cls:r.cls, text:r.text, ts:now };
                var hs=Object.keys(bucket);
                if(hs.length>SITE_HITS_MAX_PER_SERVER){
                    hs.sort(function(a,b){ return (Number(bucket[b].ts)||0)-(Number(bucket[a].ts)||0); });
                    hs.slice(SITE_HITS_MAX_PER_SERVER).forEach(function(old){ delete bucket[old]; });
                }
                store[hp]=bucket;
            });
            chrome.storage.local.set({ siteCheckByServer: store }, function(){
                if(chrome.runtime&&chrome.runtime.lastError){ console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message); }
            });
        });
    } catch(_){}
}

function _applyStoredCheckerResults() {
    return new Promise(function(resolve){
        chrome.storage.local.get(['checkerLastResults'], function(d){
            var stored = (d && d.checkerLastResults) || {};
            // Migration: старый формат {ts, mode, site, results} → дропаем (legacy)
            // Новый формат: {ping: {...}, site: {...}} – оба mode'а содержат свои results.
            if (stored && stored.mode && stored.results && !stored.ping && !stored.site) {
                stored = {}; // legacy shape – игнорируем (юзер потеряет старые результаты, acceptable)
            }
            _checkerStoredResults = stored;
            var modeKey = checkerMode || 'ping';
            var modeData = stored[modeKey];
            if (!modeData || !modeData.results) { resolve(); return; }
            // Site mode – target должен совпадать с текущим выбранным
            if (modeKey === 'site' && typeof getCheckerSiteTarget === 'function' &&
                modeData.target !== getCheckerSiteTarget()) { resolve(); return; }
            var container = $('checkerServerList');
            if (!container) { resolve(); return; }
            // [2026-06-29 fix] Матчим по host:port (стабильно), НЕ по позиционному data-key:
            // список мог перетасоваться/вырасти между прогоном пинга и открытием чекера →
            // позиционный ключ проставлял чужой пинг («волшебный» пинг соседа). Строим hp→res
            // (свежайший по ts) и даём каждому DOM-итему пинг его ТЕКУЩЕГО сервера по hp.
            var _hpRes = {};
            Object.keys(modeData.results).forEach(function(key){
                var rr = modeData.results[key];
                if (!rr || !rr.hp) return;
                if (!_hpRes[rr.hp] || (Number(rr.ts) || 0) >= (Number(_hpRes[rr.hp].ts) || 0)) _hpRes[rr.hp] = rr;
            });
            var _items = container.querySelectorAll('.checker-item[data-key]');
            Array.prototype.forEach.call(_items, function(item){
                var k = item.getAttribute('data-key');
                var pp = null;
                try { pp = (typeof resolveProxyByKey === 'function') ? resolveProxyByKey(k) : null; } catch(_e){}
                var hp = pp ? _serverKey(pp) : '';
                var res = hp ? _hpRes[hp] : null;
                if (!res) return; // нет пинга для текущего сервера на этой позиции – оставляем дефолт «–»
                var r = item.querySelector('.checker-item-result');
                if (!r) return;
                r.className = 'checker-item-result ' + (res.cls || '');
                r.textContent = res.text || '–';
            });
            resolve();
        });
    });
}

// [v2.8.0] Gate для checker-actions. Mode-aware: lookup `checkerRunHistory[checkerMode]` →
// filter sliding window (1 час) → compare с CHECKER_LIMITS[checkerMode].
// silent=true – не показывать toast (для pre-emptive disable buttons).
async function _checkerRateLimitGate(silent) {
    var d = await new Promise(function(resolve){
        chrome.storage.local.get(['isPremium', 'accountVerified', 'checkerRunHistory'], function(r){ resolve(r||{}); });
    });
    var isPremium = !!d.isPremium;
    var isVerified = d.accountVerified === true;
    var history = d.checkerRunHistory || {};
    if (isPremium) return { ok: true, isPremium: true, isVerified: isVerified };
    if (!isVerified) {
        return { ok: false, reason: 'not_verified', isPremium: false, isVerified: false };
    }
    var mode = checkerMode || 'ping';
    var limit = CHECKER_LIMITS[mode] || 1;
    var modeHist = Array.isArray(history[mode]) ? history[mode] : [];
    var now = Date.now();
    var cutoff = now - CHECKER_RATE_WINDOW_MS;
    // Sliding-window: оставляем только timestamps моложе 1 часа
    var recent = modeHist.filter(function(ts){ return typeof ts === 'number' && ts > cutoff; });
    if (recent.length >= limit) {
        // Earliest TS – когда «истечёт» (станет старше 1 часа)
        var earliest = Math.min.apply(Math, recent);
        var remainMs = (earliest + CHECKER_RATE_WINDOW_MS) - now;
        if (remainMs < 0) remainMs = 0;
        var remainMin = Math.ceil(remainMs / 60000);
        if (!silent) {
            var msgKey = mode === 'site' ? 'checkerRateLimitedSite' : 'checkerRateLimited';
            var msgFallback = mode === 'site'
                ? 'Доступно 3 раза в час. Следующая через {n} мин'
                : 'Доступно 1 раз в час. Следующая через {n} мин';
            showStatusMessage(t(msgKey, msgFallback).replace('{n}', String(remainMin)), true);
        }
        return { ok: false, reason: 'rate_limit', remainMs: remainMs, remainMin: remainMin,
            mode: mode, limit: limit, isPremium: false, isVerified: true };
    }
    return { ok: true, isPremium: false, isVerified: true, mode: mode, limit: limit };
}

// [v2.8.0] Записать факт запуска в storage history. Sliding-window: удаляем старые
// перед append. Async/awaited – иначе следующий _checkerRateLimitGate мог читать
// stale storage и не детектил cooldown (race между set и get).
function _recordCheckerRun(mode) {
    return new Promise(function(resolve){
        chrome.storage.local.get(['checkerRunHistory'], function(d){
            var h = (d && d.checkerRunHistory) || {};
            if (!Array.isArray(h[mode])) h[mode] = [];
            var now = Date.now();
            var cutoff = now - CHECKER_RATE_WINDOW_MS;
            h[mode] = h[mode].filter(function(ts){ return typeof ts === 'number' && ts > cutoff; });
            h[mode].push(now);
            chrome.storage.local.set({ checkerRunHistory: h }, function(){
                if(chrome.runtime&&chrome.runtime.lastError){
                    console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);
                }
                resolve();
            });
        });
    });
}

// [v2.8.0] Применяет UI-state для checker buttons на основе тарифа юзера:
//   Premium               → все кнопки enabled (no limits)
//   Free-verified         → individual `.checker-item-btn` ВСЕГДА disabled; `#checkAllBtn`
//                            disabled только во время cooldown (после run-all 1/час)
//   Free-non-verified     → modal вообще не открывается (premium-lock на карточке)
var _checkerCooldownExpiryTimer = null;
function _applyCheckerCooldownUI(gate) {
    var btnAll = $('checkAllBtn');
    var itemBtns = document.querySelectorAll('#checkerServerList .checker-item-btn');
    var hintEl = $('checkerFreeVerifiedHint');
    var inCooldown = gate && gate.reason === 'rate_limit';
    var isFreeVerified = gate && !gate.isPremium && gate.isVerified;
    var mode = (gate && gate.mode) || checkerMode || 'ping';
    // [v2.8.0] Auto-refresh on cooldown expiry – если юзер оставит modal открытой пока
    // earliest timestamp истекает (>1 час), buttons должны auto-enable. Симметрично с
    // applyRateLimitBanner setTimeout. Cap 24h против setTimeout int32 overflow.
    if (_checkerCooldownExpiryTimer) { clearTimeout(_checkerCooldownExpiryTimer); _checkerCooldownExpiryTimer = null; }
    if (inCooldown && gate && typeof gate.remainMs === 'number' && gate.remainMs > 0 && gate.remainMs < 24*3600*1000) {
        _checkerCooldownExpiryTimer = setTimeout(async function(){
            try {
                var freshGate = await _checkerRateLimitGate(true);
                _applyCheckerCooldownUI(freshGate);
            } catch {}
        }, gate.remainMs + 1000);
    }
    // checkAllBtn – disabled только при cooldown (free-verified юзер уже использовал лимит за час)
    if (btnAll) btnAll.disabled = inCooldown;
    // Individual buttons – disabled навсегда для free-verified (только runCheckAll доступен)
    itemBtns.forEach(function(b){ b.disabled = isFreeVerified; });
    // Hint виден только free-verified – text mode-aware (ping=1/час, site=3/час)
    if (hintEl) {
        if (isFreeVerified) {
            if (inCooldown) {
                var msgKey = mode === 'site' ? 'checkerRateLimitedSite' : 'checkerRateLimited';
                var msgFallback = mode === 'site'
                    ? 'Доступно 3 раза в час. Следующая через {n} мин'
                    : 'Доступно 1 раз в час. Следующая через {n} мин';
                hintEl.textContent = t(msgKey, msgFallback).replace('{n}', String(gate.remainMin));
            } else {
                var hintKey = mode === 'site' ? 'checkerFreeVerifiedHintSite' : 'checkerFreeVerifiedHint';
                var hintFallback = mode === 'site'
                    ? 'На бесплатном тарифе – 3 проверки в час. Premium снимает лимит.'
                    : 'На бесплатном тарифе – 1 проверка в час. Premium снимает лимит.';
                hintEl.textContent = t(hintKey, hintFallback);
            }
            hintEl.hidden = false;
        } else {
            hintEl.hidden = true;
        }
    }
}
// [v2.8.5] Предупреждение на время массовой проверки серверов. Текст зависит от тарифа:
//  • free-verified – прерывание/закрытие окна = попытка всё равно списывается (always-record-on-abort);
//  • premium – лимита нет, но закрытие окна расширения обрывает проверку.
function _showCheckerRunWarning(state){
    var el = $('checkerRunWarn'); if (!el) return;
    if (state && state.isPremium) {
        el.textContent = t('checkerWarnPremium', 'Не закрывайте окно расширения – проверка прервётся.');
    } else {
        el.textContent = t('checkerWarnFree', 'Если остановить проверку, попытка будет потрачена.');
    }
    el.hidden = false;
}
function _hideCheckerRunWarning(){
    var el = $('checkerRunWarn'); if (el) el.hidden = true;
}
async function runCheckAll(){
    var btnAll=$('checkAllBtn');
    if (_checkAllRunning) {
        // Второй клик во время работы – abort
        _checkAllAborted = true;
        if (btnAll) { btnAll.disabled = true; btnAll.textContent = t('stopping','Останавливаем…'); }
        return;
    }
    if (isVpnOn) {
        showStatusMessage(t('disableVpnForCheck', 'Отключите VPN для проверки'), true);
        return;
    }
    // [v2.8.0] Rate-limit gate (free+verified – 1/час).
    var rateState = await _checkerRateLimitGate();
    if (!rateState.ok) return;
    var container=$('checkerServerList'); if(!container) return;
    var items = Array.prototype.slice.call(container.querySelectorAll('.checker-item'));
    if (!items.length) return;
    _checkAllRunning = true;
    _checkAllAborted = false;
    clearAllCheckerResults();
    setCheckerControlsDisabled(true);
    if (btnAll) {
        btnAll.disabled = false;
        btnAll.textContent = t('stopCheck','Остановить');
        btnAll.classList.add('checker-btn-stop');
    }
    var _apbRun=$('autoPickBtn'); if (_apbRun) _apbRun.disabled = true; // [v3.1.7] автоподбор недоступен пока идёт проверка
    _showCheckerRunWarning(rateState); // [v2.8.5] предупреждение на время проверки
    // [v3.1.5 audit i3] Заряжаем лимит ДО цикла: закрытие popup в середине убивало JS-контекст раньше
    // post-loop записи → reopen проходил gate заново (пинг-режим без серверного backstop = безлимит).
    if (!rateState.isPremium && rateState.isVerified) {
        try { await _recordCheckerRun(checkerMode || 'ping'); } catch(_){}
    }
    for (var i = 0; i < items.length; i++) {
        if (_checkAllAborted) break;
        await runSingleCheck(items[i]);
        // Пауза между серверами – прокси-сеттинги успевают «отдохнуть»
        await new Promise(function(r){ setTimeout(r, 150); });
    }
    // [v3.1.5 audit i3] Расход лимита теперь заряжается ДО цикла (см. выше) — переживает закрытие popup.
    // [v3.1.7] Если проверяли «Доступность сайта» — пополняем накопитель по серверам (подсказка при наведении).
    if ((checkerMode||'ping')==='site' && _checkerStoredResults && _checkerStoredResults.site) {
        try { _foldSiteCheckByServer(_checkerStoredResults.site); } catch(_){}
    }
    _checkAllRunning = false;
    _checkAllAborted = false;
    setCheckerControlsDisabled(false);
    _hideCheckerRunWarning(); // [v2.8.5]
    if (btnAll) {
        btnAll.disabled = false;
        btnAll.textContent = t('checkAll','Проверить все');
        btnAll.classList.remove('checker-btn-stop');
    }
    var _apbEnd=$('autoPickBtn'); if (_apbEnd) _apbEnd.disabled = false; // [v3.1.7] возвращаем автоподбор
    // [v2.8.0] Rate-limit history пишется ВСЕГДА (даже при abort) – расход зафиксирован
    // выше, ДО _checkAllRunning=false (см. fix R2). Любой клик «Проверить все» = 1 расход.
    // [v2.8.0] ВСЕГДА reapply cooldown-UI – иначе на abort-path setCheckerControlsDisabled(false)
    // enable'ит .checker-item-btn даже у free-verified юзера (которому они должны быть всегда
    // disabled). Для premium этот вызов no-op (gate.ok=true → buttons стают enabled).
    var newGate = await _checkerRateLimitGate(true);
    _applyCheckerCooldownUI(newGate);
}
$('checkAllBtn')?.addEventListener('click', runCheckAll);
// [v3.1.7] Автоподбор: берёт сайт из поля чекера, проверяет все серверы, подключается к лучшему.
$('autoPickBtn')?.addEventListener('click', function(){ autoPickServerForSite(getCheckerSiteTarget()); });
// [v3.1.7] Кнопка B (главная вкладка): подобрать сервер для сайта АКТИВНОЙ вкладки.
$('autoPickTabBtn')?.addEventListener('click', function(){
    try {
        chrome.tabs.query({ active: true, currentWindow: true }, function(tabs){
            var url = tabs && tabs[0] && tabs[0].url;
            if (!url || !/^https?:\/\//i.test(url)) { openModal('autoPickNoTabModal'); return; }
            autoPickServerForSite(url);
        });
    } catch(e){ openModal('autoPickNoTabModal'); }
});
$('autoPickNoTabOk')?.addEventListener('click', function(){ closeModal('autoPickNoTabModal'); });

// Открыть checker modal
$('openCheckerModal')?.addEventListener('click', async function(){
    if (isVpnOn) {
        showStatusMessage(t('disableVpnForCheck', 'Отключите VPN для проверки'), true);
        return;
    }
    // [v2.8.0] Restore stored UI state ДО buildCheckerList – restored mode/site используется
    // в _applyStoredCheckerResults для match check (иначе site mismatch → результаты не покажутся).
    await _restoreCheckerState();
    await buildCheckerList(); // [v2.8.5] async – читает isPremium для порядка блоков; ждём готовности DOM до setCheckerMode/restore
    setCheckerMode(checkerMode); // применить текущий режим к UI (включает custom-input show/hide для site mode)
    // [v2.8.0] Восстанавливаем результаты последней проверки (из storage). После
    // setCheckerMode потому что он стирает DOM-cells; мы поверх «–» накладываем сохранённые.
    await _applyStoredCheckerResults();
    // [v2.8.0] Pre-emptive disable + hint state. Silent=true – без toast'а.
    var gate = await _checkerRateLimitGate(true);
    _applyCheckerCooldownUI(gate);
    openModal('checkerModal');
});

// ============ [v3.1.7] Автоподбор сервера для сайта (чанк 1) ============
// Premium/verified-only (как весь site-чекер). Прогоняет проверку доступности сайта по ВСЕМ
// серверам (тот же серверный check, что в site-режиме) и подключается к самому быстрому рабочему.
// Точки входа: кнопка в чекере + отложенный запуск по _pendingAutopickSite (баннер/гибрид — чанк 2).
// [v3.1.7] Одиночная серверная проверка доступности сайта через сервер (site-режим, headless — для автоподбора).
function _siteCheckOne(serverKey, targetUrl){
    return apiFetch(CHECKER_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-AnonVPN-Auth': API_AUTH_KEY },
        body: JSON.stringify({ server_key: serverKey, target_url: targetUrl }),
        signal: AbortSignal.timeout(15000)
    }).then(function(r){ if (!r.ok) throw 0; return r.json(); })
      .then(function(d){ return (d && d.ok) ? { ok: true, ms: (typeof d.time_ms === 'number' && d.time_ms >= 0) ? d.time_ms : -1 } : { ok: false, ms: -1 }; })
      .catch(function(){ return { ok: false, ms: -1 }; });
}
var _autoPickRunning = false;
async function autoPickServerForSite(rawSite){
    if (_autoPickRunning) return;
    var raw = String(rawSite || '').trim();
    if (!raw) { showStatusMessage(t('autoPickBadUrl','Укажите адрес сайта'), true); return; }
    if (!/^[a-z][a-z0-9+.\-]*:\/\//i.test(raw)) raw = 'https://' + raw;
    var origin = '', host = '', altOrigin = '', altHost = '';
    try {
        var _u = new URL(raw);
        if (_u.protocol !== 'http:' && _u.protocol !== 'https:') throw 0;
        host = _u.hostname;
        origin = _u.protocol + '//' + host + '/'; // проверяем КОРЕНЬ сайта, без пути/квери (deep-link часто требует логина)
        // [v3.1.7] www-альтернатива: instagram открывается на apex, linkedin — на www; единого правила нет,
        // поэтому если основной хост не откроется НИГДЕ — пробуем www-переключённый вариант.
        if (/^www\./i.test(host)) altHost = host.replace(/^www\./i, '');
        else if (host.split('.').length === 2) altHost = 'www.' + host;
        if (altHost) altOrigin = _u.protocol + '//' + altHost + '/';
    } catch (e) { showStatusMessage(t('autoPickBadUrl','Некорректный адрес сайта'), true); return; }
    // Ранний гейт: free-non-verified → lock-модалка чекера; cooldown у free-verified → сообщение.
    var g0 = await _checkerRateLimitGate(true);
    if (!g0.ok) {
        if (!g0.isPremium && !g0.isVerified) { openModal('checkerLockedModal'); }
        else { showStatusMessage(t('autoPickRateLimited','Лимит проверок сейчас исчерпан, попробуйте позже'), true); }
        return;
    }
    _autoPickRunning = true;
    var _apbSelf=$('autoPickBtn'); if (_apbSelf) _apbSelf.disabled = true; // [v3.1.7] кнопка неактивна пока идёт автоподбор
    try {
        // Чекер работает только при выключенном ВПН — отключаем, если включён (сайт всё равно не открылся)
        if (isVpnOn) {
            showStatusMessage(t('autoPickChecking','Проверяю серверы для сайта…'), false);
            await new Promise(function(res){ try { chrome.runtime.sendMessage({ action:'toggleProxy' }, function(){ res(); }); } catch(e){ res(); } });
            for (var wct = 0; wct < 20 && isVpnOn; wct++) { await new Promise(function(r){ setTimeout(r, 200); }); }
        }
        // Готовим чекер один раз (site-режим) + список серверов из DOM
        await buildCheckerList();
        setCheckerMode('site');
        openModal('checkerModal');
        var isPrem = !!(g0 && g0.isPremium);
        var _spD = await new Promise(function(res){ chrome.storage.local.get(['serverPings','cachedServerStats'], function(d){ res(d||{}); }); });
        var serverPings = (_spD.serverPings && typeof _spD.serverPings === 'object' && !Array.isArray(_spD.serverPings)) ? _spD.serverPings : {};
        // [v3.1.7] Карта заполненности (host:port → число юзеров) для весового подбора: глобальный
        // serverUserCounts, иначе кэш cachedServerStats. Пусто → фактор нагрузки нейтрален.
        var _loadMap = (serverUserCounts && Object.keys(serverUserCounts).length) ? serverUserCounts
            : ((_spD.cachedServerStats && typeof _spD.cachedServerStats === 'object' && !Array.isArray(_spD.cachedServerStats)) ? _spD.cachedServerStats : {});
        var _lc = $('checkerServerList');
        var _items = _lc ? Array.prototype.slice.call(_lc.querySelectorAll('.checker-item')) : [];
        var _itemByKey = {}; _items.forEach(function(it){ _itemByKey[it.getAttribute('data-key')] = it; });
        var keys = _items.map(function(it){ return it.getAttribute('data-key'); });
        if (!keys.length) { showStatusMessage(t('autoPickError','Не удалось подобрать сервер, попробуйте выбрать вручную'), true); return; }
        var custEl = $('checker-custom'); if (custEl) custEl.classList.add('hidden'); // [v3.1.7] прячем URL-поле: сайт показываем в селекторе (без дубля)
        var selEl = $('checker-site'); if (selEl) { for (var s = 0; s < selEl.options.length; s++) { if (selEl.options[s].value === 'custom') { selEl.value = 'custom'; break; } } }
        // Разовый расход лимита для free-verified: весь автоподбор (probe + прогон) = 1 проверка.
        if (!isPrem && g0.isVerified) { try { await _recordCheckerRun('site'); } catch(_){} }
        clearAllCheckerResults();
        setCheckerControlsDisabled(true);
        _checkAllAborted = false;
        // [v3.1.7] Кнопка «Проверить все» → «Остановить» на время автоподбора (клик = abort через guard
        // runCheckAll при _checkAllRunning=true: он ставит _checkAllAborted → наш цикл прервётся).
        _checkAllRunning = true;
        var _btnAll = $('checkAllBtn');
        if (_btnAll) { _btnAll.disabled = false; _btnAll.textContent = t('stopCheck','Остановить'); _btnAll.classList.add('checker-btn-stop'); }
        function _renderCell(key, res){
            var it = _itemByKey[key]; if (!it) return; var cell = it.querySelector('.checker-item-result'); if (!cell) return;
            if (res && res.ok) { if (res.ms >= 0) { cell.className = 'checker-item-result ' + pingCls(res.ms); cell.textContent = res.ms + ' ms'; } else { cell.className = 'checker-item-result ping-0'; cell.textContent = '✓'; } }
            else { cell.className = 'checker-item-result fail'; cell.textContent = '✕'; }
        }
        // [v3.1.7] Помечаем текущий проверяемый сервер «…» и прокручиваем к нему список — как в
        // runSingleCheck («Проверить все»), чтобы при автоподборе список тоже следовал за проверкой.
        function _markChecking(key){
            var it = _itemByKey[key]; if (!it) return;
            var cell = it.querySelector('.checker-item-result');
            if (cell) { cell.className = 'checker-item-result loading'; cell.textContent = '…'; }
            try { it.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch(_){}
        }
        function _setSite(url, hostLabel){ if (custEl) custEl.value = url; if (checkerSiteBtnLabel) checkerSiteBtnLabel.textContent = hostLabel || url; }
        var results = {};                 // key -> {ok, ms} победившего варианта
        var winner = origin, winnerHost = host;
        // PROBE: первые ~15% серверов проверяем ОБА варианта → дальше идёт тот, где больше ✓.
        if (altOrigin && keys.length >= 2) {
            _setSite(origin, host);
            var N = Math.min(keys.length, Math.max(2, Math.ceil(keys.length * 0.15)));
            var okA = 0, okB = 0, resA = {}, resB = {};
            for (var pi = 0; pi < N && !_checkAllAborted; pi++) {
                var pk = keys[pi];
                _markChecking(pk);
                resA[pk] = await _siteCheckOne(pk, origin); if (resA[pk].ok) okA++;
                resB[pk] = await _siteCheckOne(pk, altOrigin); if (resB[pk].ok) okB++;
                _renderCell(pk, resA[pk].ok ? resA[pk] : resB[pk]);
            }
            if (okB > okA) { winner = altOrigin; winnerHost = altHost; }
            var probeWin = (winner === altOrigin) ? resB : resA;
            keys.slice(0, N).forEach(function(k){ if (probeWin[k]) { results[k] = probeWin[k]; _renderCell(k, probeWin[k]); } });
            _setSite(winner, winnerHost);
            for (var fi = N; fi < keys.length && !_checkAllAborted; fi++) { var fk = keys[fi]; _markChecking(fk); results[fk] = await _siteCheckOne(fk, winner); _renderCell(fk, results[fk]); }
        } else {
            _setSite(winner, winnerHost);
            for (var ci = 0; ci < keys.length && !_checkAllAborted; ci++) { var ck = keys[ci]; _markChecking(ck); results[ck] = await _siteCheckOne(ck, winner); _renderCell(ck, results[ck]); }
        }
        try { chrome.storage.local.set({ checkerMode:'site', checkerSelectedSite:'custom', checkerCustomSite: winner }); } catch(_){}
        // [v3.1.7 chunk3] Персистим результаты site-проверки → карточка в списке серверов их покажет.
        try {
            var _siteRes = {};
            Object.keys(results).forEach(function(k){
                var r = results[k]; var pObj = resolveProxyByKey(k); var hp = pObj ? _serverKey(pObj) : '';
                var cls, txt;
                if (r && r.ok) { if (r.ms >= 0) { cls = pingCls(r.ms); txt = r.ms + ' ms'; } else { cls = 'ping-0'; txt = '✓'; } }
                else { cls = 'fail'; txt = '✕'; }
                _siteRes[k] = { cls: cls, text: txt, ts: Date.now(), hp: hp };
            });
            if (!_checkerStoredResults || typeof _checkerStoredResults !== 'object') _checkerStoredResults = {};
            _checkerStoredResults.site = { ts: Date.now(), target: winner, results: _siteRes };
            chrome.storage.local.set({ checkerLastResults: _checkerStoredResults });
            _foldSiteCheckByServer(_checkerStoredResults.site); // [v3.1.7] накопитель для подсказки при наведении
        } catch(_){}
        // [v3.1.7] Весовой подбор лучшего РАБОЧЕГО сервера. Score = взвешенная сумма нормализованных
        // факторов (меньше – лучше): 1) пинг user→server (serverPings), 2) заполненность (_loadMap),
        // 3) пинг server→site (r.ms), 4) небольшой бонус premium-серверам. Каждый фактор min-max
        // нормализуется [0..1] по кандидатам. Отсекаем: premium для free, не-ok, сломанные туннели,
        // провал ghost-ping. Нет user-ping → штраф (туннель не подтверждён), нет site-ms («✓») → нейтрально.
        var W_SRV_PING = 0.38, W_LOAD = 0.24, W_SITE_PING = 0.38, W_PREMIUM_BONUS = 0.10;
        var SRV_PING_MISSING = 500, SITE_MS_MISSING = 1000;
        var _cands = [];
        Object.keys(results).forEach(function(k){
            if (!isPrem && k.charAt(0) === 'p') return;
            var r = results[k]; if (!r || !r.ok) return;
            var pObj = resolveProxyByKey(k); var hp = pObj ? _serverKey(pObj) : ''; if (!hp) return;
            if (_brokenServersMap && _brokenServersMap[hp]) return;
            var sp = serverPings[hp]; if (sp && sp.fail) return;
            var srvPing = (sp && typeof sp.ms === 'number' && sp.ms > 0) ? sp.ms : null;
            var siteMs = (typeof r.ms === 'number' && r.ms >= 0) ? r.ms : null;
            var load = (_loadMap && typeof _loadMap[hp] === 'number' && _loadMap[hp] >= 0) ? _loadMap[hp] : 0;
            _cands.push({ hp: hp, isPrem: k.charAt(0) === 'p', srvPing: srvPing, siteMs: siteMs, load: load });
        });
        var best = null, bestMs = Infinity;
        if (_cands.length === 1) {
            best = { hp: _cands[0].hp };
            bestMs = _cands[0].srvPing != null ? _cands[0].srvPing : (_cands[0].siteMs != null ? _cands[0].siteMs : 8000);
        } else if (_cands.length > 1) {
            var _srv = _cands.map(function(c){ return c.srvPing == null ? SRV_PING_MISSING : c.srvPing; });
            var _site = _cands.map(function(c){ return c.siteMs == null ? SITE_MS_MISSING : c.siteMs; });
            var _load = _cands.map(function(c){ return c.load; });
            var _mm = function(a){ var mn = Math.min.apply(null, a), mx = Math.max.apply(null, a); return { mn: mn, d: (mx - mn) || 1 }; };
            var mS = _mm(_srv), mT = _mm(_site), mL = _mm(_load);
            var bestScore = Infinity;
            _cands.forEach(function(c, i){
                var nSrv = (_srv[i] - mS.mn) / mS.d;
                var nSite = (_site[i] - mT.mn) / mT.d;
                var nLoad = (_load[i] - mL.mn) / mL.d;
                var score = W_SRV_PING * nSrv + W_SITE_PING * nSite + W_LOAD * nLoad - (c.isPrem ? W_PREMIUM_BONUS : 0);
                if (score < bestScore) {
                    bestScore = score;
                    best = { hp: c.hp };
                    bestMs = c.srvPing != null ? c.srvPing : (c.siteMs != null ? c.siteMs : 8000);
                }
            });
        }
        var usedHost = winnerHost;
        if (!best) {
            showStatusMessage(t('autoPickNone','Сайт не открылся ни через один сервер — возможно, он сейчас недоступен'), true);
            return;
        }
        closeModal('checkerModal');
        // [v3.1.7] Возвращаемся на главную вкладку — чтобы юзер видел подключение, а не остался в Premium.
        try { var _mainTab = document.querySelector('.tab-btn[data-tab="main"]'); if (_mainTab) _mainTab.click(); } catch(_){}
        var pickedLabel = _connectToBestServer(best.hp);
        if (pickedLabel) {
            var srvTxt = pickedLabel;
            if (bestMs < 8000) srvTxt += ' (' + bestMs + ' ' + t('msUnit','мс') + ')';
            showStatusMessage(t('autoPickDone','Подобран {srv}, {site} должен открыться').replace('{srv}', srvTxt).replace('{site}', usedHost || t('autoPickThisSite','сайт')), false);
        } else {
            showStatusMessage(t('autoPickConnectFail','Не удалось подключиться к подобранному серверу'), true);
        }
    } catch (e) {
        showStatusMessage(t('autoPickError','Не удалось подобрать сервер, попробуйте выбрать вручную'), true);
    } finally {
        _autoPickRunning = false;
        _checkAllRunning = false;
        try { setCheckerControlsDisabled(false); } catch(_){}
        var _bA = $('checkAllBtn'); if (_bA) { _bA.disabled = false; _bA.textContent = t('checkAll','Проверить все'); _bA.classList.remove('checker-btn-stop'); }
        var _apbFin = $('autoPickBtn'); if (_apbFin) _apbFin.disabled = false; // [v3.1.7] возвращаем кнопку автоподбора
    }
}

// Подключение к серверу по host:port: находим опцию селекта, персистим выбор (как ручной), включаем ВПН.
// Возвращает подпись подключённого сервера (для тоста) или '' если сервер не найден.
function _connectToBestServer(hp){
    if (!proxySelect || !hp || !Array.isArray(cachedProxyList)) return '';
    var proxyObj = null, foundIdx = -1;
    for (var i = 0; i < proxySelect.options.length; i++) {
        var p = resolveProxyByKey(proxySelect.options[i].value);
        if (p && _serverKey(p) === hp) { proxyObj = p; foundIdx = i; break; }
    }
    if (!proxyObj) return '';
    proxySelect.selectedIndex = foundIdx;
    var _label = (proxySelect.options[foundIdx] && proxySelect.options[foundIdx].text) || t('autoPickThisSite','сервер');
    try { updateServerBtnLabel(); } catch(_){}
    chrome.storage.local.set({ selectedProxy: proxyObj, autoSelectServer: false }, function(){
        if (chrome.runtime && chrome.runtime.lastError) { console.warn("[AnonVPN] storage.set failed:", chrome.runtime.lastError.message); return; }
        try { chrome.runtime.sendMessage({ action:'toggleProxy' }, function(){}); } catch(e){}
    });
    return _label;
}

// [v3.1.7] Отложенный запуск автоподбора по _pendingAutopickSite (баннер/гибрид ставит его — чанк 2).
// Ждём готовности списка серверов (cachedProxyList), затем запускаем один раз.
(function(){
    try {
        chrome.storage.local.get(['_pendingAutopickSite'], function(d){
            var site = d && d._pendingAutopickSite;
            if (!site) return;
            try { chrome.storage.local.remove(['_pendingAutopickSite']); } catch(_){}
            var tries = 0;
            var iv = setInterval(function(){
                tries++;
                if (Array.isArray(cachedProxyList) && cachedProxyList.length) { clearInterval(iv); autoPickServerForSite(site); }
                else if (tries >= 40) { clearInterval(iv); }
            }, 250);
        });
    } catch(_){}
})();

// Abort на закрытие модалки (крестик / клик-вне-box)
$('checkerModal')?.addEventListener('click', function(e){
    if (e.target === this) _checkAllAborted = true;
});
document.querySelector('#checkerModal .modal-close')?.addEventListener('click', function(){
    _checkAllAborted = true;
});

// [v2.6.2 → v2.7.6] Ad-blocker toggle – default OFF for new users. Юзер включает
// вручную через Premium tab. Storage key: adBlockerEnabled (boolean). Missing → false.
function loadAdBlockerState(){
    var t = $('adBlockerToggle'); if (!t) return;
    chrome.storage.local.get(['adBlockerEnabled'], function(d){
        t.checked = d.adBlockerEnabled === true;
    });
}
$('adBlockerToggle')?.addEventListener('change', function(){
    chrome.storage.local.set({ adBlockerEnabled: this.checked }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
});

// [v2.8.8] Bypass .ru/.рф – российские сайты идут DIRECT (без VPN). Default ON.
// Хранится как bypassRuDomains (boolean). undefined → true (default-on для existing).
// На change шлём reapplyProxyConfig SW, чтобы новое правило подхватилось мгновенно.
function loadBypassRuState(){
    var t = $('bypassRuToggle'); if (!t) return;
    chrome.storage.local.get(['bypassRuDomains'], function(d){
        t.checked = (d.bypassRuDomains !== false); // default true
    });
}
$('bypassRuToggle')?.addEventListener('change', function(){
    var on = !!this.checked;
    chrome.storage.local.set({ bypassRuDomains: on }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
        chrome.runtime.sendMessage({ action: 'reapplyProxyConfig', reason: 'bypassRuDomains' }, function(){
            if (chrome.runtime.lastError) {/* SW asleep – applies on next wake via storage.onChanged */}
        });
    });
});
loadBypassRuState();
// Multi-popup sync: если другой popup поменял флаг – обновляем checkbox.
chrome.storage.onChanged.addListener(function(changes, area){
    if (area !== 'local') return;
    if (changes.bypassRuDomains) {
        var t = $('bypassRuToggle');
        if (t) t.checked = (changes.bypassRuDomains.newValue !== false);
    }
});

// [v3.1.1] Настройки уведомлений о конце free-сессии. Default ON (undefined → true).
// SW читает флаги в момент показа уведомления – сообщение слать не нужно.
function loadNotifyToggles(){
    chrome.storage.local.get(['notifySessionEnd', 'notifySessionSoon'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) return;
        var a = $('notifyEndToggle'), b = $('notifySoonToggle');
        if (a) a.checked = (d.notifySessionEnd !== false);
        if (b) b.checked = (d.notifySessionSoon !== false);
    });
}
$('notifyEndToggle')?.addEventListener('change', function(){
    chrome.storage.local.set({ notifySessionEnd: !!this.checked }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
});
$('notifySoonToggle')?.addEventListener('change', function(){
    chrome.storage.local.set({ notifySessionSoon: !!this.checked }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
});
loadNotifyToggles();
// [v3.1.7] Тумблер подсказки проверенных сайтов при наведении на сервер. Default ON (undefined → true).
function loadSiteHintsToggle(){
    chrome.storage.local.get(['serverSiteHintsEnabled'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) return;
        var s = $('siteHintsToggle'); if (s) s.checked = (d.serverSiteHintsEnabled !== false);
    });
}
$('siteHintsToggle')?.addEventListener('change', function(){
    chrome.storage.local.set({ serverSiteHintsEnabled: !!this.checked }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
});
loadSiteHintsToggle();
// Multi-popup sync
chrome.storage.onChanged.addListener(function(changes, area){
    if (area !== 'local') return;
    if (changes.notifySessionEnd) { var a = $('notifyEndToggle'); if (a) a.checked = (changes.notifySessionEnd.newValue !== false); }
    if (changes.notifySessionSoon) { var b = $('notifySoonToggle'); if (b) b.checked = (changes.notifySessionSoon.newValue !== false); }
    if (changes.serverSiteHintsEnabled) { var s = $('siteHintsToggle'); if (s) s.checked = (changes.serverSiteHintsEnabled.newValue !== false); }
    // [v3.1.7] Кнопка чата: появляется без переоткрытия при пересечении порога 1ч ВПН (vpnStats)
    // или сразу после активации ключа/Premium (isPremium).
    if (changes.vpnStats || changes.isPremium) { updateCommunityChatVisibility(); }
    // [v3.1.7] Баннер подтверждения почты: крестик появляется при ≥3ч ВПН (vpnStats); закрытие
    // синхронизируется между попапами (accountVerifyBannerDismissed).
    if (changes.vpnStats || changes.accountVerifyBannerDismissed) { applyAccountVerifyBanner(); }
});

// ═══════════════════════════════════════
// ═══ INIT                            ═══
// ═══════════════════════════════════════
// Auto-detect browser language
function detectBrowserLang() {
    var supported = Object.keys(LANG_FLAGS);
    var raw = (chrome.i18n && chrome.i18n.getUILanguage) ? chrome.i18n.getUILanguage() : (navigator.language || 'en');
    var code = raw.toLowerCase().replace('-','_');
    var base = code.split('_')[0];
    if (supported.indexOf(code) >= 0) return code;
    if (supported.indexOf(base) >= 0) return base;
    return 'en';
}

chrome.storage.local.get(['proxyEnabled', 'language', 'cachedTranslationsData', 'cachedTranslationsVersion', 'colorTheme'], data => {
    var lang = data.language || detectBrowserLang();
    // Save detected language if not set
    if (!data.language) chrome.storage.local.set({ language: lang }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
    isVpnOn = !!data.proxyEnabled;

    // [v2.5.8 audit] Принимаем кэш переводов только если он содержит актуальные ключи
    // [v2.6.3] + cachedTranslationsVersion должен совпадать с текущим manifest.version
    var curVer = chrome.runtime.getManifest().version;
    if (data.cachedTranslationsData && isTranslationsCacheCurrent(data.cachedTranslationsData) && data.cachedTranslationsVersion === curVer) {
        cachedTranslations = data.cachedTranslationsData;
        _cachedTranslationsVersion = data.cachedTranslationsVersion;
    }

    // Apply theme – [v2.6.5 audit] whitelist по THEMES, иначе повреждённый storage
    // поставит на body класс `theme-<мусор>` (безопасно, но DOM мусор).
    var safeTheme = (data.colorTheme && THEMES.some(function(t){return t.id===data.colorTheme;}))
        ? data.colorTheme : 'default';
    applyTheme(safeTheme);

    languageSelect.value = lang;
    updateLangBtn(lang);
    translateAll(lang);
    toggle.checked = isVpnOn;
    updateVpnButtonUI(isVpnOn);
    setVpnFieldsLocked(isVpnOn);

    if (isVpnOn) { setTimeout(() => startLocalTimer(), 300); }

    loadAutoSelectExcluded(function(){
        loadFavorites(function(){ loadProxies(); });
    });
    loadSortMode(function(){ updateSortModeUI(); });
    recheckPremiumFromServer();
    checkNewsBadge();
    checkSysMsgBadge();
    applyUpdateBanner();
    applyRateLimitBanner();
    applyUpdateAvailableBanner();
    silentVpnConflictCheck();
    checkProxyControl();
    checkSessionExpiredBannerOnInit();
    // [v2.8.5] Онбординг-модалка – инструкция по выбору сервера при первом открытии popup.
    _maybeShowOnboarding();
    // [v2.6.2] Show current IP / country flag (proxy IP if VPN ON, real if OFF)
    loadIpInfo(false);

    // Migrate old excludedDomains to blacklistDomains (one-time, pre-split upgrade only)
    chrome.storage.local.get(['excludedDomains','blacklistDomains','exclusionsMode'],function(d){
        if(!d.exclusionsMode && Array.isArray(d.excludedDomains) && d.excludedDomains.length>0 && (!Array.isArray(d.blacklistDomains) || d.blacklistDomains.length===0)){
            chrome.storage.local.set({blacklistDomains:d.excludedDomains, exclusionsMode:'blacklist'}, function(){
                if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
            });
        }
    });

    // [v2.7.3] Авто-переключение на вкладку «Новости» при открытии popup если:
    //   (а) VPN выключен (на активной сессии не отвлекаем юзера),
    //   (б) в `cachedNews` есть статья свежее чем `lastNewsTime` (последняя прочитанная).
    // Использует существующий pattern «read marker»: `loadNews()` при открытии вкладки
    // Новости сам записывает `lastNewsTime = news[0].timestamp` → повторные открытия
    // popup'а после прочтения не триггерят auto-switch. Instant-путь работает только
    // когда `cachedNews` непустой (после хотя бы одного ручного захода на News). Для
    // fresh install и update-сценариев (cachedNews в STALE_KEYS, wipe'нут) есть async
    // fallback в `checkNewsBadge()` – срабатывает через 1-3 сек после fetch, если юзер
    // не успел сам переключиться. `_newsAutoSwitched` защищает от двойного переключения.
    if (!isVpnOn && !_newsAutoSwitched) {
        chrome.storage.local.get(['cachedNews','lastNewsTime'],function(d){
            var news = Array.isArray(d.cachedNews) ? d.cachedNews : [];
            var lastSeen = Number(d.lastNewsTime) || 0;
            if (news.length && news[0] && Number(news[0].timestamp) > lastSeen && tabNews && !_newsAutoSwitched) {
                _newsAutoSwitched = true;
                tabNews.click();
            }
        });
    }
});

// ═══ STATS ═══
function formatDuration(sec){
    if(!sec||sec<1) return '0';
    var moL=t('monthShort','mo'), dL=t('dayShort','d'), hL=t('hourShort','h'), mL=t('minuteShort','m'), sL=t('secondShort','s');
    if(sec<60) return sec+sL;
    if(sec<3600) return Math.floor(sec/60)+mL;
    if(sec<86400){var h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60);return h+hL+' '+m+mL;}
    if(sec<2592000){var d=Math.floor(sec/86400),h=Math.floor((sec%86400)/3600);return d+dL+' '+h+hL;}
    var mo=Math.floor(sec/2592000),d=Math.floor((sec%2592000)/86400);return mo+moL+' '+d+dL;
}

function loadStats(){
    chrome.storage.local.get(['vpnStats'],function(d){
        var s=d.vpnStats||{};
        var el=function(id){return $(id);};
        var tt=el('statTotalTime'); if(tt) tt.textContent=formatDuration(s.totalSeconds||0);
        var ss=el('statSessions'); if(ss) ss.textContent=''+(s.totalSessions||0);
        var ts=el('statTopServer');
        if(ts){
            // [v2.8.1] serverUsage indexed by host:port (стабильный ключ).
            // Legacy fN/pN ключи от 2.8.0 фильтруем regex'ом – только host:port участвует.
            var su=s.serverUsage||{}, maxK=null, maxC=0;
            Object.keys(su).forEach(function(k){
                if (/^[a-zA-Z0-9.\-]+:\d+$/.test(k) && su[k]>maxC){ maxC=su[k]; maxK=k; }
            });
            if(maxK&&Array.isArray(cachedProxyList)){
                var _hp=String(maxK).split(':');
                var _h=_hp[0], _po=_hp[1];
                var px=null, idx=0, isPrem=false;
                for(var _ti=0; _ti<cachedProxyList.length; _ti++){
                    var _p=cachedProxyList[_ti];
                    if(_p.host===_h && String(_p.port)===String(_po)){
                        px=_p; isPrem=_p.type==='premium';
                        var _same=cachedProxyList.filter(function(x){ return isPrem ? x.type==='premium' : x.type!=='premium'; });
                        idx=_same.findIndex(function(x){ return x.host===_h && String(x.port)===String(_po); })+1;
                        break;
                    }
                }
                var tr=cachedTranslations||{}, l=getLang();
                var srvLabel=isPrem?((tr[l]&&tr[l].premiumServer)||'Premium server'):((tr[l]&&tr[l].serverItem)||'Server');
                ts.textContent='';
                if(px&&px.country){
                    var img=getFlagImg(px.country);
                    if(img) ts.appendChild(img);
                }
                var sp=document.createElement('span');
                sp.textContent=' '+srvLabel+' \u2116'+idx;
                ts.appendChild(sp);
            } else { ts.textContent='–'; }
        }
    });
}

// ═══ SETTINGS DRAWER ═══
$('openSettingsBtn')?.addEventListener('click', function(){
    var ov=$('settingsOverlay');
    // [v2.8.1 audit] aria-hidden toggle для screenreader: статически true в HTML,
    // снимаем при открытии чтобы AT увидели контент drawer'а
    if(ov){ ov.classList.add('active'); ov.setAttribute('aria-hidden','false'); }
    loadStats();
});
function closeSettings(){
    var ov=$('settingsOverlay');
    if(ov){ ov.classList.remove('active'); ov.setAttribute('aria-hidden','true'); }
    resetClearCacheConfirm();
}
$('closeSettingsBtn')?.addEventListener('click', closeSettings);
$('settingsOverlay')?.addEventListener('click', function(e){
    if(e.target===this) closeSettings();
});

// ═══════════════════════════════════════════
// ═══ [v2.8.0] ACCOUNT LINK (settings) ═══
// ═══════════════════════════════════════════
function applyAccountLinkUI(){
    chrome.storage.local.get(['accountVerified','accountEmail'], function(d){
        var unlinkedBlk = $('accountUnlinkedBlock');
        var linkedBlk = $('accountLinkedBlock');
        var emailEl = $('accountEmailDisplay');
        if (!unlinkedBlk || !linkedBlk) return;
        // [v2.8.0] Используем `hidden` атрибут вместо `style.display` – CSP `style-src 'self'`
        // блокирует inline-styles в HTML; programmatic .style.X в JS обычно ОК, но для
        // консистентности с HTML-стороной (где `accountLinkedBlock` имеет `hidden` атрибут)
        // используем native `hidden` toggle.
        if (d.accountVerified === true) {
            unlinkedBlk.hidden = true;
            linkedBlk.hidden = false;
            if (emailEl) emailEl.textContent = d.accountEmail || '–';
        } else {
            unlinkedBlk.hidden = false;
            linkedBlk.hidden = true;
        }
    });
    applyAccountVerifyBanner();
}

function applyAccountVerifyBanner(){
    var banner = $('accountVerifyBanner');
    if (!banner) return;
    chrome.storage.local.get(['accountVerified','isPremium','sessionExpired','accountVerifyBannerDismissed','vpnStats'], function(d){
        // [v2.8.0] Скрываем ТОЛЬКО для premium и для уже verified – банер должен мотивировать
        // free-юзеров подтвердить почту. При sessionExpired показывается свой большой баннер –
        // этот скрываем чтобы не дублировать UI.
        // [v3.1.7] Крестик закрытия разрешён только после ≥3ч суммарного ВПН (accountVerifyBannerDismissed).
        // До 3ч закрыть нельзя – мотивирующий CTA сохраняется для новичков.
        var dismissed = d.accountVerifyBannerDismissed === true;
        var shouldShow = (d.accountVerified !== true)
            && !d.isPremium
            && !d.sessionExpired
            && !dismissed;
        if (shouldShow) banner.removeAttribute('hidden');
        else banner.setAttribute('hidden', '');
        var closeBtn = $('accountVerifyBannerClose');
        if (closeBtn) {
            var s = (d.vpnStats && typeof d.vpnStats === 'object' && !Array.isArray(d.vpnStats)) ? d.vpnStats : {};
            var total = Number(s.totalSeconds || 0) || 0;
            if (shouldShow && total >= 3*3600) closeBtn.removeAttribute('hidden');
            else closeBtn.setAttribute('hidden', '');
        }
    });
}
// [v3.1.7] Закрытие баннера подтверждения почты (крестик виден только при ≥3ч ВПН — см. applyAccountVerifyBanner).
$('accountVerifyBannerClose')?.addEventListener('click', function(e){
    if (e){ e.preventDefault(); e.stopPropagation(); }
    chrome.storage.local.set({ accountVerifyBannerDismissed: true }, function(){
        if(chrome.runtime&&chrome.runtime.lastError){console.warn("[AnonVPN] storage.set failed:",chrome.runtime.lastError.message);return;}
    });
    var b = $('accountVerifyBanner'); if (b) b.setAttribute('hidden','');
});

// [v2.8.0 audit r6] Enter key triggers link – без этого юзер набирал код, нажимал Enter,
// ничего не происходило (input не в `<form>`, default-submit no-op'нул). UX deadend.
$('accountCodeInput')?.addEventListener('keydown', function(e){
    if (e.key === 'Enter') {
        e.preventDefault();
        var btn = $('accountLinkBtn');
        if (btn && !btn.disabled) btn.click();
    }
});

$('accountLinkBtn')?.addEventListener('click', function(){
    var input = $('accountCodeInput');
    var resBox = $('accountLinkResult');
    if (!input || !resBox) return;
    var code = String(input.value || '').trim();
    if (!/^[a-zA-Z0-9]{6,16}$/.test(code)) {
        var tr = (cachedTranslations && cachedTranslations[getLang()]) || {};
        resBox.textContent = tr.accountLinkBadCode || 'Введите 6-16 символов кода с сайта';
        resBox.className = 'settings-result show err';
        return;
    }
    var btn = $('accountLinkBtn');
    if (btn) btn.disabled = true;
    // [v2.8.0 audit r2] F119-pattern safety timeout – без него если SW умрёт mid-flight
    // (MV3 lifecycle, network stall за 10s SW timeout), кнопка остаётся disabled навсегда,
    // юзер не может ретраить. Симметрично с tryTrialBtn / recoverPremiumBtn.
    var _linkResponded = false;
    var _linkResetTimer = setTimeout(function(){
        if (_linkResponded) return;
        _linkResponded = true;
        if (btn) btn.disabled = false;
        var trT = (cachedTranslations && cachedTranslations[getLang()]) || {};
        resBox.textContent = trT.accountLinkErr || 'Ошибка связи';
        resBox.className = 'settings-result show err';
    }, 20000);
    chrome.runtime.sendMessage({ action: 'linkUid', code: code }, function(res){
        if (_linkResponded) return;
        _linkResponded = true;
        clearTimeout(_linkResetTimer);
        if (btn) btn.disabled = false;
        var tr = (cachedTranslations && cachedTranslations[getLang()]) || {};
        if (chrome.runtime && chrome.runtime.lastError) {
            resBox.textContent = tr.accountLinkErr || 'Ошибка связи';
            resBox.className = 'settings-result show err';
            return;
        }
        if (res && res.ok) {
            input.value = '';
            resBox.textContent = tr.accountLinkOk || 'Аккаунт привязан';
            resBox.className = 'settings-result show ok';
            applyAccountLinkUI();
        } else {
            var reason = (res && res.reason) ? String(res.reason) : 'unknown';
            var msg;
            if (reason === 'code_not_found') msg = tr.accountLinkBadCode || 'Код не найден или истёк';
            else if (reason === 'code_expired' || reason === 'code_already_used') msg = tr.accountLinkBadCode || 'Код истёк или уже использован';
            else if (reason === 'rate_limited') msg = tr.accountLinkRateLimit || 'Слишком много попыток, подождите';
            else if (reason === 'storage_quota_exceeded') msg = tr.storageLimitExceeded || 'Хранилище переполнено. Очистите кэш в Настройках.';
            else if (reason === 'network_error') msg = tr.trialNetworkError || 'Нет связи. Попробуйте позже';
            else msg = tr.accountLinkErr || ('Ошибка: ' + reason);
            resBox.textContent = msg;
            resBox.className = 'settings-result show err';
        }
    });
});

$('accountUnlinkBtn')?.addEventListener('click', function(){
    var tr = (cachedTranslations && cachedTranslations[getLang()]) || {};
    if (!confirm(tr.accountUnlinkConfirm || 'Отвязать расширение от аккаунта?')) return;
    chrome.runtime.sendMessage({ action: 'unlinkAccount' }, function(res){
        // [v2.8.0 audit r5] lastError-guard – если SW умер mid-flight (MV3 lifecycle),
        // callback fires с !res и runtime.lastError. Без guard applyAccountLinkUI()
        // запускался без обновления state → юзер видел старое состояние «привязан».
        if (chrome.runtime && chrome.runtime.lastError) {
            // SW недоступен – local cleanup всё равно нужен (server-side cleanup произойдёт
            // на следующей попытке link). applyAccountLinkUI читает storage, не response.
        }
        applyAccountLinkUI();
    });
});

$('accountVerifyBanner_btn')?.addEventListener('click', function(){
    // [v2.8.0] Открываем Settings drawer + скроллим к Account section + фокусируем input.
    // Так юзер сразу видит куда вводить код. Ссылка «Зарегистрироваться на anon-vpn.ru»
    // рядом с input открывает сайт для регистрации/верификации/генерации кода.
    var ov = $('settingsOverlay');
    // [v2.8.1 audit] aria-hidden toggle, как в openSettingsBtn handler
    if (ov) { ov.classList.add('active'); ov.setAttribute('aria-hidden','false'); }
    if (typeof loadStats === 'function') { try { loadStats(); } catch {} }
    setTimeout(function(){
        var section = $('accountSection');
        if (section && section.scrollIntoView) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
        var input = $('accountCodeInput');
        if (input) { try { input.focus(); } catch {} }
    }, 60);
});

// [v2.8.0] dismiss-кнопка удалена – юзер не должен иметь возможности навсегда скрыть
// CTA подтвердить почту. Банер уходит только при isPremium=true или accountVerified=true.

// Trigger refresh on popup open: send checkAccount message (force=true).
chrome.runtime.sendMessage({ action: 'checkAccount', force: true }, function(){
    if (chrome.runtime && chrome.runtime.lastError) return; // SW asleep ok
    applyAccountLinkUI();
});
applyAccountLinkUI(); // immediate first paint with cached data

// ═══════════════════════════════════════
// ═══ v2.5.9: VPN CONFLICT DETECTION ═══
// ═══════════════════════════════════════
// Uses optional "management" permission requested on demand via chrome.permissions.request().
// Silent detection runs on popup init IF permission is already granted.

function hasManagementPermission(cb){
    if (!chrome.permissions || !chrome.permissions.contains) { cb(false); return; }
    chrome.permissions.contains({permissions:['management']}, function(granted){
        cb(!!granted);
    });
}

function requestManagementPermission(cb){
    if (!chrome.permissions || !chrome.permissions.request) { cb(false); return; }
    chrome.permissions.request({permissions:['management']}, function(granted){
        cb(!!granted);
    });
}

// [v2.8.3 IDM-fix] Whitelist расширений которые легитимно используют 'proxy' Chrome
// permission для не-VPN целей (перехват загрузок, etc) – они НЕ конкурирующие VPN и
// не должны триггерить conflict-block. Регрессия 2.8.2: 4 разных юзера за 4 часа
// (чаты 235/236/237/240) – IDM Integration Module блокировал toggle AnonVPN.
// ID verified against Chrome Web Store. Имя – fallback для клонов/форков с тем же
// именем но другим ID.
var PROXY_PERMISSION_WHITELIST_IDS = {
    'ngpampappnmepgilojfohadhhmbhlaek': 'IDM Integration Module' // Internet Download Manager
};
var PROXY_PERMISSION_WHITELIST_NAMES = [
    /^idm\b/i,                         // "IDM", "IDM Integration Module"
    /internet download manager/i       // full name variants
];
function isProxyPermissionWhitelisted(ext) {
    if (PROXY_PERMISSION_WHITELIST_IDS[ext.id]) return true;
    var name = ext.name || '';
    for (var i = 0; i < PROXY_PERMISSION_WHITELIST_NAMES.length; i++) {
        if (PROXY_PERMISSION_WHITELIST_NAMES[i].test(name)) return true;
    }
    return false;
}

// [v2.8.7] Известные VPN/proxy-бренды по ИМЕНИ. Нужно потому что часть VPN запрашивает
// 'proxy' как optional permission (его нет в ext.permissions от management.getAll) либо
// перехватывает трафик иначе – и не ловится фильтром по 'proxy'. Имя – надёжный доп-сигнал.
// Конкретные бренды → минимум ложных срабатываний (свой ext исключается по id отдельно).
var VPN_BRAND_NAMES = [
    // [v2.8.7 audit] /hide\s*\.?\s*me/ снят – ловил "Hide Me Cookies" / "Hide Me Tab Bar".
    // /setup\s*vpn/ → \b…\b чтобы не ловить tutorial-расширения "How to setup VPN".
    /browsec/i, /\bhola\b/i, /zen\s*mate/i, /touch\s*vpn/i, /urban\s*vpn/i,
    /windscribe/i, /\bsetupvpn\b/i, /betternet/i, /hotspot\s*shield/i, /veepn/i,
    /ultrasurf/i, /tunnelbear/i, /\bhoxx\b/i, /dotvpn/i, /1\s*click\s*vpn/i,
    /nord\s*vpn/i, /express\s*vpn/i, /surfshark/i, /proton\s*vpn/i, /cyberghost/i,
    /\bhide\.me\b/i, /planet\s*vpn/i, /\bgom\s*vpn\b/i
];
function matchesVpnBrand(name){
    if (!name) return false;
    for (var i = 0; i < VPN_BRAND_NAMES.length; i++) {
        if (VPN_BRAND_NAMES[i].test(name)) return true;
    }
    return false;
}

function enumerateProxyExtensions(cb){
    if (!chrome.management || !chrome.management.getAll) { cb([]); return; }
    try {
        chrome.management.getAll(function(list){
            if (chrome.runtime.lastError || !Array.isArray(list)) { cb([]); return; }
            var selfId = chrome.runtime.id;
            var conflicts = list.filter(function(ext){
                if (!ext.enabled) return false;
                if (ext.id === selfId) return false;
                if (ext.type !== 'extension') return false;
                // [v2.8.7] Раньше ловили только по 'proxy' в манифесте – VPN с optional-proxy
                // или иным перехватом ускользали. Теперь: ИЛИ proxy-permission, ИЛИ имя
                // известного VPN-бренда. (checkProxyControl через levelOfControl – отдельный
                // надёжный ловец фактического перехвата chrome.proxy, независимо от прав/имени.)
                var hasProxyPerm = Array.isArray(ext.permissions) && ext.permissions.indexOf('proxy') >= 0;
                if (!hasProxyPerm && !matchesVpnBrand(ext.name)) return false;
                if (isProxyPermissionWhitelisted(ext)) return false;  // [v2.8.3] IDM и др.
                return true;
            }).map(function(ext){ return { id: ext.id, name: ext.name }; });
            cb(conflicts);
        });
    } catch(e) { cb([]); }
}

function showVpnConflictBanner(conflicts){
    var banner = $('vpnConflictBanner');
    var list = $('vpnConflictBannerList');
    if (!banner || !list || !conflicts || !conflicts.length) return;
    list.innerHTML = '';
    conflicts.forEach(function(c, i){
        if (i > 0) list.appendChild(document.createTextNode(', '));
        var strong = document.createElement('strong');
        strong.textContent = c.name;
        list.appendChild(strong);
    });
    banner.removeAttribute('hidden');
}

function hideVpnConflictBanner(){
    var banner = $('vpnConflictBanner');
    if (banner) banner.setAttribute('hidden', '');
}

// [v2.8.6] Проверка «прокси перехвачен». Chrome отдаёт управление прокси только одному
// источнику. Если ВПН включён, а chrome.proxy.settings.get() сообщает levelOfControl
// != controlled_by_this_extension – значит настройку прокси перехватили другое
// расширение / программа / корпоративная политика, и трафик идёт мимо AnonVPN
// (классическое «ВПН включён, а IP реальный»). Показываем баннер. Проверка живёт
// только в popup – без storage-флага, пересчитывается при каждом открытии.
function checkProxyControl(){
    var banner = $('proxyControlBanner');
    if (!banner) return;
    if (!chrome.proxy || !chrome.proxy.settings || !chrome.proxy.settings.get) return;
    chrome.storage.local.get(['proxyEnabled'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) return;
        if (!d || !d.proxyEnabled) { banner.setAttribute('hidden', ''); return; }
        try {
            chrome.proxy.settings.get({}, function(cfg){
                if (chrome.runtime && chrome.runtime.lastError) return;
                var loc = cfg && cfg.levelOfControl;
                if (loc && loc !== 'controlled_by_this_extension') {
                    banner.removeAttribute('hidden');
                } else {
                    banner.setAttribute('hidden', '');
                }
            });
        } catch (e) {}
    });
}

// [v2.8.2 vpn-conflict-block] Блокирует все активационные кнопки расширения если детектировано
// другое VPN-расширение. Защищает от эксплойта: юзер с другим VPN получает чистый IP не свой,
// сервер выдаёт trial / Premium activate проходит fingerprint мимо. С блоком – invariant
// «trial/Premium активируется только когда другой VPN выключен».
// Вызывается из silentVpnConflictCheck (popup-open) и storage.onChanged (multi-popup sync).
var _vpnConflictActive = false;
function applyVpnConflictBlock(conflicts){
    var blocked = !!(conflicts && conflicts.length);
    _vpnConflictActive = blocked;
    var ids = ['vpnToggleBtn', 'trialMainCtaBtn', 'recoverPremiumBtn', 'activateKey', 'timerUrgencyBtn', 'proxyToggle'];
    ids.forEach(function(id){
        var el = $(id);
        if (!el) return;
        if (blocked) {
            el.setAttribute('disabled', 'disabled');
            el.setAttribute('aria-disabled', 'true');
            el.classList.add('vpn-conflict-blocked');
            // tooltip-hint – почему недоступно. Помечаем data-attr чтобы при unblock узнать
            // что title наш (а не оригинальный с HTML), независимо от смены языка.
            if (!el.hasAttribute('data-orig-title')) el.setAttribute('data-orig-title', el.title || '');
            el.title = t('vpnConflictBlocked','Disable other VPN extensions first');
        } else {
            el.removeAttribute('disabled');
            el.removeAttribute('aria-disabled');
            el.classList.remove('vpn-conflict-blocked');
            // [v2.8.2 audit-2] Восстанавливаем оригинальный title через data-orig-title (был
            // сохранён при block). Защищает от race: юзер сменил язык между block/unblock,
            // string-сравнение el.title === t(...) ломалось → tooltip оставался stale.
            if (el.hasAttribute('data-orig-title')) {
                el.title = el.getAttribute('data-orig-title') || '';
                el.removeAttribute('data-orig-title');
            }
        }
    });
    // [v2.8.2 vpn-conflict-block] Persist в storage чтобы SW мог посмотреть статус
    // и отказать в toggle если конфликт (defense in depth – popup может быть закрыт когда
    // юзер нажимает Alt+Shift+V, флаг в storage останавливает SW-side handler).
    try { chrome.storage.local.set({ vpnConflictBlocked: blocked }); } catch (e) {}
}

// [v2.8.2 audit-7+ F40] management теперь default permission (manifest:permissions, не optional).
// hasManagementPermission всё ещё проверяем – юзер мог revoke через chrome://extensions UI.
// При revoke → applyVpnConflictBlock([]) (unblock UI), серверная ASN-защита остаётся.
function silentVpnConflictCheck(){
    // [v3.1.1] НЕ блокируем кнопки и НЕ показываем баннер по факту наличия другого VPN-расширения.
    // Причина (смоук-тест 2026-07-07): Browsec/Hola и др. ставят proxy-config сразу при УСТАНОВКЕ и
    // держат его, даже когда «не подключены» в своём UI → levelOfControl='controlled_by_other' в
    // ПРОСТОЕ → ложная блокировка (юзер поставил Browsec, не включал – а наши кнопки заблокированы,
    // баннер «обнаружены активные ВПН»). Различить «активно проксирует» от «держит config вхолостую»
    // на этапе ДО включения нельзя. Поэтому всегда разрешаем попытку; если ПОСЛЕ включения трафик
    // реально пойдёт мимо – покажет POST-проверка checkProxyControl. Anti-trial-abuse держит СЕРВЕР
    // (request-trial.php: datacenter/VPN-IP → отказ триала). Список установленных VPN виден в
    // «Полной диагностике» и по кнопке проверки в настройках – как справка, без блокировки.
    applyVpnConflictBlock([]);   // разблок всегда
    hideVpnConflictBanner();     // не пугаем «обнаружены активные ВПН»
}

// Manual check via settings drawer button
$('checkVpnConflictBtn')?.addEventListener('click', function(){
    var btn = this;
    var r = $('vpnConflictResult');
    if (!r) return;
    btn.disabled = true;
    hasManagementPermission(function(has){
        function runDetection(){
            enumerateProxyExtensions(function(conflicts){
                btn.disabled = false;
                if (conflicts.length === 0) {
                    r.textContent = t('vpnConflictNone','No conflicting VPN extensions found.');
                    r.className = 'settings-result show ok';
                    hideVpnConflictBanner();
                } else {
                    r.innerHTML = '';
                    var title = document.createElement('div');
                    title.textContent = t('vpnConflictFound','Conflicting extensions found:');
                    r.appendChild(title);
                    var ul = document.createElement('ul');
                    conflicts.forEach(function(c){
                        var li = document.createElement('li');
                        li.textContent = c.name;
                        ul.appendChild(li);
                    });
                    r.appendChild(ul);
                    r.className = 'settings-result show warn';
                    showVpnConflictBanner(conflicts);
                }
                // [v3.1.1] Manual-проверка только ПОКАЗЫВАЕТ список установленных VPN (справка) –
                // кнопки НЕ блокирует (клиентский conflict-block отключён; см. silentVpnConflictCheck).
                // Дёргаем silentVpnConflictCheck, чтобы гарантированно снять любую случайную блокировку.
                silentVpnConflictCheck();
                setTimeout(function(){ if (r) r.className = 'settings-result'; }, 10000);
            });
        }
        if (has) { runDetection(); return; }
        requestManagementPermission(function(granted){
            if (!granted) {
                btn.disabled = false;
                r.textContent = t('vpnConflictDenied','Permission denied. Cannot check other extensions.');
                r.className = 'settings-result show err';
                setTimeout(function(){ if (r) r.className = 'settings-result'; }, 5000);
                return;
            }
            runDetection();
        });
    });
});

// [v2.5.9] Diagnostic log copy – formats SW log + client state + storage into
// a plain-text report that user can paste into a support ticket.
function _pad2(n){ return (n < 10 ? '0' : '') + n; }
function _fmtLocalTime(sec){
    var d = new Date(sec * 1000);
    return d.getFullYear() + '-' + _pad2(d.getMonth()+1) + '-' + _pad2(d.getDate()) +
        ' ' + _pad2(d.getHours()) + ':' + _pad2(d.getMinutes()) + ':' + _pad2(d.getSeconds());
}
function _fmtUtc(sec){
    var d = new Date(sec * 1000);
    return d.getUTCFullYear() + '-' + _pad2(d.getUTCMonth()+1) + '-' + _pad2(d.getUTCDate()) +
        ' ' + _pad2(d.getUTCHours()) + ':' + _pad2(d.getUTCMinutes()) + ':' + _pad2(d.getUTCSeconds());
}
// [v2.8.7] Клиентская диагностика прокси-контроля: кто реально владеет chrome.proxy
// (levelOfControl) + какие ещё VPN/proxy-расширения установлены. Помогает разбирать
// «ВПН включён, а IP реальный» – сразу видно, перехватил ли кто-то управление.
function gatherClientProxyDiag(cb){
    var out = { proxyControl: 'n/a', mgmt: false, proxyExts: [] };
    var done = 0;
    function fin(){ if (++done >= 2) { try { cb(out); } catch (e) {} } }
    try {
        if (chrome.proxy && chrome.proxy.settings && chrome.proxy.settings.get) {
            chrome.proxy.settings.get({}, function(cfg){
                if (!(chrome.runtime && chrome.runtime.lastError) && cfg && cfg.levelOfControl) out.proxyControl = cfg.levelOfControl;
                fin();
            });
        } else { fin(); }
    } catch (e) { fin(); }
    try {
        hasManagementPermission(function(has){
            out.mgmt = !!has;
            if (has) { enumerateProxyExtensions(function(list){ out.proxyExts = Array.isArray(list) ? list : []; fin(); }); }
            else { fin(); }
        });
    } catch (e) { fin(); }
}

function formatDiagnosticLog(resp, clientDiag){
    var nowSec = Math.floor(Date.now() / 1000);
    var lines = [];
    lines.push('=== AnonVPN Diagnostic Log ===');
    lines.push('Generated (local): ' + _fmtLocalTime(nowSec));
    lines.push('Generated (UTC):   ' + _fmtUtc(nowSec));
    lines.push('Timezone offset:   UTC' + (new Date().getTimezoneOffset() > 0 ? '-' : '+') + Math.abs(new Date().getTimezoneOffset() / 60) + ' (min=' + (-new Date().getTimezoneOffset()) + ')');
    lines.push('');
    var s = resp && resp.state || {};
    lines.push('--- State ---');
    lines.push('Version:          ' + (s.version || '?'));
    lines.push('UID:              ' + (s.uid || '?'));
    lines.push('Extension ID:     ' + (s.extId || '?'));
    lines.push('Language:         ' + (s.language || '?'));
    lines.push('User-Agent:       ' + (navigator.userAgent || '?').slice(0, 200));
    lines.push('Platform:         ' + ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '?'));
    lines.push('VPN enabled:      ' + (s.proxyEnabled ? 'YES' : 'no'));
    // [v2.8.7] Кто реально владеет прокси + другие VPN/proxy-расширения (разбор «ВПН вкл, IP реальный»)
    var _cd = clientDiag || {};
    lines.push('Proxy control:    ' + (_cd.proxyControl || 'n/a') + (_cd.proxyControl === 'controlled_by_other_extensions' ? '  <== ПЕРЕХВАЧЕН другим расширением' : ''));
    if (!_cd.mgmt) {
        lines.push('Other VPN/proxy ext: (нет права management – проверка недоступна)');
    } else if (_cd.proxyExts && _cd.proxyExts.length) {
        lines.push('Other VPN/proxy ext: ' + _cd.proxyExts.map(function(e){ return e.name; }).join(', '));
    } else {
        lines.push('Other VPN/proxy ext: none');
    }
    lines.push('Premium:          ' + (s.isPremium ? 'YES' : 'no'));
    lines.push('Auto-select:      ' + (s.autoSelectServer ? 'on' : 'off'));
    lines.push('Session expired:  ' + (s.sessionExpired ? 'YES' : 'no'));
    lines.push('Update required:  ' + (s.updateRequired ? 'YES' : 'no'));
    lines.push('Illegal ext id:   ' + (s.illegalExtId ? 'YES' : 'no'));
    lines.push('vpnBlocked flag:  ' + (s.vpnBlockedFlag ? 'YES' : 'no'));
    lines.push('Has selected proxy: ' + (s.hasSelectedProxy ? 'yes' : 'no'));
    lines.push('Has encrypted cache: ' + (s.hasEncryptedCache ? 'yes' : 'no'));
    lines.push('Server list size (in-memory): ' + (s.serverListSize != null ? s.serverListSize : '?'));
    // [v3.1.2] Активное расхождение системных часов юзера с сервером + вердикт. Сбитые часы (>5 мин)
    // ломают HMAC-подписи (окно сервера ±300 сек) → «не подключается ни к одному серверу».
    if (typeof s.serverClockDiff === 'number') {
        var _cdAbs = Math.abs(s.serverClockDiff);
        // [v3.1.2] Расширение авто-компенсирует сдвиг до ±24ч (clockOffsetSec + запрос timestamp.php
        // при 401 err:clock), premium-expiry берёт серверное время. Поэтому «не подключится» — только
        // за пределом суток. В пределах суток работает (первый запрос чуть медленнее), но лучше синхр-ть.
        var _cdVerdict = _cdAbs < 30 ? 'норма'
            : (_cdAbs <= 86400 ? 'часы сбиты (~' + (Math.round(_cdAbs / 3600 * 10) / 10) + 'ч), расширение авто-компенсирует — подключение работает; рекомендуется синхронизировать время'
            : 'ЧАСЫ СБИТЫ БОЛЬШЕ СУТОК — за пределом авто-компенсации, VPN не подключится → синхронизируйте время системы');
        lines.push('Server time diff: ' + (s.serverClockDiff >= 0 ? '+' : '') + s.serverClockDiff + ' sec  [' + _cdVerdict + ']');
    } else {
        lines.push('Server time diff: не удалось проверить (сервер недоступен/оффлайн)');
    }
    lines.push('Clock offset:     ' + (typeof s.clockOffsetSec === 'number' ? (s.clockOffsetSec + ' sec') : '–'));
    lines.push('VPN deadline:     ' + (s.vpnDeadline ? (_fmtLocalTime(Math.floor(s.vpnDeadline/1000)) + ' (in ' + Math.round((s.vpnDeadline - Date.now())/1000) + 's)') : '–'));
    // [v2.6.2] Storage footprint – видно если у юзера остались ключи от старых версий
    if (typeof s.storageKeys === 'number') {
        lines.push('Storage keys:     ' + s.storageKeys);
        if (Array.isArray(s.storageUnknownKeys) && s.storageUnknownKeys.length) {
            lines.push('Unknown keys (from older versions):');
            s.storageUnknownKeys.forEach(function(k){
                var sz = (s.storageKeySizes && s.storageKeySizes[k]) || 0;
                lines.push('  - ' + k + ' (' + sz + ' B)');
            });
        } else {
            lines.push('Unknown keys:     none');
        }
    }
    lines.push('');
    var log = resp && Array.isArray(resp.log) ? resp.log : [];
    lines.push('--- Events (most recent ' + log.length + ') ---');
    if (log.length === 0) {
        lines.push('(empty – no events recorded since install/SW wake)');
    } else {
        for (var i = 0; i < log.length; i++) {
            var ev = log[i];
            var row;
            // [v2.8.6] churn – свёрнутые повторы перезапуска SW / пропуска фонового
            // обновления по TTL. Рендерим компактно вместо ev.c.ev.e {json}.
            if (ev.c === 'lifecycle' && ev.e === 'churn') {
                var cn = (ev.d && ev.d.n) ? ev.d.n : 1;
                row = '[' + _fmtLocalTime(ev.t) + '] lifecycle.churn – SW wake-ups/refresh-skips x' + cn + ' (coalesced)';
            } else {
                row = '[' + _fmtLocalTime(ev.t) + '] ' + ev.c + '.' + ev.e;
                if (ev.d) {
                    try { row += ' ' + JSON.stringify(ev.d); } catch {}
                }
            }
            lines.push(row);
        }
    }
    return lines.join('\n');
}

// [v3.0.1] Полная диагностика – активная проверка серверов client-side + вердикт.
// Все строки локализованы в translations.json (48 langs): на экране – через t();
// в копию для поддержки – ru/en напрямую из cachedTranslations (поддержка русскоязычная).
var _fullDiagRunning = false, _lastDiagResult = null, _lastClientProxyDiag = null, _diagConn = 0, _diagBuilt = false, _diagFinished = false;
// [v3.0.5] Цель diag-рендера параметризована: из настроек → fullDiag*, из мастера настройки → setupCheck*.
// Так «Начать проверку» в мастере показывает те же живые шаги (интернет→API→серверы→сайты), что и полная диагностика.
var _diagProgId = 'fullDiagProgress', _diagResId = 'fullDiagResult';
function _diagIsRu(){ return (typeof getLang==='function' && getLang()==='ru'); }
// Значение ключа в КОНКРЕТНОМ языке (ru|en) – для копии в поддержку (не зависит от UI-языка).
function _diagTxt(lc, key){
    var c = cachedTranslations;
    return (c && c[lc] && c[lc][key]) || (c && c.en && c.en[key]) || '';
}
var DIAG_VERDICTS = {
    illegal_ext:{lvl:'red'}, version_old:{lvl:'red'}, rate_limited:{lvl:'red'},
    device_mismatch:{lvl:'red'}, key_invalid:{lvl:'red'}, no_internet:{lvl:'red'},
    api_blocked:{lvl:'red'}, empty_list:{lvl:'red'}, all_blocked_dpi:{lvl:'red'},
    no_ipchange:{lvl:'red'}, proxy_hijacked:{lvl:'red'}, partial:{lvl:'yellow'}, sites_blocked:{lvl:'yellow'}, all_ok:{lvl:'green'}
};
var DIAG_STEPS = ['internet','api','serverlist','blocks','servers','sites'];
var DIAG_PHASE_ORDER = ['internet','api','serverlist','blocks','servers','sites'];
// [v3.1.0] Старый Chrome (<116): onAuthRequired для proxy-CONNECT НЕ срабатывает на SW-fetch, поэтому
// HTTPS-проба смены IP в диагностике ложно-нулевая (реальный сёрфинг работает через авто-прайм-вкладку –
// подтверждено на чистом кэше: свежий сервер меняет IP). На таком Chrome сигнал доступности = «подключился»
// (HTTP+DNR, кэш-независимо). Без этого юзер видит «IP не меняется, отключите VPN» при рабочем VPN.
function _diagOldChrome(){ var c=999; try{ var m=navigator.userAgent.match(/Chrome\/(\d+)/); if(m)c=parseInt(m[1],10);}catch(e){} return c<116; }
function computeDiagVerdict(R, cd){
    var st = R.steps||{}, internet = st.internet||{}, api = st.api||{}, sl = st.serverList||{}, sites = st.sites||{}, b = st.blocks||{};
    var servers = R.servers||[];
    var _oldCh = _diagOldChrome();
    var connected = servers.filter(function(s){return s.connected;});
    var ipChanged = servers.filter(function(s){return s.connected && (_oldCh || s.ipChanged);});
    // Серверные блокировки – ПЕРВЫЙ приоритет (если сервер блокирует, серверы тестить бессмысленно).
    if (b.illegal_ext) return {code:'illegal_ext'};
    if (b.version_too_old) return {code:'version_old'};
    if (b.rate_limited) return {code:'rate_limited', until:b.rl_until||'', reason:b.rl_reason||''};
    if (b.device_mismatch) return {code:'device_mismatch'};
    if (b.key_invalid) return {code:'key_invalid'};
    if (!internet.ok && (api.reachable||0) === 0) return {code:'no_internet'};
    if ((api.reachable||0) === 0) return {code:'api_blocked'};
    if ((sl.count||0) === 0) return {code:'empty_list'};
    if (connected.length === 0) return {code:'all_blocked_dpi'};
    if (ipChanged.length === 0){
        // [v3.1.4] Конфликт-данные (cd) собраны ДО вердикта: если прокси контролирует НЕ AnonVPN
        // (другое расширение / политика) – точный вердикт «перехвачен» вместо обобщённого no_ipchange.
        // Анализ 46 прогонов no_ipchange (07-10.07.2026): 54% имели перехват или другие VPN – для них
        // совет «провайдер мешает» был мимо. exts – имена найденных VPN/proxy для подстановки в текст.
        var _exts = (cd && cd.proxyExts && cd.proxyExts.length) ? cd.proxyExts.map(function(e){ return e && e.name ? e.name : ''; }).filter(Boolean) : [];
        var _pcv = (cd && cd.proxyControl) || '';
        if (_pcv === 'controlled_by_other_extensions' || _pcv === 'not_controllable') return {code:'proxy_hijacked', exts:_exts};
        return {code:'no_ipchange', exts:_exts};
    }
    if (connected.length < servers.length*0.5) return {code:'partial', working:ipChanged.length, total:servers.length};
    if (sites.tested && sites.results && sites.results.length){
        var fail = sites.results.filter(function(r){return !r.ok;});
        if (fail.length === sites.results.length) return {code:'sites_blocked'};
    }
    return {code:'all_ok', working:ipChanged.length, total:servers.length};
}
// ── Шаговый прогресс (динамика) ──
function _diagStepRow(key){ var p=$(_diagProgId); return p ? p.querySelector('.diag-step[data-dstep="'+key+'"]') : null; }
function _diagSetStep(row, state){
    if(!row) return;
    row.className = 'diag-step ' + state;
    var ico = row.querySelector('.diag-step-ico'); if(!ico) return;
    ico.textContent = '';
    if (state==='active'){ var s=document.createElement('span'); s.className='diag-spinner'; ico.appendChild(s); }
    else if (state==='done'){ ico.textContent = '✓'; }
}
function _diagBuildSteps(){
    var prog = $(_diagProgId); if(!prog) return;
    prog.className=''; prog.style.display='block'; prog.innerHTML='';
    var wrap = document.createElement('div'); wrap.className='diag-progress';
    DIAG_STEPS.forEach(function(key){
        var row = document.createElement('div'); row.className='diag-step pending'; row.setAttribute('data-dstep', key);
        var ico = document.createElement('span'); ico.className='diag-step-ico';
        var lbl = document.createElement('span'); lbl.className='diag-step-lbl'; lbl.textContent=t('diagStep_'+key);
        row.appendChild(ico); row.appendChild(lbl);
        if (key==='servers'){ var live=document.createElement('span'); live.className='diag-srv-live'; row.appendChild(live); }
        wrap.appendChild(row);
        if (key==='servers'){
            var bw=document.createElement('div'); bw.className='diag-bar-wrap'; bw.style.display='none';
            var bf=document.createElement('div'); bf.className='diag-bar-fill';
            bw.appendChild(bf); wrap.appendChild(bw);
        }
    });
    prog.appendChild(wrap);
    _diagBuilt = true;
}
function _diagRenderProgress(phase, data){
    if(!_diagBuilt) _diagBuildSteps();
    var idx = DIAG_PHASE_ORDER.indexOf(phase); if(idx<0) return;
    DIAG_PHASE_ORDER.forEach(function(key,i){
        var row=_diagStepRow(key); if(!row) return;
        var state;
        if (phase==='servers') state = (i<idx)?'done':(i===idx)?'active':'pending';
        else state = (i<=idx)?'done':(i===idx+1)?'active':'pending';
        _diagSetStep(row, state);
    });
    if (phase==='servers' && data){
        var prog=$(_diagProgId);
        var bw = prog ? prog.querySelector('.diag-bar-wrap') : null;
        var bf = bw ? bw.querySelector('.diag-bar-fill') : null;
        var row=_diagStepRow('servers'); var live = row ? row.querySelector('.diag-srv-live') : null;
        if (bw) bw.style.display='block';
        if (bf) bf.style.width = (data.total ? Math.round(100*(data.done||0)/data.total) : 0)+'%';
        if (data.connected) _diagConn++;
        var connShown = (typeof data.connTotal==='number') ? data.connTotal : _diagConn;
        if (live) live.textContent = (data.done||0)+'/'+(data.total||0)+'  ✓'+connShown;
    }
}
// ── Результат-карточка (красиво + информативно) ──
function renderDiagResult(R, cd){
    _lastDiagResult = R;
    var box = $(_diagResId); if(!box) return;
    var prog=$(_diagProgId); if(prog){ prog.style.display='none'; prog.innerHTML=''; }
    _diagBuilt=false; box.innerHTML='';
    // [v3.1.4] Повторный рендер (переоткрытие popup) приходит без cd – берём кэш последнего сбора.
    if (cd === undefined) cd = _lastClientProxyDiag;
    var v = computeDiagVerdict(R, cd);
    var def = DIAG_VERDICTS[v.code] || DIAG_VERDICTS.all_ok;
    var untilStr = '';
    if (v.until){ var _dt = new Date(String(v.until).replace(' ', 'T')); if (!isNaN(_dt.getTime())) untilStr = ' (' + t('diagClearsAround').replace('{time}', _dt.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})) + ')'; }
    var msg = t('diagV_'+v.code+'_m').replace('{working}', String(v.working||0)).replace('{total}', String(v.total||0)).replace('{until}', untilStr);
    var icons = {red:'🔴', yellow:'🟡', green:'🟢'};
    var st = R.steps||{}, servers = R.servers||[];
    var _oldCh = _diagOldChrome();
    var conn = servers.filter(function(s){return s.connected;});
    var okip = servers.filter(function(s){return s.connected && (_oldCh || s.ipChanged);});
    var noip = servers.filter(function(s){return s.connected && !(_oldCh || s.ipChanged);});
    var fail = servers.filter(function(s){return !s.connected;});
    var card = document.createElement('div'); card.className='diag-result-card lvl-'+def.lvl;
    var head = document.createElement('div'); head.className='diag-result-head';
    var badge = document.createElement('div'); badge.className='diag-result-badge'; badge.textContent=icons[def.lvl];
    var ti = document.createElement('div'); ti.className='diag-result-title'; ti.textContent=t('diagV_'+v.code+'_t');
    head.appendChild(badge); head.appendChild(ti); card.appendChild(head);
    var m = document.createElement('div'); m.className='diag-result-msg'; m.textContent=msg; card.appendChild(m);
    // [v3.1.4] Поимённый список найденных VPN/proxy-расширений (proxy_hijacked / no_ipchange).
    if (v.exts && v.exts.length){
        var mex = document.createElement('div'); mex.className='diag-result-msg';
        mex.textContent = t('diagOtherVpnsFound', 'Обнаружены VPN-расширения: {list}').replace('{list}', v.exts.join(', '));
        card.appendChild(mex);
    }
    var stats = document.createElement('div'); stats.className='diag-stats';
    function row(){ var d=document.createElement('div'); d.className='diag-stat'; stats.appendChild(d); return d; }
    function bold(txt){ var b=document.createElement('b'); b.textContent=txt; return b; }
    var r1=row(); r1.appendChild(document.createTextNode('🌐 '+t('diagLblInternet')+': ')); r1.appendChild(bold((st.internet&&st.internet.ok)?'✓':'✗'));
    var r2=row(); r2.appendChild(document.createTextNode('📡 '+t('diagLblApi')+': ')); r2.appendChild(bold(((st.api&&st.api.reachable)||0)+'/'+((st.api&&st.api.total)||5)));
    if (servers.length>0){
        var r3=row(); r3.appendChild(document.createTextNode('🖥 '+t('diagLblServers')+': ')); r3.appendChild(bold(okip.length+'/'+servers.length+' '+t('diagLblWorking')));
        var bar=document.createElement('div'); bar.className='diag-srvbar';
        function seg(cls,n){ if(n<=0)return; var s=document.createElement('span'); s.className=cls; s.style.width=(100*n/servers.length)+'%'; bar.appendChild(s); }
        seg('ok',okip.length); seg('noip',noip.length); seg('fail',fail.length);
        r3.appendChild(bar);
        var leg=document.createElement('div'); leg.className='diag-srv-legend';
        function legi(cls,txt,n){ if(n<=0)return; var i=document.createElement('i'); i.className=cls; i.appendChild(document.createTextNode(txt+' '+n)); leg.appendChild(i); }
        legi('ok',t('diagLblWorking'),okip.length);
        legi('noip',t('diagLblNoip'),noip.length);
        legi('fail',t('diagLblFailed'),fail.length);
        r3.appendChild(leg);
    }
    var fast = okip.slice().sort(function(a,b){return a.latency-b.latency;})[0];
    if (fast){
        var r5=row(); r5.appendChild(document.createTextNode('⚡ '+t('diagLblFastest')+': '));
        r5.appendChild(bold((typeof getCountryName==='function'?getCountryName(fast.country):fast.country)+' · '+fast.latency+' ms'));
    }
    if (st.sites && st.sites.tested && st.sites.results && st.sites.results.length){
        var r4=row(); r4.appendChild(document.createTextNode('🌍 '+t('diagLblSites')+': '));
        st.sites.results.forEach(function(s){ var c=document.createElement('span'); c.className='diag-site-chip '+(s.ok?'ok':'no'); c.textContent=s.name+' '+(s.ok?'✓':'✗'); r4.appendChild(c); });
    }
    card.appendChild(stats); box.appendChild(card); box.style.display='block';
    var cb=$('diagCopyResultBtn'); if(cb) cb.disabled=false;
    var cm=$('diagCopyResultMsg'); if(cm){ cm.className='settings-result'; cm.textContent=''; }
}
// [v3.0.1] Стабильный ID сервера из IP (НЕ раскрывает сам IP – нельзя обратно получить адрес
// без перебора). Хеш ИДЕНТИЧЕН PHP-стороне (admin/proxy-settings.php anonvpn_srv_hash) для
// корреляции: итеративно (h*31 + charCode) mod 2^32, затем base36, префикс S_.
function _srvHash(ip){
    ip = String(ip || '');
    var h = 0;
    for (var i = 0; i < ip.length; i++){ h = (h * 31 + ip.charCodeAt(i)) >>> 0; }
    return 'S_' + h.toString(36);
}
// ── Текст результата для копирования (в поддержку) ──
function formatDiagResultText(R, uid){
    var v=computeDiagVerdict(R, _lastClientProxyDiag); var def=DIAG_VERDICTS[v.code]||DIAG_VERDICTS.all_ok; var lc=_diagIsRu()?'ru':'en';
    var mark={red:'[!]',yellow:'[~]',green:'[OK]'};
    var st=R.steps||{}, servers=R.servers||[];
    var _oldCh=_diagOldChrome();
    var conn=servers.filter(function(s){return s.connected;});
    var okip=servers.filter(function(s){return s.connected&&(_oldCh||s.ipChanged);});
    var L=[];
    L.push('=== AnonVPN – Полная диагностика ===');
    var _ver=''; try { _ver=(chrome.runtime.getManifest&&chrome.runtime.getManifest().version)||''; } catch(e){}
    L.push('Версия: '+(_ver||'?')+(uid?(' | UID: '+uid):''));
    L.push('Вердикт: '+mark[def.lvl]+' '+_diagTxt(lc,'diagV_'+v.code+'_t'));
    L.push(_diagTxt(lc,'diagV_'+v.code+'_m').replace('{working}',String(v.working||0)).replace('{total}',String(v.total||0)).replace('{until}', v.until?(' (до '+v.until+')'):''));
    L.push('');
    // Серверные блокировки (для поддержки – точные коды)
    var bl=st.blocks||{};
    var bp=[];
    if (bl.illegal_ext) bp.push('illegal_ext');
    if (bl.version_too_old) bp.push('version_too_old(min '+(bl.min_version||'?')+')');
    if (bl.rate_limited) bp.push('rate_limited('+(bl.rl_reason||'?')+(bl.rl_until?(', until '+bl.rl_until):'')+')');
    if (bl.device_mismatch) bp.push('device_changed');
    if (bl.key_invalid) bp.push('key_invalid('+(bl.key_reason||'?')+')');
    if (bp.length) L.push('Блокировки: '+bp.join(', '));
    else if (bl.key_checked) L.push('Блокировки: нет (ключ проверен, OK)');
    else L.push('Блокировки: нет');
    L.push('Интернет: '+((st.internet&&st.internet.ok)?'OK':'FAIL'));
    L.push('Связь с серверами (api): '+((st.api&&st.api.reachable)||0)+'/'+((st.api&&st.api.total)||5));
    L.push('Серверов: '+servers.length+' | подключилось: '+conn.length+' | '+(_oldCh?'рабочих':'сменили IP')+': '+okip.length+(_oldCh?' (Chrome <116: смена IP через SW-пробу не проверяется, «подключился»=рабочий)':''));
    if (st.sites&&st.sites.tested&&st.sites.results){ L.push('Сайты: '+st.sites.results.map(function(s){return s.name+'='+(s.ok?'OK':'FAIL');}).join(' ')); }
    L.push('');
    L.push('Серверы:');
    // [v3.0.1] НЕ раскрываем host:port (утечка адресов вредит экосистеме). Номер = сквозной
    // индекс в пуле (как в списке выбора: №{idx+1}, free и premium – отдельные последовательности).
    // hash S_<хеш ip> – стабильный ID для корреляции в админке (proxy-settings.php), список может
    // сместиться → по номеру не опознать, а хеш привязан к IP. Хеш-функция ИДЕНТИЧНА PHP-стороне.
    var _sorted = servers.slice().sort(function(a,b){
        var ap = (a.type==='premium'), bp = (b.type==='premium');
        if (ap !== bp) return ap ? 1 : -1;
        return ((typeof a.idx==='number'?a.idx:9999)) - ((typeof b.idx==='number'?b.idx:9999));
    });
    _sorted.forEach(function(s){
        var num = (typeof s.idx==='number' && s.idx>=0) ? (s.idx+1) : '?';
        var mark = (s.type==='premium') ? ' (Premium)' : '';
        var status = !s.connected ? 'не подключился' : ((_oldCh || s.ipChanged) ? (s.latency+' ms') : 'IP не сменился');
        L.push('  '+(s.country||'')+' Сервер №'+num+mark+' – '+status+'  hash: '+(s.hash || (s.host ? _srvHash(s.host) : '')));
    });
    // [v3.1.1] Конфликты расширений – кто реально владеет chrome.proxy (levelOfControl) + какие ещё
    // VPN/proxy-расширения установлены. Ключевая подсказка при «ВПН включён, а IP реальный»: сразу
    // видно, перехватило ли другое расширение управление прокси. Собрано в _diagFinishOnce.
    var _cpd = _lastClientProxyDiag;
    if (_cpd) {
        L.push('');
        L.push('Конфликты расширений:');
        var _pc = _cpd.proxyControl || 'n/a';
        var _pcNote = (_pc === 'controlled_by_other_extensions') ? '  <== ПЕРЕХВАЧЕН другим расширением'
                    : (_pc === 'controlled_by_this_extension') ? '  (управляет AnonVPN)'
                    : (_pc === 'controllable_by_this_extension') ? '  (свободно, AnonVPN может управлять)'
                    : (_pc === 'not_controllable') ? '  (заблокировано политикой/системой)' : '';
        L.push('  Контроль прокси: ' + _pc + _pcNote);
        if (!_cpd.mgmt) {
            L.push('  Установленные VPN/proxy: (нет доступа к списку расширений)');
        } else if (_cpd.proxyExts && _cpd.proxyExts.length) {
            L.push('  Установленные VPN/proxy: ' + _cpd.proxyExts.map(function(e){ return e.name; }).join(', '));
        } else {
            L.push('  Установленные VPN/proxy: не обнаружено');
        }
    }
    return L.join('\n');
}
function runFullDiag(){
    if (_fullDiagRunning) return;
    // [v3.0.5] Запуск ИЗ НАСТРОЕК → рендерим в fullDiag-элементы (мастер переопределяет на setupCheck*).
    _diagProgId = 'fullDiagProgress'; _diagResId = 'fullDiagResult';
    var btn = $('fullDiagBtn'), prog = $(_diagProgId), res = $(_diagResId), cb = $('diagCopyResultBtn');
    if (res){ res.style.display='none'; res.innerHTML=''; }
    if (cb) cb.disabled = true;
    if (isVpnOn){
        _diagBuilt=false;
        if (prog){ prog.className='settings-result show err'; prog.style.display='block'; prog.innerHTML=''; prog.textContent=t('diagTurnOffVpnFull'); }
        return;
    }
    _fullDiagRunning = true; _diagConn = 0; _diagBuilt = false; _lastDiagResult = null; _diagFinished = false;
    if (btn) btn.disabled = true;
    _diagBuildSteps();
    _diagSetStep(_diagStepRow('internet'),'active');
    chrome.runtime.sendMessage({action:'runFullDiagnosis'}, function(resp){
        // [v3.0.1] Завершение приходит broadcast'ом diagDone/diagError (работает и для
        // переоткрытого popup). Здесь ловим только мгновенный reject (VPN включён / занято).
        if (chrome.runtime.lastError) return;
        if (resp && resp.error){
            if (resp.error==='diag_rate_limited'){ _diagAbort('rate_limited_diag', resp.retryInMin); return; }
            _diagAbort(resp.error); return;
        }
        if (resp && resp.ok && resp.result){ _diagFinishOnce(resp.result); }
    });
}
// Завершение/ошибка – идемпотентно (broadcast и sendResponse могут прийти оба).
// [v3.1.1] Отправка результата ПОЛНОЙ диагностики на сервер – техподдержка при обращении юзера
// сразу видит его последнее состояние (когда делал проверку + вердикт + серверы + блокировки +
// перехват прокси + установленные VPN). Best-effort, не блокирует UI. SW добавит uid/chrome_ver/version.
function _reportDiagRun(R, cd){
    if (!R) return;
    try {
        var v = (typeof computeDiagVerdict === 'function') ? computeDiagVerdict(R, cd) : null;
        var st = R.steps || {}, servers = (R.servers && R.servers.length) ? R.servers : [];
        var oldCh = (typeof _diagOldChrome === 'function') ? _diagOldChrome() : false;
        var conn = 0, work = 0;
        servers.forEach(function(s){ if (s.connected){ conn++; if (oldCh || s.ipChanged) work++; } });
        var bl = st.blocks || {}, bp = [];
        if (bl.illegal_ext) bp.push('illegal_ext');
        if (bl.version_too_old) bp.push('version_too_old');
        if (bl.rate_limited) bp.push('rate_limited:' + (bl.rl_reason || ''));
        if (bl.device_mismatch) bp.push('device_changed');
        if (bl.key_invalid) bp.push('key_invalid:' + (bl.key_reason || ''));
        var others = (cd && cd.proxyExts && cd.proxyExts.length) ? cd.proxyExts.map(function(e){ return e.name; }).join(', ') : '';
        chrome.runtime.sendMessage({ action: 'reportDiagRun', payload: {
            verdict: v ? v.code : '',
            servers_total: servers.length,
            servers_connected: conn,
            servers_working: work,
            internet_ok: (st.internet && st.internet.ok) ? 1 : 0,
            api_reachable: (st.api && st.api.reachable) || 0,
            blocks: bp.join(',').slice(0, 255),
            proxy_control: (cd && cd.proxyControl) || 'n/a',
            other_vpns: others.slice(0, 255),
            old_chrome: oldCh ? 1 : 0
        } }, function(){ if (chrome.runtime && chrome.runtime.lastError) { /* SW asleep – best-effort */ } });
    } catch (_){}
}
function _diagFinishOnce(result){
    if (_diagFinished) return;
    _diagFinished = true; _fullDiagRunning = false;
    var btn=$('fullDiagBtn'); if(btn) btn.disabled=false;
    // [v3.1.4] СНАЧАЛА конфликт-данные (локальные API, мгновенно) – вердикт зависит от них
    // (proxy_hijacked при перехвате прокси). Страховка: если callback не пришёл за 1500мс –
    // рендерим без cd (поведение как раньше). Гард исключает двойной рендер/отправку.
    var _renderedOnce = false;
    var _renderWith = function(cd){
        if (_renderedOnce) return;
        _renderedOnce = true;
        _lastClientProxyDiag = cd || null;
        if (result){ _lastDiagResult = result; renderDiagResult(result, cd); }
        _reportDiagRun(result, cd);
    };
    try { gatherClientProxyDiag(function(cd){ _renderWith(cd); }); } catch (_){ _renderWith(null); }
    setTimeout(function(){ _renderWith(null); }, 1500);
    // [v3.0.5] diagLastResult НЕ удаляем из storage – иначе после close-reopen кнопка «Скопировать
    // результат» гасла (результат жил только в _lastDiagResult в памяти). SW персистит его (sw:~5019),
    // _diagRecover восстанавливает на каждом открытии в пределах TTL. Перезапишется новой диагностикой.
}
function _diagAbort(reason, extra){
    _diagFinished = true; _fullDiagRunning = false; _diagBuilt = false;
    var btn=$('fullDiagBtn'); if(btn) btn.disabled=false;
    // [v3.1.1] Повторный запуск (runFullDiag) гасит «Скопировать» и обнуляет _lastDiagResult, а затем
    // упирается в rate-limit/ошибку → без этого кнопка оставалась мёртвой до переоткрытия popup.
    // ПРЕДЫДУЩИЙ результат жив в storage (SW персистит) – восстанавливаем его и кнопку.
    try { chrome.storage.local.get(['diagLastResult'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) return;
        if (d && d.diagLastResult){ _lastDiagResult = d.diagLastResult; var _cb=$('diagCopyResultBtn'); if(_cb) _cb.disabled=false; }
    }); } catch(_){}
    var prog=$(_diagProgId);
    var em = (reason==='rate_limited_diag') ? t('diagRateLimited').replace('{min}', String(extra||60))
           : (reason==='vpn_active') ? t('diagTurnOffVpn')
           : (reason==='ping_busy'||reason==='toggle_busy') ? t('diagBusy')
           : t('diagErrGeneric');
    if (prog){ prog.className='settings-result show err'; prog.style.display='block'; prog.innerHTML=''; prog.textContent=em; }
}
chrome.runtime.onMessage.addListener(function(m){
    if (!m) return;
    if (m.action==='diagProgress'){ _diagRenderProgress(m.phase, m); return; } // шаги рисуются в _diagProgId (мастер или настройки)
    if (m.action==='diagDone'){ _diagFinishOnce(m.result); try { _setupOnDiagDone(); } catch(_){} return; }
    if (m.action==='diagError'){ _diagAbort('error'); try { _setupOnDiagError(); } catch(_){} return; }
});
// [v3.0.1] Recovery: popup переоткрыт во время идущей диагностики (или сразу после завершения,
// если инициировавший popup был закрыт). Состояние читаем из storage (SW персистит).
(function _diagRecover(){
    try {
        chrome.storage.local.get(['diagRunning','diagProgress','diagLastResult'], function(d){
            if (chrome.runtime && chrome.runtime.lastError) return;
            if (!d) return;
            var running = d.diagRunning && (Date.now() - (d.diagRunning.ts||0) < 5*60*1000);
            if (running){
                _fullDiagRunning = true; _diagFinished = false; _diagConn = 0; _diagBuilt = false;
                var btn=$('fullDiagBtn'); if(btn) btn.disabled=true;
                if (d.diagProgress && d.diagProgress.phase){ _diagRenderProgress(d.diagProgress.phase, d.diagProgress); }
                else { _diagBuildSteps(); _diagSetStep(_diagStepRow('internet'),'active'); }
            } else if (d.diagLastResult && d.diagLastResult.ts && (Date.now() - d.diagLastResult.ts < 30*60*1000)){
                // [v3.0.5] Восстанавливаем последний результат → кнопка «Скопировать результат» активна.
                // НЕ удаляем (раньше стирали → на 2-м открытии гасло) + TTL 5→30мин: юзер успевает
                // переоткрыть popup и скопировать лог для поддержки. Перезапишется новой диагностикой.
                _lastDiagResult = d.diagLastResult; renderDiagResult(d.diagLastResult);
            }
        });
    } catch(e){}
})();
// [v3.0.1] Волна-индикатор копирования вместо статичной плашки
function _btnCopyFeedback(btn, ok){
    if (!btn) return;
    btn.classList.remove('btn-copied','btn-copyerr');
    void btn.offsetWidth;                       // рестарт CSS-анимации при повторном клике
    btn.classList.add(ok ? 'btn-copied' : 'btn-copyerr');
    if (btn._copyTo) clearTimeout(btn._copyTo);
    btn._copyTo = setTimeout(function(){ btn.classList.remove('btn-copied','btn-copyerr'); }, ok ? 1100 : 700);
}
$('diagCopyResultBtn')?.addEventListener('click', function(){
    if (!_lastDiagResult) return;
    var btn = this, msgEl = $('diagCopyResultMsg');
    if (msgEl){ msgEl.className='settings-result'; msgEl.textContent=''; }
    chrome.storage.local.get(['uid'], function(d){
        if (chrome.runtime && chrome.runtime.lastError) {}
        var text = formatDiagResultText(_lastDiagResult, d && d.uid);
        var fail = function(){
            _btnCopyFeedback(btn, false);
            if (msgEl){
                msgEl.className='settings-result show err'; msgEl.textContent=t('diagError','Ошибка');
                setTimeout(function(){ if(msgEl) msgEl.className='settings-result'; }, 3500);
            }
        };
        (navigator.clipboard && navigator.clipboard.writeText ? navigator.clipboard.writeText(text) : Promise.reject(new Error('no clipboard'))).then(function(){
            _btnCopyFeedback(btn, true);
        }).catch(function(){
            try {
                var ta=document.createElement('textarea'); ta.value=text; ta.style.position='fixed'; ta.style.opacity='0';
                document.body.appendChild(ta); ta.select();
                var ok = document.execCommand && document.execCommand('copy');
                document.body.removeChild(ta);
                if (ok) _btnCopyFeedback(btn, true); else fail();
            } catch(e){ fail(); }
        });
    });
});
$('fullDiagBtn')?.addEventListener('click', runFullDiag);

$('copyDiagBtn')?.addEventListener('click', function(){
    var btn = this;
    var r = $('copyDiagResult');
    if (r) { r.className = 'settings-result'; r.textContent = ''; }
    btn.disabled = true;
    gatherClientProxyDiag(function(clientDiag){  // [v2.8.7] сначала собрать proxy-control/ext, потом лог SW
    chrome.runtime.sendMessage({ action: 'getDiagnosticLog' }, function(resp){
        btn.disabled = false;
        if (chrome.runtime.lastError || !resp) {
            if (r) { r.textContent = t('diagError', 'Error reading log'); r.className = 'settings-result show err'; }
            return;
        }
        var text = formatDiagnosticLog(resp, clientDiag);
        (navigator.clipboard && navigator.clipboard.writeText
            ? navigator.clipboard.writeText(text)
            : Promise.reject(new Error('no clipboard'))
        ).then(function(){
            if (r) { r.textContent = t('diagCopied', 'Copied to clipboard'); r.className = 'settings-result show ok'; }
        }).catch(function(){
            // Fallback: use a temporary textarea
            try {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed'; ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                var ok = document.execCommand && document.execCommand('copy');
                document.body.removeChild(ta);
                if (r) {
                    r.textContent = ok ? t('diagCopied', 'Copied to clipboard') : t('diagError', 'Error reading log');
                    r.className = 'settings-result show ' + (ok ? 'ok' : 'err');
                }
            } catch {
                if (r) { r.textContent = t('diagError', 'Error reading log'); r.className = 'settings-result show err'; }
            }
        }).finally(function(){
            setTimeout(function(){ if (r) r.className = 'settings-result'; }, 4000);
        });
    });
    });
});

// Clear cache – reset confirm state
var clearCacheOrigHTML=null;
function resetClearCacheConfirm(){
    var btn=$('clearCacheBtn'); if(!btn||btn.dataset.confirming!=='1') return;
    if(clearCacheOrigHTML) btn.innerHTML=clearCacheOrigHTML;
    btn.classList.remove('settings-btn-confirming');
    delete btn.dataset.confirming;
    var wrap=btn.parentElement.querySelector('.settings-confirm-row');
    if(wrap) wrap.remove();
    var r=$('clearCacheResult');
    if(r) r.className='settings-result';
}

// Clear cache button – with confirmation
$('clearCacheBtn')?.addEventListener('click', function(){
    if(isVpnOn){
        var r=$('clearCacheResult');
        if(r){r.textContent=t('vpnDisabledHint','Turn off VPN first');r.className='settings-result show err';
            setTimeout(function(){r.className='settings-result';},4000);}
        return;
    }
    // Show inline confirm
    var btn=this;
    var r=$('clearCacheResult');
    if(btn.dataset.confirming==='1') return;
    btn.dataset.confirming='1';
    // Replace button content with confirmation
    clearCacheOrigHTML=btn.innerHTML;
    // [v2.5.8 audit] DOM API вместо innerHTML+t()
    btn.innerHTML='';
    var icon=document.createElement('span'); icon.className='settings-btn-icon'; icon.textContent='⚠️'; btn.appendChild(icon);
    var lbl=document.createElement('span'); lbl.textContent=t('clearCacheConfirm','Clear all cached data?'); btn.appendChild(lbl);
    btn.classList.add('settings-btn-confirming');
    // Show Yes/No buttons
    var wrap=document.createElement('div');
    wrap.className='settings-confirm-row';
    var yesBtn=document.createElement('button');
    yesBtn.className='settings-confirm-yes';
    yesBtn.textContent=t('confirmYes','Yes, clear');
    var noBtn=document.createElement('button');
    noBtn.className='settings-confirm-no';
    noBtn.textContent=t('confirmNo','Cancel');
    wrap.appendChild(yesBtn);
    wrap.appendChild(noBtn);
    btn.parentElement.insertBefore(wrap,r);

    noBtn.addEventListener('click',resetClearCacheConfirm);
    yesBtn.addEventListener('click',function(){
        resetClearCacheConfirm();
        btn.disabled=true;
        // [v2.6.0] Расширенный список: добавлены diagnosticLog и sessionExpired,
        // чтобы «Очистить кэш» действительно сбрасывал всё кэшированное состояние.
        // НЕ очищаем autoSelectServer/autoSelectScope/favoriteServers/excludedFromAutoSelect –
        // это пользовательские настройки, а не кэш.
        // [v2.7.1 fix F146] Добавлены lastNewsTime + updateAvailable/Dismissed –
        // ранее «Очистить кэш» оставлял news-таймштамп (badge не сбрасывался) и
        // soft update-banner («доступна новая версия») продолжал висеть.
        var CACHE_KEYS=[
            'proxyList','proxyListEnc','cachedProxyList','cachedServerStats','cachedServerStatsAt','cachedNews',
            'cachedTranslationsData','cachedTranslationsVersion','updateRequired','minVersion','updateUrl','illegalExtId',
            'selectedProxy','diagnosticLog','sessionExpired','proxyListFetchAt','lastHeartbeatAt',
            'lastNewsTime','updateAvailable','updateAvailableDismissed',
            // [v2.7.5 audit Pass5] pendingTraffic – persisted traffic counter; ручная очистка
            // через «Очистить кэш» симметрична STALE_KEYS wipe на real update.
            'pendingTraffic',
            // [v2.7.6 audit Pass9] symmetry с STALE_KEYS – manual «Clear cache» ранее не стирал
            // эти три кэшевых ключа: VPN-conflict scan, serverSortMode (UI sort).
            'vpnConflictList','vpnConflictLastSeen','serverSortMode',
            // [v2.7.6 audit Pass10] добавлены для full STALE_KEYS symmetry: vpnDeadline
            // (free-tier 60-min deadline) + autoSelectServer (auto-select toggle state).
            'vpnDeadline','autoSelectServer',
            // [v2.8.0] account-link state. Clear Cache локально сбрасывает флаги (юзер должен
            // заново ввести код). Сам link в БД на сервере не теряется – можно сгенерить новый
            // код на anon-vpn.ru и привязаться повторно.
            'accountVerified','accountEmail',
            // [v2.8.0] rate-limit ban state – manual clear позволяет recover если флаг застрял
            'rateLimited','rateLimitedReason','rateLimitedUntil',
            // [v2.8.0] checker state – пользователь ждёт «свежего старта» после Clear Cache:
            // results, sliding-window history, mode/site UI selection. lastCheckerRunAt – legacy.
            'checkerRunHistory','checkerLastResults','checkerMode','checkerSelectedSite','checkerCustomSite','lastCheckerRunAt',
            // [v3.1.7] накопитель проверок «Доступность сайта» по серверам (подсказка при наведении) — чистый старт.
            'siteCheckByServer',
            // [v3.0.5] fullDiagLastRun – лимит «Полной диагностики» (1/час). Ручная очистка тоже
            // сбрасывает лимит (симметрично STALE_KEYS на апдейте + checkerRunHistory выше).
            'fullDiagLastRun',
            // [v3.1.4 fix] Данные фонового ghost-пинга / замеров скорости серверов. Раньше "Очистить
            // кэш" их НЕ сбрасывал -> после очистки в модалке выбора сервера оставались старые замеры,
            // счётчик "До проверки" тикал от прежних данных, а серверы, помеченные сломанными
            // (checker-fail 3.1.3), так и висели. Теперь очистка даёт чистый старт (ghost перепингует).
            // serverPings/serverPingsRunAt/bulkPingProgress уже в STALE_KEYS -> симметрия восстановлена;
            // brokenServers self-prune 5 мин, но сбрасываем сразу для чистого списка серверов.
            'serverPings','serverPingsRunAt','bulkPingProgress','brokenServers'
        ];
        var clearedMsg=t('cacheCleared','Cache cleared');
        chrome.storage.local.remove(CACHE_KEYS,function(){
            cachedTranslations=null;
            cachedProxyList=null;
            serverUserCounts={};
            if(r){r.textContent=clearedMsg;r.className='settings-result show ok';}
            translateAll(getLang());
            loadProxies();
            setTimeout(function(){btn.disabled=false;},1000);
            setTimeout(function(){if(r)r.className='settings-result';},4000);
        });
    });
});

// ═══ EXPORT/IMPORT SETTINGS [v2.7.6] ═══
// Whitelist user-prefs only. Excluded by design:
//   uid / proxyEnabled / vpnDeadline / cached* / isPremium / premiumKey / expiresAt /
//   feedback_* / vpnStats / diagnosticLog / proxyListFetchAt / lastHeartbeatAt /
//   pendingTraffic / vpnConflictList / autoEnableHistory / _webNavRefused / sessionExpired /
//   trialAlreadyIssued / updateAvailable*. Premium-keys специально не экспортируем –
//   device-binding на сервере, перенос ключа на другую машину = device_changed на следующем
//   recheck. Юзер использует кнопку «Восстановить мой Premium» на новом устройстве.
const BACKUP_KEYS = [
    'language', 'colorTheme',
    'autoSelectServer', 'autoSelectScope',
    'favoriteServers', 'excludedFromAutoSelect',
    'blacklistDomains', 'whitelistDomains', 'exclusionsMode',
    'adBlockerEnabled', 'serverSortMode',
    'autoEnableEnabled', 'autoEnableDomains'
];
function _backupShowResult(msg, ok){
    var r = $('backupResult'); if(!r) return;
    r.textContent = msg;
    r.className = 'settings-result show ' + (ok ? 'ok' : 'err');
    setTimeout(function(){ if(r) r.className = 'settings-result'; }, 4000);
}
// [v2.7.6] Premium-gate: backup feature доступен только Premium-юзерам.
// HTML-overlay (.premium-lock) визуально блокирует кнопки + перехватывает клики на upsell,
// но defense-in-depth – проверка в handler'е тоже (на случай прямого dispatchEvent через devtools).
function _backupRequirePremium(cb){
    chrome.storage.local.get(['isPremium'], function(d){
        if (!d.isPremium) {
            window.open(upsellUrl('backup_locked'), '_blank', 'noopener,noreferrer');
            return;
        }
        cb();
    });
}
$('exportSettingsBtn')?.addEventListener('click', function(){
    _backupRequirePremium(function(){
    chrome.storage.local.get(BACKUP_KEYS, function(d){
        if (chrome.runtime && chrome.runtime.lastError) {
            _backupShowResult(t('backupExportFail','Ошибка экспорта'), false);
            return;
        }
        var settings = {};
        BACKUP_KEYS.forEach(function(k){
            if (d[k] !== undefined) settings[k] = d[k];
        });
        var payload = {
            anonvpn_backup: 1,
            version: chrome.runtime.getManifest().version,
            createdAt: new Date().toISOString(),
            settings: settings
        };
        var json;
        try { json = JSON.stringify(payload, null, 2); } catch(_) {
            _backupShowResult(t('backupExportFail','Ошибка экспорта'), false);
            return;
        }
        // [v2.7.6 audit Pass13] try/catch вокруг Blob/URL/click. OOM или quota during
        // создание blob (большой backup на низком RAM) кидал uncaught – юзер видел
        // успех в callback'е выше, но реально файл не сохранился. Теперь explicit error.
        try {
            var blob = new Blob([json], { type: 'application/json' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            var dt = new Date().toISOString().slice(0,10);
            a.download = 'anonvpn-settings-' + dt + '.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            // Освобождаем blob URL – иначе держится в памяти browser-ом до закрытия popup
            setTimeout(function(){ try { URL.revokeObjectURL(url); } catch(_) {} }, 1500);
            _backupShowResult(t('backupExported','Файл сохранён'), true);
        } catch (_) {
            _backupShowResult(t('backupExportFail','Ошибка экспорта'), false);
        }
    });
    });
});

// Sanitize импортированных настроек: whitelist + типовая проверка + cap длины массивов.
// НЕ доверяем содержимому файла – он мог быть отредактирован вручную или подложен злонамеренно.
function _sanitizeImport(s){
    var out = {};
    if (!s || typeof s !== 'object') return out;
    function isStr(v, max){ return typeof v === 'string' && v.length > 0 && v.length <= (max || 256); }
    function strArr(v, maxLen, maxItem){
        if (!Array.isArray(v)) return null;
        var max = maxLen || 500;
        var rs = [];
        for (var i = 0; i < v.length && rs.length < max; i++) {
            if (isStr(v[i], maxItem || 253)) rs.push(v[i]);
        }
        return rs;
    }
    // [v2.7.6 audit Pass13] Domain whitelist regex – defense-in-depth перед PAC/DNR.
    // Пропускает: a-z, 0-9, точка, дефис, двоеточие (для host:port в favoriteServers/excludedFromAutoSelect).
    // Блокирует: <script>, *, %00, control-chars, unicode-доменам (IDN не поддержан в DNR ASCII-only).
    function domArr(v, maxLen, maxItem){
        var arr = strArr(v, maxLen, maxItem); if (!arr) return null;
        var rs = [];
        for (var i = 0; i < arr.length; i++) {
            if (/^[a-z0-9.\-:]+$/i.test(arr[i])) rs.push(arr[i].toLowerCase());
        }
        return rs;
    }
    if (isStr(s.language, 8)) out.language = s.language;
    if (isStr(s.colorTheme, 32)) out.colorTheme = s.colorTheme;
    if (typeof s.autoSelectServer === 'boolean') out.autoSelectServer = s.autoSelectServer;
    if (s.autoSelectScope === 'all' || s.autoSelectScope === 'free' || s.autoSelectScope === 'premium') out.autoSelectScope = s.autoSelectScope;
    var fs = domArr(s.favoriteServers, 100, 64); if (fs) out.favoriteServers = fs;
    var ex = domArr(s.excludedFromAutoSelect, 100, 64); if (ex) out.excludedFromAutoSelect = ex;
    var bl = domArr(s.blacklistDomains, 1000, 253); if (bl) out.blacklistDomains = bl;
    var wl = domArr(s.whitelistDomains, 1000, 253); if (wl) out.whitelistDomains = wl;
    if (s.exclusionsMode === 'blacklist' || s.exclusionsMode === 'whitelist') out.exclusionsMode = s.exclusionsMode;
    if (typeof s.adBlockerEnabled === 'boolean') out.adBlockerEnabled = s.adBlockerEnabled;
    if (s.serverSortMode === 'load' || s.serverSortMode === 'index' || s.serverSortMode === 'country' || s.serverSortMode === 'ping') out.serverSortMode = s.serverSortMode;
    if (typeof s.autoEnableEnabled === 'boolean') out.autoEnableEnabled = s.autoEnableEnabled;
    var ae = domArr(s.autoEnableDomains, 500, 253); if (ae) out.autoEnableDomains = ae;
    return out;
}

var _pendingImport = null;
$('importSettingsBtn')?.addEventListener('click', function(){
    _backupRequirePremium(function(){
        if (isVpnOn) {
            _backupShowResult(t('vpnDisabledHint','Сначала выключите VPN'), false);
            return;
        }
        var fi = $('importSettingsFile');
        // Reset value: re-import того же файла должен снова триггерить change-event
        if (fi) { fi.value = ''; fi.click(); }
    });
});
$('importSettingsFile')?.addEventListener('change', function(e){
    var file = e.target.files && e.target.files[0];
    if (!file) return;
    // 1 MB cap – больше реальный backup быть не может (1000 доменов × 253 char + meta < 300 KB)
    if (file.size > 1024 * 1024) {
        _backupShowResult(t('backupImportTooLarge','Файл слишком большой'), false);
        return;
    }
    var reader = new FileReader();
    reader.onload = function(ev){
        var raw = ev.target && ev.target.result;
        if (typeof raw !== 'string') {
            _backupShowResult(t('backupImportInvalid','Неверный формат файла'), false);
            return;
        }
        var parsed = null;
        try { parsed = JSON.parse(raw); }
        catch(_) {
            _backupShowResult(t('backupImportInvalid','Неверный формат файла'), false);
            return;
        }
        if (!parsed || typeof parsed !== 'object' || parsed.anonvpn_backup !== 1 || !parsed.settings || typeof parsed.settings !== 'object') {
            _backupShowResult(t('backupImportInvalid','Неверный формат файла'), false);
            return;
        }
        var clean = _sanitizeImport(parsed.settings);
        var keyCount = Object.keys(clean).length;
        if (!keyCount) {
            _backupShowResult(t('backupImportEmpty','В файле нет данных для импорта'), false);
            return;
        }
        _pendingImport = clean;
        var det = $('importConfirmDetails');
        if (det) det.textContent = t('backupImportSummary','Будет применено настроек: ') + keyCount;
        openModal('importConfirmModal');
        // [v2.7.6 audit Pass13 UX] Перенос фокуса на «Импортировать» – keyboard-only юзер
        // не должен TAB'ать через всю модалку. setTimeout – даёт CSS-анимации modalIn
        // завершиться до фокуса (иначе фокус скачет на mid-animation элемент).
        setTimeout(function(){ try { var y = $('importConfirmYes'); if (y) y.focus(); } catch(_) {} }, 80);
    };
    reader.onerror = function(){
        _backupShowResult(t('backupImportInvalid','Неверный формат файла'), false);
    };
    reader.readAsText(file, 'utf-8');
});
$('importConfirmNo')?.addEventListener('click', function(){
    closeModal('importConfirmModal');
    _pendingImport = null;
});
$('importConfirmYes')?.addEventListener('click', function(){
    if (!_pendingImport) { closeModal('importConfirmModal'); return; }
    if (isVpnOn) {
        // Защита от race: VPN включился между открытием модала и подтверждением
        closeModal('importConfirmModal');
        _pendingImport = null;
        _backupShowResult(t('vpnDisabledHint','Сначала выключите VPN'), false);
        return;
    }
    // [v2.7.6 audit Pass14] Re-check Premium перед запись'ю – premium мог expire между
    // открытием модала и confirm. Без проверки storage.set всё равно сработает (storage не
    // знает про premium-gate), и юзер потеряет настройки в storage без UI-доступа к ним.
    _backupRequirePremium(function(){
    var data = _pendingImport;
    _pendingImport = null;
    chrome.storage.local.set(data, function(){
        closeModal('importConfirmModal');
        if (chrome.runtime && chrome.runtime.lastError) {
            _backupShowResult(t('backupImportFail','Ошибка импорта'), false);
            return;
        }
        _backupShowResult(t('backupImported','Импорт завершён'), true);
        // Закрываем popup чтобы при следующем открытии всё применилось через
        // cold-state init (translateAll, applyTheme, syncDnr – SW реагирует на storage.onChanged
        // для autoEnable*/adBlocker/isPremium, остальное применится на reopen).
        // [v2.7.6 audit Pass13 UX] 2 сек вместо 1.5 – даёт юзеру прочесть «Импорт завершён»
        // на медленных устройствах. Слишком долго (>3s) – юзер начнёт тыкать по UI после reload.
        setTimeout(function(){ try { window.close(); } catch(_) {} }, 2000);
    });
    });
});

// ═══ SUPPORT LINK WITH PARAMS ═══
function getSiteLang() {
    var supported = ['ru','en','zh','es','de','fr','pt'];
    var lang = getLang();
    return supported.indexOf(lang) >= 0 ? lang : 'en';
}

// [v2.6.2] «Обратная связь» теперь открывает хаб поддержки: страница + чат + FAQ.
$('supportBtn')?.addEventListener('click', function(e){
    e.preventDefault();
    openSupportModal();
});

function openSupportModal(){
    var modal = $('supportModal');
    var frame = $('supportFaqFrame');
    var titleEl = $('supportModalTitle');
    if (!modal || !frame) return;
    if (titleEl) titleEl.textContent = t('supportModalTitle', 'Поддержка');
    setText('openSupportPageLabel', t('openSupportPage', 'Страница поддержки'));
    setText('openSupportChatLabel', t('openSupportChat', 'Чат поддержки'));
    setText('supportFaqTitle', t('supportFaqTitle', 'Частые вопросы'));
    chrome.storage.local.get(['isPremium','feedback_email','colorTheme'], function(d){
        getDeviceId().then(function(uid){
            var params = new URLSearchParams({
                v: chrome.runtime.getManifest().version,
                s: d.isPremium ? 'premium' : 'free',
                uid: uid,
                lang: getSiteLang(),
                theme: (d.colorTheme === 'dark') ? 'dark' : 'light'
            });
            if (d.feedback_email) params.set('email', d.feedback_email);
            var url = 'https://balancing.apiget.ru/AnonVPN/lk/support/faq-embed.php?' + params.toString();
            if (frame.dataset.lastUrl !== url) {
                frame.src = url;
                frame.dataset.lastUrl = url;
            }
            openModal('supportModal');
        }).catch(function(e){
            // [v2.7.4 audit r3] getDeviceId rejection (rare storage failure) – открываем модал
            // без uid params, чтобы юзер не остался без поддержки. faq-embed.php терпит отсутствие uid.
            console.warn('[AnonVPN] getDeviceId failed in support:', e);
            openModal('supportModal');
        });
    });
}

// «Страница поддержки» – открыть полную версию в новой вкладке
$('openSupportPageBtn')?.addEventListener('click', function(){
    chrome.storage.local.get(['isPremium'], function(d){
        var ver = chrome.runtime.getManifest().version;
        var status = d.isPremium ? 'premium' : 'free';
        var url = 'https://balancing.apiget.ru/AnonVPN/lk/support/?lang=' + getSiteLang() + '&v=' + encodeURIComponent(ver) + '&s=' + status;
        window.open(url, '_blank', 'noopener,noreferrer');
    });
});

// [v2.6.2] In-popup chat – embed widget at anon-vpn.ru/support/chat-embed.php
// Params: v (version), s (free|premium), uid (per-install id), lang, theme (light|dark),
// optional email (from feedback form). 'name' не собираем в расширении – не передаём.
function openSupportChat(){
    var modal = $('supportChatModal');
    var frame = $('supportChatFrame');
    var titleEl = $('supportChatTitle');
    if (!modal || !frame) return;
    closeSettings(); // settings drawer has z-index 10000 – would cover the chat modal (9999)
    closeModal('supportModal'); // закрыть хаб поддержки, если открыт
    if (titleEl) titleEl.textContent = t('supportChatTitle', 'Чат поддержки');
    chrome.storage.local.get(['isPremium','feedback_email','colorTheme'], function(d){
        getDeviceId().then(function(uid){
            var params = new URLSearchParams({
                v: chrome.runtime.getManifest().version,
                s: d.isPremium ? 'premium' : 'free',
                uid: uid,
                lang: getSiteLang(),
                theme: (d.colorTheme === 'dark') ? 'dark' : 'light'
            });
            // [v3.1.1] Chrome-версия + ОС в params → chat-embed.php добавит их в [info]-блок,
            // чтобы AI-бот сразу применял правило про старый Chrome (109 = потолок Win7/8.1),
            // не дожидаясь диагностического лога от пользователя.
            try {
                var _ua = navigator.userAgent, _cr = _ua.match(/Chrome\/(\d+)/);
                if (_cr) params.set('cr', _cr[1]);
                var _os = /Windows NT 10\.0/.test(_ua) ? 'Windows 10/11'
                    : /Windows NT 6\.3/.test(_ua) ? 'Windows 8.1'
                    : /Windows NT 6\.2/.test(_ua) ? 'Windows 8'
                    : /Windows NT 6\.1/.test(_ua) ? 'Windows 7'
                    : /Mac OS X/.test(_ua) ? 'macOS'
                    : /Linux/.test(_ua) ? 'Linux' : '';
                if (_os) params.set('os', _os);
            } catch (e) { /* UA parse best-effort – не ломаем открытие чата */ }
            if (d.feedback_email) params.set('email', d.feedback_email);
            var url = 'https://balancing.apiget.ru/AnonVPN/lk/support/chat-embed.php?' + params.toString();
            // Re-set src only if changed – preserves chat session on re-open
            if (frame.dataset.lastUrl !== url) {
                frame.src = url;
                frame.dataset.lastUrl = url;
            }
            openModal('supportChatModal');
        }).catch(function(e){
            // [v2.7.4 audit r3] getDeviceId rejection – открываем чат без uid (chat-embed
            // создаст сессию по user_token из localStorage юзера, uid опционален).
            console.warn('[AnonVPN] getDeviceId failed in chat:', e);
            openModal('supportChatModal');
        });
    });
}
$('openSupportChatBtn')?.addEventListener('click', openSupportChat);

$('privacyBtn')?.addEventListener('click', function(e){
    e.preventDefault();
    window.open('https://balancing.apiget.ru/AnonVPN/lk/privacy/?lang=' + getSiteLang(), '_blank', 'noopener,noreferrer');
});

// [v3.1.7] Общий чат пользователей → новая вкладка (RKN-safe редиректор lk/chat/, как остальные ссылки).
$('communityChatBtn')?.addEventListener('click', function(e){
    e.preventDefault();
    window.open('https://balancing.apiget.ru/AnonVPN/lk/chat/?lang=' + getSiteLang(), '_blank', 'noopener,noreferrer');
});

// Account buy button → open buy modal
$('accountBuyBtn')?.addEventListener('click', function(){
    var title = $('buyModalTitle');
    var text = $('buyModalText');
    if (title) title.textContent = t('buyModalTitle', 'Купить премиум');
    if (text) text.textContent = t('buyModalText', '');
    var actionTg = $('buyModalAction');
    var actionSite = $('buyModalActionSite');
    if (actionTg) actionTg.textContent = t('buyModalAction', 'Купить через Telegram');
    if (actionSite) {
        actionSite.textContent = t('buyModalActionSite', 'Купить на сайте');
        actionSite.href = siteUrl('account_buy');
    }
    openModal('buyPremiumModal');
});

// [v2.5.9] Session expired sticky banner (timer-disconnect)
function showSessionExpiredBanner(){
    var b = $('sessionExpiredBanner');
    if (!b) return;
    // Не показываем premium-пользователям и когда VPN уже включён
    chrome.storage.local.get(['isPremium'], function(d){
        if (d.isPremium || isVpnOn) { b.setAttribute('hidden',''); return; }
        b.removeAttribute('hidden');
    });
}
function hideSessionExpiredBanner(clearFlag){
    var b = $('sessionExpiredBanner');
    if (b) b.setAttribute('hidden','');
    if (clearFlag) chrome.storage.local.remove(['sessionExpired']);
}
function checkSessionExpiredBannerOnInit(){
    chrome.storage.local.get(['sessionExpired','isPremium'], function(d){
        if (!d.sessionExpired) return;
        if (d.isPremium) { chrome.storage.local.remove(['sessionExpired']); return; }
        if (isVpnOn) { chrome.storage.local.remove(['sessionExpired']); return; }
        showSessionExpiredBanner();
    });
}

$('sessionExpiredClose')?.addEventListener('click', function(){
    hideSessionExpiredBanner(true);
});
$('sessionExpiredPremiumBtn')?.addEventListener('click', function(){
    var title = $('buyModalTitle');
    var text = $('buyModalText');
    if (title) title.textContent = t('buyModalTitle', 'Купить премиум');
    if (text) text.textContent = t('buyModalText', '');
    var actionTg = $('buyModalAction');
    var actionSite = $('buyModalActionSite');
    if (actionTg) actionTg.textContent = t('buyModalAction', 'Купить через Telegram');
    if (actionSite) {
        actionSite.textContent = t('buyModalActionSite', 'Купить на сайте');
        actionSite.href = siteUrl('session_expired_buy');
    }
    openModal('buyPremiumModal');
    // [v2.7.0 fix F28] Скрываем sticky-баннер после действия – иначе остаётся
    // навсегда (storage flag persist), юзер закрывает popup, открывает – снова видит.
    hideSessionExpiredBanner(true);
});
$('sessionExpiredTrialBtn')?.addEventListener('click', function(){
    // [v2.7.0 fix F28] Если trial уже использован – открываем upsell вместо trial-info
    // (модалка вводила в заблуждение: показывала инструкцию для trial, который недоступен).
    chrome.storage.local.get(['trialAlreadyIssued'], function(d){
        if (d.trialAlreadyIssued) {
            chrome.tabs.create({ url: upsellUrl('session_expired_trial_unavail') }).catch(() => {});
        } else {
            openTrialInfoModal();
        }
        hideSessionExpiredBanner(true);
    });
});

// [v2.5.9] Trial info modal – explains trial flow and offers two access paths:
//   1) "Web TG" – open web.telegram.org directly (may work without VPN in some regions)
//   2) "Enable VPN + Web TG" – toggle VPN on via SW, wait for success, then open web.telegram.org
// When VPN is already on, only the direct "Web TG" option is shown.
var TG_WEB_URL = TG_URLS.web; // [v2.6.5] backcompat alias

function openTrialInfoModal(){
    var t_el = $('trialInfoTitle');
    if (t_el) t_el.textContent = t('trialInfoTitle', 'Trial Premium');
    var txt_el = $('trialInfoText');
    if (txt_el) {
        var tmpl = t('trialInfoText', 'The Telegram bot <b>@exp_AnonVPN_bot</b> will open. It will issue a trial Premium key. Copy the key, return to the extension → «Premium» tab → paste the key and click OK. Premium features will be activated for the trial period.');
        renderRichTextSafe(txt_el, tmpl);
    }
    var cancel_el = $('trialInfoCancel');
    if (cancel_el) cancel_el.textContent = t('trialInfoCancel', 'Cancel');

    var webBtn = $('trialInfoWebBtn');
    var vpnWebBtn = $('trialInfoVpnWebBtn');

    if (webBtn) {
        webBtn.disabled = false;
        webBtn.textContent = t('trialInfoWebBtn', 'Web TG');
    }
    if (vpnWebBtn) {
        vpnWebBtn.disabled = false;
        vpnWebBtn.textContent = t('trialInfoVpnWebBtn', 'Enable VPN + Web TG');
    }

    if (isVpnOn) {
        // VPN on – hide "Enable VPN + Web TG" variant
        if (vpnWebBtn) vpnWebBtn.setAttribute('hidden','');
    } else {
        if (vpnWebBtn) vpnWebBtn.removeAttribute('hidden');
    }

    openModal('trialInfoModal');
}

$('trialInfoCancel')?.addEventListener('click', function(){
    closeModal('trialInfoModal');
});

// Direct Web TG – no VPN toggling
$('trialInfoWebBtn')?.addEventListener('click', function(){
    window.open(TG_WEB_URL, '_blank', 'noopener,noreferrer');
    setTimeout(function(){ closeModal('trialInfoModal'); }, 100);
});

// Enable VPN then open Web TG
$('trialInfoVpnWebBtn')?.addEventListener('click', function(){
    var btn = this;
    btn.disabled = true;
    btn.textContent = t('connecting', 'Connecting...');
    // Also disable sibling Web TG button to prevent double-action
    var webBtn = $('trialInfoWebBtn');
    if (webBtn) webBtn.disabled = true;
    chrome.runtime.sendMessage({ action: 'toggleProxy' }, function(res){
        if (chrome.runtime.lastError || !res || res.error || !res.proxyEnabled) {
            btn.disabled = false;
            btn.textContent = t('trialInfoVpnWebBtn', 'Enable VPN + Web TG');
            if (webBtn) webBtn.disabled = false;
            var errKey = (res && res.error === 'timeout') ? 'connectionTimeout' : 'connectionError';
            showStatusMessage(t(errKey, 'Connection error'), true, 'vpn');
            return;
        }
        // VPN now ON – sync local UI state (mirrors performVpnToggle post-connect logic)
        toggle.checked = true;
        isVpnOn = true;
        updateVpnButtonUI(true);
        setVpnFieldsLocked(true);
        startLocalTimer();
        hideSessionExpiredBanner(true);
        // Small delay so proxy auth is primed before Telegram tab loads
        setTimeout(function(){
            window.open(TG_WEB_URL, '_blank', 'noopener,noreferrer');
            closeModal('trialInfoModal');
        }, 600);
    });
});
$('sessionExpiredDetailsBtn')?.addEventListener('click', function(){
    chrome.tabs.create({ url: upsellUrl('session_expired_details') }).catch(() => {});
    // [v2.7.0 fix F28] Скрываем sticky-баннер после действия – иначе flag persist'ит
    // в storage, реоткрытие popup'а снова покажет баннер.
    hideSessionExpiredBanner(true);
});

// [v2.5.9] High-load banner buttons
$('loadWarningBuyBtn')?.addEventListener('click', function(){
    var title = $('buyModalTitle');
    var text = $('buyModalText');
    if (title) title.textContent = t('buyModalTitle', 'Купить премиум');
    if (text) text.textContent = t('buyModalText', '');
    var actionTg = $('buyModalAction');
    var actionSite = $('buyModalActionSite');
    if (actionTg) actionTg.textContent = t('buyModalAction', 'Купить через Telegram');
    if (actionSite) {
        actionSite.textContent = t('buyModalActionSite', 'Купить на сайте');
        actionSite.href = siteUrl('load_warning_buy');
    }
    openModal('buyPremiumModal');
});
$('loadWarningTrialBtn')?.addEventListener('click', function(){
    // [v2.5.9] Route through trial modal for consistency with sessionExpired banner.
    // Modal will handle VPN-off case (Web TG vs Enable VPN + Web TG).
    openTrialInfoModal();
});

// ═══ BUY PREMIUM MODAL ═══
buyPremiumBtn?.addEventListener('click', () => {
    chrome.storage.local.get(['isPremium'], function(d) {
        var title = $('buyModalTitle');
        var text = $('buyModalText');
        var actionTg = $('buyModalAction');
        var actionSite = $('buyModalActionSite');
        if (d.isPremium) {
            if (title) title.textContent = t('managePremium', 'Управление премиумом');
            if (text) text.textContent = t('managePremiumText', 'Ваш премиум аккаунт активен. Продлить премиум или получить поддержку:');
            if (actionTg) actionTg.textContent = t('manageTelegram', 'Управление в Telegram');
            if (actionSite) {
                actionSite.textContent = t('manageOnSite', 'Управление на сайте');
                actionSite.href = siteUrl('manage_premium');
            }
        } else {
            if (title) title.textContent = t('buyModalTitle', 'Купить премиум');
            if (text) text.textContent = t('buyModalText', '');
            if (actionTg) actionTg.textContent = t('buyModalAction', 'Купить через Telegram');
            if (actionSite) {
                actionSite.textContent = t('buyModalActionSite', 'Купить на сайте');
                actionSite.href = siteUrl('premium_tab_buy');
            }
        }
        openModal('buyPremiumModal');
    });
});

// ═══ VERSION ═══
if (versionSpan) {
    chrome.runtime.sendMessage({ action: "getVersion" }, res => {
        // [v2.6.5 audit] lastError read (suppress «Unchecked runtime.lastError» warning)
        if (chrome.runtime.lastError) return;
        if (res && res.version) versionSpan.textContent = 'v'+res.version;
    });
}

// [v2.6.5] Синхронизируем TG-ссылки в HTML с константами TG_URLS.
// HTML содержит те же URL как fallback; если бот переедет – правим TG_URLS
// в начале этого файла, HTML обновим при следующем релизе.
(function syncTgLinks(){
    var webLinks = ['premiumTrialHint', 'buyModalActionWeb'];
    webLinks.forEach(function(id){ var e = $(id); if (e) e.href = TG_URLS.web; });
    var directLinks = ['buyModalAction'];
    directLinks.forEach(function(id){ var e = $(id); if (e) e.href = TG_URLS.direct; });
})();

// [v2.7.6 audit Pass6] Event delegation для remove-buttons в exclusions/auto-enable.
// Раньше renderExclList/renderAutoEnableList добавлял per-item addEventListener при
// каждом render – listeners аккумулировались на старых DOM-нодах перед .innerHTML
// очисткой контейнера. Single delegation на permanent container фиксит leak.
(function attachListItemDelegation(){
    ['blacklistItems', 'whitelistItems'].forEach(function(id){
        var c = $(id); if (!c) return;
        c.addEventListener('click', function(e){
            var t = e.target; if (!t) return;
            var btn = (typeof t.closest === 'function') ? t.closest('.remove-excl') : null;
            if (!btn || !c.contains(btn)) return;
            // [v2.8.1 audit] dataset.domain (не idx) – symmetric с auto-enable.
            removeExclItem(btn.dataset.list, btn.dataset.domain);
        });
    });
    // [v2.8.1 audit] FIX: контейнер реально называется `autoEnableList` (см. popup.html L599).
    // С 2.7.6 (Pass6 рефакторинг) делегирование слушало несуществующий `autoEnableItems` →
    // $() возвращал null, addEventListener никогда не attach'ился, клик «✕» ничего не удалял.
    // Регрессия жила 5 релизов (2.7.6 → 2.8.0). Параллельно перешли на data-domain
    // (см. renderAutoEnableList) – это устраняет lost-update race по индексам.
    var aeC = $('autoEnableList');
    if (aeC) aeC.addEventListener('click', function(e){
        var t = e.target; if (!t) return;
        var btn = (typeof t.closest === 'function') ? t.closest('.remove-excl') : null;
        if (!btn || !aeC.contains(btn)) return;
        removeAutoEnableItem(btn.dataset.domain);
    });
})();

});
