"""
agents/dom_fetcher.py - DOM FETCHER UTILITY
Fetches web pages and extracts locator-relevant elements to give Agent B
real selectors and Agent C a reference DOM for accuracy validation.

Supports multi-page crawling: fetches the base URL, discovers internal links
(1-level deep), and also accepts explicit extra URLs from requirements.
Produces a consolidated locator registry keyed by page URL.
"""

import json
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _get_response(url: str, timeout: int = 20):
    """Fetch a URL, with SSL fallback. Returns (response, error_str)."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp, ""
    except requests.exceptions.SSLError:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, headers=_HEADERS, timeout=timeout, verify=False)
            resp.raise_for_status()
            return resp, ""
        except Exception as e:
            return None, str(e)
    except Exception as e:
        return None, str(e)


def fetch_dom_snapshot(url: str, timeout: int = 20) -> dict:
    """
    Fetch the page at `url` and return a structured DOM snapshot
    containing locator-relevant elements.

    Returns a dict with:
        url      - the fetched URL
        title    - page <title>
        elements - list of dicts, one per interactive/notable element
        error    - non-empty string if fetch failed
    """
    resp, err = _get_response(url, timeout)
    if err:
        return {"url": url, "title": "", "elements": [], "error": err}

    soup = BeautifulSoup(resp.text, "html.parser")
    return {
        "url":      url,
        "title":    soup.title.string.strip() if soup.title else "",
        "elements": _extract_elements(soup),
        "error":    "",
    }


# ── Multi-page crawl & locator registry ──────────────────────────────────────

def _discover_internal_links(soup: BeautifulSoup, base_url: str,
                              max_links: int = 20) -> list[str]:
    """Extract internal links (same origin) from a page, up to max_links."""
    parsed_base = urlparse(base_url)
    origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    seen: set[str] = set()
    links: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Skip anchors, javascript, mailto
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        # Same origin only
        if f"{parsed.scheme}://{parsed.netloc}" != origin:
            continue
        # Normalize — strip fragment
        normalised = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalised += f"?{parsed.query}"
        if normalised not in seen and normalised != base_url.rstrip("/"):
            seen.add(normalised)
            links.append(normalised)
        if len(links) >= max_links:
            break

    return links


def build_locator_registry(base_url: str,
                           extra_urls: list[str] | None = None,
                           max_pages: int = 10,
                           timeout: int = 20,
                           log=None) -> dict:
    """
    Build a multi-page locator registry.

    1. Fetch the base URL and extract elements + internal links.
    2. Crawl discovered internal links (1-level deep, up to max_pages).
    3. Also fetch any extra_urls provided explicitly.
    4. Return a registry dict: {pages: [{url, title, elements}], errors: [str]}

    The registry is saved to output/locators.json.
    """
    pages: list[dict] = []
    errors: list[str] = []
    visited: set[str] = set()

    def _fetch_and_add(url: str):
        if url in visited:
            return
        visited.add(url)
        if log:
            log(f"   Fetching: {url}")
        snap = fetch_dom_snapshot(url, timeout)
        if snap.get("error"):
            errors.append(f"{url}: {snap['error']}")
            if log:
                log(f"   ⚠️  Error: {snap['error']}")
        else:
            pages.append({
                "url":      snap["url"],
                "title":    snap["title"],
                "elements": snap["elements"],
            })
            if log:
                log(f"   ✅ {len(snap['elements'])} elements")

    # ── Base URL ──────────────────────────────────────────────────────────
    resp, err = _get_response(base_url, timeout)
    if err:
        errors.append(f"{base_url}: {err}")
        registry = {"pages": pages, "errors": errors}
        _save_registry(registry)
        return registry

    soup = BeautifulSoup(resp.text, "html.parser")
    base_snap = {
        "url":      base_url,
        "title":    soup.title.string.strip() if soup.title else "",
        "elements": _extract_elements(soup),
    }
    pages.append(base_snap)
    visited.add(base_url)
    visited.add(base_url.rstrip("/"))
    if log:
        log(f"   ✅ Base: {len(base_snap['elements'])} elements from '{base_snap['title']}'")

    # ── Discover and crawl internal links ─────────────────────────────────
    internal_links = _discover_internal_links(soup, base_url, max_links=max_pages * 2)
    for link in internal_links:
        if len(pages) >= max_pages:
            break
        _fetch_and_add(link)

    # ── Extra URLs from requirements ──────────────────────────────────────
    for url in (extra_urls or []):
        url = url.strip()
        if url and url not in visited:
            _fetch_and_add(url)

    registry = {"pages": pages, "errors": errors}
    _save_registry(registry)
    return registry


def _save_registry(registry: dict):
    """Persist the registry to output/locators.json."""
    out = Path(__file__).parent.parent / "output"
    out.mkdir(exist_ok=True)
    (out / "locators.json").write_text(json.dumps(registry, indent=2))


def registry_to_text(registry: dict) -> str:
    """Convert the full multi-page registry to text for LLM prompts."""
    if not registry.get("pages"):
        err_str = "; ".join(registry.get("errors", []))
        return f"DOM FETCH ERROR: {err_str}\nLocators could not be verified."

    lines: list[str] = []
    total_elements = sum(len(p["elements"]) for p in registry["pages"])
    lines.append(f"LOCATOR REGISTRY — {len(registry['pages'])} page(s), "
                 f"{total_elements} total elements")
    lines.append("=" * 60)

    for page in registry["pages"]:
        lines.append("")
        lines.append(f"PAGE URL   : {page['url']}")
        lines.append(f"PAGE TITLE : {page['title']}")
        lines.append(f"ELEMENTS   : {len(page['elements'])}")
        lines.append("-" * 60)
        for el in page["elements"]:
            parts = [el.get("tag", "?")]
            for k in ("id", "name", "type", "placeholder", "aria-label",
                      "for", "role", "href", "data-testid"):
                if el.get(k):
                    parts.append(f'{k}="{el[k]}"')
            if el.get("text"):
                parts.append(f'text="{el["text"]}"')
            if el.get("options"):
                parts.append(f'options={el["options"]}')
            lines.append("  " + " | ".join(parts))

    if registry.get("errors"):
        lines.append("")
        lines.append("FETCH ERRORS:")
        for e in registry["errors"]:
            lines.append(f"  ⚠️  {e}")

    return "\n".join(lines)


# ── Element extraction ────────────────────────────────────────────────────────

def _get_text(tag: Tag, max_len: int = 100) -> str:
    text = tag.get_text(separator=" ", strip=True)
    return text[:max_len] if len(text) > max_len else text


def _sel(*keys):
    """Return a helper that picks named attributes from a tag."""
    def _pick(tag: Tag) -> dict:
        return {k: tag.get(k) for k in keys if tag.get(k)}
    return _pick


def _extract_elements(soup: BeautifulSoup) -> list:
    elements = []
    seen_ids: set[str] = set()

    def _add(entry: dict):
        # Deduplicate by id when present
        eid = entry.get("id")
        if eid:
            if eid in seen_ids:
                return
            seen_ids.add(eid)
        elements.append(entry)

    # ── Inputs ────────────────────────────────────────────────────────────
    for el in soup.find_all("input"):
        entry = {"tag": "input"}
        for attr in ("id", "name", "type", "placeholder", "aria-label",
                     "value", "data-testid", "class", "role"):
            if el.get(attr):
                entry[attr] = el[attr]
        entry.setdefault("type", "text")
        _add(entry)

    # ── Textareas ─────────────────────────────────────────────────────────
    for el in soup.find_all("textarea"):
        entry = {"tag": "textarea"}
        for attr in ("id", "name", "placeholder", "aria-label",
                     "data-testid", "class"):
            if el.get(attr):
                entry[attr] = el[attr]
        _add(entry)

    # ── Selects ───────────────────────────────────────────────────────────
    for el in soup.find_all("select"):
        entry = {"tag": "select"}
        for attr in ("id", "name", "aria-label", "data-testid", "class"):
            if el.get(attr):
                entry[attr] = el[attr]
        entry["options"] = [o.get_text(strip=True)
                            for o in el.find_all("option")][:15]
        _add(entry)

    # ── Buttons ───────────────────────────────────────────────────────────
    for el in soup.find_all("button"):
        entry = {"tag": "button", "text": _get_text(el)}
        for attr in ("id", "type", "aria-label", "data-testid", "class",
                     "name", "value"):
            if el.get(attr):
                entry[attr] = el[attr]
        _add(entry)

    # ── Links ─────────────────────────────────────────────────────────────
    for el in soup.find_all("a"):
        txt = _get_text(el)
        if not txt:
            continue
        entry = {"tag": "a", "text": txt}
        for attr in ("href", "id", "aria-label", "data-testid", "class",
                     "role"):
            if el.get(attr):
                entry[attr] = el[attr]
        _add(entry)

    # ── Labels ────────────────────────────────────────────────────────────
    for el in soup.find_all("label"):
        txt = _get_text(el)
        if not txt:
            continue
        entry = {"tag": "label", "text": txt}
        for attr in ("for", "id", "class"):
            if el.get(attr):
                entry[attr] = el[attr]
        _add(entry)

    # ── Headings ─────────────────────────────────────────────────────────
    for tag_name in ("h1", "h2", "h3", "h4"):
        for el in soup.find_all(tag_name):
            txt = _get_text(el)
            if txt:
                entry = {"tag": tag_name, "text": txt}
                for attr in ("id", "class"):
                    if el.get(attr):
                        entry[attr] = el[attr]
                _add(entry)

    # ── Forms ─────────────────────────────────────────────────────────────
    for el in soup.find_all("form"):
        entry = {"tag": "form"}
        for attr in ("id", "name", "action", "method", "class"):
            if el.get(attr):
                entry[attr] = el[attr]
        _add(entry)

    # ── Elements with data-testid not already captured ────────────────────
    for el in soup.find_all(attrs={"data-testid": True}):
        if el.name not in ("input", "textarea", "select", "button", "a",
                           "label"):
            entry = {"tag": el.name, "data-testid": el["data-testid"],
                     "text": _get_text(el)}
            for attr in ("id", "class", "role"):
                if el.get(attr):
                    entry[attr] = el[attr]
            _add(entry)

    # ── Elements with ARIA roles ───────────────────────────────────────────
    for el in soup.find_all(attrs={"role": True}):
        if el.name not in ("input", "button", "a", "select", "textarea"):
            entry = {"tag": el.name, "role": el["role"],
                     "text": _get_text(el)}
            for attr in ("id", "aria-label", "data-testid", "class"):
                if el.get(attr):
                    entry[attr] = el[attr]
            _add(entry)

    return elements


# ── Text conversion for LLM prompts ──────────────────────────────────────────

def dom_snapshot_to_text(snapshot: dict) -> str:
    """
    Convert a DOM snapshot dict to a readable text block suitable for
    injection into LLM prompts.
    """
    if snapshot.get("error"):
        return (
            f"DOM FETCH ERROR for {snapshot['url']}: {snapshot['error']}\n"
            "Locators could not be verified against the live page."
        )

    lines = [
        f"PAGE URL   : {snapshot['url']}",
        f"PAGE TITLE : {snapshot['title']}",
        f"ELEMENTS   : {len(snapshot['elements'])} interactive/notable elements captured",
        "",
        "ELEMENT LIST  (tag | attributes | text)",
        "-" * 60,
    ]
    for el in snapshot["elements"]:
        parts = [el.get("tag", "?")]
        for k in ("id", "name", "type", "placeholder", "aria-label",
                  "for", "role", "href", "data-testid"):
            if el.get(k):
                parts.append(f'{k}="{el[k]}"')
        if el.get("text"):
            parts.append(f'text="{el["text"]}"')
        if el.get("options"):
            parts.append(f'options={el["options"]}')
        lines.append("  " + " | ".join(parts))

    return "\n".join(lines)
