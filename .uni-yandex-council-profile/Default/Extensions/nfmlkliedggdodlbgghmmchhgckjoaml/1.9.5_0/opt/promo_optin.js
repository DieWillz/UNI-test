/**
 * Promo Opt-in Popup JavaScript
 * =============================
 * Handles user interaction with the promotional feature opt-in popup.
 *
 * User Flow:
 * 1. User sees disclosure about what the feature does
 * 2. User must check the checkbox to enable "Yes, Activate" button
 * 3. User can click "No Thanks" or close button to opt out
 * 4. Preference is saved to chrome.storage.local
 *
 * Storage keys set:
 * - promo_autocomment_enabled: boolean - User's choice (true = opted in, false = opted out)
 *
 * Analytics events:
 * - promo_optin_yes: User opted in
 * - promo_optin_no: User opted out or dismissed
 *
 * @see support-blockify.html for the UI
 * @see yt_autocomment.js for the feature this enables
 */

if (document.readyState === 'loading') {
  // DOM is still loading, wait for the event
  document.addEventListener('DOMContentLoaded', init);
} else {
  // DOM is already loaded (interactive or complete), run immediately
  init();
}

function init()
{
    chrome.storage.local.set({ promo_optin_shown_: true });

    const supportToggle = document.getElementById('supportToggle');
    const firstVisitButtons = document.getElementById('firstVisitButtons');
    const returningVisitorUI = document.getElementById('returningVisitorUI');
    const dontCareBtn = document.getElementById('dontCareBtn');
    const supportBtn = document.getElementById('supportBtn');

    // Load and display actual ads blocked count
    loadAdsBlockedCount();

    // Check if promo_autocomment_enabled has been set before
    chrome.storage.local.get(['promo_autocomment_enabled'], function(result) {
        const isValueSet = result.promo_autocomment_enabled !== undefined;

        if (isValueSet) {
            // Returning visitor: show toggle UI
            firstVisitButtons.classList.add('none');
            returningVisitorUI.classList.remove('none');
            supportToggle.checked = result.promo_autocomment_enabled === true;
            updateCloseButtonVisibility();
        } else {
            // First-time visitor: show two buttons
            firstVisitButtons.classList.remove('none');
            returningVisitorUI.classList.add('none');
        }
    });

    // First visit: "I don't care" button - save preference and close
    dontCareBtn.addEventListener('click', function() {
        savePreference(false);
        trackOptIn(false);
        window.close();
    });

    // First visit: "Support Blockify" button
    supportBtn.addEventListener('click', function() {
        savePreference(true);
        trackOptIn(true);

        // Show thank you overlay (closes when user clicks "Got It!")
        const thankYouOverlay = document.getElementById('thankYouOverlay');
        thankYouOverlay.classList.remove('none');
    });

    // Fetch ads blocked count from storage and display it
    function loadAdsBlockedCount() {
        chrome.storage.local.get(['blockedCount', 'removedcount'], function(result) {
            const totalBlocked = (result.blockedCount || 0) + (result.removedcount || 0);
            const countElement = document.getElementById('adsBlockedCount');

            if (countElement) {
                if (totalBlocked > 0) {
                    // Format number with commas and add "+" suffix
                    countElement.textContent = formatNumber(totalBlocked) + '+';
                    // Calculate and display impact metrics
                    displayImpactMetrics(totalBlocked);
                } else {
                    // Fallback if no count available
                    countElement.textContent = 'many';
                    displayImpactMetrics(500); // Default estimate
                }
            }
        });
    }

    // Calculate and display impact metrics based on ads blocked
    function displayImpactMetrics(adsBlocked) {
        /**
         * Practical, conservative impact formulas:
         *
         * TIME SAVED:
         * - "blocked" events include different ad surfaces and durations
         * - many video ads are skippable at ~5s, while others are longer
         * - use a conservative blended estimate: 6 seconds per blocked ad
         *
         * ENERGY SAVED (Wh per ad):
         * Device power consumption during video ad playback:
         * - CPU/GPU for video decoding: ~200-400mW
         * - Display (already on): ~0 additional
         * - Network radio for streaming: ~100-200mW
         * - Total additional power for ad: ~400mW average
         *
         * Network infrastructure energy (data centers, routers, etc.):
         * - ~0.06 kWh per GB of data transferred (IEA estimate)
         * - 2 MB per ad = 0.002 GB × 0.06 kWh = 0.00012 kWh = 0.12 Wh
         *
         * Device energy per ad:
         * - 400mW × 12 seconds = 400mW × (12/3600)h = 0.00133 Wh ≈ 0.0013 Wh
         *
         * Total energy per ad: 0.12 + 0.0013 ≈ 0.12 Wh (network dominates)
         * Conservative estimate: 0.1 Wh per ad
         *
         * CO2 EMISSIONS SAVED:
         * - Global average grid intensity: ~475g CO2/kWh (IEA 2023)
         * - Per ad: 0.0001 kWh × 475g = 0.0475g CO2
         * - Rounded: 0.05g CO2 per ad
         *
         * For context:
         * - 1000 ads = 100 Wh = 0.1 kWh saved, 47.5g CO2 avoided
         * - 10,000 ads = 1 kWh saved, 475g CO2 avoided
         * - A tree absorbs ~21 kg CO2/year, so 44,000 ads ≈ 1 tree-year
         */

        const SECONDS_PER_AD = 6;
        const WH_PER_AD = 0.1;              // Watt-hours of energy saved per ad
        const GRAMS_CO2_PER_AD = 0.05;      // Grams of CO2 emissions avoided per ad

        // Time saved
        const secondsSaved = adsBlocked * SECONDS_PER_AD;
        const timeSavedElement = document.getElementById('timeSaved');
        if (timeSavedElement) {
            timeSavedElement.textContent = formatTime(secondsSaved);
        }

        // Energy saved (in Wh) - hide if < 1 kWh (1000 Wh)
        const whSaved = adsBlocked * WH_PER_AD;
        const kwhSaved = whSaved / 1000;
        const energySavedElement = document.getElementById('energySaved');
        const energySavedStat = document.getElementById('energySavedStat');
        const divider1 = document.getElementById('divider1');

        if (energySavedElement && energySavedStat) {
            if (kwhSaved >= 1) {
                energySavedElement.textContent = formatEnergy(whSaved);
                energySavedStat.classList.remove('none');
                if (divider1) divider1.classList.remove('none');
            } else {
                energySavedStat.classList.add('none');
                if (divider1) divider1.classList.add('none');
            }
        }

        // CO2 emissions reduced (in grams) - hide if < 1 kg (1000 g)
        const gramsCO2Saved = adsBlocked * GRAMS_CO2_PER_AD;
        const kgCO2Saved = gramsCO2Saved / 1000;
        const co2SavedElement = document.getElementById('co2Saved');
        const co2SavedStat = document.getElementById('co2SavedStat');
        const divider2 = document.getElementById('divider2');

        if (co2SavedElement && co2SavedStat) {
            if (kgCO2Saved >= 1) {
                co2SavedElement.textContent = formatCO2(gramsCO2Saved);
                co2SavedStat.classList.remove('none');
                if (divider2) divider2.classList.remove('none');
            } else {
                co2SavedStat.classList.add('none');
                if (divider2) divider2.classList.add('none');
            }
        }

        // Show sentence format if both other stats are hidden
        const timeSavedStat = document.getElementById('timeSavedStat');
        const impactStats = document.getElementById('impactStats');
        const timeSentence = document.getElementById('timeSentence');
        const timeSavedHours = document.getElementById('timeSavedHours');

        if (timeSavedStat && impactStats && timeSentence && timeSavedHours) {
            if (kwhSaved < 1 && kgCO2Saved < 1) {
                // Hide regular stat, show sentence
                timeSavedStat.classList.add('none');
                impactStats.classList.add('single-stat');
                timeSentence.classList.remove('none');
                // Calculate hours
                const hours = Math.floor(secondsSaved / 3600);
                timeSavedHours.textContent = hours;
            } else {
                timeSavedStat.classList.remove('none');
                impactStats.classList.remove('single-stat');
                timeSentence.classList.add('none');
            }
        }
    }

    // Format seconds into human-readable time
    function formatTime(seconds) {
        if (seconds < 60) {
            return seconds + 's';
        } else if (seconds < 3600) {
            const mins = Math.round(seconds / 60);
            return mins + ' min';
        } else {
            const hours = seconds / 3600;
            if (hours >= 10) {
                return Math.round(hours) + ' hrs';
            }
            return Math.round(hours * 10) / 10 + ' hrs';
        }
    }

    // Format Watt-hours into human-readable energy
    function formatEnergy(wh) {
        if (wh < 1) {
            // Show in milliwatt-hours for very small values
            const mwh = Math.round(wh * 1000);
            return mwh + ' mWh';
        } else if (wh < 1000) {
            // Show in Watt-hours
            if (wh < 10) {
                return Math.round(wh * 10) / 10 + ' Wh';
            }
            return Math.round(wh) + ' Wh';
        } else {
            // Show in kilowatt-hours
            const kwh = wh / 1000;
            if (kwh < 10) {
                return Math.round(kwh * 100) / 100 + ' kWh';
            }
            return Math.round(kwh * 10) / 10 + ' kWh';
        }
    }

    // Format CO2 grams into human-readable format
    function formatCO2(grams) {
        if (grams < 1) {
            // Very small - show in milligrams
            const mg = Math.round(grams * 1000);
            return mg + ' mg';
        } else if (grams < 1000) {
            // Show in grams
            if (grams < 10) {
                return Math.round(grams * 10) / 10 + ' g';
            }
            return Math.round(grams) + ' g';
        } else {
            // Show in kilograms
            const kg = grams / 1000;
            if (kg < 10) {
                return Math.round(kg * 100) / 100 + ' kg';
            }
            return Math.round(kg * 10) / 10 + ' kg';
        }
    }

    // Format MB into human-readable data size (kept for potential future use)
    function formatData(mb) {
        if (mb < 1000) {
            return Math.round(mb) + ' MB';
        } else {
            const gb = mb / 1000;
            if (gb >= 10) {
                return Math.round(gb) + ' GB';
            }
            return Math.round(gb * 10) / 10 + ' GB';
        }
    }

    // Format number with commas (e.g., 1234 -> "1,234")
    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    // Confirm modal elements
    const confirmModal = document.getElementById('confirmModal');
    const confirmNoSupport = document.getElementById('confirmNoSupport');
    const confirmYesSupport = document.getElementById('confirmYesSupport');

    // Helper function to show thank you overlay
    function showThankYouAndClose() {
        const thankYouOverlay = document.getElementById('thankYouOverlay');
        thankYouOverlay.classList.remove('none');
    }

    // Thank you "Got It!" button - closes the tab
    const thankYouGotItBtn = document.getElementById('thankYouGotItBtn');
    thankYouGotItBtn.addEventListener('click', function() {
        window.close();
    });

    // Support toggle - saves automatically on change
    supportToggle.addEventListener('change', function() {
        if (supportToggle.checked) {
            // Turning ON - save and show thank you
            savePreference(true);
            trackOptIn(true);
            showThankYouAndClose();
        } else {
            // Turning OFF - save immediately without confirmation
            savePreference(false);
            trackOptIn(false);
            updateCloseButtonVisibility();
        }
    });

    // User confirms they don't want to support
    confirmNoSupport.addEventListener('click', function() {
        supportToggle.checked = false;
        savePreference(false);
        trackOptIn(false);
        confirmModal.classList.add('none');
        updateCloseButtonVisibility();
    });

    // User confirms they do want to support
    confirmYesSupport.addEventListener('click', function() {
        confirmModal.classList.add('none');
        savePreference(true);
        trackOptIn(true);
        showThankYouAndClose();
    });

    // Click outside modal (on overlay) closes without changes
    confirmModal.addEventListener('click', function(e) {
        if (e.target === confirmModal) {
            // Clicked on overlay, not inside the box - just close
            confirmModal.classList.add('none');
        }
    });

    // Pressing Escape key closes modal without changes
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !confirmModal.classList.contains('none')) {
            confirmModal.classList.add('none');
        }
    });

    // Close tab button
    const closeTabBtn = document.getElementById('closeTabBtn');
    closeTabBtn.addEventListener('click', function() {
        window.close();
    });

    // Helper function to update close button visibility based on toggle state
    function updateCloseButtonVisibility() {
        if (supportToggle.checked) {
            closeTabBtn.style.display = 'block';
        } else {
            closeTabBtn.style.display = 'none';
        }
    }

    // Save user preference to storage (single variable)
    function savePreference(optedIn) {
        chrome.storage.local.set({
            'promo_autocomment_enabled': optedIn
        });
    }

    // Track opt-in decision for analytics
    function trackOptIn(optedIn) {
        chrome.storage.sync.get(['user_stat_uuid'], function(result) {
            const uuid = result.user_stat_uuid || 'unknown';
            const data = {
                user_id: uuid,
                tag: optedIn ? 'promo_optin_yes' : 'promo_optin_no'
            };

            fetch('https://insights.getblockify.com/metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            }).catch(function(error) {
                console.error('Error tracking opt-in:', error);
            });
        });
    }

};
