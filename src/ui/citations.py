"""
Inline citation badges and always-visible source cards for LexAI assistant messages.

Parses the SOURCES/LAHTEET/KALLOR block from LLM responses and renders
them as styled HTML badge-links inline and as source cards below the answer.
"""

import base64
import html
import re

import streamlit as st
import streamlit.components.v1 as components

from src.config.translations import t


def _safe_url(url: str) -> str:
    """Validate URL scheme — allow only http/https to prevent javascript: XSS."""
    if url and url.startswith(("http://", "https://")):
        return html.escape(url, quote=True)
    return ""


# Regex to split response text from the sources block.
# Matches SOURCES:, LAHTEET:, KALLOR:, KILDER: (with optional heading markup)
_SOURCES_RE = re.compile(
    r"\n\s*(?:\*{0,2})(SOURCES|L\u00c4HTEET|K\u00c4LLOR|KILDER)\s*:?\s*(?:\*{0,2})\s*\n",
    re.IGNORECASE,
)

# Regex to extract individual source lines: - [CaseID](url) or - [CaseID]
_SOURCE_LINE_RE = re.compile(
    r"-\s*\[([^\]]+)\]\(([^)]+)\)",
)

# Regex to find inline case citations:
# Finnish: [KKO:2024:76], [KHO:2023:T97]
# EU: [C-311/18], [T-123/20], [ECLI:EU:C:2024:123]
_INLINE_CITE_RE = re.compile(r"\[(?:(?:KKO|KHO):[^\]]+|[CT]-\d+/\d{2,4}|ECLI:EU:[CT]:\d{4}:\d+)\]")

# Regex to split on ## section headings
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def parse_response_and_sources(response: str) -> tuple[str, list[dict[str, str]]]:
    """Split an LLM response into answer text and a list of source dicts.

    Returns:
        (answer_text, sources) where sources is a list of
        {"case_id": "KKO:2024:76", "url": "https://..."} dicts.
    """
    if not response:
        return "", []

    match = _SOURCES_RE.search(response)
    if not match:
        return response.strip(), []

    answer_text = response[: match.start()].strip()
    sources_block = response[match.end() :]

    sources: list[dict[str, str]] = []
    for raw_line in sources_block.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _SOURCE_LINE_RE.search(line)
        if m:
            sources.append({"case_id": m.group(1), "url": m.group(2)})
        elif line.startswith("-"):
            # Source without URL: - [KKO:2024:76]
            case_match = re.search(r"\[([^\]]+)\]", line)
            if case_match:
                sources.append({"case_id": case_match.group(1), "url": ""})

    return answer_text, sources


def _linkify_inline_citations(text: str, url_map: dict[str, str], theme: dict | None = None) -> str:
    """Replace [KKO:2024:76] patterns in answer text with styled HTML badge-links.

    Text is HTML-escaped first to prevent XSS from LLM output, then
    citation patterns (which survive escaping) are replaced with safe
    badge HTML.
    """
    escaped_text = html.escape(text)
    if not url_map:
        return escaped_text

    accent = (theme or {}).get("accent", "#2563eb")

    def _replace_cite(m: re.Match) -> str:
        cite = m.group(0)
        case_id = cite[1:-1]
        safe_case_id = html.escape(case_id)
        safe_url = _safe_url(url_map.get(case_id, ""))
        badge_style = (
            f"display:inline-block;background:{accent}18;color:{accent};"
            f"border:1px solid {accent}40;border-radius:4px;"
            f"padding:1px 6px;font-size:0.82em;font-weight:600;"
            f"text-decoration:none;white-space:nowrap;"
        )
        if safe_url:
            return f'<a href="{safe_url}" target="_blank" style="{badge_style}">{safe_case_id}</a>'
        return f'<span style="{badge_style}">{safe_case_id}</span>'

    return _INLINE_CITE_RE.sub(_replace_cite, escaped_text)


def _render_source_cards(
    sources: list[dict[str, str]],
    message_idx: int,
    lang: str,
    theme: dict | None = None,
) -> None:
    """Render always-visible source cards (not collapsed)."""
    if not sources:
        return

    th = theme or {}
    border = th.get("border", "#e2e8f0")
    surface = th.get("surface", "#f8fafc")
    accent = th.get("accent", "#2563eb")
    text_color = th.get("text", "#0f172a")

    # Try to get enriched metadata from session state
    metadata = st.session_state.get(f"msg_metadata_{message_idx}", {})
    search_results = metadata.get("search_results", [])

    # Build a lookup from case_id to search result metadata
    meta_lookup: dict[str, dict] = {}
    for sr in search_results:
        sr_meta = sr.get("metadata", {}) if isinstance(sr, dict) else {}
        cid = sr_meta.get("case_id", "")
        if cid:
            meta_lookup[cid] = sr_meta

    st.markdown(
        f"<div style='margin-top:0.75rem;margin-bottom:0.25rem;font-weight:600;"
        f"font-size:0.9rem;color:{text_color};'>"
        f"\U0001f4da {t('sources_heading', lang)} ({len(sources)})</div>",
        unsafe_allow_html=True,
    )

    for src in sources:
        case_id = src["case_id"]
        url = src["url"]
        sr_meta = meta_lookup.get(case_id, {})

        # Enrich with metadata when available
        court = sr_meta.get("court", "")
        year = sr_meta.get("year", "")
        keywords = sr_meta.get("keywords") or sr_meta.get("legal_domains") or []
        if isinstance(keywords, list):
            keywords = ", ".join(keywords[:3])

        safe_case_id = html.escape(case_id)
        safe_url = _safe_url(url)
        title_html = (
            f'<a href="{safe_url}" target="_blank" style="color:{accent};font-weight:600;'
            f'text-decoration:none;font-size:0.88rem;">{safe_case_id}</a>'
            if safe_url
            else f'<span style="color:{accent};font-weight:600;font-size:0.88rem;">{safe_case_id}</span>'
        )

        meta_parts = []
        if court:
            meta_parts.append(html.escape(court.upper() if len(court) <= 4 else court))
        if year:
            meta_parts.append(html.escape(str(year)))
        if keywords:
            meta_parts.append(html.escape(str(keywords)))
        meta_html = (
            f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px;">{" &middot; ".join(meta_parts)}</div>'
            if meta_parts
            else ""
        )

        st.markdown(
            f'<div style="border:1px solid {border};border-left:3px solid {accent};'
            f"border-radius:8px;padding:0.5rem 0.75rem;margin-bottom:0.375rem;"
            f'background:{surface};">'
            f"{title_html}{meta_html}</div>",
            unsafe_allow_html=True,
        )


def _parse_sections(answer_text: str) -> list[tuple[str, str]]:
    """Split answer text on ## headings into (heading, content) tuples.

    If no ## markers found, returns a single section with empty heading (graceful fallback).
    """
    parts = _SECTION_RE.split(answer_text)
    if len(parts) <= 1:
        # No section markers found
        return [("", answer_text)]

    sections: list[tuple[str, str]] = []
    # parts[0] is text before the first ##, parts[1] is first heading, parts[2] is content, etc.
    if parts[0].strip():
        sections.append(("", parts[0].strip()))
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if heading or content:
            sections.append((heading, content))
    return sections


def _render_confidence_badge(message_idx: int, lang: str, theme: dict | None = None) -> None:
    """Render a traffic-light confidence badge from metadata. Skips if no metadata."""
    metadata = st.session_state.get(f"msg_metadata_{message_idx}", {})
    score = metadata.get("relevancy_score")
    if score is None:
        return

    try:
        score = int(score)
    except (ValueError, TypeError):
        return

    reason = metadata.get("relevancy_reason", "")

    if score >= 4:
        color = "#22c55e"
        label = t("confidence_high", lang)
    elif score == 3:
        color = "#f59e0b"
        label = t("confidence_medium", lang)
    else:
        color = "#ef4444"
        label = t("confidence_low", lang)

    th = theme or {}
    text_color = th.get("text", "#0f172a")

    badge_html = (
        f'<div style="display:inline-flex;align-items:center;gap:6px;margin:0.5rem 0;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:{color};"></span>'
        f'<span style="font-size:0.82rem;font-weight:600;color:{text_color};">'
        f"{label} ({score}/5)</span>"
    )
    if reason:
        badge_html += (
            f'<span style="font-size:0.78rem;color:#64748b;margin-left:4px;">&mdash; {html.escape(reason)}</span>'
        )
    badge_html += "</div>"

    st.markdown(badge_html, unsafe_allow_html=True)


def render_assistant_message(
    response: str,
    lang: str,
    message_idx: int,
    theme: dict | None = None,
    render_sources: bool = True,
) -> None:
    """Render an assistant message with inline citation badges, sections, confidence, and source cards."""
    answer_text, sources = parse_response_and_sources(response)

    # Build URL map for inline citation linking
    url_map = {src["case_id"]: src["url"] for src in sources if src.get("url")}

    # Parse sections
    sections = _parse_sections(answer_text)

    verbose = st.session_state.get("verbose_mode", False)

    if len(sections) > 1:
        # Structured response with ## headings
        for i, (heading, content) in enumerate(sections):
            if not content:
                continue
            linkified = _linkify_inline_citations(content, url_map, theme)
            if heading:
                # First section expanded always; others expanded only in verbose mode
                expanded = (i <= 1) or verbose
                with st.expander(heading, expanded=expanded):
                    st.markdown(linkified, unsafe_allow_html=True)
            else:
                # Preamble text before first heading
                st.markdown(linkified, unsafe_allow_html=True)
    else:
        # Single block (no section markers)
        linkified = _linkify_inline_citations(answer_text, url_map, theme)
        st.markdown(linkified, unsafe_allow_html=True)

    # Copy button: use full response so user gets the whole answer (including sources block)
    _render_copy_button(response, lang, message_idx)

    # Confidence badge
    _render_confidence_badge(message_idx, lang, theme)

    # Source cards (always visible, not collapsed)
    if render_sources:
        _render_source_cards(sources, message_idx, lang, theme)


def _render_copy_button(text: str, lang: str, message_idx: int) -> None:
    """Render a small copy-to-clipboard button.

    The payload is base64-encoded and decoded in JS to prevent
    </script> breakout attacks from LLM output.
    """
    copy_label = html.escape(t("copy_response", lang))
    copied_label = html.escape(t("copied", lang))
    b64_payload = base64.b64encode(text.encode("utf-8")).decode("ascii")

    components.html(
        f"""
        <div style="text-align: right; margin-top: -8px; margin-bottom: 4px;">
            <button id="copy-btn-{message_idx}"
                onclick="copyText_{message_idx}()"
                style="background: transparent; border: 1px solid #e2e8f0; border-radius: 6px;
                       padding: 2px 10px; cursor: pointer; font-size: 0.8rem; color: #64748b;
                       transition: all 0.2s;">
                \U0001f4cb {copy_label}
            </button>
        </div>
        <div id="copy-data-{message_idx}" data-b64="{b64_payload}" style="display:none;"></div>
        <script>
        (function() {{
            var b64 = document.getElementById('copy-data-{message_idx}').dataset.b64;
            var payload = decodeURIComponent(escape(atob(b64)));
            window.copyText_{message_idx} = function() {{
                navigator.clipboard.writeText(payload).then(function() {{
                    var btn = document.getElementById('copy-btn-{message_idx}');
                    if (btn) {{
                        btn.textContent = '\u2705 {copied_label}';
                        setTimeout(function() {{
                            btn.innerHTML = '\U0001f4cb {copy_label}';
                        }}, 2000);
                    }}
                }}).catch(function(err) {{
                    console.error('Copy failed', err);
                }});
            }};
        }})();
        </script>
        """,
        height=36,
    )
