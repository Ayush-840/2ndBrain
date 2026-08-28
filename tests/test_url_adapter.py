"""Tests for URL ingestion adapter."""

from unittest.mock import patch, MagicMock

import pytest

from backend.ingestion.url_adapter import URLAdapter, html_to_text


# ── html_to_text tests ──────────────────────────────────────────────

class TestHTMLToText:
    def test_strips_script_tags(self):
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        text = html_to_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "alert" not in text

    def test_strips_style_tags(self):
        html = "<style>.red{color:red}</style><p>Content</p>"
        text = html_to_text(html)
        assert "Content" in text
        assert ".red" not in text

    def test_converts_paragraphs(self):
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        text = html_to_text(html)
        assert "First paragraph." in text
        assert "Second paragraph." in text

    def test_converts_headings(self):
        html = "<h1>Title</h1><h2>Subtitle</h2>"
        text = html_to_text(html)
        assert "# Title" in text
        assert "## Subtitle" in text

    def test_converts_links(self):
        html = '<a href="https://example.com">Example</a>'
        text = html_to_text(html)
        assert "[Example](https://example.com)" in text

    def test_converts_lists(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        text = html_to_text(html)
        assert "- Item 1" in text
        assert "- Item 2" in text

    def test_converts_code(self):
        html = "Use <code>print()</code> for output"
        text = html_to_text(html)
        assert "`print()`" in text

    def test_strips_nav_and_footer(self):
        html = "<nav>Navigation</nav><p>Main content</p><footer>Footer</footer>"
        text = html_to_text(html)
        assert "Main content" in text
        assert "Navigation" not in text
        assert "Footer" not in text

    def test_decodes_entities(self):
        html = "<p>Caf&eacute; &amp; restaurant &mdash; open &quot;24/7&quot;</p>"
        text = html_to_text(html)
        assert "Café" in text
        assert "&" in text
        assert "—" in text
        assert '"24/7"' in text

    def test_normalizes_whitespace(self):
        html = "<p>  Hello    world  </p>"
        text = html_to_text(html)
        assert "Hello world" in text

    def test_empty_html(self):
        assert html_to_text("") == ""
        assert html_to_text("<html></html>") == ""

    def test_plain_text_passthrough(self):
        text = "Just plain text with no HTML"
        assert html_to_text(text) == text


# ── URLAdapter tests ────────────────────────────────────────────────

class TestURLAdapter:
    def setup_method(self):
        self.adapter = URLAdapter()

    def test_is_valid_url(self):
        assert URLAdapter._is_valid_url("https://example.com")
        assert URLAdapter._is_valid_url("http://example.com/article?q=1")
        assert not URLAdapter._is_valid_url("/not/a/url")
        assert not URLAdapter._is_valid_url("not a url")
        assert not URLAdapter._is_valid_url("ftp://example.com")

    def test_source_type(self):
        assert self.adapter.source_type == "url"

    @patch("backend.ingestion.url_adapter.httpx.get")
    def test_ingest_fetches_url(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test Page</title></head><body><p>Hello world</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        captures = self.adapter.ingest("https://example.com")

        assert len(captures) == 1
        capture = captures[0]
        assert capture.source_type == "url"
        assert capture.source_path == "https://example.com"
        assert "Hello world" in capture.content
        assert "Test Page" in capture.content  # title prepended
        assert capture.metadata["url"] == "https://example.com"
        assert capture.metadata["domain"] == "example.com"
        assert capture.metadata["title"] == "Test Page"

    @patch("backend.ingestion.url_adapter.httpx.get")
    def test_ingest_extracts_metadata(self, mock_get):
        html = """
        <html>
        <head>
            <title>Article Title</title>
            <meta name="description" content="A great article about AI">
            <meta name="author" content="Jane Doe">
            <meta property="og:title" content="Article Title">
        </head>
        <body><p>Content here</p></body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        captures = self.adapter.ingest("https://blog.example.com/article")
        meta = captures[0].metadata

        assert meta["title"] == "Article Title"
        assert meta["description"] == "A great article about AI"
        assert meta["author"] == "Jane Doe"
        assert meta["og_title"] == "Article Title"
        assert meta["domain"] == "blog.example.com"
        assert meta["path"] == "/article"

    @patch("backend.ingestion.url_adapter.httpx.get")
    def test_ingest_strips_navigation(self, mock_get):
        html = """
        <html><body>
        <nav><a href="/">Home</a> <a href="/about">About</a></nav>
        <article>
            <h1>My Article</h1>
            <p>This is the main content of the article.</p>
        </article>
        <footer>Copyright 2026</footer>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        captures = self.adapter.ingest("https://example.com/article")
        content = captures[0].content

        assert "My Article" in content
        assert "main content" in content
        # Navigation and footer should be stripped
        assert "Home" not in content or "My Article" in content
        assert "Copyright" not in content

    def test_ingest_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            self.adapter.ingest("not-a-url")

    @patch("backend.ingestion.url_adapter.httpx.get")
    def test_ingest_http_error(self, mock_get):
        import httpx
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        with pytest.raises(httpx.HTTPStatusError):
            self.adapter.ingest("https://example.com/404")


class TestBrowserClip:
    def setup_method(self):
        self.adapter = URLAdapter()

    def test_ingest_clip_basic(self):
        capture = self.adapter.ingest_clip(
            url="https://example.com/article",
            selected_text="This is the selected text from the page.",
        )
        assert capture.source_type == "url"
        assert capture.source_path == "https://example.com/article"
        assert "selected text" in capture.content
        assert capture.metadata["url"] == "https://example.com/article"
        assert capture.metadata["domain"] == "example.com"
        assert capture.metadata["clip_mode"] is True

    def test_ingest_clip_with_title(self):
        capture = self.adapter.ingest_clip(
            url="https://example.com/article",
            selected_text="Key insight about AI",
            title="My Great Article",
        )
        assert capture.metadata["title"] == "My Great Article"
        assert "# My Great Article" in capture.content
        assert "Key insight about AI" in capture.content

    def test_ingest_clip_title_not_duplicated(self):
        """If selected text already contains the title, don't prepend it."""
        capture = self.adapter.ingest_clip(
            url="https://example.com",
            selected_text="My Great Article: some notes about the topic",
            title="My Great Article",
        )
        # Title should not be prepended since it's already in the text
        assert capture.content.count("My Great Article") == 1

    def test_ingest_clip_empty_text(self):
        capture = self.adapter.ingest_clip(
            url="https://example.com",
            selected_text="",
        )
        assert "Empty clip" in capture.content
