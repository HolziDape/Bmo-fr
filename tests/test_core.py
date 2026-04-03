"""
Tests für bmo_core.py

Deckt ab:
  - process_text(): Action-Routing, Plain-Text-Fallback, History-Trimming,
                    remote=True blockiert lokale Aktionen (_REMOTE_SKIP)
  - spotify_volume(): Clamping 0-100, volume_up/down Grenzen
  - set_timer(): Eintrag erscheint in _active_timers
  - get_weather() / get_news(): Parsing mit gemocktem HTTP
  - Flask-Routen: /ping, /process, /timers, /history/clear, /conversations
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

import bmo_core


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _ollama_response(content: str) -> dict:
    """Minimaler ollama.chat()-Rückgabewert."""
    return {"message": {"content": content}}


# ── process_text ──────────────────────────────────────────────────────────────

class TestProcessText:
    """Unit-Tests für process_text() mit gemocktem ollama.chat."""

    def _call(self, ollama_reply: str, text: str = "Hallo", remote: bool = False):
        with patch("bmo_core.ollama") as mock_ollama:
            mock_ollama.chat.return_value = _ollama_response(ollama_reply)
            return bmo_core.process_text(text, remote=remote)

    def test_plain_text_returned_unchanged(self):
        result, action, params = self._call("Hallo zurück!")
        assert result == "Hallo zurück!"
        assert action is None
        assert params == {}

    def test_action_get_time_returns_clock_string(self):
        result, action, params = self._call('{"action": "get_time"}')
        assert action == "get_time"
        assert "Uhr" in result

    def test_action_get_joke_returns_string(self):
        result, action, params = self._call('{"action": "get_joke"}')
        assert action == "get_joke"
        assert isinstance(result, str) and len(result) > 0

    def test_action_get_status_contains_cpu_and_ram(self):
        with patch("bmo_core.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 42
            mock_psutil.virtual_memory.return_value = MagicMock(percent=77)
            with patch("bmo_core.ollama") as mock_ollama:
                mock_ollama.chat.return_value = _ollama_response('{"action": "get_status"}')
                result, action, _ = bmo_core.process_text("Status?")
        assert action == "get_status"
        assert "42" in result and "77" in result

    def test_action_get_weather_includes_city(self):
        with patch("bmo_core.get_weather", return_value="sonnig und 20°C"):
            result, action, _ = self._call('{"action": "get_weather", "location": "Wien"}')
        assert action == "get_weather"
        assert "Wien" in result

    def test_malformed_json_falls_back_to_plain_text(self):
        raw = '{"action": "get_time" BROKEN'
        result, action, _ = self._call(raw)
        assert action is None
        assert result == raw

    def test_history_grows_with_each_call(self):
        with patch("bmo_core.ollama") as mock_ollama:
            mock_ollama.chat.return_value = _ollama_response("ok")
            bmo_core.process_text("erste Frage")
            bmo_core.process_text("zweite Frage")
        # 2 Turns × 2 Nachrichten (user + assistant) = 4
        assert len(bmo_core._conversation_history) == 4

    def test_history_trimmed_to_max_history_times_2(self):
        with patch("bmo_core.ollama") as mock_ollama:
            mock_ollama.chat.return_value = _ollama_response("ok")
            for _ in range(bmo_core.MAX_HISTORY + 5):
                bmo_core.process_text("msg")
        assert len(bmo_core._conversation_history) <= bmo_core.MAX_HISTORY * 2

    def test_ollama_error_returns_error_message(self):
        with patch("bmo_core.ollama") as mock_ollama:
            mock_ollama.chat.side_effect = Exception("verbindung weg")
            result, action, _ = bmo_core.process_text("Hallo")
        assert action is None
        assert "Ollama" in result or "nicht erreichbar" in result

    # ── remote=True blockiert lokale Aktionen ────────────────────────────────

    def test_remote_blocks_shutdown(self):
        """shutdown_pc darf bei remote=True nicht wirklich ausgeführt werden."""
        with patch("bmo_core.threading.Thread") as mock_thread:
            self._call('{"action": "shutdown_pc"}', remote=True)
        mock_thread.assert_not_called()

    def test_remote_blocks_spotify_play(self):
        """spotify_play darf bei remote=True nicht aufgerufen werden."""
        with patch("bmo_core.spotify_play") as mock_play:
            self._call('{"action": "spotify_play", "query": "Coldplay"}', remote=True)
        mock_play.assert_not_called()

    def test_remote_blocks_set_timer(self):
        with patch("bmo_core.set_timer") as mock_timer:
            self._call('{"action": "set_timer", "minutes": 5, "label": "Test"}', remote=True)
        mock_timer.assert_not_called()

    def test_remote_blocks_open_app(self):
        with patch("bmo_core.open_app") as mock_app:
            self._call('{"action": "open_app", "name": "chrome"}', remote=True)
        mock_app.assert_not_called()

    def test_remote_allows_info_actions(self):
        """get_time ist keine lokale Aktion — auch remote erlaubt."""
        result, action, _ = self._call('{"action": "get_time"}', remote=True)
        assert action == "get_time"
        assert "Uhr" in result

    def test_remote_false_executes_shutdown(self):
        """Bei remote=False soll shutdown_pc über einen Thread gestartet werden."""
        with patch("bmo_core.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            self._call('{"action": "shutdown_pc"}', remote=False)
        mock_thread.assert_called()


# ── spotify_volume ────────────────────────────────────────────────────────────

class TestSpotifyVolume:
    def _call(self, level):
        mock_sp = MagicMock()
        with patch("bmo_core.get_spotify", return_value=mock_sp):
            result = bmo_core.spotify_volume(level)
        return result, mock_sp

    def test_volume_50_passes_through(self):
        result, mock_sp = self._call(50)
        mock_sp.volume.assert_called_once_with(50)
        assert "50%" in result

    def test_volume_above_100_clamped_to_100(self):
        result, mock_sp = self._call(150)
        mock_sp.volume.assert_called_once_with(100)
        assert "100%" in result

    def test_volume_below_0_clamped_to_0(self):
        result, mock_sp = self._call(-30)
        mock_sp.volume.assert_called_once_with(0)
        assert "0%" in result

    def test_volume_up_does_not_exceed_100(self):
        mock_sp = MagicMock()
        mock_sp.current_playback.return_value = {"device": {"volume_percent": 90}}
        with patch("bmo_core.get_spotify", return_value=mock_sp):
            bmo_core.spotify_volume_up()
        mock_sp.volume.assert_called_once_with(100)  # 90+20=110 → 100

    def test_volume_down_does_not_go_below_0(self):
        mock_sp = MagicMock()
        mock_sp.current_playback.return_value = {"device": {"volume_percent": 5}}
        with patch("bmo_core.get_spotify", return_value=mock_sp):
            bmo_core.spotify_volume_down()
        mock_sp.volume.assert_called_once_with(0)  # 5-20=-15 → 0


# ── set_timer ─────────────────────────────────────────────────────────────────

class TestSetTimer:
    def test_timer_appears_in_active_timers(self):
        with patch("bmo_core.threading.Timer") as mock_timer_cls:
            mock_timer_cls.return_value = MagicMock()
            bmo_core.set_timer(5, "Nudeln")
        assert len(bmo_core._active_timers) == 1
        assert bmo_core._active_timers[0]["label"] == "Nudeln"

    def test_timer_without_label_uses_minutes_as_label(self):
        with patch("bmo_core.threading.Timer") as mock_timer_cls:
            mock_timer_cls.return_value = MagicMock()
            bmo_core.set_timer(3)
        assert "3" in bmo_core._active_timers[0]["label"]

    def test_timer_return_message_contains_label(self):
        with patch("bmo_core.threading.Timer") as mock_timer_cls:
            mock_timer_cls.return_value = MagicMock()
            result = bmo_core.set_timer(10, "Kaffee")
        assert "Kaffee" in result

    def test_multiple_timers_all_tracked(self):
        with patch("bmo_core.threading.Timer") as mock_timer_cls:
            mock_timer_cls.return_value = MagicMock()
            bmo_core.set_timer(1, "A")
            bmo_core.set_timer(2, "B")
        assert len(bmo_core._active_timers) == 2


# ── get_weather / get_news ────────────────────────────────────────────────────

class TestGetWeather:
    def test_returns_response_text_on_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "sonnig und 22°C"
        with patch("bmo_core.requests.get", return_value=mock_resp):
            assert bmo_core.get_weather("Berlin") == "sonnig und 22°C"

    def test_returns_fallback_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("bmo_core.requests.get", return_value=mock_resp):
            assert bmo_core.get_weather("Nowhere") == "leider unbekannt"

    def test_returns_fallback_on_network_error(self):
        with patch("bmo_core.requests.get", side_effect=Exception("timeout")):
            assert bmo_core.get_weather("Berlin") == "nicht erreichbar"


class TestGetNews:
    def test_returns_top_3_headlines(self):
        fake_feed = MagicMock()
        fake_feed.entries = [MagicMock(title=f"Headline {i}") for i in range(5)]

        with patch("bmo_core.feedparser") as mock_fp, \
             patch("bmo_core.urllib.request.urlopen"), \
             patch("bmo_core.urllib.request.Request"):
            mock_fp.parse.return_value = fake_feed
            result = bmo_core.get_news()

        assert "Headline 0" in result
        assert "Headline 1" in result
        assert "Headline 2" in result
        assert "Headline 3" not in result  # nur erste 3

    def test_returns_fallback_on_error(self):
        with patch("bmo_core.urllib.request.urlopen", side_effect=Exception("network")):
            result = bmo_core.get_news()
        assert isinstance(result, str) and len(result) > 0


# ── Flask-Routen ──────────────────────────────────────────────────────────────

class TestCoreRoutes:
    def test_ping_returns_200(self, core_client):
        resp = core_client.get("/ping")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_process_empty_message_returns_fallback(self, core_client):
        resp = core_client.post("/process", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["response"]
        assert data["action"] is None

    def test_process_with_message_calls_process_text(self, core_client):
        with patch("bmo_core.process_text", return_value=("Antwort!", None, {})) as mock_pt, \
             patch("bmo_core.save_conversation"):
            resp = core_client.post("/process", json={"message": "Wie geht's?"})
        assert resp.status_code == 200
        mock_pt.assert_called_once_with("Wie geht's?", remote=False)
        assert resp.get_json()["response"] == "Antwort!"

    def test_process_remote_flag_passed_through(self, core_client):
        with patch("bmo_core.process_text", return_value=("ok", None, {})) as mock_pt, \
             patch("bmo_core.save_conversation"):
            core_client.post("/process", json={"message": "Hallo", "remote": True})
        mock_pt.assert_called_once_with("Hallo", remote=True)

    def test_timers_endpoint_returns_list(self, core_client):
        resp = core_client.get("/timers")
        assert resp.status_code == 200
        assert "timers" in resp.get_json()

    def test_history_clear_resets_conversation(self, core_client):
        bmo_core._conversation_history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hey"},
        ]
        resp = core_client.post("/history/clear")
        assert resp.status_code == 200
        assert bmo_core._conversation_history == []

    def test_conversations_delete_removes_file(self, core_client, tmp_path):
        dummy = tmp_path / "conversations.json"
        dummy.write_text("[]", encoding="utf-8")
        with patch("bmo_core.CONVERSATIONS_PATH", str(dummy)):
            resp = core_client.delete("/conversations")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert not dummy.exists()
