"""Browser anti-detection and fingerprinting module.

Implements stealth techniques from the NoDriver Stealth & Anti-Detection Reference
to minimize bot detection during SERP scraping:

- Chrome flags for automation concealment (§3)
- JavaScript stealth injection — navigator.webdriver, cdc_*, chrome object, etc. (§4)
- CDP fingerprint emulation — UserAgent, timezone, locale, viewport, etc. (§5)
- JavaScript fingerprint spoofing — screen, WebGL, plugins, etc. (§6)
- WebRTC IP leak prevention — 3-layer defense (§7)
- Cloudflare Turnstile countermeasures (§8)

Each section is numbered to match the corresponding section in the reference document.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# §12 — Fingerprint Profile (Device Template)
# ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FingerprintProfile:
    """Consistent browser fingerprint for anti-detection.

    Default values represent a common Windows desktop Chrome setup.
    All fields are used for fingerprint spoofing to ensure cross-signal consistency.
    A mismatch between any two signals (e.g. UA says Chrome 125 but userAgentData
    says Chrome 120) is a detection vector.
    """

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    platform: str = "Win32"
    language: str = "en-US"
    timezone: str = "America/New_York"
    screen_width: int = 1920
    screen_height: int = 1080
    webgl_vendor: str = "Google Inc. (NVIDIA)"
    webgl_renderer: str = (
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER "
        "Direct3D11 vs_5_0 ps_5_0, D3D11)"
    )
    hardware_concurrency: int = 8
    device_memory: int = 8
    max_touch_points: int = 0
    mobile: bool = False

    @property
    def chrome_version(self) -> str:
        """Extract major Chrome version from user agent."""
        match = re.search(r"Chrome/(\d+)", self.user_agent)
        return match.group(1) if match else "125"

    @property
    def platform_version(self) -> str:
        """Get platform version string for userAgentData high-entropy values."""
        return "15.0.0" if self.platform == "Win32" else "10.15.7"


# Default profile — a realistic Windows desktop Chrome setup.
DEFAULT_FINGERPRINT = FingerprintProfile()


# ──────────────────────────────────────────────────────────────
# §3 — Anti-Detection: Chrome Flags
# ──────────────────────────────────────────────────────────────


def build_chrome_flags(profile: FingerprintProfile) -> list[str]:
    """Build anti-detection Chrome flags for ``uc.start(browser_args=…)``.

    Each flag targets a specific detection vector.  See §3 of the Browser Stealth
    Reference for detailed explanations of every flag.

    Args:
        profile: Fingerprint profile (used for window size).

    Returns:
        List of Chrome flag strings.
    """
    return [
        # ── §3.1  Core stealth ────────────────────────────────
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={profile.screen_width},{profile.screen_height}",
        # ── §3.2 + §3.4  Disabled features (single flag — Chrome uses last-wins)
        (
            "--disable-features=IsolateOrigins,site-per-process,"
            "OptimizationHints,OptimizationHintsFetching,TranslateUI,"
            "InterestFeedContentSuggestions,MediaRouter"
        ),
        # ── §3.3  WebRTC IP leak prevention (Layer 2 of 3) ───
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        # ── §3.4  Anti-Turnstile / behavioural flags ──────────
        "--disable-component-update",
        # ── Stability / noise reduction ────────────────────────
        "--disable-extensions",
        "--disable-infobars",
    ]


# ──────────────────────────────────────────────────────────────
# §4 — Anti-Detection: Global JS Stealth
# ──────────────────────────────────────────────────────────────
# Injection method : CDP Page.addScriptToEvaluateOnNewDocument(runImmediately=True)
# Timing           : Runs BEFORE any page JavaScript on every new document.
# Guard            : window._eF_ prevents double-injection.

_JS_GLOBAL_STEALTH = r"""
(function() {
    if (window._eF_) return;
    window._eF_ = true;

    /* §4.1  navigator.webdriver → undefined */
    Object.defineProperty(navigator, 'webdriver', {
        get: function() { return undefined; }
    });

    /* §4.2  cdc_* global variable cleanup */
    for (var key in window) {
        if (key.substring(0, 4) === 'cdc_') {
            delete window[key];
        }
    }

    /* §4.3  window.chrome object */
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() {},
            sendMessage: function() {}
        };
    }

    /* §4.4  Error.stack CDP frame filtering */
    var _origPrepareStackTrace = Error.prepareStackTrace;
    Error.prepareStackTrace = function(error, structuredStackTrace) {
        var filtered = structuredStackTrace.filter(function(callSite) {
            var fileName = callSite.getFileName() || '';
            return fileName.indexOf('devtools:') === -1 &&
                   fileName.indexOf('nodriver') === -1 &&
                   fileName.indexOf('puppeteer') === -1;
        });
        if (_origPrepareStackTrace) {
            return _origPrepareStackTrace(error, filtered);
        }
        return filtered.map(function(cs) {
            return '    at ' + cs.toString();
        }).join('\n');
    };

    /* §4.5  navigator.permissions.query override */
    var _origPermsQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = function(desc) {
        if (desc && desc.name === 'notifications') {
            return Promise.resolve({state: 'prompt', onchange: null});
        }
        return _origPermsQuery(desc);
    };

    /* §4.6  navigator.languages consistency */
    if (!navigator.language || typeof navigator.language !== 'string') {
        Object.defineProperty(navigator, 'language', {
            get: function() { return 'en-US'; }
        });
    }
    if (!navigator.languages || !Array.isArray(navigator.languages) ||
        navigator.languages.length === 0) {
        Object.defineProperty(navigator, 'languages', {
            get: function() { return Object.freeze(['en-US', 'en']); }
        });
    }

    /* §4.7  Console filtering — suppress bot-signal messages */
    var _origWarn = console.warn;
    console.warn = function() {
        var msg = arguments[0];
        if (typeof msg === 'string') {
            if (msg.indexOf('preloaded using link preload') !== -1) return;
            if (msg.indexOf('Private Access Token') !== -1) return;
        }
        return _origWarn.apply(console, arguments);
    };
    var _origError = console.error;
    console.error = function() {
        var msg = arguments[0];
        if (typeof msg === 'string') {
            if (msg.indexOf('600010') !== -1) return;
        }
        return _origError.apply(console, arguments);
    };

    /* §4.8  document.hasFocus() → always true */
    document.hasFocus = function() { return true; };

    /* §4.9  window.outerWidth / outerHeight → match inner */
    Object.defineProperty(window, 'outerWidth', {
        get: function() { return window.innerWidth; }
    });
    Object.defineProperty(window, 'outerHeight', {
        get: function() { return window.innerHeight; }
    });
})();
"""


# ──────────────────────────────────────────────────────────────
# §7 — WebRTC IP Leak Prevention  (Layer 3: JS Stub)
# ──────────────────────────────────────────────────────────────
# Replaces the native WebRTC API with fake implementations so that
# STUN/TURN requests can never leak the real IP.
# Guard: window._eW_ prevents double-injection.

_JS_WEBRTC_BLOCK = r"""
(function() {
    if (window._eW_) return;
    window._eW_ = true;

    /* FakePC — stubs all methods, returns empty promises */
    function FakePC(config) {
        this.localDescription = null;
        this.remoteDescription = null;
        this.signalingState = 'stable';
        this.iceConnectionState = 'new';
        this.iceGatheringState = 'new';
        this.connectionState = 'new';
        this.currentLocalDescription = null;
        this.currentRemoteDescription = null;
        this.pendingLocalDescription = null;
        this.pendingRemoteDescription = null;
        this.onicecandidate = null;
        this.ontrack = null;
        this.onicecandidateerror = null;
        this.onnegotiationneeded = null;
        this.onsignalingstatechange = null;
        this.oniceconnectionstatechange = null;
        this.onicegatheringstatechange = null;
        this.onconnectionstatechange = null;
        this.ondatachannel = null;
        this.onremovetrack = null;
    }
    FakePC.prototype.createOffer = function() {
        return Promise.resolve({type: 'offer', sdp: ''});
    };
    FakePC.prototype.createAnswer = function() {
        return Promise.resolve({type: 'answer', sdp: ''});
    };
    FakePC.prototype.setLocalDescription = function(desc) {
        this.localDescription = desc;
        this.currentLocalDescription = desc;
        return Promise.resolve();
    };
    FakePC.prototype.setRemoteDescription = function(desc) {
        this.remoteDescription = desc;
        this.currentRemoteDescription = desc;
        return Promise.resolve();
    };
    FakePC.prototype.addIceCandidate = function() {
        return Promise.resolve();
    };
    FakePC.prototype.createDataChannel = function(label) {
        return {label: label, readyState: 'closed', close: function() {}};
    };
    FakePC.prototype.getStats = function() {
        return Promise.resolve(new Map());
    };
    FakePC.prototype.close = function() {
        this.signalingState = 'closed';
        this.connectionState = 'closed';
        this.iceConnectionState = 'closed';
    };
    FakePC.prototype.addEventListener = function() {};
    FakePC.prototype.removeEventListener = function() {};
    FakePC.prototype.dispatchEvent = function() { return true; };

    window.RTCPeerConnection = FakePC;
    window.webkitRTCPeerConnection = FakePC;
    window.mozRTCPeerConnection = FakePC;

    window.RTCSessionDescription = function(init) {
        this.type = init ? init.type : '';
        this.sdp = init ? init.sdp : '';
    };

    window.RTCIceCandidate = function(init) {
        this.candidate = init ? init.candidate : '';
        this.sdpMid = init ? init.sdpMid : '';
        this.sdpMLineIndex = init ? init.sdpMLineIndex : 0;
    };
})();
"""


# ──────────────────────────────────────────────────────────────
# §6 — Fingerprint Spoofing: JS Injection Layer
# ──────────────────────────────────────────────────────────────


def build_fingerprint_script(profile: FingerprintProfile) -> str:
    """Build the JavaScript fingerprint-spoofing script.

    Fills the gaps where CDP Emulation APIs do not reach (screen properties,
    WebGL, userAgentData, plugins, etc.).  The generated script is injected
    via ``CDP Page.addScriptToEvaluateOnNewDocument(runImmediately=True)``.

    Args:
        profile: Fingerprint profile with spoofing values.

    Returns:
        JavaScript source code string.
    """
    version = profile.chrome_version
    full_version = f"{version}.0.6422.112"
    mobile_js = "true" if profile.mobile else "false"

    # JSON-escape string values for safe JS interpolation (prevents injection)
    _version = json.dumps(version)
    _full_version = json.dumps(full_version)
    _platform = json.dumps(profile.platform)
    _platform_version = json.dumps(profile.platform_version)
    _language = json.dumps(profile.language)
    _webgl_vendor = json.dumps(profile.webgl_vendor)
    _webgl_renderer = json.dumps(profile.webgl_renderer)

    return f"""
(function() {{
    if (window._eP_) return;
    window._eP_ = true;

    /* §6.1  window.screen.* — CDP setDeviceMetricsOverride does NOT touch these */
    var _screen = Object.create(window.screen);
    Object.defineProperty(_screen, 'width',       {{ get: function() {{ return {profile.screen_width}; }} }});
    Object.defineProperty(_screen, 'height',      {{ get: function() {{ return {profile.screen_height}; }} }});
    Object.defineProperty(_screen, 'availWidth',  {{ get: function() {{ return {profile.screen_width}; }} }});
    Object.defineProperty(_screen, 'availHeight', {{ get: function() {{ return {profile.screen_height} - 40; }} }});
    Object.defineProperty(_screen, 'colorDepth',  {{ get: function() {{ return 24; }} }});
    Object.defineProperty(_screen, 'pixelDepth',  {{ get: function() {{ return 24; }} }});
    Object.defineProperty(window, 'screen', {{
        get: function() {{ return _screen; }}
    }});

    /* §6.2  navigator.deviceMemory */
    Object.defineProperty(Navigator.prototype, 'deviceMemory', {{
        get: function() {{ return {profile.device_memory}; }}
    }});

    /* §6.3  navigator.hardwareConcurrency (safety net for CDP override) */
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
        get: function() {{ return {profile.hardware_concurrency}; }}
    }});

    /* §6.4  navigator.userAgentData (User-Agent Client Hints) */
    var _brands = Object.freeze([
        {{ brand: 'Google Chrome', version: {_version} }},
        {{ brand: 'Chromium', version: {_version} }},
        {{ brand: 'Not.A/Brand', version: '24' }}
    ]);
    var _uaData = {{
        brands: _brands,
        mobile: {mobile_js},
        platform: {_platform},
        getHighEntropyValues: function(hints) {{
            return Promise.resolve({{
                brands: _brands,
                mobile: {mobile_js},
                platform: {_platform},
                platformVersion: {_platform_version},
                architecture: 'x86',
                bitness: '64',
                model: '',
                uaFullVersion: {_full_version},
                fullVersionList: _brands.map(function(b) {{
                    return {{ brand: b.brand, version: {_full_version} }};
                }})
            }});
        }},
        toJSON: function() {{
            return {{
                brands: _brands,
                mobile: {mobile_js},
                platform: {_platform}
            }};
        }}
    }};
    Object.defineProperty(Navigator.prototype, 'userAgentData', {{
        get: function() {{ return _uaData; }}
    }});

    /* §6.5  navigator.languages / navigator.language */
    var _lang = {_language};
    var _baseLang = _lang.split('-')[0];
    var _langs = _baseLang !== _lang ? [_lang, _baseLang] : [_lang];
    Object.defineProperty(Navigator.prototype, 'language', {{
        get: function() {{ return _lang; }}
    }});
    Object.defineProperty(Navigator.prototype, 'languages', {{
        get: function() {{ return Object.freeze(_langs.slice()); }}
    }});

    /* §6.6  navigator.maxTouchPoints */
    Object.defineProperty(Navigator.prototype, 'maxTouchPoints', {{
        get: function() {{ return {profile.max_touch_points}; }}
    }});

    /* §6.7  WebGL vendor / renderer spoofing (CDP has NO WebGL override) */
    var origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        if (param === 0x9245) return {_webgl_vendor};
        if (param === 0x9246) return {_webgl_renderer};
        return origGetParam.call(this, param);
    }};
    var origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {{
        if (param === 0x9245) return {_webgl_vendor};
        if (param === 0x9246) return {_webgl_renderer};
        return origGetParam2.call(this, param);
    }};

    /* §6.10  navigator.platform override */
    Object.defineProperty(Navigator.prototype, 'platform', {{
        get: function() {{ return {_platform}; }}
    }});

    /* §6.11  navigator.connection (NetworkInformation API) */
    if (navigator.connection) {{
        var _conn = Object.create(Object.getPrototypeOf(navigator.connection));
        Object.defineProperty(_conn, 'downlink',      {{ get: function() {{ return 10; }} }});
        Object.defineProperty(_conn, 'effectiveType', {{ get: function() {{ return '4g'; }} }});
        Object.defineProperty(_conn, 'rtt',           {{ get: function() {{ return 50; }} }});
        Object.defineProperty(_conn, 'saveData',      {{ get: function() {{ return false; }} }});
        Object.defineProperty(Navigator.prototype, 'connection', {{
            get: function() {{ return _conn; }}
        }});
    }}

    /* §6.12  navigator.plugins — empty array is an automation signal */
    var _plugins = {{
        0: {{ name: 'PDF Viewer',         filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
        1: {{ name: 'Chrome PDF Viewer',   filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
        2: {{ name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
        length: 3,
        item: function(i) {{ return this[i] || null; }},
        namedItem: function(n) {{
            for (var i = 0; i < this.length; i++) {{
                if (this[i].name === n) return this[i];
            }}
            return null;
        }},
        refresh: function() {{}}
    }};
    Object.defineProperty(Navigator.prototype, 'plugins', {{
        get: function() {{ return _plugins; }}
    }});

    /* §6.13  chrome.loadTimes — missing = automation */
    if (window.chrome) {{
        window.chrome.loadTimes = function() {{
            return {{
                requestTime: performance.timing.navigationStart / 1000,
                startLoadTime: performance.timing.navigationStart / 1000,
                commitLoadTime: performance.timing.navigationStart / 1000 + 0.1,
                finishDocumentLoadTime: performance.timing.loadEventEnd / 1000 || Date.now() / 1000,
                finishLoadTime: performance.timing.loadEventEnd / 1000 || Date.now() / 1000,
                firstPaintTime: 0,
                firstPaintAfterLoadTime: 0,
                navigationType: 'Other',
                wasFetchedViaSpdy: false,
                wasNpnNegotiated: true,
                npnNegotiatedProtocol: 'h2',
                wasAlternateProtocolAvailable: false,
                connectionInfo: 'h2'
            }};
        }};

        /* §6.14  chrome.csi — missing = automation */
        window.chrome.csi = function() {{
            return {{
                onloadT: Date.now(),
                pageT: performance.now(),
                startE: Date.now(),
                tran: 15
            }};
        }};
    }}

    /* §6.9  Performance.hardwareConcurrency safety net */
    if (window.Performance && window.Performance.prototype) {{
        Object.defineProperty(window.Performance.prototype, 'hardwareConcurrency', {{
            get: function() {{ return {profile.hardware_concurrency}; }}
        }});
    }}
}})();
"""


# ──────────────────────────────────────────────────────────────
# §7 — WebRTC Preferences  (Layer 1: Chromium Preferences)
# ──────────────────────────────────────────────────────────────


def inject_webrtc_prefs(user_data_dir: str) -> None:
    """Write WebRTC preferences into Chrome's ``Default/Preferences`` file.

    This is **Layer 1 of 3** for WebRTC IP leak prevention and must be called
    *before* the browser is launched, because Chrome reads this file on startup.

    Args:
        user_data_dir: Path to the Chrome user-data directory.
    """
    prefs_path = Path(user_data_dir) / "Default" / "Preferences"
    prefs_path.parent.mkdir(parents=True, exist_ok=True)

    prefs: dict = {}
    if prefs_path.exists():
        try:
            with open(prefs_path, "r") as f:
                prefs = json.load(f)
        except (json.JSONDecodeError, OSError):
            prefs = {}

    # WebRTC core prefs
    prefs.setdefault("profile", {})
    prefs["profile"]["webRTC"] = {
        "multiple_routes_enabled": False,
        "nonproxied_udp_enabled": False,
        "network_link_capacity_estimate": False,
    }

    # default_public_interface_only (= 1)
    prefs.setdefault("default_content_setting_values", {})
    prefs["default_content_setting_values"]["webrtc_ip_handling_policy"] = 1

    # Enable mDNS for local-IP masking
    prefs.setdefault("browser", {})
    prefs["browser"]["enabled_labs_experiments"] = [
        "enable-webrtc-hide-local-ips-with-mdns@1",
    ]

    try:
        with open(prefs_path, "w") as f:
            json.dump(prefs, f, indent=2)
        logger.debug("WebRTC preferences injected into %s", prefs_path)
    except OSError as exc:
        logger.warning("Failed to write WebRTC preferences: %s", exc)


# ──────────────────────────────────────────────────────────────
# §5 — CDP Fingerprint Emulation + Script Injection
# ──────────────────────────────────────────────────────────────


async def apply_stealth(browser, profile: FingerprintProfile) -> bool:
    """Apply all anti-detection measures to a browser instance.

    Must be called **after** ``uc.start()`` but **before** navigating to the
    target URL.  Uses CDP commands for server-side overrides and injects three
    JavaScript stealth scripts via ``addScriptToEvaluateOnNewDocument`` so they
    run before any page JavaScript on *every* new document.

    Injection order (critical):

    1. ``Debugger.disable()`` — prevents Turnstile ``debugger;`` timing detection
    2. ``Page.set_bypass_csp(True)`` — ensures JS injection is not blocked by CSP
    3. CDP fingerprint overrides — UserAgent, timezone, locale, viewport, HW concurrency
    4. Global stealth script — navigator.webdriver, cdc_*, chrome object, etc.
    5. WebRTC block script — replaces RTCPeerConnection with stubs
    6. Fingerprint script — screen, WebGL, plugins, userAgentData, etc.

    Args:
        browser: nodriver ``Browser`` instance (just created).
        profile: Fingerprint profile to apply.

    Returns:
        ``True`` if stealth was fully applied, ``False`` if any critical step failed.
    """
    try:
        tab = browser.main_tab
        if tab is None:
            logger.warning("No main tab available for stealth application")
            return False

        # Import CDP command modules — these are auto-generated from the CDP spec.
        try:
            from nodriver.cdp import debugger as cdp_debugger
            from nodriver.cdp import emulation as cdp_emulation
            from nodriver.cdp import network as cdp_network
            from nodriver.cdp import page as cdp_page
        except ImportError as exc:
            logger.warning("CDP modules not available — stealth skipped: %s", exc)
            return False

        # ── Step 1: Debugger.disable() — must come first ──────
        try:
            await tab.send(cdp_debugger.disable())
        except Exception:
            logger.debug("Debugger.disable() skipped (debugger may not be attached)")

        # ── Step 2: Bypass CSP ────────────────────────────────
        try:
            await tab.send(cdp_page.set_bypass_csp(True))
        except Exception as exc:
            logger.debug("set_bypass_csp failed: %s", exc)

        # ── Step 3: CDP fingerprint overrides ─────────────────

        # User-Agent (+ Accept-Language header, platform header)
        try:
            await tab.send(cdp_network.set_user_agent_override(
                user_agent=profile.user_agent,
                accept_language=f"{profile.language},en;q=0.9",
                platform=profile.platform,
            ))
        except Exception as exc:
            logger.debug("set_user_agent_override failed: %s", exc)

        # Timezone
        try:
            await tab.send(cdp_emulation.set_timezone_override(
                timezone_id=profile.timezone,
            ))
        except Exception as exc:
            logger.debug("set_timezone_override failed: %s", exc)

        # Locale
        try:
            await tab.send(cdp_emulation.set_locale_override(
                locale=profile.language,
            ))
        except Exception as exc:
            logger.debug("set_locale_override failed: %s", exc)

        # Viewport / device metrics
        try:
            await tab.send(cdp_emulation.set_device_metrics_override(
                width=profile.screen_width,
                height=profile.screen_height,
                device_scale_factor=1,
                mobile=profile.mobile,
            ))
        except Exception as exc:
            logger.debug("set_device_metrics_override failed: %s", exc)

        # Hardware concurrency
        try:
            await tab.send(cdp_emulation.set_hardware_concurrency_override(
                hardware_concurrency=profile.hardware_concurrency,
            ))
        except Exception as exc:
            logger.debug("set_hardware_concurrency_override failed: %s", exc)

        # ── Steps 4-6: Inject JS stealth scripts ──────────────
        fingerprint_script = build_fingerprint_script(profile)

        scripts = [
            ("global_stealth", _JS_GLOBAL_STEALTH),
            ("webrtc_block", _JS_WEBRTC_BLOCK),
            ("fingerprint", fingerprint_script),
        ]

        for name, script in scripts:
            # Register for all FUTURE navigations
            try:
                await tab.send(cdp_page.add_script_to_evaluate_on_new_document(
                    source=script,
                    run_immediately=True,
                ))
            except Exception as exc:
                logger.debug("add_script (%s) failed: %s", name, exc)

            # Also evaluate IMMEDIATELY on the current page (about:blank)
            try:
                await tab.evaluate(script)
            except Exception:
                # Expected to fail on about:blank for some scripts
                logger.debug("Immediate evaluate (%s) skipped", name)

        logger.debug(
            "Stealth applied: UA=%s… tz=%s screen=%dx%d",
            profile.user_agent[:60],
            profile.timezone,
            profile.screen_width,
            profile.screen_height,
        )
        return True

    except Exception as exc:
        logger.warning("Failed to apply stealth measures: %s", exc)
        return False
