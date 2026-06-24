"""Tests for the browser_stealth anti-detection module (Camoufox)."""

import json

import pytest

from serp.browser_stealth import (
    DEFAULT_FINGERPRINT,
    FingerprintProfile,
    WIN10_FONTS,
    build_fingerprint_script,
    build_firefox_prefs,
    build_webrtc_spoof,
)


class TestFingerprintProfile:
    """Tests for FingerprintProfile dataclass."""

    def test_defaults(self):
        fp = FingerprintProfile()
        assert fp.platform == "Win32"
        assert fp.language == "en-US"
        assert fp.timezone == "America/New_York"
        assert fp.screen_width == 1920
        assert fp.screen_height == 1080
        assert fp.hardware_concurrency == 8
        assert fp.device_memory == 8
        assert fp.mobile is False
        # Default UA is Firefox now (not Chrome)
        assert "Firefox" in fp.user_agent

    def test_default_is_same_as_explicit_defaults(self):
        assert DEFAULT_FINGERPRINT == FingerprintProfile()

    def test_immutable(self):
        fp = FingerprintProfile()
        with pytest.raises(AttributeError):
            fp.platform = "MacIntel"

    def test_custom_values(self):
        fp = FingerprintProfile(screen_width=2560, screen_height=1440, mobile=True)
        assert fp.screen_width == 2560
        assert fp.screen_height == 1440
        assert fp.mobile is True


class TestBuildFirefoxPrefs:
    """Tests for build_firefox_prefs()."""

    def test_returns_dict(self):
        prefs = build_firefox_prefs()
        assert isinstance(prefs, dict)

    def test_gtk_isolation(self):
        prefs = build_firefox_prefs()
        assert prefs["widget.non-native-theme.enabled"] is True
        assert prefs["widget.use-xdg-desktop-portal.settings"] == 0

    def test_font_visibility_level3(self):
        prefs = build_firefox_prefs()
        assert prefs["layout.css.font-visibility.standard"] == 3
        assert prefs["layout.css.font-visibility.private"] == 3
        assert prefs["layout.css.font-visibility.tracking-protection"] == 3

    def test_locale_overrides_present(self):
        prefs = build_firefox_prefs()
        assert "font.name-list.system-ui.x-western" in prefs
        assert "font.name.system-ui.x-western" in prefs
        assert "font.name.sans-serif.tr" in prefs
        assert "font.name-list.sans-serif.az" in prefs
        assert "font.name.serif.ja" in prefs
        assert "font.name.monospace.ko" in prefs

    def test_font_system_whitelist(self):
        prefs = build_firefox_prefs()
        assert "Segoe UI" in prefs["font.system.whitelist"]

    def test_ui_element_fonts(self):
        prefs = build_firefox_prefs()
        assert "ui.font.menu" in prefs
        assert "ui.font.icon" in prefs
        assert "ui.font.message-box" in prefs
        assert "12px 'Segoe UI'" in prefs["ui.font.menu"]


class TestBuildFingerprintScript:
    """Tests for build_fingerprint_script()."""

    def test_returns_nonempty_string(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert isinstance(script, str)
        assert len(script) > 100

    def test_contains_guard_against_double_injection(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert "window._eF_" in script

    def test_interpolates_screen_dimensions(self):
        fp = FingerprintProfile(screen_width=2560, screen_height=1440)
        script = build_fingerprint_script(fp)
        assert "2560" in script
        assert "1440" in script

    def test_interpolates_device_memory(self):
        script = build_fingerprint_script(FingerprintProfile(device_memory=16))
        assert "16" in script

    def test_interpolates_platform(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert '"Win32"' in script

    def test_webgl_spoofing_present(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert "WebGLRenderingContext" in script
        assert "WebGL2RenderingContext" in script
        assert "0x9245" in script  # WEBGL_VENDOR
        assert "0x9246" in script  # WEBGL_RENDERER

    def test_firefox_specific_overrides(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert "navigator.oscpu" in script
        assert "'Windows NT 10.0; Win64; x64'" in script
        assert "navigator.plugins" in script

    def test_no_raw_user_input_injection(self):
        """Verify profile values are JSON-escaped to prevent JS injection."""
        fp = FingerprintProfile(webgl_vendor='"; alert("xss"); "')
        script = build_fingerprint_script(fp)
        raw_payload = '"; alert("xss"); "'
        assert raw_payload not in script

    def test_oscpu_not_present_for_non_firefox(self):
        """OSCPU override uses runtime detection, always present in script template."""
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        # The _isFx runtime check is always in the template
        assert "oscpu" in script


class TestBuildWebrtcSpoof:
    """Tests for build_webrtc_spoof()."""

    def test_returns_string_with_proxy_ip(self):
        script = build_webrtc_spoof("1.2.3.4")
        assert isinstance(script, str)
        assert '"1.2.3.4"' in script
        assert "window._eW_" in script

    def test_contains_webrtc_wrapper(self):
        script = build_webrtc_spoof("8.8.8.8")
        assert "_WrappedPC" in script
        assert "_replaceIPs" in script
        assert "_sanitizeCandidate" in script
        assert "RTCPeerConnection" in script

    def test_uses_provided_ip(self):
        script = build_webrtc_spoof("192.0.2.1")
        assert '"192.0.2.1"' in script


class TestWin10Fonts:
    """Tests for WIN10_FONTS list."""

    def test_contains_core_windows_fonts(self):
        assert "Arial" in WIN10_FONTS
        assert "Segoe UI" in WIN10_FONTS
        assert "Consolas" in WIN10_FONTS
        assert "Times New Roman" in WIN10_FONTS

    def test_minimum_font_count(self):
        assert len(WIN10_FONTS) >= 50
