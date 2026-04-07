#!/usr/bin/env python3
"""Bulk-clean downloaded LaravelDaily lesson pages.

- Removes breadcrumb navigation in the lesson header.
- Removes the floating Feedback button, modal dialog, and feedback-related scripts.
- Rewrites links to LaravelDaily lesson URLs to local HTML files.
- Removes non-functional Livewire UI (Completed button) and Spotlight search overlay.
- Removes leftover Livewire/EasyMDE assets and scripts from static exports.

By default, the script is rerun-friendly: it won't warn when a section is
already removed (0 matches). Use --strict to warn when a section isn't found.

Intended to run against static HTML files in ./laraveldaily/*.html.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass
class FileChangeStats:
    breadcrumb_removed: int = 0
    feedback_markup_removed: int = 0
    feedback_scripts_removed: int = 0
    lesson_links_rewritten: int = 0
    comments_section_removed: int = 0
    livewire_completed_button_removed: int = 0
    spotlight_removed: int = 0
    livewire_assets_removed: int = 0
    easymde_assets_removed: int = 0
    comments_editor_scripts_removed: int = 0
    ui_strings_translated: int = 0
    lesson_body_strings_translated: int = 0
    local_nav_inserted: int = 0


BREADCRUMB_BLOCK_RE = re.compile(
    r"\n\s*<!-- Breadcrumbs -->\s*\n\s*<nav class=\"mb-6\" aria-label=\"Breadcrumb\">.*?</nav>\s*\n",
    re.S,
)

FEEDBACK_MARKUP_RE = re.compile(
    r"\n\s*<!-- Feedback Modal -->\s*\n\s*<!-- Feedback Button -->.*?</dialog>\s*\n",
    re.S | re.I,
)

SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)

SAVED_FROM_LESSON_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*saved from url=\(\d+\)(https?://laraveldaily\.com/lesson/[^\s]+)\s*-->",
    re.I,
)

HREF_LESSON_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"href=\"(https?://laraveldaily\.com/lesson/[^\"#?\s]+)([^\"]*)\"",
    re.I,
)

COMMENTS_SECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\n\s*<!-- Comments Section -->.*?(?=\n\s*</main>)",
    re.S | re.I,
)

LIVEWIRE_SCRIPT_SRC_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*<script\s+src=\"\./[^\"]*livewire\.js\"[^>]*></script>\s*",
    re.I,
)

LIVEWIRE_INIT_SCRIPT_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*<script\b[^>]*>\s*window\.livewire\s*=.*?</script>\s*",
    re.S | re.I,
)

LIVEWIRE_COMPLETED_BUTTON_RE: Final[re.Pattern[str]] = re.compile(
    r"\n\s*<div\s+wire:id=\"[^\"]+\">.*?wire:click=\"toggleCompleted\".*?\n\s*</div>\s*\n\s*<!--\s*Livewire Component wire-end:[^>]*-->\s*",
    re.S | re.I,
)

SPOTLIGHT_OVERLAY_RE: Final[re.Pattern[str]] = re.compile(
    r"\n\s*<div\s+wire:id=\"[^\"]+\">\s*\n\s*<div[^>]*x-data=\"Spotlight\.config\(.*?\n\s*</div>\s*\n\s*</div>\s*\n\s*<!--\s*Livewire Component wire-end:[^>]*-->\s*",
    re.S | re.I,
)

EASYMDE_JS_RE: Final[re.Pattern[str]] = re.compile(
    r"<script\s+src=\"\./[^\"]*easymde(?:\.min)?\.js\"[^>]*>\s*</script>",
    re.I,
)

EASYMDE_CSS_RE: Final[re.Pattern[str]] = re.compile(
    r"<link\b[^>]*href=\"\./[^\"]*easymde(?:\.min)?\.css\"[^>]*>",
    re.I,
)

NAV_REMOVED_RE: Final[re.Pattern[str]] = re.compile(
    r"\n\s*<!-- Navigation removed -->\s*\n",
    re.I,
)

LOCAL_NAV_MARKER: Final[str] = "<!-- Local Site Navigation (FDC) -->"
LOCAL_NAV_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"\n\s*<!-- Local Site Navigation \(FDC\) -->\s*\n\s*<header\b.*?</header>\s*\n",
    re.S | re.I,
)

LOCAL_NAV_HTML: Final[str] = (
    "\n"
    + LOCAL_NAV_MARKER
    + "\n"
    + '<header class="sticky top-0 z-50 backdrop-blur bg-slate-950/70 border-b border-slate-800">\n'
    + '  <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">\n'
    + '    <a href="../index.html" class="font-semibold tracking-tight">FDC • MBO Utrecht</a>\n'
    + '    <nav class="text-sm flex gap-4 flex-wrap justify-end">\n'
    + '      <a class="hover:text-white text-slate-200" href="../dashboard.html">Dashboard</a>\n'
    + '      <a class="hover:text-white text-slate-200" href="../start-hier.html">Start hier</a>\n'
    + '      <a class="hover:text-white text-slate-200" href="../challenge.html">De Challenge</a>\n'
    + '      <a class="hover:text-white text-slate-200" href="../tutorials.html">Tutorials</a>\n'
    + '      <a class="hover:text-white text-slate-200" href="../certificaat.html">Certificaat</a>\n'
    + "    </nav>\n"
    + "  </div>\n"
    + "</header>\n\n"
)

ARTICLE_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"(<article\b[^>]*\bclass=\"[^\"]*\bprose\b[^\"]*\"[^>]*>)(.*?)(</article>)",
    re.S | re.I,
)


class DeepLTranslator:
    def __init__(self, *, auth_key: str, api_url: str) -> None:
        self._auth_key = auth_key
        self._api_url = api_url

    def translate_texts(
        self, texts: list[str], *, source_lang: str, target_lang: str
    ) -> list[str]:
        if not texts:
            return []

        results: list[str] = []

        def batches(values: list[str]) -> list[list[str]]:
            # DeepL supports multiple `text` params. Keep batches modest.
            max_items = 40
            max_chars = 12000
            out: list[list[str]] = []
            current: list[str] = []
            current_chars = 0
            for value in values:
                value_len = len(value)
                if current and (
                    len(current) >= max_items or current_chars + value_len > max_chars
                ):
                    out.append(current)
                    current = []
                    current_chars = 0
                current.append(value)
                current_chars += value_len
            if current:
                out.append(current)
            return out

        for batch in batches(texts):
            fields: list[tuple[str, str]] = [
                ("auth_key", self._auth_key),
                ("target_lang", target_lang.upper()),
                ("source_lang", source_lang.upper()),
                ("preserve_formatting", "1"),
            ]
            for text in batch:
                fields.append(("text", text))

            body = urllib.parse.urlencode(fields).encode("utf-8")
            request = urllib.request.Request(
                self._api_url,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(
                    f"DeepL API error ({exc.code}). Response: {detail[:500]}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"DeepL API connection error: {exc}") from exc

            translations = payload.get("translations")
            if not isinstance(translations, list):
                raise RuntimeError(
                    "Unexpected DeepL response format (missing translations)"
                )

            results.extend(
                [t.get("text", "") for t in translations if isinstance(t, dict)]
            )

        if len(results) != len(texts):
            raise RuntimeError(
                f"DeepL returned {len(results)} translations for {len(texts)} inputs"
            )

        return results


def translate_lesson_body_to_dutch(
    html: str,
    *,
    translator: DeepLTranslator,
    source_lang: str,
    target_lang: str,
) -> tuple[str, int]:
    """Translate the lesson body inside the main <article class="... prose ...">.

    Skips code blocks and other technical tags.
    """

    try:
        from bs4 import BeautifulSoup, NavigableString  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency for content translation. Install with: pip install beautifulsoup4"
        ) from exc

    match = ARTICLE_BLOCK_RE.search(html)
    if not match:
        return html, 0

    article_open, article_inner, article_close = (
        match.group(1),
        match.group(2),
        match.group(3),
    )

    soup = BeautifulSoup(article_inner, "html.parser")
    skip_tags = {"script", "style", "pre", "code", "kbd", "samp", "var", "svg", "math"}

    text_nodes: list[NavigableString] = []
    texts: list[str] = []

    for node in soup.descendants:
        if not isinstance(node, NavigableString):
            continue
        if not node.strip():
            continue
        parent = getattr(node, "parent", None)
        if not parent or not getattr(parent, "name", None):
            continue
        if parent.name in skip_tags:
            continue
        if parent.find_parent(list(skip_tags)) is not None:
            continue

        text_nodes.append(node)
        texts.append(str(node))

    if not texts:
        return html, 0

    translated_texts = translator.translate_texts(
        texts, source_lang=source_lang, target_lang=target_lang
    )
    for node, translated_text in zip(text_nodes, translated_texts, strict=True):
        node.replace_with(translated_text)

    new_inner = "".join(str(child) for child in soup.contents)
    new_article = f"{article_open}{new_inner}{article_close}"

    updated_html = ARTICLE_BLOCK_RE.sub(new_article, html, count=1)
    return updated_html, len(text_nodes)


def translate_ui_to_dutch(html: str) -> tuple[str, int]:
    """Translate small UI strings to Dutch.

    Intentionally limited in scope to avoid touching lesson body text.
    """

    translated = 0

    # Skip link
    html, n = re.subn(
        r">\s*Skip to main content\s*<",
        ">Ga naar hoofdinhoud<",
        html,
        flags=re.I,
    )
    translated += n

    # Previous/Next buttons (header)
    html, n = re.subn(
        r'aria-label="Previous lesson"',
        'aria-label="Vorige les"',
        html,
        flags=re.I,
    )
    translated += n
    html, n = re.subn(
        r'aria-label="Next lesson"',
        'aria-label="Volgende les"',
        html,
        flags=re.I,
    )
    translated += n

    # Lesson navigation (bottom) labels
    html, n = re.subn(
        r'(<div[^>]*class="text-xs\s+text-gray-400\s+mb-1"[^>]*>)\s*Previous\s*(</div>)',
        r"\1Vorige\2",
        html,
        flags=re.I,
    )
    translated += n
    html, n = re.subn(
        r'(<div[^>]*class="text-xs\s+text-gray-400\s+mb-1"[^>]*>)\s*Next\s*(</div>)',
        r"\1Volgende\2",
        html,
        flags=re.I,
    )
    translated += n

    # Generic button text snippets
    html, n = re.subn(
        r'(<span[^>]*class="text-sm\s+text-gray-300"[^>]*>)\s*Autoplay\s*(</span>)',
        r"\1Automatisch afspelen\2",
        html,
        flags=re.I,
    )
    translated += n

    # Show/Hide lessons list strings used inside x-text.
    # These appear both as literal quotes and as HTML entities (&#39;).
    for old, new in (
        ("'Hide Lessons List'", "'Verberg lessenlijst'"),
        ("'Show Lessons List'", "'Toon lessenlijst'"),
        ("&#39;Hide Lessons List&#39;", "&#39;Verberg lessenlijst&#39;"),
        ("&#39;Show Lessons List&#39;", "&#39;Toon lessenlijst&#39;"),
        ("Hide Lessons List", "Verberg lessenlijst"),
        ("Show Lessons List", "Toon lessenlijst"),
    ):
        count = html.count(old)
        if count:
            html = html.replace(old, new)
            translated += count

    # Scroll to top
    count = html.count('aria-label="Scroll to top"')
    if count:
        html = html.replace('aria-label="Scroll to top"', 'aria-label="Naar boven"')
        translated += count

    # Copy button
    for old, new in (
        ('aria-label="Copy to Clipboard"', 'aria-label="Kopieer naar klembord"'),
        ('title="Copy to Clipboard"', 'title="Kopieer naar klembord"'),
    ):
        count = html.count(old)
        if count:
            html = html.replace(old, new)
            translated += count

    # Lesson label: "Lesson 09/26" -> "Les 09/26"
    html, n = re.subn(
        r"(<span>\s*)Lesson(\s*[0-9]{1,2}\s*/\s*[0-9]{1,2}\s*</span>)",
        r"\1Les\2",
        html,
        flags=re.I,
    )
    translated += n

    # Reading time
    # "12 min read" -> "12 min leestijd" (sidebar list)
    html, n = re.subn(
        r'(<span[^>]*class="text-xs\s+text-gray-400\s+flex-shrink-0"[^>]*>)\s*(\d+)\s*min\s+read\s*(</span>)',
        r"\1\2 min leestijd\3",
        html,
        flags=re.I,
    )
    translated += n

    # Generic occurrences like <span>2 min read</span>
    html, n = re.subn(
        r"\b(\d+)\s*min\s+read\b",
        r"\1 min leestijd",
        html,
        flags=re.I,
    )
    translated += n

    # Generic occurrences like "1 h 56 min read" -> "1 u 56 min leestijd"
    html, n = re.subn(
        r"\b(\d+)\s*h\s+(\d+)\s*min\s+read\b",
        r"\1 u \2 min leestijd",
        html,
        flags=re.I,
    )
    translated += n

    # If a prior pass already translated "min read" but left "h" intact.
    html, n = re.subn(
        r"\b(\d+)\s*h\s+(\d+)\s*min\s+leestijd\b",
        r"\1 u \2 min leestijd",
        html,
        flags=re.I,
    )
    translated += n

    return html, translated


def ensure_local_site_nav(html: str) -> tuple[str, int]:
    # If nav already exists, keep it in sync with the template.
    if LOCAL_NAV_MARKER in html:
        updated, n = LOCAL_NAV_BLOCK_RE.subn("\n" + LOCAL_NAV_HTML, html, count=1)
        return updated, n

    updated, n = NAV_REMOVED_RE.subn("\n" + LOCAL_NAV_HTML, html, count=1)
    return updated, n


def remove_script_blocks_containing(
    html: str, needles: tuple[str, ...]
) -> tuple[str, int]:
    removed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal removed
        block = match.group(0)
        if any(needle in block for needle in needles):
            removed += 1
            return ""
        return block

    return SCRIPT_BLOCK_RE.sub(repl, html), removed


def remove_feedback_scripts(html: str) -> tuple[str, int]:
    return remove_script_blocks_containing(html, ("feedbackModal", "feedbackForm"))


def normalize_lesson_url(url: str) -> str:
    url = url.strip()
    if url.endswith("/"):
        url = url[:-1]
    url = url.split("#", 1)[0]
    return url


def extract_lesson_url_from_file(html: str, file_path: Path) -> str:
    match = SAVED_FROM_LESSON_URL_RE.search(html)
    if not match:
        raise ValueError(
            f"Could not find saved-from lesson URL in {file_path}. "
            "Expected a comment like: <!-- saved from url=(...)https://laraveldaily.com/lesson/... -->"
        )
    return normalize_lesson_url(match.group(1))


def build_lesson_url_map(files: list[Path]) -> dict[str, str]:
    url_to_filename: dict[str, str] = {}

    for file_path in files:
        html = file_path.read_text(encoding="utf-8", errors="ignore")
        url = extract_lesson_url_from_file(html, file_path)
        if url in url_to_filename and url_to_filename[url] != file_path.name:
            raise ValueError(
                f"Duplicate lesson URL mapping for {url}: {url_to_filename[url]} vs {file_path.name}"
            )
        url_to_filename[url] = file_path.name

    return url_to_filename


def rewrite_lesson_links(
    html: str, *, current_lesson_url: str, url_to_filename: dict[str, str]
) -> tuple[str, int]:
    rewritten = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal rewritten
        base_url = normalize_lesson_url(match.group(1))
        suffix = match.group(2) or ""
        filename = url_to_filename.get(base_url)
        if not filename:
            return match.group(0)

        rewritten += 1
        if base_url == current_lesson_url and suffix.startswith("#"):
            return f'href="{suffix}"'
        return f'href="{filename}{suffix}"'

    return HREF_LESSON_URL_RE.sub(repl, html), rewritten


def process_file(
    path: Path,
    *,
    url_to_filename: dict[str, str],
    translate_lesson_body: bool,
    deepl_auth_key: str | None,
    source_lang: str,
    target_lang: str,
    output_dir: Path | None,
    in_place: bool,
) -> FileChangeStats:
    original = path.read_text(encoding="utf-8", errors="ignore")
    updated = original
    stats = FileChangeStats()

    current_lesson_url = extract_lesson_url_from_file(updated, path)

    updated, n = BREADCRUMB_BLOCK_RE.subn("\n", updated, count=1)
    stats.breadcrumb_removed = n

    updated, n = ensure_local_site_nav(updated)
    stats.local_nav_inserted = n

    updated, n = FEEDBACK_MARKUP_RE.subn("\n", updated, count=1)
    stats.feedback_markup_removed = n

    updated, n = remove_feedback_scripts(updated)
    stats.feedback_scripts_removed = n

    updated, n = LIVEWIRE_COMPLETED_BUTTON_RE.subn("\n", updated)
    stats.livewire_completed_button_removed = n

    updated, n = SPOTLIGHT_OVERLAY_RE.subn("\n", updated)
    stats.spotlight_removed = n

    updated, n1 = LIVEWIRE_SCRIPT_SRC_RE.subn("\n", updated)
    updated, n2 = LIVEWIRE_INIT_SCRIPT_RE.subn("\n", updated)
    stats.livewire_assets_removed = n1 + n2

    updated, n1 = EASYMDE_JS_RE.subn("", updated)
    updated, n2 = EASYMDE_CSS_RE.subn("", updated)
    stats.easymde_assets_removed = n1 + n2

    updated, n = remove_script_blocks_containing(
        updated,
        (
            "Laravel Comments scripts were loaded",
            "EasyMDE",
            "loadEasyMDE",
            'Alpine.data("compose"',
        ),
    )
    stats.comments_editor_scripts_removed = n

    updated, n = translate_ui_to_dutch(updated)
    stats.ui_strings_translated = n

    if translate_lesson_body:
        if not deepl_auth_key:
            raise RuntimeError(
                "Lesson-body translation requested but no DeepL auth key provided. "
                "Set DEEPL_AUTH_KEY or pass --deepl-auth-key."
            )

        api_url = os.environ.get("DEEPL_API_URL")
        if not api_url:
            api_url = (
                "https://api-free.deepl.com/v2/translate"
                if deepl_auth_key.endswith(":fx")
                else "https://api.deepl.com/v2/translate"
            )

        translator = DeepLTranslator(auth_key=deepl_auth_key, api_url=api_url)
        updated, n = translate_lesson_body_to_dutch(
            updated,
            translator=translator,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        stats.lesson_body_strings_translated = n

    updated, n = rewrite_lesson_links(
        updated,
        current_lesson_url=current_lesson_url,
        url_to_filename=url_to_filename,
    )
    stats.lesson_links_rewritten = n

    updated, n = COMMENTS_SECTION_RE.subn("\n", updated, count=1)
    stats.comments_section_removed = n

    output_path = path
    if not in_place and output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / path.name

    if output_path != path or updated != original:
        output_path.write_text(updated, encoding="utf-8")

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean laraveldaily/*.html pages")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Warn if expected sections are not found (0 matches).",
    )
    parser.add_argument(
        "--translate-lesson-body",
        action="store_true",
        help=(
            "Translate the lesson article body to Dutch via DeepL. "
            "Requires DEEPL_AUTH_KEY (or --deepl-auth-key) and beautifulsoup4."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Write updated files to a separate directory (e.g. laraveldaily-nl). "
            "Useful to avoid overwriting originals."
        ),
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write changes back into the original files (default behavior for cleanup-only runs).",
    )
    parser.add_argument(
        "--deepl-auth-key",
        default=None,
        help="DeepL API key. Prefer setting DEEPL_AUTH_KEY env var.",
    )
    parser.add_argument(
        "--source-lang",
        default="EN",
        help="Source language for translation (default: EN).",
    )
    parser.add_argument(
        "--target-lang",
        default="NL",
        help="Target language for translation (default: NL).",
    )
    args = parser.parse_args(argv)

    files = [Path(p) for p in sorted(glob.glob("laraveldaily/*.html"))]
    if not files:
        raise SystemExit("No files matched laraveldaily/*.html")

    url_to_filename = build_lesson_url_map(files)

    output_dir = Path(args.output_dir) if args.output_dir else None
    in_place = bool(args.in_place) or output_dir is None

    if args.translate_lesson_body and output_dir is None and not args.in_place:
        raise SystemExit(
            "Refusing to overwrite originals for full lesson translation. "
            "Use --output-dir laraveldaily-nl (recommended) or --in-place."
        )

    totals = FileChangeStats()
    missing_breadcrumb = []
    missing_feedback = []
    missing_comments = []

    deepl_auth_key = args.deepl_auth_key or os.environ.get("DEEPL_AUTH_KEY")

    for file_path in files:
        stats = process_file(
            file_path,
            url_to_filename=url_to_filename,
            translate_lesson_body=args.translate_lesson_body,
            deepl_auth_key=deepl_auth_key,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            output_dir=output_dir,
            in_place=in_place,
        )
        totals.breadcrumb_removed += stats.breadcrumb_removed
        totals.feedback_markup_removed += stats.feedback_markup_removed
        totals.feedback_scripts_removed += stats.feedback_scripts_removed
        totals.lesson_links_rewritten += stats.lesson_links_rewritten
        totals.comments_section_removed += stats.comments_section_removed
        totals.livewire_completed_button_removed += (
            stats.livewire_completed_button_removed
        )
        totals.spotlight_removed += stats.spotlight_removed
        totals.livewire_assets_removed += stats.livewire_assets_removed
        totals.easymde_assets_removed += stats.easymde_assets_removed
        totals.comments_editor_scripts_removed += stats.comments_editor_scripts_removed
        totals.ui_strings_translated += stats.ui_strings_translated
        totals.lesson_body_strings_translated += stats.lesson_body_strings_translated
        totals.local_nav_inserted += stats.local_nav_inserted

        if stats.breadcrumb_removed > 1 or (
            args.strict and stats.breadcrumb_removed != 1
        ):
            missing_breadcrumb.append((str(file_path), stats.breadcrumb_removed))
        if stats.feedback_markup_removed > 1 or (
            args.strict and stats.feedback_markup_removed != 1
        ):
            missing_feedback.append((str(file_path), stats.feedback_markup_removed))
        if stats.comments_section_removed > 1 or (
            args.strict and stats.comments_section_removed != 1
        ):
            missing_comments.append((str(file_path), stats.comments_section_removed))

    print(f"Processed {len(files)} files")
    print(
        "Removed:",
        {
            "breadcrumb_blocks": totals.breadcrumb_removed,
            "feedback_markup_blocks": totals.feedback_markup_removed,
            "feedback_script_blocks": totals.feedback_scripts_removed,
            "lesson_links_rewritten": totals.lesson_links_rewritten,
            "comments_sections_removed": totals.comments_section_removed,
            "livewire_completed_buttons_removed": totals.livewire_completed_button_removed,
            "spotlight_overlays_removed": totals.spotlight_removed,
            "livewire_assets_removed": totals.livewire_assets_removed,
            "easymde_assets_removed": totals.easymde_assets_removed,
            "comments_editor_scripts_removed": totals.comments_editor_scripts_removed,
            "ui_strings_translated": totals.ui_strings_translated,
            "lesson_body_strings_translated": totals.lesson_body_strings_translated,
            "local_nav_inserted": totals.local_nav_inserted,
        },
    )

    if missing_breadcrumb:
        print(
            "WARNING: breadcrumb block replacements unexpected (use --strict to flag 0 matches) for:"
        )
        for p, c in missing_breadcrumb[:10]:
            print(f"  {p}: {c}")

    if missing_feedback:
        print(
            "WARNING: feedback markup replacements unexpected (use --strict to flag 0 matches) for:"
        )
        for p, c in missing_feedback[:10]:
            print(f"  {p}: {c}")

    if missing_comments:
        print(
            "WARNING: comments section replacements unexpected (use --strict to flag 0 matches) for:"
        )
        for p, c in missing_comments[:10]:
            print(f"  {p}: {c}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
