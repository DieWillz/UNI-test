// Keepalive: maintains a port connection to the service worker
// This prevents SW from sleeping while VPN is active.
// [v2.6.5] setInterval ping убран — дублировал chrome.alarms(0.5min) в SW,
// а сам по себе долгоживущий port уже держит SW активным.
let port = null;

function connect() {
    // [v2.7.0 fix F52] Wrap в try/catch — при throw'ящем connect (manifest error,
    // permission revoked, SW crash) offscreen doc раньше тихо умирал без retry.
    try {
        port = chrome.runtime.connect({ name: 'keepalive' });
        port.onDisconnect.addListener(() => {
            // Reconnect if disconnected (SW restarted)
            port = null;
            setTimeout(connect, 1000);
        });
    } catch (e) {
        port = null;
        setTimeout(connect, 1000);
    }
}

// [v2.7.0 fix F52] Глобальный error trap — без него uncaught exception в offscreen
// убивает doc (no auto-restart в MV3), VPN keepalive ломается.
self.addEventListener('error', () => {});
self.addEventListener('unhandledrejection', () => {});

connect();
