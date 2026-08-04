async function cdn_fetch_switches() {
    var url = 'https://blockify.b-cdn.net/switches190.json';

    fetch(url, { cache: 'no-cache' })
        .then(response => {
            if (!response.ok) {
                console.error(response);
            }
            return response.json();
        })
        .then(data => {
            if (data && data["yt_injection"]) {
                chrome.storage.local.get(['switches'], (result) => {
                    var old_switches = result.switches;
                    if (!old_switches || JSON.stringify(old_switches) !== JSON.stringify(data)) {
                        chrome.storage.local.set({ "switches": data });
                    }
                });
            }
        })
        .catch(error => {
            console.error('Fetch error:', error.message);
        });
};

if (document.readyState === 'complete') {
    cdn_fetch_switches();
} else {
    window.addEventListener("load", cdn_fetch_switches);
}