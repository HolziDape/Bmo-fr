"""
Tests for bmo_web.py

Covers:
  - _load_config() / _save_config(): round-trip preserves all keys
  - login_required decorator:
      • no password set  → redirect to /setup
      • password set, unauthenticated, /api/ path → 401 JSON
      • password set, unauthenticated, HTML path → redirect to /login
      • authenticated → request passes through
  - /login POST: correct password sets session and redirects
  - /login POST: wrong password shows error (no redirect)
  - /api/status fallback when core is unavailable
"""

import os
from unittest.mock import MagicMock, patch

import pytest

import bmo_web


# ── _load_config / _save_config ───────────────────────────────────────────────

class TestConfigRoundtrip:
    def test_save_then_load_preserves_all_keys(self, tmp_path):
        cfg_file = tmp_path / "bmo_config.txt"
        data = {"WEB_PASSWORD": "geheim", "FRIEND_URL": "http://192.168.1.2:5000"}

        with patch("bmo_web._CONFIG_PATH", str(cfg_file)):
            bmo_web._save_config(data)
            loaded = bmo_web._load_config()

        assert loaded == data

    def test_load_nonexistent_returns_empty_dict(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.txt")
        with patch("bmo_web._CONFIG_PATH", missing):
            result = bmo_web._load_config()
        assert result == {}

    def test_load_ignores_comment_lines(self, tmp_path):
        cfg_file = tmp_path / "bmo_config.txt"
        cfg_file.write_text("# Kommentar\nWEB_PASSWORD=abc\n", encoding="utf-8")
        with patch("bmo_web._CONFIG_PATH", str(cfg_file)):
            result = bmo_web._load_config()
        assert result == {"WEB_PASSWORD": "abc"}

    def test_save_then_load_roundtrip_with_special_chars(self, tmp_path):
        cfg_file = tmp_path / "bmo_config.txt"
        data = {"WEB_PASSWORD": "p@$$w0rd!äöü"}
        with patch("bmo_web._CONFIG_PATH", str(cfg_file)):
            bmo_web._save_config(data)
            loaded = bmo_web._load_config()
        assert loaded["WEB_PASSWORD"] == "p@$$w0rd!äöü"


# ── login_required ────────────────────────────────────────────────────────────

class TestLoginRequired:
    """
    The decorator reads the module-level WEB_PASSWORD, so we patch it there.
    The / route and /api/status are both protected by @login_required.
    """

    def test_no_password_redirects_to_setup(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", None):
            resp = web_client.get("/")
        assert resp.status_code in (301, 302)
        assert "/setup" in resp.headers["Location"]

    def test_unauthenticated_api_route_returns_401(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", "geheim"), \
             patch("bmo_web.psutil") as mock_ps, \
             patch("bmo_web.req") as mock_req:
            mock_req.get.side_effect = Exception("core down")
            mock_ps.cpu_percent.return_value = 10
            mock_ps.virtual_memory.return_value = MagicMock(percent=50)
            resp = web_client.get("/api/status")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "error" in data or "Nicht eingeloggt" in str(data)

    def test_unauthenticated_html_route_redirects_to_login(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", "geheim"):
            resp = web_client.get("/")
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers["Location"]

    def test_authenticated_request_passes_through(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", "geheim"), \
             patch("bmo_web.req") as mock_req, \
             patch("bmo_web.psutil") as mock_ps:
            mock_req.get.side_effect = Exception("core down")
            mock_ps.cpu_percent.return_value = 5
            mock_ps.virtual_memory.return_value = MagicMock(percent=30)

            with web_client.session_transaction() as sess:
                sess["authenticated"] = True

            resp = web_client.get("/api/status")
        assert resp.status_code == 200


# ── /login POST ───────────────────────────────────────────────────────────────

class TestLoginRoute:
    def test_correct_password_sets_session_and_redirects(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", "richtig"):
            resp = web_client.post(
                "/login",
                data={"password": "richtig"},
                follow_redirects=False,
            )
        assert resp.status_code in (301, 302)
        # Session must be marked authenticated
        with web_client.session_transaction() as sess:
            assert sess.get("authenticated") is True

    def test_wrong_password_does_not_redirect(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", "richtig"):
            resp = web_client.post(
                "/login",
                data={"password": "falsch"},
                follow_redirects=False,
            )
        # Stays on login page (200 re-render) — not a redirect
        assert resp.status_code == 200
        with web_client.session_transaction() as sess:
            assert not sess.get("authenticated")


# ── /api/status fallback ──────────────────────────────────────────────────────

class TestStatusFallback:
    """When bmo_core is unreachable, /api/status falls back to local psutil."""

    def _authenticated_get(self, web_client):
        with web_client.session_transaction() as sess:
            sess["authenticated"] = True

    def test_fallback_returns_cpu_and_ram(self, web_client):
        with patch("bmo_web.WEB_PASSWORD", "pw"), \
             patch("bmo_web.req") as mock_req, \
             patch("bmo_web.psutil") as mock_ps:
            mock_req.get.side_effect = Exception("core offline")
            mock_ps.cpu_percent.return_value = 55
            mock_ps.virtual_memory.return_value = MagicMock(percent=66)

            self._authenticated_get(web_client)
            resp = web_client.get("/api/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cpu"] == 55
        assert data["ram"] == 66
