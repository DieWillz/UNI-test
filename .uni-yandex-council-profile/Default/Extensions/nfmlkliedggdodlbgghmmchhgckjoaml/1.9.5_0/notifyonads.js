
function checker(o) {
    var one = document.querySelectorAll('[aria-label="Sponsored"]').length; //adfound
    var two = document.getElementsByClassName("ytp-ad-badge--clean-player").length; //adfound

    if (one > 0 || two > 0) {
        //either one, adfound
        //ping: algo does not work
        letusknow(0);
        return;
    }
    else {
        if (o < 6500) {
            window.nno = o + 500;
            setTimeout(function () {
                checker(window.nno);
            }, 500);
        }
        else {
            //time up, 5s
            //made it till here
            //ping: does work
            letusknow(1);
            return;
        }
    }
};

chrome.storage.local.get(['staticrules', 'exceptions', 'switches'], (result) => {
    var shouldInject = true;

    if (result && result.switches && result.switches.yt_injection == "disabled") {
        shouldInject = false;
    }

    if (result.staticrules === "disabled") {
        shouldInject = false;
    }

    if (result.exceptions && Array.isArray(result.exceptions)) {
        if (result.exceptions.includes('www.youtube.com') || result.exceptions.includes('youtube.com')) {
            shouldInject = false;
        }
    }

    // CSS bases ad blocking
    if (shouldInject) {
        if (document.readyState === 'complete') {
            pageloaded();
        } else {
            window.addEventListener("load", pageloaded);
        }
    }

    if (result && result.switches && result.switches.yt_mutify == "enabled") {
        mutify();
    }

});

function pageloaded() {
    document.body.setAttribute("bl-ext-enbld-hai-k-na", "T"); //controlled by exclusions
    checker(0); //tracking
};

async function letusknow(o) {
    var result = await chrome.storage.sync.get(["user_stat_uuid"]);
    var uuid = result["user_stat_uuid"];
    if (!uuid) {
        uuid = crypto.randomUUID() || "f7450bd0-5f20-4f1a-a34f-5ba8ce74a8e1";
    }

    if (uuid && o !== undefined && o !== null) {
        if (o == 0) {
            var data =
            {
                "user_id": uuid,
                "tag": "yt_ad_error"
            };
            eventping(data);
        }
        else if (o == 1) {
            var data =
            {
                "user_id": uuid,
                "tag": "yt_ad_success"
            };
            eventping(data);
        }
    }
};

function eventping(data) {
    // Send the data to the endpoint
    fetch('https://insights.getblockify.com/metrics', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
        .catch(error => {
            console.error('Error while sending data:', error);
        });
};

function mutify() {

    if (!document.body) {
        document.addEventListener('DOMContentLoaded', mutify);
        return;
    }

    // Function to handle ad detection and muting
    function handleAdStatus() {
        var ad = document.querySelector('.ad-showing');

        if (ad) {
            chrome.runtime.sendMessage({ muteTab: true });
        } else {
            chrome.runtime.sendMessage({ Unmute: true });
        }
    };

    // Initial check when the script runs
    handleAdStatus();

    // Create a MutationObserver to watch for DOM changes
    var adObserver = new MutationObserver((mutations) => {
        handleAdStatus();
    });

    // Configure and start the observer
    adObserver.observe(document.body, {
        childList: true, // Watch for changes to the direct children
        subtree: true,   // Watch for changes in the entire subtree
        attributes: true, // Watch for attribute changes
        attributeFilter: ['.ad-showing']
    });
};