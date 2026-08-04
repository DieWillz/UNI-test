if (typeof window !== 'undefined' && window.XMLHttpRequest && typeof pruneHuluMPDXmlAds === 'function') {
    const origOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = new Proxy(origOpen, {
        apply: function(target, thisArg, argumentsList) {
            const url = (typeof argumentsList[1] === 'string') ? argumentsList[1] : '';
            const isHuluMPD = url.includes('hulustream.com') && url.includes('.mpd');
            if (isHuluMPD) {
                thisArg.addEventListener('readystatechange', function() {
                    console.log("testing inside addeventlistener")
                    if (this.readyState === 4 && this.status === 200) {
                        const contentType = this.getResponseHeader && this.getResponseHeader('content-type') || '';
                        if (/application\/(xml|dash\+xml)|text\/xml/i.test(contentType)) {
                            let originalText = this.responseText;
                            let prunedText = pruneHuluMPDXmlAds(originalText);
                            if (prunedText !== originalText) {
                                try {
                                    Object.defineProperty(this, 'response', { value: prunedText });
                                    Object.defineProperty(this, 'responseText', { value: prunedText });
                                } catch (e) {
                                    // ignore
                                }
                            }
                        }
                    }
                });
            }
            return Reflect.apply(target, thisArg, argumentsList);
        }
    });
}

function pruneHuluMPDXmlAds(xmlString) {
    if (typeof xmlString !== 'string' || !/^\s*</.test(xmlString) || !/>\s*$/.test(xmlString)) return xmlString;
    try {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlString, "application/xml");
        const periods = xmlDoc.querySelectorAll('Period[id^="Ad"], Period[id^="ad"]');
        periods.forEach(node => node.parentNode.removeChild(node));
        const baseUrls = xmlDoc.querySelectorAll('BaseURL');
        baseUrls.forEach(node => {
            if (node.textContent.includes('/ads-')) {
                node.parentNode.removeChild(node);
            }
        });
        const mpd = xmlDoc.querySelector('MPD');
        if (mpd && mpd.hasAttribute('mediaPresentationDuration')) {
            mpd.removeAttribute('mediaPresentationDuration');
        }
        const allPeriods = xmlDoc.querySelectorAll('Period[start]');
        allPeriods.forEach(node => node.removeAttribute('start'));
        const serializer = new XMLSerializer();
        return serializer.serializeToString(xmlDoc);
    } catch (e) {
        return xmlString;
    }
}


(function() {
    const adKeys = [
        "breaks",
        "pause_ads",
        "custom_breaks_data"
    ];

    function pruneAdsFromJson(obj) {
        if (!obj || typeof obj !== "object") return obj;
        for (const key of adKeys) {
            if (key in obj) {
                delete obj[key];
            }
        }
        for (const k in obj) {
            if (typeof obj[k] === "object") {
                obj[k] = pruneAdsFromJson(obj[k]);
            }
        }
        return obj;
    }
const origFetch = window.fetch;
window.fetch = function(...args) {
    return origFetch.apply(this, args).then(async response => {
        //  console.log("Fetch URL:", response.url);
        const url = response.url || (args[0] && args[0].url) || "";
        if (url.includes("hulu.com") && url.includes("/playlist")) {
            const cloned = response.clone();
            const contentType = response.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
                try {
                    const json = await cloned.json();
                    const pruned = pruneAdsFromJson(json);
                    return new Response(JSON.stringify(pruned), {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers
                    });
                } catch (e) {
                    return response;
                }
            }
            return response;
        } 
        return response;
    });
};
})();