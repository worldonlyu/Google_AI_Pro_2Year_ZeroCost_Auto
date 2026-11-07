import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure repo root is in Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import automation_engine
from automation_engine import (
    find_chrome_path,
    get_profile_dir,
    get_totp,
    parse_proxy_string,
    PROFILES_DIR,
    SCREENSHOTS_DIR,
)


class TestLinuxSupport(unittest.TestCase):
    def test_find_chrome_path_env_var(self):
        """CHROME_PATH environment variable should be preferred if set."""
        with tempfile.NamedTemporaryFile(suffix="-fake-chrome", delete=False) as tf:
            fake_path = tf.name

        try:
            os.chmod(fake_path, 0o755)
            with patch.dict(os.environ, {"CHROME_PATH": fake_path}):
                found = find_chrome_path(raise_if_missing=True)
                self.assertEqual(os.path.abspath(found), os.path.abspath(fake_path))
        finally:
            if os.path.exists(fake_path):
                os.remove(fake_path)

    def test_find_chrome_path_nonexistent_env_var(self):
        """Nonexistent CHROME_PATH should raise FileNotFoundError when required."""
        with patch.dict(os.environ, {"CHROME_PATH": "/path/to/definitely/nonexistent/chrome"}):
            with self.assertRaises(FileNotFoundError) as ctx:
                find_chrome_path(raise_if_missing=True)
            self.assertIn("Configured CHROME_PATH does not exist", str(ctx.exception))

    def test_find_chrome_path_missing_raises_actionable_error(self):
        """When no browser candidate exists, raise actionable FileNotFoundError."""
        with patch.dict(os.environ, {"CHROME_PATH": ""}, clear=False):
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", return_value=False):
                    with self.assertRaises(FileNotFoundError) as ctx:
                        find_chrome_path(raise_if_missing=True)
                    err_msg = str(ctx.exception)
                    self.assertIn("No Google Chrome or Chromium executable found", err_msg)
                    self.assertIn("CHROME_PATH", err_msg)

    def test_find_chrome_path_fallback_empty_when_not_required(self):
        """When raise_if_missing=False and no browser exists, return empty string."""
        with patch.dict(os.environ, {"CHROME_PATH": ""}, clear=False):
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", return_value=False):
                    found = find_chrome_path(raise_if_missing=False)
                    self.assertEqual(found, "")

    def test_get_profile_dir_sanitizes_and_creates(self):
        """Ensure profile directory is created safely without illegal characters."""
        profile_dir = get_profile_dir("Account 1!", "test.user+demo@example.com")
        try:
            self.assertTrue(os.path.exists(profile_dir))
            self.assertTrue(os.path.isdir(profile_dir))
            self.assertTrue(profile_dir.startswith(PROFILES_DIR))
            # Check that dangerous or path-separating characters were sanitized
            base = os.path.basename(profile_dir)
            self.assertNotIn("+", base)
            self.assertNotIn("@", base)
            self.assertNotIn(" ", base)
        finally:
            if os.path.exists(profile_dir):
                import shutil
                shutil.rmtree(profile_dir, ignore_errors=True)

    def test_screenshots_dir_exists(self):
        """Ensure SCREENSHOTS_DIR is created reliably."""
        self.assertTrue(os.path.exists(SCREENSHOTS_DIR))
        self.assertTrue(os.path.isdir(SCREENSHOTS_DIR))

    def test_parse_proxy_string(self):
        """Test proxy string parsing for supported schemes and formats."""
        res1 = parse_proxy_string("http://user:pass@127.0.0.1:8080")
        self.assertIsNotNone(res1)
        self.assertEqual(res1["scheme"], "http")
        self.assertEqual(res1["host"], "127.0.0.1")
        self.assertEqual(res1["port"], 8080)
        self.assertEqual(res1["username"], "user")
        self.assertEqual(res1["password"], "pass")

        res2 = parse_proxy_string("socks5://proxy.example.com:1080")
        self.assertIsNotNone(res2)
        self.assertEqual(res2["scheme"], "socks5")
        self.assertEqual(res2["host"], "proxy.example.com")
        self.assertEqual(res2["port"], 1080)

        res3 = parse_proxy_string("1.2.3.4:9000:alice:secret123")
        self.assertIsNotNone(res3)
        self.assertEqual(res3["host"], "1.2.3.4")
        self.assertEqual(res3["port"], 9000)
        self.assertEqual(res3["username"], "alice")
        self.assertEqual(res3["password"], "secret123")

        self.assertIsNone(parse_proxy_string(""))

    def test_get_totp(self):
        """Verify TOTP generation helper."""
        self.assertEqual(get_totp(""), "")
        # Standard RFC 6238 Base32 test key (JBSWY3DPEHPK3PXP)
        code = get_totp("JBSWY3DPEHPK3PXP")
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_app_and_engine_import_cleanly(self):
        """Confirm app and engine import without launching browser automation."""
        import app
        self.assertIsNotNone(app.app)
        self.assertEqual(app.app.title, "Google AI Pro (5 TB) 零成本两年全自动控制台")


if __name__ == "__main__":
    unittest.main()
