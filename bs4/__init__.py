"""A tiny subset implementation of BeautifulSoup used for parsing simple HTML.

This lightweight module emulates the small portion of the BeautifulSoup API
required by the project. It should not be considered a drop-in replacement for
`beautifulsoup4`, but it is sufficient for the basic parsing tasks performed in
this repository (locating script tags and reading their content).

The implementation is intentionally minimal: it uses the standard library's
``html.parser`` module to build a tree of :class:`Tag` objects. Only the methods
used by the scraper are implemented (:meth:`find`, :meth:`find_all`, and
:meth:`get_text`).
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Union

__all__ = ["BeautifulSoup", "Tag"]


class Tag:
    """Represents a very small subset of a BeautifulSoup Tag.

    Only the behaviour required by the scraper is implemented. The API mirrors
    the real BeautifulSoup tag just enough to work with the code in this
    repository and is *not* a general purpose parser.
    """

    def __init__(self, name: str, attrs: Optional[Dict[str, str]] = None, parent: Optional["Tag"] = None) -> None:
        self.name = name
        self.attrs = attrs or {}
        self.parent = parent
        self.children: List[Union["Tag", str]] = []

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------
    def append(self, child: Union["Tag", str]) -> None:
        if isinstance(child, Tag):
            child.parent = self
        self.children.append(child)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def find(self, name: Optional[str] = None) -> Optional["Tag"]:
        """Return the first descendant whose tag name matches ``name``.

        If ``name`` is ``None`` the first descendant :class:`Tag` object is
        returned regardless of its name.
        """

        for child in self.children:
            if isinstance(child, Tag):
                if name is None or child.name == name:
                    return child
                result = child.find(name)
                if result is not None:
                    return result
        return None

    def find_all(self, name: Optional[str] = None) -> List["Tag"]:
        """Return all descendant tags that match ``name``.

        When ``name`` is ``None`` every descendant :class:`Tag` is returned.
        """

        matches: List[Tag] = []
        for child in self.children:
            if isinstance(child, Tag):
                if name is None or child.name == name:
                    matches.append(child)
                matches.extend(child.find_all(name))
        return matches

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.attrs.get(key, default)

    @property
    def string(self) -> Optional[str]:
        """Return the text content if the tag only contains a single string.
        """

        if not self.children:
            return ""
        if len(self.children) == 1 and isinstance(self.children[0], str):
            return self.children[0]
        if all(isinstance(child, str) for child in self.children):
            return "".join(self.children)  # pragma: no cover - minimal helper
        return None

    def get_text(self, strip: bool = False) -> str:
        """Return the concatenated text of all descendants."""

        parts: List[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child.strip() if strip else child)
            else:
                parts.append(child.get_text(strip=strip))
        text = "".join(parts)
        return text.strip() if strip else text

    # ------------------------------------------------------------------
    # Representation helpers
    # ------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - debug helper
        attrs = " ".join(f"{k}='{v}'" for k, v in self.attrs.items())
        if attrs:
            attrs = " " + attrs
        return f"<{self.name}{attrs}>"


class _SoupBuilder(HTMLParser):
    """Internal helper that builds a very small DOM-like tree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Tag("[document]")
        self.current = self.root

    # HTMLParser callbacks ------------------------------------------------
    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attributes = {k: v or "" for k, v in attrs}
        new_tag = Tag(tag, attributes, self.current)
        self.current.append(new_tag)
        self.current = new_tag

    def handle_endtag(self, tag: str) -> None:
        cursor = self.current
        while cursor is not None and cursor.name != tag:
            cursor = cursor.parent
        if cursor is not None and cursor.parent is not None:
            self.current = cursor.parent
        else:
            self.current = self.root

    def handle_data(self, data: str) -> None:
        if data:
            self.current.append(data)

    def close(self) -> Tag:
        super().close()
        return self.root


class BeautifulSoup:
    """A tiny subset of :class:`bs4.BeautifulSoup` used for scraping."""

    def __init__(self, markup: str, parser: str = "html.parser") -> None:
        if parser != "html.parser":  # pragma: no cover - defensive guard
            raise ValueError("Only the built-in 'html.parser' is supported")
        builder = _SoupBuilder()
        builder.feed(markup)
        self.root = builder.close()

    # Public API ----------------------------------------------------------
    def find(self, name: Optional[str] = None) -> Optional[Tag]:
        return self.root.find(name)

    def find_all(self, name: Optional[str] = None) -> List[Tag]:
        return self.root.find_all(name)

    def get_text(self, strip: bool = False) -> str:
        return self.root.get_text(strip=strip)

    # Compatibility helpers ----------------------------------------------
    def __iter__(self) -> Iterable[Tag]:  # pragma: no cover - convenience
        return iter(self.root.children)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return repr(self.root)
