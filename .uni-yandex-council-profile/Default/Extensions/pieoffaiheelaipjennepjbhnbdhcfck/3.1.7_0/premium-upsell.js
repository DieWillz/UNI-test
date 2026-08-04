// AnonVPN — Premium Upsell page
// Language switching: relies on CSS rules in help.css
// `[data-lang]{display:none}` + `html[lang=X] [data-lang=X]{display:revert}`.
// We only flip <html lang>; CSS handles visibility, no inline-style writes
// (CSP `style-src 'self'` compliant, no per-element loop).

(function() {
  var LANGS = ['ru','en','zh','es','de','fr','pt'];

  function detectLang() {
    try {
      var raw = (typeof chrome !== 'undefined' && chrome.i18n && chrome.i18n.getUILanguage)
        ? chrome.i18n.getUILanguage()
        : (navigator.language || 'en');
      var base = String(raw || 'en').toLowerCase().split(/[-_]/)[0];
      return LANGS.indexOf(base) >= 0 ? base : 'en';
    } catch { return 'en'; }
  }

  // [v2.7.5] Sync: set <html lang> before first paint so CSS-based language
  // gating shows the correct variant immediately. Script is loaded with
  // `defer`, so this runs once HTML parsing is done but before
  // DOMContentLoaded handlers in this same closure.
  // [v3.0.3 fix] До первого paint ставим body[data-app-lang] (новый help.css) + html lang,
  // чтобы не мелькала пустая страница. defer-скрипт: HTML распарсен, body уже есть.
  try { var _initLang = detectLang(); document.documentElement.lang = _initLang; if (document.body) document.body.setAttribute('data-app-lang', _initLang); } catch {}

  // [v2.5.9] НЕ пишем в chrome.storage.local.language — смена языка в upsell
  // применяется только к текущей странице, не трогает popup / help. На
  // следующем открытии язык восстановится из глобального popup-лэнга.
  function setLang(lang) {
    var displayLang = LANGS.indexOf(lang) >= 0 ? lang : 'en';
    // [v3.0.3 fix] help.css был переписан и гейтит [data-lang] через body[data-app-lang]
    // (а не html[lang], как раньше). Ставим ОБА (как help.js), иначе весь мультиязычный
    // контент остаётся display:none → страница пустая («где данные?»).
    try { document.body.setAttribute('data-app-lang', displayLang); } catch (e) {}
    document.documentElement.lang = displayLang;
    LANGS.forEach(function(l) {
      var btn = document.getElementById('setLang_' + l);
      if (btn) btn.classList.toggle('active', l === displayLang);
    });
  }

  function init() {
    // [v2.6.5] Пробрасываем исходный utm_medium из открывшего upsell CTA
    // в финальную ссылку «Купить на сайте». Так в БД виден сквозной путь,
    // а не один upsell_secondary.
    try {
      var siteBtn = document.getElementById('upsellSiteBuyBtn');
      if (siteBtn) {
        var params = new URLSearchParams(window.location.search);
        var orig = params.get('utm_medium') || 'upsell_direct';
        var v = '';
        try { v = (chrome.runtime.getManifest && chrome.runtime.getManifest().version) || ''; } catch {}
        var url = 'https://balancing.apiget.ru/AnonVPN/lk/premium-access-payment/'
                + '?utm_source=ext'
                + '&utm_medium=' + encodeURIComponent(orig + '_upsell')
                + '&utm_campaign=v' + v;
        siteBtn.href = url;
      }
    } catch {}

    LANGS.forEach(function(l) {
      var btn = document.getElementById('setLang_' + l);
      if (btn) btn.addEventListener('click', function() { setLang(l); });
    });

    try {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(['language'], function(data) {
          if (chrome.runtime && chrome.runtime.lastError) {
            setLang(detectLang());
            return;
          }
          var saved = data && data.language;
          var initial = LANGS.indexOf(saved) >= 0 ? saved : detectLang();
          setLang(initial);
        });
      } else {
        setLang(detectLang());
      }
    } catch {
      setLang(detectLang());
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
