"""Browser anti-detection and fingerprinting module for Camoufox (Firefox/Gecko).

Camoufox handles most anti-detection at the C++/BrowserForge level.
This module provides the JavaScript safety net that fills remaining gaps:

1. JS Stealth — navigator.webdriver cleanup, permission overrides (§4)
2. JS Font Spoof — FontFaceSet filtering, CSS prototype overrides (§6/§11)
3. JS WebRTC Spoof — Functional RTCPeerConnection with IP sanitization (§10)
4. JS Fingerprint — Screen, navigator, WebGL, oscpu overrides (§5)

Each section is numbered to match BROWSER_STEALTH_REFERENCE.md.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Windows 10 Font List for Camoufox
# ──────────────────────────────────────────────────────────────

WIN10_FONTS = [
    "Arial", "Segoe UI", "Consolas", "Times New Roman",
    "Calibri", "Cambria", "Candara", "Courier New",
    "Georgia", "Impact", "Lucida Console", "Lucida Sans Unicode",
    "MS Sans Serif", "MS Serif", "Palatino Linotype",
    "Tahoma", "Trebuchet MS", "Verdana",
    "Arial Black", "Arial Narrow", "Book Antiqua",
    "Bookman Old Style", "Century Gothic", "Century Schoolbook",
    "Comic Sans MS", "Copperplate Gothic", "Courier",
    "Ebrima", "Franklin Gothic", "Gabriola",
    "Gadugi", "Garamond", "Gautami",
    "Gill Sans MT", "Gloucester MT", "Goudy Old Style",
    "Haettenschweiler", "HoloLens MDL2 Assets", "Impact",
    "Imprint MT Shadow", "Informal Roman", "Javanese Text",
    "Kartika", "Khmer UI", "KodchiangUPC",
    "Lao UI", "Lucida Bright", "Lucida Calligraphy",
    "Lucida Fax", "Lucida Handwriting", "Lucida Sans",
    "Lucida Sans Typewriter", "Magneto", "Maiandra GD",
    "Malgun Gothic", "Microsoft Himalaya", "Microsoft JhengHei",
    "Microsoft New Tai Lue", "Microsoft PhagsPa", "Microsoft Sans Serif",
    "Microsoft Tai Le", "Microsoft Uighur", "Microsoft YaHei",
    "Microsoft Yi Baiti", "MingLiU", "Modern",
    "Mongolian Baiti", "Monotype Corsiva", "Myanmar Text",
    "Narkisim", "Niagara Engraved", "Niagara Solid",
    "NSimSun", "Nyala", "OCR A Extended",
    "Old English Text MT", "Onyx", "Palace Script MT",
    "Papyrus", "Parchment", "Perpetua",
    "Perpetua Titling MT", "Playbill", "Poor Richard",
    "Pristina", "Rage Italic", "Ravie",
    "Rockwell", "Script MT Bold", "Segoe Print",
    "Segoe Script", "Segoe UI Historic", "Segoe UI Symbol",
    "Showcard Gothic", "SimSun", "Snap ITC",
    "Stencil", "Sylfaen", "Symbol",
    "Tamil Latha", "Telugu", "Times New Roman",
    "Traditional Arabic", "Trebuchet MS", "Tunga",
    "Urdu Typesetting", "Vani", "Verdana",
    "Vijaya", "Webdings", "Wingdings",
    "Wingdings 2", "Wingdings 3",
]

# ──────────────────────────────────────────────────────────────
# Firefox User Preferences — The "Nuclear Option"
# ──────────────────────────────────────────────────────────────

_LOCALE_BRANCHES = [
    "x-western", "tr", "az", "x-central-euro", "x-cyrillic",
    "x-baltic", "el", "he", "ar", "th",
    "zh-CN", "zh-HK", "zh-TW", "ja", "ko",
    "x-unicode", "x-user-def",
]


def build_firefox_prefs() -> dict[str, object]:
    """Build Firefox about:config preferences for Windows spoofing.

    Returns a dict of 50+ prefs that sever Gecko's connection to the
    Linux host OS.  Pass these to ``AsyncCamoufox(firefox_user_prefs=...)``.

    Categories:
    1. GTK / XDG Desktop Portal Isolation
    2. Font Visibility (Level 3 — All Fonts)
    3. CSS Generic Family Overrides (17 Locales)
    4. Font System Whitelist
    5. UI Element Fonts
    """
    prefs: dict[str, object] = {}

    # ── 1. GTK / XDG Desktop Portal Isolation ────────────────
    prefs["widget.non-native-theme.enabled"] = True
    prefs["widget.use-xdg-desktop-portal.settings"] = 0

    # ── 2. Font Visibility (Level 3 — All Fonts) ─────────────
    prefs["layout.css.font-visibility.standard"] = 3
    prefs["layout.css.font-visibility.private"] = 3
    prefs["layout.css.font-visibility.tracking-protection"] = 3

    # ── 3. CSS Generic Family Overrides (17 Locales) ─────────
    for _loc in _LOCALE_BRANCHES:
        prefs[f"font.name-list.system-ui.{_loc}"] = "Segoe UI, Arial, sans-serif"
        prefs[f"font.name.system-ui.{_loc}"] = "Segoe UI"
        prefs[f"font.name.sans-serif.{_loc}"] = "Arial"
        prefs[f"font.name-list.sans-serif.{_loc}"] = "Arial, Segoe UI, sans-serif"
        prefs[f"font.name.serif.{_loc}"] = "Times New Roman"
        prefs[f"font.name-list.serif.{_loc}"] = "Times New Roman, serif"
        prefs[f"font.name.monospace.{_loc}"] = "Consolas"
        prefs[f"font.name-list.monospace.{_loc}"] = "Consolas, Courier New, monospace"

    # ── 4. Font System Whitelist ──────────────────────────────
    prefs["font.system.whitelist"] = (
        "Arial, Consolas, Courier New, Georgia, Impact, Lucida Console, "
        "Lucida Sans Unicode, MS Sans Serif, MS Serif, Palatino Linotype, "
        "Segoe UI, Tahoma, Times New Roman, Trebuchet MS, Verdana"
    )

    # ── 5. UI Element Fonts (prevent GTK font leaks) ─────────
    prefs["ui.font.menu"] = "12px 'Segoe UI'"
    prefs["ui.font.icon"] = "12px 'Segoe UI'"
    prefs["ui.font.caption"] = "12px 'Segoe UI'"
    prefs["ui.font.status-bar"] = "12px 'Segoe UI'"
    prefs["ui.font.message-box"] = "12px 'Segoe UI'"
    prefs["ui.font.small-caption"] = "12px 'Segoe UI'"

    return prefs


# ──────────────────────────────────────────────────────────────
# §12 — Fingerprint Profile (Device Template)
# ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FingerprintProfile:
    """Consistent browser fingerprint for anti-detection.

    Default values represent a common Windows desktop profile.
    Camoufox handles most of these at C++/BrowserForge level;
    the JS safety net fills remaining gaps.

    Note: For Camoufox, the primary OS/platform/user-agent spoofing
    happens via the ``os=`` parameter.  These fields are used by the
    JS safety net for defense-in-depth.
    """

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
        "Gecko/20100101 Firefox/140.0"
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


# Default profile — a realistic Windows desktop Firefox setup.
DEFAULT_FINGERPRINT = FingerprintProfile()


# ──────────────────────────────────────────────────────────────
# §11 — JS Stealth Layer (Minimal Automation Cleanup)
# ──────────────────────────────────────────────────────────────

_JS_STEALTH = r"""
(function() {
    if (window._eFz_) return;
    window._eFz_ = true;

    /* navigator.webdriver → undefined (Firefox-native clean) */
    Object.defineProperty(navigator, 'webdriver', {
        get: function() { return undefined; },
        configurable: true
    });

    /* navigator.permissions.query override */
    var _origPermsQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = function(desc) {
        if (desc && desc.name === 'notifications') {
            return Promise.resolve({state: 'prompt', onchange: null});
        }
        return _origPermsQuery(desc);
    };

    /* navigator.languages consistency */
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

    /* document.hasFocus() → always true */
    document.hasFocus = function() { return true; };

    /* window.outerWidth / outerHeight → match inner */
    Object.defineProperty(window, 'outerWidth', {
        get: function() { return window.innerWidth; }
    });
    Object.defineProperty(window, 'outerHeight', {
        get: function() { return window.innerHeight; }
    });

    /* Chrome-only global cleanup (Firefox only) */
    ['chrome', 'opr', 'yandex'].forEach(function(p) {
        if (window[p]) { delete window[p]; }
    });
})();
"""


# ──────────────────────────────────────────────────────────────
# §10 — WebRTC Spoofing (Functional IP Sanitization)
# ──────────────────────────────────────────────────────────────
# Replaces native RTCPeerConnection with a functional wrapper that
# sanitizes ICE candidates and SDP descriptions.
# Guard: window._eW_ prevents double-injection.


def build_webrtc_spoof(proxy_ip: str = "0.0.0.0") -> str:
    """Build the WebRTC spoof init script with the given proxy IP.

    Args:
        proxy_ip: Public IP of the proxy to inject into ICE candidates.

    Returns:
        JavaScript source code string.
    """
    _ip = json.dumps(proxy_ip)
    return f"""
(function() {{
    if (window._eW_) return;
    window._eW_ = true;

    var _proxyIP = {_ip};

    /* ── IP replacement in SDP ─────────────────────────── */
    function _replaceIPs(sdp) {{
        return sdp.replace(/(\\d{{1,3}}\\.){{3}}\\d{{1,3}}/g, function(m) {{
            var p = m.split('.');
            /* Skip private / loopback / CGNAT ranges */
            if (p[0] === '10' || p[0] === '127' || p[0] === '0') return m;
            if (p[0] === '169' && p[1] === '254') return m;
            if (p[0] === '172' && parseInt(p[1]) >= 16 && parseInt(p[1]) <= 31) return m;
            if (p[0] === '192' && p[1] === '168') return m;
            if (p[0] === '100' && parseInt(p[1]) >= 64 && parseInt(p[1]) <= 127) return m;
            return _proxyIP;
        }});
    }}

    /* ── Candidate sanitizer ────────────────────────────── */
    function _sanitizeCandidate(e, ip) {{
        if (e.candidate && e.candidate.candidate) {{
            e.candidate.candidate = _replaceIPs(e.candidate.candidate);
        }}
    }}

    /* ── Wrapper class ──────────────────────────────────── */
    var NativePC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (!NativePC) return;

    function _WrappedPC(config) {{
        var self = this;
        var _pc = new NativePC(config);
        var _savedHandlers = {{}};
        var _origAdd = _pc.addEventListener.bind(_pc);

        /* Intercept createOffer */
        var _origCreateOffer = _pc.createOffer.bind(_pc);
        _pc.createOffer = function() {{
            return _origCreateOffer.apply(this, arguments).then(function(desc) {{
                if (desc && desc.sdp) desc.sdp = _replaceIPs(desc.sdp);
                return desc;
            }});
        }};

        /* Intercept createAnswer */
        var _origCreateAnswer = _pc.createAnswer.bind(_pc);
        _pc.createAnswer = function() {{
            return _origCreateAnswer.apply(this, arguments).then(function(desc) {{
                if (desc && desc.sdp) desc.sdp = _replaceIPs(desc.sdp);
                return desc;
            }});
        }};

        /* Intercept setLocalDescription */
        var _origSetLocal = _pc.setLocalDescription.bind(_pc);
        _pc.setLocalDescription = function(desc) {{
            if (desc && desc.sdp) desc.sdp = _replaceIPs(desc.sdp);
            return _origSetLocal(desc);
        }};

        /* Intercept setRemoteDescription */
        var _origSetRemote = _pc.setRemoteDescription.bind(_pc);
        _pc.setRemoteDescription = function(desc) {{
            if (desc && desc.sdp) desc.sdp = _replaceIPs(desc.sdp);
            return _origSetRemote(desc);
        }};

        /* Intercept onicecandidate */
        Object.defineProperty(_pc, 'onicecandidate', {{
            get: function() {{ return _savedHandlers['icecandidate']; }},
            set: function(fn) {{
                _savedHandlers['icecandidate'] = fn;
                if (fn) {{
                    _pc.addEventListener('icecandidate', function(e) {{
                        _sanitizeCandidate(e, _proxyIP);
                        fn.call(_pc, e);
                    }});
                }}
            }},
            configurable: true
        }});

        /* Intercept addEventListener for icecandidate */
        _pc.addEventListener = function(type, handler, options) {{
            if (type === 'icecandidate') {{
                var wrapped = function(e) {{
                    _sanitizeCandidate(e, _proxyIP);
                    handler.call(this, e);
                }};
                return _origAdd(type, wrapped, options);
            }}
            return _origAdd(type, handler, options);
        }};

        /* Proxy: expose underlying PC properties */
        var propNames = Object.getOwnPropertyNames(NativePC.prototype);
        propNames.forEach(function(name) {{
            if (!(name in self)) {{
                Object.defineProperty(self, name, {{
                    get: function() {{ return _pc[name]; }},
                    set: function(v) {{ _pc[name] = v; }},
                    configurable: true
                }});
            }}
        }});

        self._pc = _pc;
    }}

    /* Wrap all methods */
    var _methods = ['createOffer', 'createAnswer', 'setLocalDescription',
                    'setRemoteDescription', 'addIceCandidate', 'close',
                    'getStats', 'createDataChannel',
                    'addEventListener', 'removeEventListener', 'dispatchEvent'];
    _methods.forEach(function(m) {{
        if (NativePC.prototype[m]) {{
            _WrappedPC.prototype[m] = function() {{
                return this._pc[m].apply(this._pc, arguments);
            }};
        }}
    }});

    window.RTCPeerConnection = _WrappedPC;
    window.webkitRTCPeerConnection = _WrappedPC;
    window.mozRTCPeerConnection = _WrappedPC;
}})();
"""


# ──────────────────────────────────────────────────────────────
# §6 — Fingerprint Spoofing: JS Injection Layer
# ──────────────────────────────────────────────────────────────


def build_fingerprint_script(profile: FingerprintProfile) -> str:
    """Build the JavaScript fingerprint-spoofing script.

    Fills gaps not covered by Camoufox C++/BrowserForge:
    - window.screen.*
    - navigator.deviceMemory
    - navigator.languages / language
    - navigator.maxTouchPoints
    - WebGL vendor/renderer
    - navigator.platform (extra safety)
    - navigator.oscpu (Firefox-specific leak)
    - navigator.connection (NetworkInformation API)
    - navigator.plugins

    Args:
        profile: Fingerprint profile with spoofing values.

    Returns:
        JavaScript source code string.
    """
    _platform = json.dumps(profile.platform)
    _language = json.dumps(profile.language)
    _webgl_vendor = json.dumps(profile.webgl_vendor)
    _webgl_renderer = json.dumps(profile.webgl_renderer)

    return f"""
(function() {{
    if (window._eF_) return;
    window._eF_ = true;

    var _ua = navigator.userAgent;
    var _isFx = (_ua.indexOf('Firefox') !== -1);

    /* §6.1  window.screen.* */
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

    /* §6.3  navigator.hardwareConcurrency (safety net) */
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {{
        get: function() {{ return {profile.hardware_concurrency}; }}
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

    /* §6.7  WebGL vendor / renderer spoofing */
    if ({_webgl_vendor} && {_webgl_renderer}) {{
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
    }}

    /* §6.10  navigator.platform override */
    Object.defineProperty(Navigator.prototype, 'platform', {{
        get: function() {{ return {_platform}; }}
    }});

    /* §6.11  navigator.oscpu (Firefox-specific leak) */
    if (_isFx) {{
        Object.defineProperty(Navigator.prototype, 'oscpu', {{
            get: function() {{ return 'Windows NT 10.0; Win64; x64'; }}
        }});
    }}

    /* §6.12  navigator.connection (NetworkInformation API) */
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

    /* §6.13  navigator.plugins — Firefox-native plugin list */
    if (_isFx) {{
        var _plugins = {{
            0: {{ name: 'PDF Viewer',         filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
            1: {{ name: 'DRM Content Decryption Module', filename: 'drm-cdm', description: 'Widevine Content Decryption Module' }},
            2: {{ name: 'Firefox PDF Viewer',  filename: 'internal-pdf-viewer', description: 'Firefox PDF Viewer' }},
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
    }}

    /* §6.14  Firefox internal consistency */
    if (_isFx) {{
        Object.defineProperty(Navigator.prototype, 'vendor', {{
            get: function() {{ return ''; }}
        }});
        Object.defineProperty(Navigator.prototype, 'product', {{
            get: function() {{ return 'Gecko'; }}
        }});
        Object.defineProperty(Navigator.prototype, 'buildID', {{
            get: function() {{ return '20181001000000'; }}
        }});
    }}

    /* Performance.hardwareConcurrency safety net */
    if (window.Performance && window.Performance.prototype) {{
        Object.defineProperty(window.Performance.prototype, 'hardwareConcurrency', {{
            get: function() {{ return {profile.hardware_concurrency}; }}
        }});
    }}
}})();
"""


# ──────────────────────────────────────────────────────────────
# §6/§11 — JS Font Spoof (Font Whitelist + CSS Prototype Overrides)
# ──────────────────────────────────────────────────────────────

_JS_FONT_SPOOF = r"""
(function() {
    if (window._eFzF_) return;
    window._eFzF_ = true;

    /* Windows 10 font whitelist (lowercase) */
    var _fonts = {};
    var _fontList = [
        'arial', 'segoe ui', 'consolas', 'times new roman',
        'calibri', 'cambria', 'candara', 'courier new',
        'georgia', 'impact', 'lucida console', 'lucida sans unicode',
        'ms sans serif', 'ms serif', 'palatino linotype',
        'tahoma', 'trebuchet ms', 'verdana',
        'arial black', 'arial narrow', 'book antiqua',
        'bookman old style', 'century gothic', 'comic sans ms',
        'courier', 'ebrima', 'franklin gothic',
        'gabriola', 'gadugi', 'garamond',
        'gill sans mt', 'goudy old style', 'haettenschweiler',
        'lucida bright', 'lucida calligraphy', 'lucida fax',
        'lucida handwriting', 'lucida sans', 'magneto',
        'maiandra gd', 'malgun gothic', 'microsoft sans serif',
        'microsoft yahei', 'monotype corsiva', 'nyala',
        'ocr a extended', 'old english text mt', 'onyx',
        'palace script mt', 'papyrus', 'parchment',
        'perpetua', 'playbill', 'poor richard',
        'pristina', 'rage italic', 'ravie',
        'rockwell', 'script mt bold', 'segoe print',
        'segoe script', 'segoe ui historic', 'segoe ui symbol',
        'showcard gothic', 'simsun', 'snap itc',
        'stencil', 'sylfaen', 'symbol',
        'webdings', 'wingdings'
    ];
    _fontList.forEach(function(f) { _fonts[f] = true; });

    function _ok(family) {
        if (!family) return true;
        var f = family.toLowerCase().replace(/["']/g, '').trim();
        /* Always allow CSS generic families */
        if (f === 'sans-serif' || f === 'serif' || f === 'monospace' ||
            f === 'system-ui' || f === 'cursive' || f === 'fantasy') return true;
        return !!_fonts[f];
    }

    /* ── FontFaceSet Iteration Filtering ─────────────────── */
    function _filteredForEach(callback, thisArg) {
        var self = this;
        var orig = FontFaceSet.prototype.forEach;
        return orig.call(self, function(face) {
            if (_ok(face.family)) {
                callback.call(thisArg, face);
            }
        });
    }

    function _filteredIterator() {
        var self = this;
        var faces = [];
        FontFaceSet.prototype.forEach.call(self, function(face) {
            if (_ok(face.family)) faces.push(face);
        });
        var idx = 0;
        return {
            next: function() {
                if (idx < faces.length) return {value: faces[idx++], done: false};
                return {value: undefined, done: true};
            }
        };
    }

    if (window.FontFaceSet) {
        FontFaceSet.prototype.forEach = _filteredForEach;
        FontFaceSet.prototype.values = _filteredIterator;
        FontFaceSet.prototype.entries = _filteredIterator;
        FontFaceSet.prototype.keys = _filteredIterator;
        FontFaceSet.prototype[Symbol.iterator] = _filteredIterator;
    }

    /* ── queryLocalFonts() Filtering ─────────────────────── */
    if (window.queryLocalFonts) {
        var _origQuery = window.queryLocalFonts.bind(window);
        window.queryLocalFonts = function() {
            return _origQuery().then(function(fonts) {
                return fonts.filter(function(f) { return _ok(f.family); });
            });
        };
    }

    /* ── CSS Prototype Override (CreepJS Defense) ────────── */
    var _cssProto = CSSStyleDeclaration.prototype;
    var _origGetPropertyValue = _cssProto.getPropertyValue;
    _cssProto.getPropertyValue = function(prop) {
        var val = _origGetPropertyValue.call(this, prop);
        if ((prop === 'font-family' || prop === 'font') && val) {
            if (val.includes('Cantarell') || val.includes('Ubuntu') ||
                val.includes('Linux') || val.includes('system-ui') || val.includes('sans-serif')) {
                return val.replace(/Cantarell|Ubuntu|Linux|sans-serif|system-ui/g, 'Segoe UI');
            }
        }
        return val;
    };

    var _descFontFamily = Object.getOwnPropertyDescriptor(_cssProto, 'fontFamily');
    if (_descFontFamily && _descFontFamily.get) {
        Object.defineProperty(_cssProto, 'fontFamily', {
            get: function() {
                var val = _descFontFamily.get.call(this);
                if (val && (val.includes('Cantarell') || val.includes('Ubuntu') || val.includes('Linux'))) {
                    return 'Segoe UI, Arial, sans-serif';
                }
                return val;
            },
            set: _descFontFamily.set,
            configurable: true
        });
    }

    var _descFont = Object.getOwnPropertyDescriptor(_cssProto, 'font');
    if (_descFont && _descFont.get) {
        Object.defineProperty(_cssProto, 'font', {
            get: function() {
                var val = _descFont.get.call(this);
                if (val && (val.includes('Cantarell') || val.includes('Ubuntu') || val.includes('Linux'))) {
                    return val.replace(/Cantarell|Ubuntu|Linux|sans-serif|system-ui/g, 'Segoe UI');
                }
                return val;
            },
            set: _descFont.set,
            configurable: true
        });
    }
})();
"""


# ──────────────────────────────────────────────────────────────
# Stealth Application Helper
# ──────────────────────────────────────────────────────────────


async def apply_stealth(page, profile: FingerprintProfile, proxy_ip: str = "") -> None:
    """Apply all JS stealth init scripts to a page.

    Injection order (critical):
    1. ``_JS_STEALTH`` — navigator.webdriver cleanup, permissions
    2. ``_JS_FONT_SPOOF`` — Font whitelist + CSS prototype overrides
    3. ``_JS_WEBRTC_SPOOF`` — ICE candidate sanitization
    4. ``fingerprint_script`` — Screen/navigator/WebGL/oscpu spoofing

    Args:
        page: Playwright ``Page`` instance (from ``browser.new_page()``).
        profile: Fingerprint profile to apply.
        proxy_ip: Public IP of the proxy for WebRTC spoofing (optional).
    """
    scripts = [
        ("stealth", _JS_STEALTH),
        ("font_spoof", _JS_FONT_SPOOF),
        ("webrtc_spoof", build_webrtc_spoof(proxy_ip)),
        ("fingerprint", build_fingerprint_script(profile)),
    ]

    for name, script in scripts:
        try:
            await page.add_init_script(script)
            logger.debug("Init script '%s' registered", name)
        except Exception as exc:
            logger.debug("Init script '%s' failed: %s", name, exc)

    logger.debug(
        "Stealth applied: %d scripts, screen=%dx%d, tz=%s",
        len(scripts),
        profile.screen_width,
        profile.screen_height,
        profile.timezone,
    )
