"""Tests for Telegram update parsing and link extraction."""

from ig_threads_telebot.telegram import parse_links, validate_update


class TestValidateUpdate:
    def test_valid_text_message(self):
        update = {"message": {"text": "hello"}}
        assert validate_update(update) is True

    def test_valid_caption(self):
        update = {"message": {"caption": "check this out"}}
        assert validate_update(update) is True

    def test_missing_message(self):
        update = {"edited_message": {"text": "hello"}}
        assert validate_update(update) is False

    def test_empty_text(self):
        update = {"message": {"text": ""}}
        assert validate_update(update) is False

    def test_channel_post(self):
        update = {"channel_post": {"text": "some text"}}
        assert validate_update(update) is True


class TestParseLinks:
    def test_single_instagram_post(self):
        update = {"message": {"text": "Look at this https://www.instagram.com/p/ABC123/"}}
        assert parse_links(update) == ["https://www.instagram.com/p/ABC123"]

    def test_single_instagram_reel(self):
        update = {"message": {"text": "https://instagram.com/reel/XYZ789"}}
        assert parse_links(update) == ["https://instagram.com/reel/XYZ789"]

    def test_single_threads_post(self):
        update = {"message": {"text": "https://www.threads.net/@user.name/post/ABC123/"}}
        assert parse_links(update) == ["https://www.threads.net/@user.name/post/ABC123"]

    def test_multiple_links(self):
        text = (
            "Check these out:\n"
            "https://instagram.com/p/AAA\n"
            "https://threads.net/@someone/post/BBB\n"
            "https://instagram.com/reel/CCC"
        )
        update = {"message": {"text": text}}
        result = parse_links(update)
        assert len(result) == 3
        assert "https://instagram.com/p/AAA" in result
        assert "https://threads.net/@someone/post/BBB" in result
        assert "https://instagram.com/reel/CCC" in result

    def test_duplicate_links(self):
        text = "https://instagram.com/p/AAA https://instagram.com/p/AAA"
        update = {"message": {"text": text}}
        assert parse_links(update) == ["https://instagram.com/p/AAA"]

    def test_no_links(self):
        update = {"message": {"text": "just a regular message"}}
        assert parse_links(update) == []

    def test_links_in_caption(self):
        update = {"message": {"caption": "https://instagram.com/p/CAP123"}}
        assert parse_links(update) == ["https://instagram.com/p/CAP123"]

    def test_non_ig_threads_links_ignored(self):
        update = {"message": {"text": "https://twitter.com/user/status/123 https://example.com"}}
        assert parse_links(update) == []

    def test_threads_share_link(self):
        update = {"message": {"text": "https://www.threads.com/share/BAD707IrTq/"}}
        assert parse_links(update) == ["https://www.threads.com/share/BAD707IrTq"]

    def test_threads_share_link_no_www(self):
        update = {"message": {"text": "https://threads.com/share/XYZ123"}}
        assert parse_links(update) == ["https://threads.com/share/XYZ123"]

    def test_threads_post_and_share_mixed(self):
        text = (
            "https://threads.net/@user/post/AAA\n"
            "https://www.threads.com/share/BBB"
        )
        update = {"message": {"text": text}}
        result = parse_links(update)
        assert len(result) == 2
        assert "https://threads.net/@user/post/AAA" in result
        assert "https://www.threads.com/share/BBB" in result
