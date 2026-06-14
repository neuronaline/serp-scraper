"""Tests for the browser_stealth anti-detection module."""

import json
import tempfile
from pathlib import Path

import pytest

from serp.browser_stealth import (
    DEFAULT_FINGERPRINT,
    FingerprintProfile,
    build_chrome_flags,
    build_fingerprint_script,
    inject_webrtc_prefs,
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

    def test_default_is_same_as_explicit_defaults(self):
        assert DEFAULT_FINGERPRINT == FingerprintProfile()

    def test_immutable(self):
        fp = FingerprintProfile()
        with pytest.raises(AttributeError):
            fp.platform = "MacIntel"

    def test_chrome_version_extracts_from_ua(self):
        fp = FingerprintProfile(user_agent="Mozilla/5.0 Chrome/128.0.0.0 Safari/537.36")
        assert fp.chrome_version == "128"

    def test_chrome_version_fallback(self):
        fp = FingerprintProfile(user_agent="no-chrome-here")
        assert fp.chrome_version == "125"

    def test_platform_version_win32(self):
        assert FingerprintProfile(platform="Win32").platform_version == "15.0.0"

    def test_platform_version_other(self):
        assert FingerprintProfile(platform="MacIntel").platform_version == "10.15.7"

    def test_custom_values(self):
        fp = FingerprintProfile(screen_width=2560, screen_height=1440, mobile=True)
        assert fp.screen_width == 2560
        assert fp.screen_height == 1440
        assert fp.mobile is True


class TestBuildChromeFlags:
    """Tests for build_chrome_flags()."""

    def test_returns_list_of_strings(self):
        flags = build_chrome_flags(DEFAULT_FINGERPRINT)
        assert isinstance(flags, list)
        assert all(isinstance(f, str) for f in flags)

    def test_contains_core_stealth_flags(self):
        flags = build_chrome_flags(DEFAULT_FINGERPRINT)
        flags_str = " ".join(flags)
        assert "--disable-blink-features=AutomationControlled" in flags
        assert "--disable-dev-shm-usage" in flags
        assert "--no-first-run" in flags
        assert "--disable-extensions" in flags
        assert "--disable-infobars" in flags

    def test_contains_webrtc_flags(self):
        flags = build_chrome_flags(DEFAULT_FINGERPRINT)
        assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in flags

    def test_window_size_uses_profile(self):
        fp = FingerprintProfile(screen_width=2560, screen_height=1440)
        flags = build_chrome_flags(fp)
        assert "--window-size=2560,1440" in flags


class TestBuildFingerprintScript:
    """Tests for build_fingerprint_script()."""

    def test_returns_nonempty_string(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert isinstance(script, str)
        assert len(script) > 100

    def test_contains_guard_against_double_injection(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert "window._eP_" in script

    def test_interpolates_screen_dimensions(self):
        fp = FingerprintProfile(screen_width=2560, screen_height=1440)
        script = build_fingerprint_script(fp)
        assert "2560" in script
        assert "1440" in script

    def test_interpolates_device_memory(self):
        script = build_fingerprint_script(FingerprintProfile(device_memory=16))
        assert "16" in script

    def test_interpolates_chrome_version(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        # DEFAULT has Chrome 125 in user_agent
        assert '"125"' in script

    def test_interpolates_platform(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert '"Win32"' in script

    def test_webgl_spoofing_present(self):
        script = build_fingerprint_script(DEFAULT_FINGERPRINT)
        assert "WebGLRenderingContext" in script
        assert "WebGL2RenderingContext" in script
        assert "0x9245" in script  # WEBGL_VENDOR
        assert "0x9246" in script  # WEBGL_RENDERER

    def test_no_raw_user_input_injection(self):
        """Verify profile values are JSON-escaped to prevent JS injection."""
        fp = FingerprintProfile(webgl_vendor='"; alert("xss"); "')
        script = build_fingerprint_script(fp)
        # json.dumps wraps in quotes and escapes inner quotes, so the raw
        # unescaped payload should never appear verbatim.
        raw_payload = '"; alert("xss"); "'
        assert raw_payload not in script


class TestInjectWebrtcPrefs:
    """Tests for inject_webrtc_prefs()."""

    def test_creates_default_preferences_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inject_webrtc_prefs(tmpdir)
            prefs_path = Path(tmpdir) / "Default" / "Preferences"
            assert prefs_path.exists()
            prefs = json.loads(prefs_path.read_text())
            assert prefs["profile"]["webRTC"]["multiple_routes_enabled"] is False
            assert prefs["profile"]["webRTC"]["nonproxied_udp_enabled"] is False
            assert prefs["default_content_setting_values"]["webrtc_ip_handling_policy"] == 1

    def test_merges_with_existing_preferences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prefs_path = Path(tmpdir) / "Default" / "Preferences"
            prefs_path.parent.mkdir(parents=True)
            prefs_path.write_text(json.dumps({"existing_key": "value"}))

            inject_webrtc_prefs(tmpdir)
            prefs = json.loads(prefs_path.read_text())
            # Existing key preserved
            assert prefs["existing_key"] == "value"
            # WebRTC prefs added
            assert prefs["profile"]["webRTC"]["multiple_routes_enabled"] is False

    def test_creates_default_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inject_webrtc_prefs(tmpdir)
            assert (Path(tmpdir) / "Default" / "Preferences").exists()
