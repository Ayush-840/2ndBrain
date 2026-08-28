"""URL / browser-clip ingestion adapter.

Fetches a web page, extracts readable content (title, main text, metadata),
and returns a Capture.  Supports two modes:

  1. **Full page** — fetch URL, strip HTML, extract readable text
  2. **Browser clip** — accept pre-selected text + URL (from a browser extension)

The adapter uses httpx for fetching and a lightweight HTML-to-text pipeline
(no heavy deps like readability-lxml — keeps things simple for v1).
"""

from __future__ import annotations

import re
import html as html_lib
import logging
from urllib.parse import urlparse

import httpx

from backend.ingestion.base import Capture, IngestionAdapter

logger = logging.getLogger(__name__)

# Default request headers to avoid bot detection
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tags to remove entirely (including content)
_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "iframe"}


class URLAdapter(IngestionAdapter):
    """Fetch and extract readable content from web pages."""

    source_type = "url"

    def __init__(
        self,
        timeout: float = 30.0,
        follow_redirects: bool = True,
    ):
        self._timeout = timeout
        self._follow_redirects = follow_redirects

    def ingest(self, source: str) -> list[Capture]:
        """Ingest a single URL.

        Args:
            source: A URL string (https://example.com/article).

        Returns:
            A single Capture with the extracted page content.

        Raises:
            ValueError: If the source is not a valid URL.
            httpx.HTTPError: If the fetch fails.
        """
        if not self._is_valid_url(source):
            raise ValueError(f"Invalid URL: {source}")

        return [self._fetch_and_extract(source)]

    def ingest_clip(
        self,
        url: str,
        selected_text: str,
        title: str = "",
    ) -> Capture:
        """Ingest a browser clip (URL + user-selected text).

        This is the path used when a browser extension sends a selection.
        The selected text takes priority; the URL provides context.
        """
        metadata = {
            "url": url,
            "domain": urlparse(url).netloc,
            "title": title,
            "clip_mode": True,
        }

        content = selected_text.strip()
        if not content:
            content = f"[Empty clip from {url}]"

        # Prepend title if available and not already in the text
        if title and title.lower() not in content.lower():
            content = f"# {title}\n\n{content}"

        return self._make_capture(
            content=content,
            source_path=url,
            metadata=metadata,
        )

    def _fetch_and_extract(self, url: str) -> Capture:
        """Fetch a URL and extract readable content."""
        response = httpx.get(
            url,
            headers=_DEFAULT_HEADERS,
            timeout=self._timeout,
            follow_redirects=self._follow_redirects,
        )
        response.raise_for_status()

        html = response.text
        metadata = self._extract_metadata(html, url)

        # Extract readable text from HTML
        content = html_to_text(html)

        # Prepend title for context
        title = metadata.get("title", "")
        if title and title.lower() not in content.lower():
            content = f"# {title}\n\n{content}"

        return self._make_capture(
            content=content.strip(),
            source_path=url,
            metadata=metadata,
        )

    def _extract_metadata(self, html: str, url: str) -> dict:
        """Extract metadata from HTML head."""
        parsed = urlparse(url)
        metadata: dict = {
            "url": url,
            "domain": parsed.netloc,
            "path": parsed.path,
        }

        # Extract <title>
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            metadata["title"] = title_match.group(1).strip()

        # Extract meta tags
        for pattern, key in [
            (r'<meta\s+name="description"\s+content="([^"]*)"', "description"),
            (r'<meta\s+content="([^"]*)"\s+name="description"', "description"),
            (r'<meta\s+name="author"\s+content="([^"]*)"', "author"),
            (r'<meta\s+property="og:title"\s+content="([^"]*)"', "og_title"),
            (r'<meta\s+property="og:description"\s+content="([^"]*)"', "og_description"),
            (r'<meta\s+property="og:image"\s+content="([^"]*)"', "og_image"),
        ]:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()

        # Extract publication date from common patterns
        for pattern in [
            r'<meta\s+property="article:published_time"\s+content="([^"]*)"',
            r'<meta\s+name="date"\s+content="([^"]*)"',
            r'<time[^>]*datetime="([^"]*)"',
        ]:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                metadata["published_date"] = match.group(1).strip()
                break

        return metadata

    @staticmethod
    def _is_valid_url(source: str) -> bool:
        """Check if a string looks like a valid URL."""
        try:
            result = urlparse(source)
            return result.scheme in ("http", "https") and bool(result.netloc)
        except Exception:
            return False


def html_to_text(html: str) -> str:
    """Convert HTML to plain text.

    Lightweight approach using only stdlib (re + html):
    1. Remove non-content tags (script, style, nav, etc.) with content
    2. Convert semantic tags to readable equivalents (headings, links, lists, code)
    3. Convert block-level tags to newlines
    4. Strip all remaining HTML tags
    5. Decode HTML entities
    6. Normalize whitespace
    """
    text = html

    # ── Step 1: Remove non-content tags entirely (including content) ──
    for tag in _STRIP_TAGS:
        text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(rf"<{tag}[^>]*/?>", "", text, flags=re.IGNORECASE)

    # ── Step 2: Convert semantic tags BEFORE generic block conversion ──

    # Headings → markdown
    for i in range(1, 7):
        prefix = "#" * i
        text = re.sub(
            rf"<h{i}[^>]*>(.*?)</h{i}>",
            rf"\n{prefix} \1\n",
            text, flags=re.IGNORECASE | re.DOTALL,
        )

    # Links → [text](url)
    def _link_repl(m):
        tag = m.group(0)
        link_text = m.group(1)
        href_match = re.search(r'href="([^"]*)"', tag)
        if href_match:
            return f"[{link_text.strip()}]({href_match.group(1)})"
        return link_text

    text = re.sub(r"<a[^>]*>(.*?)</a>", _link_repl, text, flags=re.IGNORECASE | re.DOTALL)

    # Code → backticks
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n", text, flags=re.IGNORECASE | re.DOTALL)

    # List items → bullet points
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)

    # ── Step 3: Convert block tags to newlines ──
    block_tags = {
        "p", "div", "blockquote", "section", "article",
        "main", "figure", "figcaption", "details", "summary",
        "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "pre",
    }
    for tag in block_tags:
        text = re.sub(rf"<{tag}[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(rf"</{tag}>", "\n", text, flags=re.IGNORECASE)

    # <br> and <hr>
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<hr\s*/?>", "\n---\n", text, flags=re.IGNORECASE)

    # ── Step 4: Strip all remaining HTML tags ──
    text = re.sub(r"<[^>]+>", "", text)

    # ── Step 5: Decode HTML entities (stdlib handles all of them) ──
    text = html_lib.unescape(text)

    # ── Step 6: Normalize whitespace ──
    text = re.sub(r"[^\S\n]+", " ", text)        # collapse horizontal whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)        # max 2 consecutive newlines
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = text.strip()

    return text
