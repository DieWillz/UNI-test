/**
 * YouTube Auto-Comment Promotion Script
 * =====================================
 * Posts promotional comments on YouTube videos for users who have opted in.
 * This helps spread awareness of Blockify through organic user engagement.
 *
 * IMPORTANT: This feature is entirely opt-in. Users must explicitly consent
 * via the promo_optin popup before any comments are posted.
 *
 * Architecture:
 * - Uses a hidden iframe approach to avoid disrupting user's video watching
 * - Main page: Monitors playback, creates hidden iframe when ready to comment
 * - Iframe: Detects it's in iframe mode via URL hash, posts comment, signals completion
 * - Main page: Receives success signal via postMessage, destroys iframe
 *
 * Features:
 * - Rate limiting: Maximum 1 comment per 24 hours
 * - Per-video tracking: Won't comment on the same video twice
 * - Login check: Only works when user is logged into YouTube
 * - Playback delay: Waits 10 seconds of video playback before commenting
 * - Hidden iframe: Does not scroll or disrupt user's main viewing experience
 * - SPA navigation support: Works with YouTube's single-page app navigation
 *
 * Storage keys used:
 * - promo_autocomment_enabled: boolean - Whether user opted in
 * - promo_last_comment_time: number - Timestamp of last comment
 * - promo_commented_videos: string[] - List of video IDs already commented on
 *
 * Analytics events:
 * - promo_comment_posted: Successfully posted a comment
 *
 * @requires User must be logged into YouTube
 * @requires User must have opted in via promo_optin popup
 * @see support-blockify.html for the opt-in flow
 */

(function () {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================

    /** Storage key for persisted promo comments */
    const COMMENT_TEXTS_STORAGE_KEY = 'blockify_promo_comment_texts';

    /** Endpoint for remotely managed promo comments */
    const COMMENT_TEXTS_ENDPOINT = 'https://blockify.b-cdn.net/cc.json';

    /** Default promotional comments (fallback) */
    const COMMENT_TEXTS_FALLBACK = [
        "who else is enjoying this video ad-free with Blockify?",
        "No more cringy \"Learn AI and get rich\" ads - all thanks to Blockify",
        "No more annoying \"Single moms in your area\" ads - thanks to Blockify",
        "No more suspicious 'I bought a Lambo at 19' tutorials - all thanks to Blockify",
        "No more 'Passive income secrets' popping up mid-video - all thanks to Blockify",
        "No more 'Is crypto dead?' clickbait ads - all thanks to Blockify",
        "No more weirdly specific ads based on conversations you had yesterday - all thanks to Blockify",
        "No more sketchy 'One weird trick to melt belly fat' ads - all thanks to Blockify",
        "No more \"AI side hustle\" gurus yelling at you mid-video, all thanks to Blockify.",
        "No more \"Quit your job in 30 days with AI\" nonsense, all thanks to Blockify.",
        "No more \"I made $10,000 this week using AI\" fake flex ads - all thanks to Blockify.",
        "No more \"Buy my AI course\" ambush ads - all thanks to Blockify.",
        "No more \"I'll mentor you to riches with AI\" cringe pitches, all thanks to Blockify.",
        "No more \"Make money while you sleep with AI\" fantasy ads - all thanks to Blockify.",
        "No more \"AI will replace your job - buy my course\" fearbait - all thanks to Blockify.",
        "No more \"Use AI to get rich fast\" spam - all thanks to Blockify.",
        "No more non-skippable video ads --- all thanks to Blockify.",
        "loving this video ad-free with Blockify ad-blocker!!",
        "Not all heroes wear capes. Some just build tools like Blockify so we can actually watch videos in peace.🫡",
        "Blockify user here. If ads were a person, I'd ghost 'em. 👻",
        "Ads interrupting like that annoying ex? try Blockify!",
        "Tired of pre-roll ads killing the vibe? use Blockify!",
        "best find ever: Blockify ad blocker zaps ads on all sites, including yt!",
        "No more double pre-roll ads - all thanks to Blockify",
        "No more mid-roll 'Right at the climax' ads - all thanks to Blockify",
        "No more 'My AI agency made $50k/month' ads - all thanks to Blockify",
        "No more 'This AI bot trades for you' ads - all thanks to Blockify",
        "No more 'I'm 19 and financially free' ads - all thanks to Blockify",
        "No more 'You won't believe what happens next' ads - all thanks to Blockify",
        "No more 'Doctor-approved miracle gummies' ads - all thanks to Blockify",
        "No more 'Lose weight while you sleep' ads - all thanks to Blockify",
        "No more 'Don't skip—this will change your life' guilt-trip ads - all thanks to Blockify",
        "loving this video ad-free with Blockify!!",
        "loving this video ad-free with Blockify ad-blocker!!"
    ];

    /** Runtime comments source (localStorage/remote with fallback) */
    let commentTexts = COMMENT_TEXTS_FALLBACK.slice();

    /** Runtime switch controlled by config payload: { "comment_texts": ["none"] } */
    let commentsDisabled = false;

    /**
     * Return true when payload is explicit disable signal.
     * @param {unknown} candidate
     * @returns {boolean}
     */
    function isCommentDisableSignal(candidate) {
        if (!Array.isArray(candidate) || candidate.length !== 1) {
            return false;
        }

        const [value] = candidate;
        return typeof value === 'string' && value.trim().toLowerCase() === 'none';
    }

    /**
     * Validate and normalize a comment array.
     * @param {unknown} candidate
     * @returns {string[]|null}
     */
    function normalizeCommentTexts(candidate) {
        if (!Array.isArray(candidate)) {
            return null;
        }

        const normalized = candidate
            .filter(item => typeof item === 'string')
            .map(item => item.trim())
            .filter(item => item.length > 0);

        if (normalized.length === 0) {
            return null;
        }

        return Array.from(new Set(normalized));
    }

    /**
     * Load comment texts from localStorage.
     * Falls back silently when localStorage is empty/invalid.
     */
    function loadCommentTextsFromLocalStorage() {
        try {
            const raw = localStorage.getItem(COMMENT_TEXTS_STORAGE_KEY);
            if (!raw) {
                return;
            }

            const parsed = JSON.parse(raw);
            const storedArray = Array.isArray(parsed)
                ? parsed
                : (parsed && parsed.comment_texts);

            if (isCommentDisableSignal(storedArray)) {
                commentsDisabled = true;
                commentTexts = [];
                return;
            }

            const normalized = normalizeCommentTexts(storedArray);
            if (normalized) {
                commentsDisabled = false;
                commentTexts = normalized;
            }
        } catch (error) {
            // Keep fallback comments on parse/storage errors.
        }
    }

    /**
     * Persist comment texts to localStorage.
     * @param {string[]} texts
     */
    function saveCommentTextsToLocalStorage(texts) {
        try {
            localStorage.setItem(COMMENT_TEXTS_STORAGE_KEY, JSON.stringify(texts));
        } catch (error) {
            // Ignore storage failures and continue with in-memory values.
        }
    }

    /**
     * Fetch latest comment texts from backend and refresh localStorage.
     * Supported payloads:
     * - { "comment_texts": ["..."] }
     * - ["..."] (legacy/simple format)
     * @param {{ applyToRuntime?: boolean }} [options]
     */
    async function refreshCommentTextsFromEndpoint(options = {}) {
        const applyToRuntime = options.applyToRuntime === true;

        try {
            const response = await fetch(COMMENT_TEXTS_ENDPOINT, { cache: 'no-cache' });
            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            const remoteArray = Array.isArray(payload)
                ? payload
                : (payload && payload.comment_texts);

            if (isCommentDisableSignal(remoteArray)) {
                saveCommentTextsToLocalStorage(['none']);
                if (applyToRuntime) {
                    commentsDisabled = true;
                    commentTexts = [];
                }
                return;
            }

            const normalized = normalizeCommentTexts(remoteArray);
            if (!normalized) {
                return;
            }

            saveCommentTextsToLocalStorage(normalized);
            if (applyToRuntime) {
                commentsDisabled = false;
                commentTexts = normalized;
            }
        } catch (error) {
            // Keep existing comment source when fetch/parsing fails.
        }
    }

    // Initialize comments from localStorage first; fallback remains in place.
    loadCommentTextsFromLocalStorage();

    /** Get a random comment from the array */
    function getRandomComment() {
        if (commentsDisabled) {
            return null;
        }

        const source = (Array.isArray(commentTexts) && commentTexts.length > 0)
            ? commentTexts
            : COMMENT_TEXTS_FALLBACK;

        if (!Array.isArray(source) || source.length === 0) {
            return null;
        }

        return source[Math.floor(Math.random() * source.length)];
    }

    /** Delay before attempting to comment after page load (milliseconds) */
    const COMMENT_DELAY_MS = 7000; // 7 seconds

    /** Minimum time between comments across all videos (milliseconds) */
    const RATE_LIMIT_MS = 1000; //24 * 60 * 60 * 1000; // 24 hours //change this later

    /** Window name to identify when running in comment posting mode (iframe) */
    /** Using window.name instead of URL params because YouTube strips URL parameters during SPA navigation */
    const COMMENT_IFRAME_NAME = 'blockify-promo-comment-iframe';

    /** Timeout for iframe comment operation (milliseconds) */
    const IFRAME_TIMEOUT_MS = 60000; // 60 seconds (longer to allow YouTube to fully load)

    // =========================================================================
    // STATE VARIABLES
    // =========================================================================

    /** Flag to prevent multiple comment attempts per page load */
    let hasAttemptedComment = false;

    /** Reference to the hidden iframe element */
    let commentIframe = null;

    /** Last URL we processed (for detecting navigation) */
    let lastProcessedUrl = null;

    /** Timer ID for the comment delay (so we can cancel on navigation) */
    let commentTimerId = null;

    /** Flag to track if message listener is already set up */
    let messageListenerSetup = false;

    /** Video ID when timer was started (to validate it hasn't changed) */
    let timerVideoId = null;

    // =========================================================================
    // STORAGE/PREFERENCE FUNCTIONS
    // =========================================================================

    /**
     * Check if user has opted in to the promo feature.
     * @returns {Promise<boolean>} True if user opted in
     */
    function checkOptInStatus() {
        return new Promise((resolve) => {
            chrome.storage.local.get(['promo_autocomment_enabled'], function (result) {
                const isOptedIn = result.promo_autocomment_enabled === true;
                resolve(isOptedIn);
            });
        });
    }

    /**
     * Check if enough time has passed since the last comment (rate limiting).
     * Enforces the 24-hour minimum between comments.
     * @returns {Promise<boolean>} True if we can comment (rate limit not exceeded)
     */
    function checkRateLimit() {
        return new Promise((resolve) => {
            chrome.storage.local.get(['promo_last_comment_time'], function (result) {
                const lastCommentTime = result.promo_last_comment_time || 0;
                const timeSinceLastComment = Date.now() - lastCommentTime;
                const canComment = timeSinceLastComment >= RATE_LIMIT_MS;
                resolve(canComment);
            });
        });
    }

    /**
     * Check if we've already commented on this specific video.
     * Prevents duplicate comments on the same video.
     * @param {string} videoId - YouTube video ID
     * @returns {Promise<boolean>} True if we haven't commented yet
     */
    function checkVideoCommented(videoId) {
        return new Promise((resolve) => {
            chrome.storage.local.get(['promo_commented_videos'], function (result) {
                const commentedVideos = result.promo_commented_videos || [];
                const notCommentedYet = !commentedVideos.includes(videoId);
                resolve(notCommentedYet);
            });
        });
    }

    /**
     * Save record of commenting on a video.
     * Updates both the video list and the last comment timestamp.
     * Limits stored videos to 100 to prevent storage bloat.
     * @param {string} videoId - YouTube video ID that was commented on
     */
    function saveCommentedVideo(videoId) {
        chrome.storage.local.get(['promo_commented_videos'], function (result) {
            let commentedVideos = result.promo_commented_videos || [];
            commentedVideos.push(videoId);
            // Keep only last 100 videos to prevent storage bloat
            if (commentedVideos.length > 100) {
                commentedVideos = commentedVideos.slice(-100);
            }
            chrome.storage.local.set({
                'promo_commented_videos': commentedVideos,
                'promo_last_comment_time': Date.now()
            });
        });
    }

    // =========================================================================
    // IFRAME DETECTION
    // =========================================================================

    /**
     * Check if we're running inside any iframe.
     * @returns {boolean} True if in an iframe
     */
    function isInIframe() {
        try {
            return window.self !== window.top;
        } catch (e) {
            return true; // Cross-origin iframe
        }
    }

    /**
     * Classify execution context for strict iframe gating.
     * - top_frame: regular YouTube page
     * - comment_iframe: hidden iframe created by this script for auto-commenting
     * - other_iframe: any iframe that is not our comment iframe (must not run logic)
     * @returns {'top_frame'|'comment_iframe'|'other_iframe'}
     */
    function getFrameContext() {
        if (!isInIframe()) {
            return 'top_frame';
        }

        const parentIsYouTube = isYouTubeHostname(getParentFrameHostname());
        const isCommentIframe =
            window.name === COMMENT_IFRAME_NAME &&
            window.location.hostname.endsWith('youtube.com') &&
            window.location.pathname === '/watch' &&
            parentIsYouTube;

        return isCommentIframe ? 'comment_iframe' : 'other_iframe';
    }

    /**
     * Check if a hostname belongs to YouTube.
     * @param {string|null} hostname
     * @returns {boolean}
     */
    function isYouTubeHostname(hostname) {
        if (!hostname || typeof hostname !== 'string') {
            return false;
        }
        const normalizedHost = hostname.toLowerCase();
        return normalizedHost === 'youtube.com' || normalizedHost.endsWith('.youtube.com');
    }

    /**
     * Resolve parent frame hostname using same-origin access first, then referrer fallback.
     * @returns {string|null}
     */
    function getParentFrameHostname() {
        if (!isInIframe()) {
            return null;
        }

        try {
            if (window.parent && window.parent !== window && window.parent.location) {
                const directHost = window.parent.location.hostname;
                if (directHost) {
                    return directHost.toLowerCase();
                }
            }
        } catch (error) {
            // Expected for cross-origin parents. Fall back to document.referrer.
        }

        if (!document.referrer) {
            return null;
        }

        try {
            return new URL(document.referrer).hostname.toLowerCase();
        } catch (error) {
            return null;
        }
    }

    /**
     * Early mute is only allowed for our hidden comment iframe when parent is YouTube.
     * This avoids touching regular embedded YouTube frames on non-YouTube sites.
     * @returns {boolean}
     */
    function shouldPrioritizeIframeMute() {
        if (FRAME_CONTEXT !== 'comment_iframe') {
            return false;
        }

        return isYouTubeHostname(getParentFrameHostname());
    }

    // Strict frame-context gate: never run in non-comment iframes.
    const FRAME_CONTEXT = getFrameContext();
    if (FRAME_CONTEXT === 'other_iframe') {
        return;
    }

    // Prioritize muting immediately in our hidden iframe to avoid background audio overlap.
    if (shouldPrioritizeIframeMute()) {
        hardMuteMedia();
    }

    // =========================================================================
    // YOUTUBE PAGE INTERACTION FUNCTIONS
    // =========================================================================

    /**
     * Extract the video ID from the current page URL.
     * @returns {string|null} Video ID or null if not on a video page
     */
    function getVideoId() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('v');
    }

    /**
     * Check if user is logged in to YouTube.
     * Looks for any of the avatar/account indicators.
     * @returns {boolean} True if user appears to be logged in
     */
    function isUserLoggedIn() {
        const avatarBtn = document.querySelector('#avatar-btn');
        const avatarImg = document.querySelector('[alt="Avatar image"]');
        const accountMenu = document.querySelector('[aria-label="Account menu"]');
        return !!(avatarBtn || avatarImg || accountMenu);
    }

    /**
     * Wait for the comment placeholder to appear.
     * YouTube lazy-loads this element only after scrolling down.
     * Scrolls incrementally by 10% of page height, waiting 5 seconds at each step.
     * @returns {Promise<Element|null>} The placeholder element or null if not found after 100% scroll
     */
    async function waitForPlaceholder() {
        const SCROLL_INCREMENT = 0.1; // 10% of page height
        const WAIT_PER_SCROLL_MS = 5000; // 5 seconds wait after each scroll
        const CHECK_INTERVAL_MS = 500; // Check every 500ms during wait period

        /**
         * Check if the placeholder element exists in the DOM
         * @returns {Element|null} The placeholder element or null
         */
        function findPlaceholder() {
            return document.querySelector('#placeholder-area') ||
                document.querySelector('#simplebox-placeholder');
        }

        /**
         * Get the total scrollable height of the document
         * @returns {number} Total scrollable height in pixels
         */
        function getScrollHeight() {
            return Math.max(
                document.body.scrollHeight,
                document.documentElement.scrollHeight
            );
        }

        // First check if placeholder is already visible (before any scrolling)
        let placeholder = findPlaceholder();
        if (placeholder) {
            return placeholder;
        }

        // Scroll incrementally by 10% until we reach 100% or find the placeholder
        for (let scrollPercent = SCROLL_INCREMENT; scrollPercent <= 1.0; scrollPercent += SCROLL_INCREMENT) {
            const scrollHeight = getScrollHeight();
            const targetScrollY = scrollHeight * scrollPercent;

            window.scrollTo(0, targetScrollY);

            // Wait and check periodically during the wait period
            const checksPerWait = Math.floor(WAIT_PER_SCROLL_MS / CHECK_INTERVAL_MS);

            for (let checkCount = 0; checkCount < checksPerWait; checkCount++) {
                await new Promise(r => setTimeout(r, CHECK_INTERVAL_MS));

                placeholder = findPlaceholder();
                if (placeholder) {
                    return placeholder;
                }
            }
        }

        // Final check after reaching 100%
        placeholder = findPlaceholder();
        if (placeholder) {
            return placeholder;
        }

        return null;
    }

    /**
     * Wait for the comment input to appear after clicking placeholder.
     * @returns {Promise<Element|null>} The input element or null if timeout
     */
    async function waitForCommentInput() {
        const maxWait = 5000;
        const checkInterval = 300;
        let waited = 0;

        return new Promise((resolve) => {
            const check = () => {
                const input = document.querySelector('#contenteditable-root') ||
                    document.querySelector('[aria-label="Add a comment..."]');

                if (input) {
                    resolve(input);
                    return;
                }

                waited += checkInterval;
                if (waited >= maxWait) {
                    resolve(null);
                    return;
                }

                setTimeout(check, checkInterval);
            };
            check();
        });
    }

    /**
     * Click placeholder to activate comment input, then focus the input.
     * @returns {Promise<boolean>} True if input was found and activated
     */
    async function activateCommentInput() {
        const placeholder = await waitForPlaceholder();
        if (!placeholder) {
            return false;
        }

        placeholder.click();
        await new Promise(r => setTimeout(r, 500));

        const commentInput = await waitForCommentInput();
        if (commentInput) {
            commentInput.focus();
            return true;
        }
        return false;
    }

    /**
     * Type the promotional comment into the comment input field.
     * Uses a small delay to allow YouTube's UI to be ready.
     * @returns {Promise<boolean>} True if comment was typed successfully
     */
    function typeComment() {
        return new Promise((resolve) => {
            setTimeout(() => {
                const commentInput = document.querySelector('#contenteditable-root') ||
                    document.querySelector('[aria-label="Add a comment..."]');
                if (commentInput) {
                    commentInput.focus();
                    const commentText = getRandomComment();
                    if (!commentText) {
                        resolve(false);
                        return;
                    }
                    commentInput.textContent = commentText;
                    commentInput.dispatchEvent(new Event('input', { bubbles: true }));
                    resolve(true);
                } else {
                    resolve(false);
                }
            }, 500);
        });
    }

    /**
     * Click the submit button to post the comment.
     * Uses a small delay to ensure the button is enabled after typing.
     * @returns {Promise<boolean>} True if submit button was clicked
     */
    function submitComment() {
        return new Promise((resolve) => {
            setTimeout(() => {
                const submitBtn = document.querySelector('#submit-button button') ||
                    document.querySelector('#submit-button') ||
                    document.querySelector('[aria-label="Comment"]');
                if (submitBtn && !submitBtn.disabled) {
                    submitBtn.click();
                    resolve(true);
                } else {
                    resolve(false);
                }
            }, 500);
        });
    }

    /**
     * Wait for login elements to be available.
     * Only checks for login indicators, skips YouTube init check.
     * @returns {Promise<void>}
     */
    async function waitForYouTubeInit() {
        const maxWait = 15000;
        const checkInterval = 500;
        let waited = 0;

        return new Promise((resolve) => {
            const check = () => {
                const avatarBtn = document.querySelector('#avatar-btn');
                const avatarImg = document.querySelector('[alt="Avatar image"]');
                const accountMenu = document.querySelector('[aria-label="Account menu"]');
                const hasLoginIndicator = !!(avatarBtn || avatarImg || accountMenu);

                if (hasLoginIndicator) {
                    resolve();
                    return;
                }

                waited += checkInterval;
                if (waited >= maxWait) {
                    resolve();
                    return;
                }

                setTimeout(check, checkInterval);
            };
            check();
        });
    }

    // =========================================================================
    // HIDDEN IFRAME MANAGEMENT (Main Page)
    // =========================================================================

    /**
     * Create a hidden iframe to post the comment without disrupting user experience.
     * The iframe loads the same video page with a URL parameter to identify it.
     * Since both parent and iframe are on youtube.com (same origin), they share cookies/session.
     * @param {string} videoId - YouTube video ID
     */
    function createCommentIframe(videoId) {
        destroyCommentIframe();

        const iframeUrl = `https://www.youtube.com/watch?v=${videoId}&autoplay=0&mute=1&playsinline=1`;

        commentIframe = document.createElement('iframe');
        commentIframe.id = 'blockify-promo-iframe';
        commentIframe.name = COMMENT_IFRAME_NAME;
        commentIframe.src = iframeUrl;

        //commentIframe.allow = 'publickey-credentials-get';
        commentIframe.allow = "autoplay 'none'; publickey-credentials-get;";
        commentIframe.sandbox = "allow-same-origin allow-scripts allow-forms";
        commentIframe.credentials = 'include';
        commentIframe.referrerPolicy = 'no-referrer-when-downgrade';

        commentIframe.style.cssText = `
            all: unset !important;
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            opacity: 0 !important;
            pointer-events: none !important;
            border: none !important;
            z-index: -100000000 !important;
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
            user-select: none !important;
        `;

        document.body.appendChild(commentIframe);

        // Set timeout to destroy iframe if it takes too long
        setTimeout(() => {
            if (commentIframe) {
                destroyCommentIframe();
            }
        }, IFRAME_TIMEOUT_MS);
    }

    /**
     * Destroy the hidden comment iframe.
     */
    function destroyCommentIframe() {
        if (commentIframe) {
            commentIframe.remove();
            commentIframe = null;
        }
        const existingIframe = document.getElementById('blockify-promo-iframe');
        if (existingIframe) {
            existingIframe.remove();
        }
    }

    /**
     * Listen for messages from the comment iframe.
     * Only sets up the listener once to prevent duplicates.
     */
    function setupIframeMessageListener() {
        if (messageListenerSetup) {
            return;
        }

        messageListenerSetup = true;

        window.addEventListener('message', function (event) {
            if (event.data && event.data.type === 'blockify-promo-result') {
                if (event.data.success) {
                    saveCommentedVideo(event.data.videoId);
                }

                // Always destroy the iframe after receiving result
                destroyCommentIframe();
            }
        });
    }

    // =========================================================================
    // IFRAME MODE: Comment Posting (Inside Hidden Iframe)
    // =========================================================================

    /**
     * Post comment when running inside the hidden iframe.
     * This function handles the actual comment posting in iframe mode.
     * Handles: waiting for YouTube to load, login check, scrolling, input activation, typing, and submitting.
     * Since iframe is same-origin as parent, cookies/session are shared.
     * @async
     */
    async function postCommentInIframe() {
        const videoId = getVideoId();
        let success = false;
        let failReason = '';

        // Mute any video immediately to avoid audio
        const video = document.querySelector('video');
        if (video) {
            video.muted = true;
            video.pause();
        }

        await waitForYouTubeInit();

        // Check login in iframe context (shares cookies with parent)
        let loginAttempts = 0;
        const maxLoginAttempts = 3;
        const loginRetryDelay = 4000;

        while (!isUserLoggedIn() && loginAttempts < maxLoginAttempts) {
            loginAttempts++;
            if (loginAttempts < maxLoginAttempts) {
                await new Promise(r => setTimeout(r, loginRetryDelay));
            }
        }

        if (!isUserLoggedIn()) {
            failReason = 'not_logged_in';
            sendResultToParent(success, videoId, failReason);
            return;
        }

        const activated = await activateCommentInput();
        if (!activated) {
            failReason = 'input_activation_failed';
            sendResultToParent(success, videoId, failReason);
            return;
        }

        await new Promise(r => setTimeout(r, 500));

        const typed = await typeComment();
        if (!typed) {
            failReason = 'typing_failed';
            sendResultToParent(success, videoId, failReason);
            return;
        }

        const submitted = await submitComment();
        if (!submitted) {
            failReason = 'submit_failed';
            sendResultToParent(success, videoId, failReason);
            return;
        }

        success = true;
        await new Promise(r => setTimeout(r, 1000));
        sendResultToParent(success, videoId, failReason);
    }

    /**
     * Send result back to parent window.
     * @param {boolean} success - Whether comment was posted successfully
     * @param {string} videoId - The video ID
     * @param {string} failReason - Reason for failure if not successful
     */
    function sendResultToParent(success, videoId, failReason) {
        if (window.parent && window.parent !== window) {
            window.parent.postMessage({
                type: 'blockify-promo-result',
                success: success,
                videoId: videoId,
                failReason: failReason
            }, '*');
        }
    }

    // =========================================================================
    // MAIN PAGE: Comment Initiation Logic
    // =========================================================================

    /**
     * Main function to initiate the comment process.
     * Creates a hidden iframe to post the comment without disrupting user experience.
     *
     * Main page checks (before creating iframe):
     * - User has opted in
     * - Rate limit not exceeded (24 hours)
     * - Haven't commented on this video before
     *
     * Iframe handles:
     * - Scrolling to comments
     * - Typing and posting comment
     *
     * Login state is checked on main page and passed to iframe via URL parameter.
     *
     * @async
     */
    async function initiateComment() {

        if (hasAttemptedComment) {
            return;
        }
        hasAttemptedComment = true;

        if (commentsDisabled) {
            return;
        }

        const videoId = getVideoId();
        if (!videoId) {
            return;
        }


        const canComment = await checkRateLimit();
        if (!canComment) {
            return;
        }

        const notCommentedYet = await checkVideoCommented(videoId);
        if (!notCommentedYet) {
            return;
        }

        createCommentIframe(videoId);
    }

    // =========================================================================
    // ANALYTICS
    // =========================================================================

    /**
     * Track that a comment was successfully posted.
     * Sends event to Blockify analytics endpoint.
     * @param {string} videoId - YouTube video ID
     */
    function trackCommentPosted(videoId) {
        chrome.storage.sync.get(['user_stat_uuid'], function (result) {
            const uuid = result.user_stat_uuid || 'unknown';
            const data = {
                user_id: uuid,
                tag: 'promo_comment_posted',
                video_id: videoId
            };

            fetch('https://insights.getblockify.com/metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            }).catch(function (error) {
                console.error('[Blockify Promo] Error tracking comment:', error);
            });
        });
    }

    // =========================================================================
    // VIDEO PLAYBACK MONITORING (Main Page Only)
    // =========================================================================

    /**
     * Monitor video playback to determine when to attempt commenting.
     * Waits for PLAYBACK_DELAY_MS of playback before triggering comment.
     * Retries every second if video element is not yet available.
     * Only runs on the main page, not in the hidden iframe.
     */
    function monitorPlayback() {
        if (commentTimerId) {
            clearTimeout(commentTimerId);
            commentTimerId = null;
        }

        timerVideoId = getVideoId();

        commentTimerId = setTimeout(() => {
            const currentVideoId = getVideoId();

            if (currentVideoId !== timerVideoId) {
                return;
            }

            if (!hasAttemptedComment) {
                initiateComment();
            }
        }, COMMENT_DELAY_MS);
    }

    // =========================================================================
    // INITIALIZATION
    // =========================================================================

    /**
     * Initialize the promo feature for the main page.
     * Only runs on YouTube video watch pages (/watch).
     * Sets up message listener and starts the comment delay timer.
     * @async
     */
    async function initMainPage() {

        const currentUrl = window.location.href;

        if (!window.location.pathname.includes('/watch')) {
            return;
        }

        if (currentUrl === lastProcessedUrl && hasAttemptedComment) {
            return;
        }


        hasAttemptedComment = false;
        lastProcessedUrl = currentUrl;

        setupIframeMessageListener();
        monitorPlayback();
    }

    /*
    function observr() {
        // REQUIREMENT: Handle edge cases (document.body not ready)
        if (!document.body) 
        {
                    document.querySelectorAll('video, audio').forEach(video => {
                    video.muted = true;
                    video.volume = 0;
                });
            document.addEventListener('DOMContentLoaded', observr);
            return;
        }
    
        // CORE LOGIC: Enforce Silence
        // Includes guard clause to prevent infinite loops/stack overflow
        const enforceSilence = (media) => {
            if (media.muted !== true || media.volume !== 0) {
                media.muted = true;
                media.volume = 0;
            }
        };
    
        // SETUP: Attach listeners safely
        const setupMedia = (media) => {
            // Optimization: Prevent attaching duplicate listeners to the same node
            if (media.dataset.observrAttached === 'true') {
                // Even if attached, ensure it is silent right now
                enforceSilence(media);
                return;
            }
    
            enforceSilence(media);
    
            // REQUIREMENT: Mute as soon as there are changes to volume/mute state
            // 'volumechange' catches User interactions (sliders) and JS property updates
            media.addEventListener('volumechange', () => enforceSilence(media));
            
            // Mark as handled so we don't attach listeners again
            media.dataset.observrAttached = 'true';
        };
    
        // OBSERVER CALLBACK
        const callback = (mutationsList) => {
            mutationsList.forEach((mutation) => {
                
                // REQUIREMENT: Mute all newly added audio / video
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) { // 1 = Element Node
                            // Direct match
                            if (node.tagName === 'VIDEO' || node.tagName === 'AUDIO') {
                                setupMedia(node);
                            }
                            // Nested match (if a container div was added)
                            if (node.hasChildNodes()) {
                                node.querySelectorAll('video, audio').forEach(setupMedia);
                            }
                        }
                    });
                }
    
                // REQUIREMENT: Handle HTML attribute changes (e.g. script removes 'muted' attr)
                if (mutation.type === 'attributes') {
                    // We call enforceSilence directly here as listener is likely already attached
                    enforceSilence(mutation.target);
                }
            });
        };
    
        // INIT OBSERVER
        const observer = new MutationObserver(callback);
    
        observer.observe(document.body, {
            childList: true,      // Detect new nodes
            subtree: true,        // Detect deep nesting
            attributes: true,     // Detect attribute modifications
            attributeFilter: ['muted', 'src'] // Optimization: Only watch relevant attributes
        });
    
        // INITIAL SWEEP: Handle elements existing before script ran
        document.querySelectorAll('video, audio').forEach(setupMedia);
    };
    */

    function observr() {

        /**
         * 1. THE ENFORCER
         * Silences media. Includes guard clauses to prevent infinite recursion
         * when we programmatically set the volume (which triggers events).
         */
        const enforceSilence = (media) => {
            // Check exact state to avoid redundant writes/loops
            if (media.muted !== true || media.volume !== 0) {
                media.muted = true;
                media.volume = 0;
                // console.log('Silenced:', media); // Debugging
            }
        };

        /**
         * 2. THE SETUP
         * Attaches fail-safe listeners to individual media elements.
         * Uses a data attribute to ensure we don't attach listeners twice.
         */
        const attachEnforcer = (media) => {
            // If we've already set this one up, just double-check silence and exit
            if (media.dataset.silencerAttached === 'true') {
                enforceSilence(media);
                return;
            }

            // Apply silence immediately
            enforceSilence(media);

            // Attach Listeners
            // 'volumechange': Catches JS property changes and user sliders
            // 'play': Catches players that auto-unmute when playback starts (e.g., custom ads)
            // 'loadedmetadata': Catches elements created before their audio tracks were ready
            ['volumechange', 'play', 'loadedmetadata'].forEach(event => {
                media.addEventListener(event, () => enforceSilence(media));
            });

            // Mark as handled
            media.dataset.silencerAttached = 'true';
        };

        /**
         * 3. THE WATCHDOG (MutationObserver)
         * Handles new DOM elements AND attribute modifications.
         */
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {

                // A. Handle New Elements (ChildList)
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        // Only check Element nodes (Type 1)
                        if (node.nodeType === 1) {
                            // 1. Direct Match (<video> or <audio>)
                            if (node.tagName === 'VIDEO' || node.tagName === 'AUDIO') {
                                attachEnforcer(node);
                            }
                            // 2. Nested Match (Deep scan if the node has children)
                            // Optimization: Check hasChildNodes() before running querySelectorAll
                            else if (node.hasChildNodes()) {
                                node.querySelectorAll('video, audio').forEach(attachEnforcer);
                            }
                        }
                    });
                }

                // B. Handle Attribute Changes (Attributes)
                // Catches scenarios where a script changes <video muted="true"> to <video muted="false">
                // without triggering a JS event, or changes the 'src' which might reset volume.
                else if (mutation.type === 'attributes') {
                    // mutation.target is the element that changed
                    // We call enforceSilence directly as listeners are likely already attached
                    enforceSilence(mutation.target);
                }
            });
        });

        /**
         * 4. INITIALIZATION
         */
        // Config: Watch for children, deep subtree, and specific attributes
        const config = {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['muted', 'src'] // Performance: Ignore class/style changes
        };

        // A. Start Observing
        // We observe documentElement (<html>) to catch elements even before <body> exists
        observer.observe(document.documentElement, config);

        // B. Initial Sweep
        // Handle any elements that existed before this script ran
        const initialScan = () => {
            document.querySelectorAll('video, audio').forEach(attachEnforcer);
        };

        // Run scan immediately
        initialScan();

        // Safety: Run scan again on DOMContentLoaded in case we missed early partial parses
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initialScan);
        }

    };


    /**
     * Initialize when running inside the hidden comment iframe.
     * Immediately starts the comment posting process.
     * @async
     */
    function hardMuteMedia() {
        if (window.__blockifyHardMuteApplied) {
            return;
        }
        window.__blockifyHardMuteApplied = true;

        const forceMute = (media, shouldPause) => {
            if (!media || (media.tagName !== 'VIDEO' && media.tagName !== 'AUDIO')) {
                return;
            }
            media.muted = true;
            media.volume = 0;
            media.defaultMuted = true;
            if (media.autoplay) {
                media.autoplay = false;
            }
            if (shouldPause && typeof media.pause === 'function') {
                media.pause();
            }
        };

        const handleMediaEvent = (event) => {
            const shouldPause = event.type === 'play' || event.type === 'playing';
            forceMute(event.target, shouldPause);
        };

        ['loadstart', 'loadedmetadata', 'canplay', 'play', 'playing', 'volumechange'].forEach((type) => {
            document.addEventListener(type, handleMediaEvent, true);
        });

        document.querySelectorAll('video, audio').forEach((media) => forceMute(media, false));

        const originalPlay = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function (...args) {
            this.muted = true;
            this.volume = 0;
            this.defaultMuted = true;
            if (this.autoplay) {
                this.autoplay = false;
            }
            return originalPlay.apply(this, args);
        };
    }

    async function initIframe() {
        hardMuteMedia();

        document.querySelectorAll('video, audio').forEach(video => {
            video.muted = true;
            video.volume = 0;
        });

        observr();

        if (document.readyState !== 'complete') {
            await new Promise(resolve => window.addEventListener('load', resolve));
        }

        await new Promise(r => setTimeout(r, 2000));

        if (document.visibilityState === 'visible') {
            postCommentInIframe();
        } else {
            document.addEventListener('visibilitychange', function onVisibilityChange() {
                if (document.visibilityState === 'visible') {
                    document.removeEventListener('visibilitychange', onVisibilityChange);
                    postCommentInIframe();
                }
            });
        }
    }

    /**
     * Handle URL change - cleanup and reinitialize.
     */
    function handleUrlChange() {
        if (commentTimerId) {
            clearTimeout(commentTimerId);
            commentTimerId = null;
        }

        destroyCommentIframe();

        hasAttemptedComment = false;
        lastProcessedUrl = null;
        timerVideoId = null;

        initMainPage();
    }

    /**
     * Set up observers to detect YouTube SPA navigation.
     * YouTube uses client-side navigation, so page loads don't trigger
     * normal page load events. We use multiple methods to detect URL changes:
     * 1. MutationObserver on body (catches most changes)
     * 2. popstate event (catches browser back/forward)
     * 3. yt-navigate-finish event (YouTube's custom navigation event)
     * Only used on main page, not in iframe.
     */
    function setupNavigationObserver() {
        if (!document.body) {
            setTimeout(setupNavigationObserver, 100);
            return;
        }

        let lastUrl = location.href;

        new MutationObserver(() => {
            const url = location.href;
            if (url !== lastUrl) {
                lastUrl = url;
                handleUrlChange();
            }
        }).observe(document.body, { subtree: true, childList: true });

        window.addEventListener('popstate', () => {
            const url = location.href;
            if (url !== lastUrl) {
                lastUrl = url;
                handleUrlChange();
            }
        });

        window.addEventListener('yt-navigate-finish', () => {
            const url = location.href;
            if (url !== lastUrl) {
                lastUrl = url;
                handleUrlChange();
            }
        });
    }

    // =========================================================================
    // SCRIPT ENTRY POINT
    // =========================================================================

    /**
     * Main initialization function.
     * Called when tab is active and ready.
     */
    async function startScript() {
        const isOptedIn = await checkOptInStatus();
        if (!isOptedIn) {
            return;
        }

        // Refresh comment list only for opted-in users on top frame.
        // Keep current run based on localStorage/runtime state; this updates next runs.
        // Avoid duplicate fetches from the hidden comment iframe.
        if (FRAME_CONTEXT === 'top_frame') {
            void refreshCommentTextsFromEndpoint({ applyToRuntime: false });
        }

        if (FRAME_CONTEXT === 'comment_iframe') {
            initIframe();
        } else {
            if (document.readyState === 'complete') {
                initMainPage();
                setupNavigationObserver();
            } else {
                window.addEventListener('load', function () {
                    initMainPage();
                    setupNavigationObserver();
                });
            }
        }
    }

    startScript();
})();
