// AnonVPN – help.html [v3.0.2]
// Мультиязычность (ru/en/zh/es/de/fr/pt): показ активного языка через body[data-app-lang]
// (CSS прячет неактивные data-lang). Начальный язык – из настроек расширения (chrome.storage
// language), иначе из языка браузера, иначе ru. Кнопки в шапке переключают page-scoped
// (НЕ меняют язык расширения). Плюс плавное появление секций (fade-up).
// Внешний скрипт: extension CSP script-src 'self'.
(function () {
  'use strict';
  var LANGS = ['ru', 'en', 'zh', 'es', 'de', 'fr', 'pt'];
  var TITLES = {
    ru: 'AnonVPN – как пользоваться',
    en: 'AnonVPN – how to use',
    zh: 'AnonVPN – 使用指南',
    es: 'AnonVPN – cómo usar',
    de: 'AnonVPN – Anleitung',
    fr: 'AnonVPN – comment utiliser',
    pt: 'AnonVPN – como usar'
  };
  function applyLang(lang) {
    if (LANGS.indexOf(lang) < 0) lang = 'ru';
    document.body.setAttribute('data-app-lang', lang);
    document.documentElement.lang = lang;
    if (TITLES[lang]) { try { document.title = TITLES[lang]; } catch (e) {} }
    var btns = document.querySelectorAll('.lang-switch [data-set-lang]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('active', btns[i].getAttribute('data-set-lang') === lang);
    }
  }
  function navLang() {
    var n = String(navigator.language || 'ru').slice(0, 2).toLowerCase();
    return LANGS.indexOf(n) >= 0 ? n : 'ru';
  }
  function pickInitialLang(cb) {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(['language'], function (d) {
          if (chrome.runtime && chrome.runtime.lastError) { cb(navLang()); return; }
          var l = (d && typeof d.language === 'string') ? d.language : '';
          cb(LANGS.indexOf(l) >= 0 ? l : navLang());
        });
        return;
      }
    } catch (e) {}
    cb(navLang());
  }
  function reveal() {
    var els = document.querySelectorAll('.fade-up');
    if (!('IntersectionObserver' in window)) {
      for (var i = 0; i < els.length; i++) els[i].classList.add('visible');
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    for (var j = 0; j < els.length; j++) io.observe(els[j]);
  }
  function init() {
    var sw = document.querySelector('.lang-switch');
    if (sw) sw.addEventListener('click', function (e) {
      var b = (e.target && e.target.closest) ? e.target.closest('[data-set-lang]') : null;
      if (b) applyLang(b.getAttribute('data-set-lang'));
    });
    pickInitialLang(applyLang);
    reveal();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
