"""Tests for Google Sheets archive / move operations."""

from unittest.mock import MagicMock, patch

import gspread
import pytest

from ig_threads_telebot import sheets


def _make_worksheet(values, title="ws"):
    ws = MagicMock()
    ws.title = title
    ws.get_all_values.return_value = values
    ws.append_row = MagicMock()
    ws.append_rows = MagicMock()
    ws.clear = MagicMock()
    return ws


HEADER = ["timestamp", "url", "rectified", "username", "platform", "status", "suffix", "comments"]


class TestMoveDownloadedToArchive:
    @patch("ig_threads_telebot.sheets._get_client")
    def test_moves_downloaded_rows_and_removes_them(self, _get_client):
        pending = ["t1", "url1", "r1", "user1", "instagram", "PENDING", "", ""]
        dl1 = ["t2", "url2", "r2", "user2", "instagram", "DOWNLOADED", "", ""]
        dl2 = ["t3", "url3", "r3", "user3", "threads", "DOWNLOADED", "", ""]
        pending2 = ["t4", "url4", "r4", "user4", "instagram", "PENDING", "", ""]
        stream = _make_worksheet([HEADER, pending, dl1, dl2, pending2])
        archive = _make_worksheet([HEADER])

        sheet = MagicMock()
        sheet.worksheet.side_effect = {"stream": stream, "archive": archive}.get
        client = MagicMock()
        client.open_by_key.return_value = sheet
        _get_client.return_value = client

        with patch.object(sheets, "_SPREADSHEET_ID", "sheet-id"):
            result = sheets.move_downloaded_to_archive()

        assert result == {"moved": 2, "archive_created": False}

        # The two DOWNLOADED rows were appended to the archive (header excluded).
        archive.append_rows.assert_called_once()
        moved_rows = archive.append_rows.call_args.args[0]
        assert moved_rows == [dl1, dl2]
        assert archive.append_rows.call_args.kwargs == {"value_input_option": "USER_ENTERED"}

        # The stream was cleared and rewritten keeping header + non-downloaded rows.
        stream.clear.assert_called_once()
        stream.append_rows.assert_called_once()
        written = stream.append_rows.call_args.args[0]
        assert written == [HEADER, pending, pending2]

    @patch("ig_threads_telebot.sheets._get_client")
    def test_creates_archive_worksheet_when_missing(self, _get_client):
        downloaded = ["t1", "url1", "u1", "ig", "instagram", "DOWNLOADED", "", ""]
        stream = _make_worksheet([HEADER, downloaded])
        archive_new = _make_worksheet([])

        sheet = MagicMock()

        def worksheet(name):
            if name == "archive":
                raise gspread.exceptions.WorksheetNotFound
            return stream

        sheet.worksheet.side_effect = worksheet
        sheet.add_worksheet.return_value = archive_new

        client = MagicMock()
        client.open_by_key.return_value = sheet
        _get_client.return_value = client

        with patch.object(sheets, "_SPREADSHEET_ID", "sheet-id"):
            result = sheets.move_downloaded_to_archive()

        assert result == {"moved": 1, "archive_created": True}
        sheet.add_worksheet.assert_called_once()
        archive_new.append_row.assert_called_once_with(HEADER, value_input_option="USER_ENTERED")
        archive_new.append_rows.assert_called_once()
        assert archive_new.append_rows.call_args.args[0] == [downloaded]
        assert archive_new.append_rows.call_args.kwargs == {"value_input_option": "USER_ENTERED"}

    @patch("ig_threads_telebot.sheets._get_client")
    def test_no_downloaded_rows_is_noop(self, _get_client):
        stream = _make_worksheet([HEADER, ["t1", "url1", "u1", "ig", "instagram", "PENDING", "", ""]])
        archive = _make_worksheet([HEADER])

        sheet = MagicMock()
        sheet.worksheet.side_effect = {"stream": stream, "archive": archive}.get
        client = MagicMock()
        client.open_by_key.return_value = sheet
        _get_client.return_value = client

        with patch.object(sheets, "_SPREADSHEET_ID", "sheet-id"):
            result = sheets.move_downloaded_to_archive()

        assert result == {"moved": 0, "archive_created": False}
        archive.append_rows.assert_not_called()
        stream.clear.assert_not_called()

    @patch("ig_threads_telebot.sheets._get_client")
    def test_empty_stream_is_noop(self, _get_client):
        stream = _make_worksheet([])

        sheet = MagicMock()
        sheet.worksheet.return_value = stream
        client = MagicMock()
        client.open_by_key.return_value = sheet
        _get_client.return_value = client

        with patch.object(sheets, "_SPREADSHEET_ID", "sheet-id"):
            result = sheets.move_downloaded_to_archive()

        assert result == {"moved": 0, "archive_created": False}

    def test_missing_spreadsheet_id_raises(self):
        with patch.object(sheets, "_SPREADSHEET_ID", ""):
            with pytest.raises(RuntimeError, match="GOOGLE_SPREADSHEET_ID"):
                sheets.move_downloaded_to_archive()

    @patch("ig_threads_telebot.sheets._get_client")
    def test_status_column_found_from_header(self, _get_client):
        header = ["a", "b", "status", "c"]
        stream = _make_worksheet(
            [
                header,
                ["x", "y", "DOWNLOADED", "z"],
                ["x", "y", "PENDING", "z"],
            ]
        )
        archive = _make_worksheet([header])

        sheet = MagicMock()
        sheet.worksheet.side_effect = {"stream": stream, "archive": archive}.get
        client = MagicMock()
        client.open_by_key.return_value = sheet
        _get_client.return_value = client

        with patch.object(sheets, "_SPREADSHEET_ID", "sheet-id"):
            result = sheets.move_downloaded_to_archive()

        assert result["moved"] == 1
        assert archive.append_rows.call_args.args[0] == [["x", "y", "DOWNLOADED", "z"]]

    @patch("ig_threads_telebot.sheets._get_client")
    def test_empty_rows_are_dropped_from_stream_rewrite(self, _get_client):
        # Two PENDING rows, one DOWNLOADED row, plus padded empty rows that
        # get_all_values() can return — the empty rows must not survive the rewrite.
        pending = ["t1", "url1", "r1", "user1", "instagram", "PENDING", "", ""]
        pending2 = ["t2", "url2", "r2", "user2", "instagram", "PENDING", "", ""]
        downloaded = ["t3", "url3", "r3", "user3", "threads", "DOWNLOADED", "", ""]
        empty = ["", "", "", "", "", "", "", ""]
        stream = _make_worksheet([HEADER, pending, downloaded, empty, pending2, []])
        archive = _make_worksheet([HEADER])

        sheet = MagicMock()
        sheet.worksheet.side_effect = {"stream": stream, "archive": archive}.get
        client = MagicMock()
        client.open_by_key.return_value = sheet
        _get_client.return_value = client

        with patch.object(sheets, "_SPREADSHEET_ID", "sheet-id"):
            result = sheets.move_downloaded_to_archive()

        assert result == {"moved": 1, "archive_created": False}
        archive.append_rows.assert_called_once()
        assert archive.append_rows.call_args.args[0] == [downloaded]

        # Stream rewritten with header + the two PENDING rows only; empties gone.
        stream.clear.assert_called_once()
        written = stream.append_rows.call_args.args[0]
        assert written == [HEADER, pending, pending2]
