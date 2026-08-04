// [v2.8.0] update_page.js – Premium-upsell page logic.
// Language sources (in priority): chrome.storage.local.language → chrome.i18n.getUILanguage() → 'en'.
// 7 поддерживаемых языков (как в premium-upsell.html): ru, en, zh, es, de, fr, pt.
// Цены тянутся с /AnonVPN/plans-public.php (single source: config/plans.json + future-block).

(function(){
    var SUPPORTED = ['ru','en','zh','es','de','fr','pt'];
    var L = {
        ru: {
            brandTag: 'Premium',
            whyLabel: 'Почему Вы здесь',
            whyReason1: 'AnonVPN обновился до новой версии',
            whyReason2: 'Вы пользуетесь бесплатной версией. Эта страница открывается у пользователей без Premium при каждом обновлении',
            whyReason3: 'ЭТО НЕ РЕКЛАМА',
            heroTitle: 'Безлимитный VPN без ограничений',
            heroSub: 'Откройте все возможности расширения. Без ограничений по времени, без переполненных серверов, без рекламы и трекеров.',
            buyBtn: 'Активировать Premium',
            heroPriceTmpl: 'от {price} {currency}',
            heroPriceLoading: 'тариф',
            heroTrialPreLabel: 'Или попробуйте бесплатно',
            heroTrialHeadline: '3 дня Premium – без карты, без кодов',
            featuresTitle: 'Что входит в Premium',
            feat1Name: 'Безлимит времени', feat1Desc: 'Бесплатные сессии – 60 минут. Premium – без таймера. Сидите часами, никаких принудительных переподключений.',
            feat2Name: 'Premium-серверы', feat2Desc: 'Отдельная сеть с меньшей нагрузкой. Скорость выше, задержка ниже, перебои реже. Также есть доступ к перегруженным бесплатным серверам.',
            feat3Name: 'Блокировка рекламы', feat3Desc: 'Обширный фильтр против рекламы и трекеров – большинство популярных рекламных сетей и аналитики не доходит до браузера.',
            feat4Name: 'Авто-включение', feat4Desc: 'Указали любимые сайты – VPN сам включается, как только их открываете. Сворачивается на остальном трафике.',
            feat5Name: 'Цветовые темы', feat5Desc: 'Меняйте оформление под себя. Для тех, кому базовая палитра уже надоела.',
            feat6Name: 'Резервная копия настроек', feat6Desc: 'Экспорт-импорт списка серверов, фильтров сайтов, тем. Перенос в другой браузер за пару кликов.',
            ctaTitleTmpl: 'Premium от {price} {currency}',
            ctaTitleLoading: 'Premium-доступ',
            ctaSub: 'От 3 дней до года. Отмена в любой момент.',
            ctaFineprint: 'Без автопродления по умолчанию. Без скрытых комиссий.',
            trialTitle: '3 дня Premium бесплатно',
            trialText: 'Один клик внутри расширения. Без регистрации, без карты, без кодов. Пробный период выдаётся один раз на устройство.',
            trialStep1: 'Откройте расширение AnonVPN',
            trialStep2: 'Перейдите на вкладку «Премиум»',
            trialStep3: 'Нажмите жёлтую кнопку «🎁 Получить 3 дня Premium бесплатно»',
            openExt: 'Открыть расширение',
            openExtHint: 'Если кнопка не сработала – кликните на иконку AnonVPN в панели браузера.',
            fullFaq: 'FAQ', privacy: 'Политика конфиденциальности'
        },
        en: {
            brandTag: 'Premium',
            whyLabel: 'Why are you here',
            whyReason1: 'AnonVPN was updated to a new version',
            whyReason2: 'You are on the free plan. This page opens for free users at every update',
            whyReason3: 'THIS IS NOT AN AD',
            heroTitle: 'Unlimited VPN, no restrictions',
            heroSub: 'Unlock all extension features. No time limits, no overcrowded servers, no ads or trackers.',
            buyBtn: 'Activate Premium',
            heroPriceTmpl: 'from {price} {currency}',
            heroPriceLoading: 'plan',
            heroTrialPreLabel: 'Or try for free',
            heroTrialHeadline: '3 days Premium – no card, no codes',
            featuresTitle: "What's in Premium",
            feat1Name: 'Unlimited time', feat1Desc: 'Free sessions – 60 minutes. Premium – no timer. Stay connected for hours, no forced reconnects.',
            feat2Name: 'Premium servers', feat2Desc: 'Separate network with lower load. Higher speed, lower ping, fewer disconnects. Plus access to busy free servers.',
            feat3Name: 'Ad blocker', feat3Desc: 'Extensive filter against ads and trackers – most popular ad networks and analytics never reach your browser.',
            feat4Name: 'Auto-enable', feat4Desc: 'Set favorite sites – VPN turns on automatically when you open them. Stays off for everything else.',
            feat5Name: 'Color themes', feat5Desc: 'Customize the look. For those tired of the default palette.',
            feat6Name: 'Settings backup', feat6Desc: 'Export and import server list, site filters, themes. Transfer to another browser in a couple of clicks.',
            ctaTitleTmpl: 'Plans from {price} {currency}',
            ctaTitleLoading: 'Premium plans',
            ctaSub: 'From 3 days to a year. Cancel any time.',
            ctaFineprint: 'No auto-renewal by default. No hidden fees.',
            trialTitle: '3 days Premium free',
            trialText: 'One click inside the extension. No signup, no card, no codes. Trial is one-per-device.',
            trialStep1: 'Open the AnonVPN extension',
            trialStep2: 'Go to the "Premium" tab',
            trialStep3: 'Click the yellow "🎁 Get 3 days Premium free" button',
            openExt: 'Open extension',
            openExtHint: 'If the button does nothing – click the AnonVPN icon in the browser toolbar.',
            fullFaq: 'FAQ', privacy: 'Privacy policy'
        },
        zh: {
            brandTag: 'Premium',
            whyLabel: '您为何在此',
            whyReason1: 'AnonVPN 已更新到新版本',
            whyReason2: '您使用的是免费版。每次更新时，此页面会向免费用户打开',
            whyReason3: '这不是广告',
            heroTitle: '无限制 VPN，无任何限制',
            heroSub: '解锁所有扩展功能。无时间限制，无过载服务器，无广告和追踪器。',
            buyBtn: '激活 Premium',
            heroPriceTmpl: '起价 {price} {currency}',
            heroPriceLoading: '套餐',
            heroTrialPreLabel: '或免费试用',
            heroTrialHeadline: '3 天 Premium – 无需信用卡，无需代码',
            featuresTitle: 'Premium 包含内容',
            feat1Name: '无限时长', feat1Desc: '免费会话 60 分钟。Premium 无计时器。连续使用数小时，无强制重连。',
            feat2Name: 'Premium 服务器', feat2Desc: '独立网络，负载更低。速度更快，ping 更低，断线更少。还可访问繁忙的免费服务器。',
            feat3Name: '广告拦截', feat3Desc: '强大的广告和追踪器过滤器 – 主流广告网络和分析工具均无法到达浏览器。',
            feat4Name: '自动启用', feat4Desc: '设置收藏网站 – 打开时 VPN 自动开启。其他流量保持关闭。',
            feat5Name: '颜色主题', feat5Desc: '自定义外观。适合厌倦默认配色的用户。',
            feat6Name: '设置备份', feat6Desc: '导出和导入服务器列表、网站过滤器、主题。几次点击即可迁移到其他浏览器。',
            ctaTitleTmpl: '套餐起价 {price} {currency}',
            ctaTitleLoading: 'Premium 套餐',
            ctaSub: '从 3 天到 1 年。可随时取消。',
            ctaFineprint: '默认不自动续费。无隐藏费用。',
            trialTitle: '3 天 Premium 免费',
            trialText: '在扩展内一键激活。无需注册、无需卡、无需代码。试用每台设备仅一次。',
            trialStep1: '打开 AnonVPN 扩展',
            trialStep2: '切换到「Premium」标签',
            trialStep3: '点击黄色按钮「🎁 获取 3 天免费 Premium」',
            openExt: '打开扩展',
            openExtHint: '如果按钮无效 – 请点击浏览器工具栏中的 AnonVPN 图标。',
            fullFaq: '常见问题', privacy: '隐私政策'
        },
        es: {
            brandTag: 'Premium',
            whyLabel: 'Por qué estás aquí',
            whyReason1: 'AnonVPN se actualizó a una nueva versión',
            whyReason2: 'Usas la versión gratuita. Esta página se abre para usuarios gratuitos en cada actualización',
            whyReason3: 'ESTO NO ES PUBLICIDAD',
            heroTitle: 'VPN ilimitado sin restricciones',
            heroSub: 'Desbloquea todas las funciones. Sin límites de tiempo, sin servidores saturados, sin anuncios ni rastreadores.',
            buyBtn: 'Activar Premium',
            heroPriceTmpl: 'desde {price} {currency}',
            heroPriceLoading: 'plan',
            heroTrialPreLabel: 'O pruébalo gratis',
            heroTrialHeadline: '3 días Premium – sin tarjeta, sin códigos',
            featuresTitle: 'Qué incluye Premium',
            feat1Name: 'Tiempo ilimitado', feat1Desc: 'Sesiones gratuitas – 60 minutos. Premium – sin temporizador. Permanece conectado durante horas sin reconexiones forzadas.',
            feat2Name: 'Servidores Premium', feat2Desc: 'Red separada con menor carga. Mayor velocidad, menor ping, menos desconexiones. Acceso a servidores gratuitos saturados.',
            feat3Name: 'Bloqueador de anuncios', feat3Desc: 'Filtro extenso contra anuncios y rastreadores – la mayoría de redes publicitarias no llega al navegador.',
            feat4Name: 'Activación automática', feat4Desc: 'Configura sitios favoritos – el VPN se activa solo al abrirlos. Se desactiva para el resto del tráfico.',
            feat5Name: 'Temas de color', feat5Desc: 'Personaliza la apariencia. Para quienes se aburrieron de la paleta predeterminada.',
            feat6Name: 'Copia de seguridad', feat6Desc: 'Exporta e importa lista de servidores, filtros de sitios, temas. Transfiere a otro navegador en un par de clics.',
            ctaTitleTmpl: 'Planes desde {price} {currency}',
            ctaTitleLoading: 'Planes Premium',
            ctaSub: 'De 3 días a un año. Cancela cuando quieras.',
            ctaFineprint: 'Sin renovación automática por defecto. Sin comisiones ocultas.',
            trialTitle: '3 días Premium gratis',
            trialText: 'Un clic dentro de la extensión. Sin registro, sin tarjeta, sin códigos. Prueba uno por dispositivo.',
            trialStep1: 'Abre la extensión AnonVPN',
            trialStep2: 'Ve a la pestaña «Premium»',
            trialStep3: 'Haz clic en el botón amarillo «🎁 Obtener 3 días Premium gratis»',
            openExt: 'Abrir extensión',
            openExtHint: 'Si el botón no funciona – haz clic en el icono de AnonVPN en la barra del navegador.',
            fullFaq: 'FAQ', privacy: 'Política de privacidad'
        },
        de: {
            brandTag: 'Premium',
            whyLabel: 'Warum sind Sie hier',
            whyReason1: 'AnonVPN wurde auf eine neue Version aktualisiert',
            whyReason2: 'Sie nutzen die kostenlose Version. Diese Seite öffnet sich für kostenlose Nutzer bei jedem Update',
            whyReason3: 'DAS IST KEINE WERBUNG',
            heroTitle: 'Unbegrenztes VPN ohne Einschränkungen',
            heroSub: 'Schalten Sie alle Funktionen frei. Keine Zeitlimits, keine überfüllten Server, keine Werbung oder Tracker.',
            buyBtn: 'Premium aktivieren',
            heroPriceTmpl: 'ab {price} {currency}',
            heroPriceLoading: 'Tarif',
            heroTrialPreLabel: 'Oder kostenlos testen',
            heroTrialHeadline: '3 Tage Premium – ohne Karte, ohne Codes',
            featuresTitle: 'Was Premium beinhaltet',
            feat1Name: 'Unbegrenzte Zeit', feat1Desc: 'Kostenlose Sitzungen – 60 Minuten. Premium – kein Timer. Stundenlang verbunden bleiben, keine erzwungenen Neuverbindungen.',
            feat2Name: 'Premium-Server', feat2Desc: 'Separates Netzwerk mit geringerer Auslastung. Höhere Geschwindigkeit, niedrigerer Ping, weniger Unterbrechungen. Plus Zugriff auf ausgelastete kostenlose Server.',
            feat3Name: 'Werbeblocker', feat3Desc: 'Umfangreicher Filter gegen Werbung und Tracker – die meisten populären Werbenetzwerke erreichen den Browser nicht.',
            feat4Name: 'Auto-Aktivierung', feat4Desc: 'Lieblingsseiten festgelegt – VPN wird automatisch aktiviert. Bleibt für anderen Traffic deaktiviert.',
            feat5Name: 'Farbthemen', feat5Desc: 'Passen Sie das Aussehen an. Für alle, denen die Standardpalette langweilig wurde.',
            feat6Name: 'Einstellungssicherung', feat6Desc: 'Server-Liste, Site-Filter und Themen exportieren/importieren. Übertragung in einen anderen Browser mit wenigen Klicks.',
            ctaTitleTmpl: 'Tarife ab {price} {currency}',
            ctaTitleLoading: 'Premium-Tarife',
            ctaSub: 'Von 3 Tagen bis 1 Jahr. Jederzeit kündbar.',
            ctaFineprint: 'Standardmäßig keine automatische Verlängerung. Keine versteckten Gebühren.',
            trialTitle: '3 Tage Premium kostenlos',
            trialText: 'Ein Klick in der Erweiterung. Ohne Registrierung, ohne Karte, ohne Codes. Testphase einmal pro Gerät.',
            trialStep1: 'Öffnen Sie die AnonVPN-Erweiterung',
            trialStep2: 'Gehen Sie zum Tab „Premium"',
            trialStep3: 'Klicken Sie den gelben Button „🎁 3 Tage Premium kostenlos"',
            openExt: 'Erweiterung öffnen',
            openExtHint: 'Wenn der Button nichts tut – klicken Sie auf das AnonVPN-Symbol in der Browser-Symbolleiste.',
            fullFaq: 'FAQ', privacy: 'Datenschutzerklärung'
        },
        fr: {
            brandTag: 'Premium',
            whyLabel: 'Pourquoi êtes-vous ici',
            whyReason1: 'AnonVPN a été mis à jour vers une nouvelle version',
            whyReason2: 'Vous utilisez la version gratuite. Cette page s\'ouvre pour les utilisateurs gratuits à chaque mise à jour',
            whyReason3: "CECI N'EST PAS UNE PUBLICITÉ",
            heroTitle: 'VPN illimité sans restrictions',
            heroSub: "Débloquez toutes les fonctionnalités. Pas de limite de temps, pas de serveurs surchargés, pas de publicités ni de trackers.",
            buyBtn: 'Activer Premium',
            heroPriceTmpl: 'à partir de {price} {currency}',
            heroPriceLoading: 'forfait',
            heroTrialPreLabel: 'Ou essayez gratuitement',
            heroTrialHeadline: '3 jours Premium – sans carte, sans codes',
            featuresTitle: 'Ce qui est inclus dans Premium',
            feat1Name: 'Temps illimité', feat1Desc: 'Sessions gratuites – 60 minutes. Premium – sans minuteur. Restez connecté pendant des heures, sans reconnexions forcées.',
            feat2Name: 'Serveurs Premium', feat2Desc: 'Réseau séparé avec une charge plus faible. Vitesse supérieure, ping plus bas, moins de déconnexions. Accès aux serveurs gratuits saturés.',
            feat3Name: 'Bloqueur de publicités', feat3Desc: 'Filtre étendu contre la publicité et les traceurs – la plupart des réseaux publicitaires populaires n\'atteignent pas le navigateur.',
            feat4Name: 'Activation automatique', feat4Desc: 'Sites favoris configurés – le VPN s\'active automatiquement à leur ouverture. Reste désactivé pour le reste du trafic.',
            feat5Name: 'Thèmes de couleur', feat5Desc: 'Personnalisez l\'apparence. Pour ceux fatigués de la palette par défaut.',
            feat6Name: 'Sauvegarde des paramètres', feat6Desc: 'Exporter et importer la liste de serveurs, filtres de sites, thèmes. Transfert vers un autre navigateur en quelques clics.',
            ctaTitleTmpl: 'Forfaits à partir de {price} {currency}',
            ctaTitleLoading: 'Forfaits Premium',
            ctaSub: 'De 3 jours à 1 an. Résiliation à tout moment.',
            ctaFineprint: 'Pas de renouvellement automatique par défaut. Pas de frais cachés.',
            trialTitle: '3 jours Premium gratuits',
            trialText: 'Un clic dans l\'extension. Sans inscription, sans carte, sans codes. Essai un par appareil.',
            trialStep1: 'Ouvrez l\'extension AnonVPN',
            trialStep2: 'Allez à l\'onglet « Premium »',
            trialStep3: 'Cliquez sur le bouton jaune « 🎁 Obtenir 3 jours Premium gratuits »',
            openExt: 'Ouvrir l\'extension',
            openExtHint: 'Si le bouton ne fonctionne pas – cliquez sur l\'icône AnonVPN dans la barre du navigateur.',
            fullFaq: 'FAQ', privacy: 'Politique de confidentialité'
        },
        pt: {
            brandTag: 'Premium',
            whyLabel: 'Por que você está aqui',
            whyReason1: 'AnonVPN foi atualizado para uma nova versão',
            whyReason2: 'Você usa a versão gratuita. Esta página abre para usuários gratuitos a cada atualização',
            whyReason3: 'ISTO NÃO É PUBLICIDADE',
            heroTitle: 'VPN ilimitado sem restrições',
            heroSub: 'Desbloqueie todos os recursos da extensão. Sem limites de tempo, sem servidores sobrecarregados, sem anúncios ou rastreadores.',
            buyBtn: 'Ativar Premium',
            heroPriceTmpl: 'a partir de {price} {currency}',
            heroPriceLoading: 'plano',
            heroTrialPreLabel: 'Ou experimente grátis',
            heroTrialHeadline: '3 dias Premium – sem cartão, sem códigos',
            featuresTitle: 'O que está incluído no Premium',
            feat1Name: 'Tempo ilimitado', feat1Desc: 'Sessões gratuitas – 60 minutos. Premium – sem timer. Fique conectado por horas, sem reconexões forçadas.',
            feat2Name: 'Servidores Premium', feat2Desc: 'Rede separada com menor carga. Maior velocidade, menor ping, menos desconexões. Acesso a servidores gratuitos sobrecarregados.',
            feat3Name: 'Bloqueador de anúncios', feat3Desc: 'Filtro extenso contra anúncios e rastreadores – a maioria das redes publicitárias populares não chega ao navegador.',
            feat4Name: 'Ativação automática', feat4Desc: 'Sites favoritos configurados – o VPN ativa automaticamente quando você os abre. Fica desativado para o resto do tráfego.',
            feat5Name: 'Temas de cor', feat5Desc: 'Personalize a aparência. Para quem está cansado da paleta padrão.',
            feat6Name: 'Backup de configurações', feat6Desc: 'Exporte e importe a lista de servidores, filtros de sites, temas. Transferência para outro navegador em alguns cliques.',
            ctaTitleTmpl: 'Planos a partir de {price} {currency}',
            ctaTitleLoading: 'Planos Premium',
            ctaSub: 'De 3 dias a 1 ano. Cancele a qualquer momento.',
            ctaFineprint: 'Sem renovação automática por padrão. Sem taxas ocultas.',
            trialTitle: '3 dias Premium grátis',
            trialText: 'Um clique dentro da extensão. Sem registro, sem cartão, sem códigos. Teste único por dispositivo.',
            trialStep1: 'Abra a extensão AnonVPN',
            trialStep2: 'Vá para a aba «Premium»',
            trialStep3: 'Clique no botão amarelo «🎁 Obter 3 dias Premium grátis»',
            openExt: 'Abrir extensão',
            openExtHint: 'Se o botão não funcionar – clique no ícone do AnonVPN na barra do navegador.',
            fullFaq: 'FAQ', privacy: 'Política de privacidade'
        }
    };

    function detectLangFromUI() {
        try {
            var raw = (chrome.i18n && chrome.i18n.getUILanguage) ? chrome.i18n.getUILanguage() : 'en';
            var base = raw.toLowerCase().split(/[-_]/)[0];
            return SUPPORTED.indexOf(base) >= 0 ? base : 'en';
        } catch { return 'en'; }
    }

    function el(id){ return document.getElementById(id); }
    function setText(id, txt){ var e = el(id); if (e) e.textContent = txt; }

    var CURRENCY_SYMBOLS = { 'RUB': '₽', 'USD': '$', 'EUR': '€' };
    function fmtPrice(price, currency) {
        var sym = CURRENCY_SYMBOLS[currency] || currency || '';
        var n = Math.round(Number(price) || 0);
        var s = String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        return s + ' ' + sym;
    }

    var t = null; // current translations

    function updateLangSwitchActive(lang){
        var btns = document.querySelectorAll('.lang-switch button[data-lang-btn]');
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].getAttribute('data-lang-btn') === lang) btns[i].classList.add('active');
            else btns[i].classList.remove('active');
        }
    }

    function render(lang){
        document.documentElement.lang = lang;
        t = L[lang] || L.en;
        updateLangSwitchActive(lang);
        setText('brandTag', t.brandTag);
        setText('whyLabel', t.whyLabel);
        setText('whyReason1', t.whyReason1);
        setText('whyReason2', t.whyReason2);
        setText('whyReason3', t.whyReason3);
        setText('heroTitle', t.heroTitle);
        setText('heroSub', t.heroSub);
        setText('buyBtnHero', t.buyBtn);
        setText('heroPrice', t.heroPriceLoading);
        setText('heroTrialPreLabel', t.heroTrialPreLabel);
        setText('heroTrialHeadline', t.heroTrialHeadline);
        setText('featuresTitle', t.featuresTitle);
        for (var i = 1; i <= 6; i++) {
            setText('feat' + i + 'Name', t['feat' + i + 'Name']);
            setText('feat' + i + 'Desc', t['feat' + i + 'Desc']);
        }
        setText('ctaTitle', t.ctaTitleLoading);
        setText('ctaSub', t.ctaSub);
        setText('buyBtnMain', t.buyBtn);
        setText('ctaFineprint', t.ctaFineprint);
        setText('trialTitle', t.trialTitle);
        setText('trialText', t.trialText);
        setText('trialStep1', t.trialStep1);
        setText('trialStep2', t.trialStep2);
        setText('trialStep3', t.trialStep3);
        setText('openExtBtn', t.openExt);
        setText('openExtHint', t.openExtHint);
        setText('fullFaqLink', t.fullFaq);
        setText('privacyLink', t.privacy);
        // Если уже подгрузили цены – обновить
        if (cachedPrice) applyPrice(cachedPrice);
    }

    var cachedPrice = null;
    function applyPrice(p){
        if (!t || !p) return;
        var priceStr = fmtPrice(p.min_price, p.currency);
        var heroPriceTxt = (t.heroPriceTmpl || 'from {price} {currency}').replace('{price} {currency}', priceStr);
        var ctaTitleTxt = (t.ctaTitleTmpl || 'Plans from {price} {currency}').replace('{price} {currency}', priceStr);
        setText('heroPrice', heroPriceTxt);
        setText('ctaTitle', ctaTitleTxt);
    }

    // Buy buttons
    function openBuy(){
        var v = (chrome.runtime.getManifest && chrome.runtime.getManifest().version) || '';
        var url = 'https://balancing.apiget.ru/AnonVPN/lk/premium-access-payment/?utm_source=ext&utm_medium=update_page&utm_campaign=v' + v;
        try { chrome.tabs.create({ url: url }).catch(function(){}); }
        catch(e) { window.open(url, '_blank'); }
    }
    var btn1 = el('buyBtnHero'); if (btn1) btn1.addEventListener('click', openBuy);
    var btn2 = el('buyBtnMain'); if (btn2) btn2.addEventListener('click', openBuy);

    // Open extension
    var openExtBtn = el('openExtBtn');
    if (openExtBtn) {
        openExtBtn.addEventListener('click', function(){
            try { if (chrome.action && chrome.action.openPopup) chrome.action.openPopup().catch(function(){}); } catch(e) {}
        });
    }

    // Lang-switch buttons – клик меняет язык только для этой страницы (НЕ пишем в storage,
    // как в premium-upsell.js – выбор юзера в popup'е остаётся неизменным).
    var langBtns = document.querySelectorAll('.lang-switch button[data-lang-btn]');
    for (var li = 0; li < langBtns.length; li++) {
        (function(btn){
            btn.addEventListener('click', function(){
                var L_ = btn.getAttribute('data-lang-btn');
                if (SUPPORTED.indexOf(L_) >= 0) render(L_);
            });
        })(langBtns[li]);
    }

    // Приоритет языка: 1) URL ?lang= (deep-link), 2) chrome.storage.local.language (popup),
    // 3) chrome.i18n.getUILanguage() (system), 4) 'en' fallback.
    function getUrlLang(){
        try {
            var p = new URLSearchParams(window.location.search);
            var u = (p.get('lang') || '').toLowerCase().split(/[-_]/)[0];
            return SUPPORTED.indexOf(u) >= 0 ? u : null;
        } catch { return null; }
    }
    function pickLang(stored){
        var url = getUrlLang();
        if (url) return url;
        if (typeof stored === 'string' && SUPPORTED.indexOf(stored) >= 0) return stored;
        return detectLangFromUI();
    }
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(['language'], function(data){
            render(pickLang(data && data.language));
        });
    } else {
        render(detectLangFromUI());
    }

    // FAQ-ссылка в footer: всегда передаёт текущий язык в help.html (deep-link)
    function syncFaqLink(){
        var a = el('fullFaqLink');
        if (a) a.href = 'help.html?lang=' + encodeURIComponent(document.documentElement.lang || 'en') + '#faq';
    }
    // Перевешиваем после render и при смене языка (через MutationObserver на html lang)
    var observer = new MutationObserver(syncFaqLink);
    try { observer.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] }); } catch {}
    syncFaqLink();

    // Цены – единый источник на сервере (config/plans.json через plans-public.php).
    // [v3.0.4] apiget.ru убран: его нет в CSP connect-src (страничный fetch → блок) + это старая
    // машина, бэкенд на VPS. Failover по whitelisted API-доменам (те же, что в SW apiFetch).
    var PLANS_DOMAINS = ['https://api.bot-support.ru','https://api.unkill.ru','https://api.sibirlife.ru','https://api.1150.ru','https://api.foofle.ru'];
    (function tryPlans(i){
        if (i >= PLANS_DOMAINS.length) return; // все домены не ответили — placeholder из render() остаётся
        fetch(PLANS_DOMAINS[i] + '/AnonVPN/plans-public.php', {
            cache: 'no-store',
            signal: AbortSignal.timeout ? AbortSignal.timeout(8000) : undefined
        }).then(function(r){
            if (!r.ok) throw new Error('http ' + r.status);
            return r.json();
        }).then(function(data){
            if (!data || !data.ok || typeof data.min_price !== 'number') return;
            cachedPrice = { min_price: data.min_price, currency: data.currency };
            applyPrice(cachedPrice);
        }).catch(function(){
            tryPlans(i + 1); // следующий домен
        });
    })(0);
})();
