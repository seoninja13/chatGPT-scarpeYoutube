"""Scrape all video URLs from a YouTube channel using Python and Beautiful Soup.

The script targets the ``/videos`` tab of a YouTube channel. It works by
requesting the HTML for the page, extracting the ``ytInitialData`` bootstrap JSON
payload, and then following the continuation tokens exposed by that payload to
retrieve every video listed on the channel.

Due to the dynamic nature of YouTube's frontend, the script talks to the same
internal API the website uses (``youtubei/v1/browse``). The required keys and
context objects are sourced from the ``ytcfg`` configuration dictionary that is
also embedded in the HTML. All HTTP requests are made with the standard library
(`urllib.request`). When the ``beautifulsoup4`` package is installed the real
Beautiful Soup implementation is used; otherwise the script falls back to a
bundled minimal parser so that it can operate in restricted environments.

Example usage::

    python scrape_youtube_channel.py https://www.youtube.com/@abbasravji --output videos.json

The resulting JSON file contains a list of dictionaries where each entry
represents a video published on the channel. The ``url`` field can be used to
visit the video on YouTube.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener

try:  # pragma: no cover - import-time optional dependency resolution
    from bs4 import BeautifulSoup  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - fallback for restricted envs
    from lite_soup import BeautifulSoup

YOUTUBE_BASE_URL = "https://www.youtube.com"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class VideoEntry:
    """Metadata for a single YouTube video."""

    video_id: str
    title: str
    url: str
    view_count_text: Optional[str]
    published_time: Optional[str]

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "url": self.url,
            "view_count_text": self.view_count_text,
            "published_time": self.published_time,
        }


class YouTubeChannelScraper:
    """Scrape all video URLs from a YouTube channel."""

    def __init__(self, channel_url: str) -> None:
        normalized = channel_url.rstrip("/")
        if "/videos" not in normalized:
            normalized = f"{normalized}/videos"
        self.channel_url = normalized
        self.opener = build_opener()
        self.opener.addheaders = list(DEFAULT_HEADERS.items())
        self.api_key: Optional[str] = None
        self.api_context: Optional[Dict[str, object]] = None

    # ------------------------------------------------------------------
    # High level public API
    # ------------------------------------------------------------------
    def scrape(self, limit: Optional[int] = None) -> List[VideoEntry]:
        """Return every video entry published on the channel."""

        html = self._fetch(self.channel_url)
        initial_data, config = self._extract_bootstrap_data(html)
        self._prepare_api(config)

        grid_contents = self._extract_initial_grid(initial_data)
        videos, tokens = self._extract_videos_from_grid(grid_contents)

        collected: List[VideoEntry] = videos
        seen_ids = {entry.video_id for entry in videos}

        for token in self._iterate_continuations(tokens, limit=limit, seen_ids=seen_ids, collected=collected):
            # The generator takes care of populating ``collected`` as a side effect.
            if token is None:  # pragma: no cover - defensive safety net
                break

        if limit is not None:
            return collected[:limit]
        return collected

    # ------------------------------------------------------------------
    # Networking helpers
    # ------------------------------------------------------------------
    def _fetch(self, url: str, payload: Optional[Dict[str, object]] = None) -> str:
        data: Optional[bytes]
        headers: Dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            data = None

        request = Request(url, data=data, headers=headers)
        with self.opener.open(request) as response:
            charset = response.headers.get_content_charset("utf-8")
            body = response.read().decode(charset)
        return body

    # ------------------------------------------------------------------
    # Bootstrap data extraction
    # ------------------------------------------------------------------
    def _extract_bootstrap_data(self, html: str) -> Tuple[Dict[str, object], Dict[str, object]]:
        soup = BeautifulSoup(html, "html.parser")
        initial_data = self._find_json_in_scripts(soup, [
            "var ytInitialData = ",
            "window['ytInitialData'] = ",
            'window["ytInitialData"] = ',
            "ytInitialData = ",
        ])
        if initial_data is None:
            raise RuntimeError("Could not locate ytInitialData in the page")

        config = self._find_json_in_scripts(soup, ["ytcfg.set("])
        if config is None:
            raise RuntimeError("Could not locate ytcfg bootstrap data")
        return initial_data, config

    def _find_json_in_scripts(self, soup: BeautifulSoup, patterns: Iterable[str]) -> Optional[Dict[str, object]]:
        for script in soup.find_all("script"):
            content = script.string or script.get_text()
            if not content:
                continue
            for marker in patterns:
                parsed = self._extract_json_object(content, marker)
                if parsed is not None:
                    return parsed
        return None

    def _extract_json_object(self, text: str, marker: str) -> Optional[Dict[str, object]]:
        index = text.find(marker)
        if index == -1:
            return None
        index = text.find("{", index + len(marker))
        if index == -1:
            return None
        brace_stack = 0
        for pos in range(index, len(text)):
            char = text[pos]
            if char == "{" or char == "[":
                brace_stack += 1
            elif char == "}" or char == "]":
                brace_stack -= 1
                if brace_stack == 0:
                    json_blob = text[index : pos + 1]
                    try:
                        return json.loads(json_blob)
                    except json.JSONDecodeError:
                        return None
        return None

    def _prepare_api(self, config: Dict[str, object]) -> None:
        api_key = config.get("INNERTUBE_API_KEY")
        context = config.get("INNERTUBE_CONTEXT")
        if not isinstance(api_key, str) or not isinstance(context, dict):
            raise RuntimeError("Failed to extract API configuration from ytcfg")
        self.api_key = api_key
        self.api_context = context

    # ------------------------------------------------------------------
    # Initial grid parsing helpers
    # ------------------------------------------------------------------
    def _extract_initial_grid(self, initial_data: Dict[str, object]) -> List[Dict[str, object]]:
        try:
            tabs = initial_data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]  # type: ignore[index]
        except (KeyError, TypeError) as error:  # pragma: no cover - defensive guard
            raise RuntimeError("Unexpected response structure while locating tabs") from error

        for tab in tabs:
            renderer = tab.get("tabRenderer") if isinstance(tab, dict) else None
            if not isinstance(renderer, dict):
                continue
            if renderer.get("selected"):
                content = renderer.get("content")
                if not isinstance(content, dict):
                    continue
                grid = self._find_value(content, "richGridRenderer")
                if isinstance(grid, dict):
                    contents = grid.get("contents")
                    if isinstance(contents, list):
                        return contents
        raise RuntimeError("Could not find the grid renderer for the videos tab")

    # ------------------------------------------------------------------
    # Continuation handling
    # ------------------------------------------------------------------
    def _iterate_continuations(
        self,
        tokens: List[str],
        *,
        limit: Optional[int],
        seen_ids: set[str],
        collected: List[VideoEntry],
    ) -> Iterable[Optional[str]]:
        while tokens:
            token = tokens.pop(0)
            response = self._fetch_continuation(token)
            items = self._find_value(response, "continuationItems")
            if not isinstance(items, list):
                yield None
                continue
            videos, new_tokens = self._extract_videos_from_grid(items)
            for entry in videos:
                if entry.video_id in seen_ids:
                    continue
                collected.append(entry)
                seen_ids.add(entry.video_id)
                if limit is not None and len(collected) >= limit:
                    return
            tokens.extend(new_tokens)
            yield token

    def _fetch_continuation(self, token: str) -> Dict[str, object]:
        if not self.api_key or not self.api_context:
            raise RuntimeError("API configuration has not been initialised")
        url = f"{YOUTUBE_BASE_URL}/youtubei/v1/browse?key={self.api_key}"
        payload = {"context": self.api_context, "continuation": token}
        raw = self._fetch(url, payload=payload)
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Video extraction helpers
    # ------------------------------------------------------------------
    def _extract_videos_from_grid(self, items: List[Dict[str, object]]) -> Tuple[List[VideoEntry], List[str]]:
        videos: List[VideoEntry] = []
        tokens: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            renderer = item.get("richItemRenderer")
            if isinstance(renderer, dict):
                content = renderer.get("content")
                if isinstance(content, dict):
                    video = content.get("videoRenderer")
                    if isinstance(video, dict):
                        entry = self._parse_video_renderer(video)
                        if entry is not None:
                            videos.append(entry)
                continue
            continuation = item.get("continuationItemRenderer")
            if isinstance(continuation, dict):
                token = self._extract_continuation_token(continuation)
                if token:
                    tokens.append(token)
        return videos, tokens

    def _parse_video_renderer(self, renderer: Dict[str, object]) -> Optional[VideoEntry]:
        video_id = renderer.get("videoId")
        if not isinstance(video_id, str):
            return None
        url = urljoin(YOUTUBE_BASE_URL, f"/watch?v={video_id}")
        title_info = renderer.get("title", {})
        title = self._extract_text_from_runs(title_info)
        if not title:
            title = ""
        view_count_text = self._extract_text(renderer.get("viewCountText"))
        published_time = self._extract_text(renderer.get("publishedTimeText"))
        return VideoEntry(video_id=video_id, title=title, url=url, view_count_text=view_count_text, published_time=published_time)

    def _extract_continuation_token(self, renderer: Dict[str, object]) -> Optional[str]:
        endpoint = renderer.get("continuationEndpoint")
        if isinstance(endpoint, dict):
            command = endpoint.get("continuationCommand")
            if isinstance(command, dict):
                token = command.get("token")
                if isinstance(token, str):
                    return token
        continuation_data = renderer.get("reloadContinuationData")
        if isinstance(continuation_data, dict):
            token = continuation_data.get("continuation")
            if isinstance(token, str):
                return token
        return None

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _extract_text(self, node: object) -> Optional[str]:
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            simple_text = node.get("simpleText")
            if isinstance(simple_text, str):
                return simple_text
            runs = node.get("runs")
            if isinstance(runs, list):
                return "".join(part for part in self._extract_runs_text(runs))
        return None

    def _extract_text_from_runs(self, data: object) -> Optional[str]:
        if isinstance(data, dict):
            if "runs" in data:
                return "".join(part for part in self._extract_runs_text(data["runs"]))
            if "simpleText" in data and isinstance(data["simpleText"], str):
                return data["simpleText"]
        return None

    def _extract_runs_text(self, runs: object) -> Iterable[str]:
        if not isinstance(runs, list):
            return []
        text_parts: List[str] = []
        for item in runs:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return text_parts

    def _find_value(self, node: object, key: str) -> Optional[object]:
        if isinstance(node, dict):
            if key in node:
                return node[key]
            for value in node.values():
                found = self._find_value(value, key)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_value(item, key)
                if found is not None:
                    return found
        return None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", help="YouTube channel URL or handle")
    parser.add_argument("--output", "-o", help="Optional path to write the scraped data as JSON")
    parser.add_argument(
        "--limit",
        type=int,
        help="Stop after collecting this many videos. Useful for quick smoke tests.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    scraper = YouTubeChannelScraper(args.channel)
    try:
        videos = scraper.scrape(limit=args.limit)
    except (HTTPError, URLError) as error:
        print(f"Network error while contacting YouTube: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - defensive guard
        print(f"Failed to scrape channel: {error}", file=sys.stderr)
        return 1

    serialisable = [entry.as_dict() for entry in videos]
    output = json.dumps(serialisable, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
