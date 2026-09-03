"""Tests for the Lambda handler command routing."""

from unittest.mock import patch

from ig_threads_telebot.handler import lambda_handler


def _event(text: str) -> dict:
    import json

    return {"body": json.dumps({"message": {"text": text}})}


class TestGArchiveCommand:
    @patch("ig_threads_telebot.handler.move_downloaded_to_archive")
    def test_garchive_dispatches_to_sheets_move(self, _move):
        _move.return_value = {"moved": 3, "archive_created": False}
        resp = lambda_handler(_event("/garchive"), None)

        assert resp["statusCode"] == 200
        _move.assert_called_once()
        import json

        body = json.loads(resp["body"])
        assert body["ok"] is True
        assert body["garchived"] == {"moved": 3, "archive_created": False}

    @patch("ig_threads_telebot.handler.move_downloaded_to_archive")
    def test_garchive_handles_runtime_error(self, _move):
        _move.side_effect = RuntimeError("GOOGLE_SPREADSHEET_ID environment variable is not set.")
        resp = lambda_handler(_event("/garchive"), None)
        body = __import__("json").loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["ok"] is False
        assert body["error"] == "GOOGLE_SPREADSHEET_ID environment variable is not set."

    @patch("ig_threads_telebot.handler.move_downloaded_to_archive")
    def test_garchive_handles_unexpected_error(self, _move):
        _move.side_effect = ValueError("boom")
        resp = lambda_handler(_event("/garchive"), None)
        body = __import__("json").loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["ok"] is False
        assert body["error"] == "garchive_failed"

    @patch("ig_threads_telebot.handler.append_links")
    def test_links_still_routed_when_not_a_command(self, _append):
        resp = lambda_handler(_event("https://instagram.com/p/ABC123 https://threads.net/@u/post/X"), None)
        import json

        body = json.loads(resp["body"])
        assert body == {"ok": True, "links_found": 2}
        _append.assert_called_once()
