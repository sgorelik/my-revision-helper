"""
Pulling instructional links out of the documents that already contain them.

Workbooks arrive with "Khan Academy: Exponent properties" style links already in
them. Those are exactly the prerequisites a student needs, so they should be
picked up on upload rather than retyped by hand.

The important detail is that a Word hyperlink's address is **not in the visible
text**. It lives in `word/_rels/document.xml.rels`, and the document body only
carries a relationship id next to the anchor text. Extracting URLs by scanning
the extracted text therefore finds nothing at all in a real workbook — every
link has to come from the relationship file, matched back to its anchor text so
it gets a readable label.

Parsing is done with regexes over the XML rather than a real parser, matching
what `file_processing` already does for document text, and avoiding handing
arbitrary uploaded XML to a parser that expands entities.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from html import unescape
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Bare URLs sitting in plain text, e.g. a PDF or a pasted worksheet. Trailing
# punctuation is trimmed because a URL at the end of a sentence collects it.
_TEXT_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_TRAILING_JUNK = ".,;:!?)]}>'\""

# Sites common in UK revision material, so a link with no usable anchor text
# still gets a name a child recognises rather than a raw domain.
_KNOWN_SITES = [
    ("khanacademy.org", "Khan Academy"),
    ("bbc.co.uk/bitesize", "BBC Bitesize"),
    ("bbc.com/bitesize", "BBC Bitesize"),
    ("youtube.com", "Video"),
    ("youtu.be", "Video"),
    ("senecalearning.com", "Seneca"),
    ("physicsandmathstutor.com", "Physics & Maths Tutor"),
    ("savemyexams.com", "Save My Exams"),
    ("corbettmaths.com", "Corbettmaths"),
    ("drfrostmaths.com", "Dr Frost Maths"),
    ("quizlet.com", "Quizlet"),
]


def _clean_url(url: str) -> Optional[str]:
    """Trim a URL found in prose and reject anything not http(s)."""
    cleaned = url.strip().rstrip(_TRAILING_JUNK)
    if not cleaned.lower().startswith(("http://", "https://")):
        return None
    # A bare scheme with no host is not a link.
    if len(cleaned) < len("http://a.bc"):
        return None
    return cleaned


def label_for_url(url: str) -> str:
    """A readable name for a link that arrived without one."""
    lowered = url.lower()
    for fragment, name in _KNOWN_SITES:
        if fragment in lowered:
            return name

    host = re.sub(r"^https?://(www\.)?", "", lowered).split("/")[0]
    return host or "Open this"


def kind_for_url(url: str) -> str:
    """
    Whether this is something to watch, read or practise.

    Only used to pick an icon and a verb, so a rough guess is fine; anything
    unrecognised is called "watch" because that is what most of these are.
    """
    lowered = url.lower()
    if any(f in lowered for f in ("youtube.com", "youtu.be", "/video", "vimeo.com")):
        return "watch"
    if any(f in lowered for f in ("bitesize", "wikipedia.org", "/revision/", "/notes")):
        return "read"
    if any(f in lowered for f in ("quizlet", "/exercise", "/practice", "/quiz")):
        return "practise"
    return "watch"


def links_from_docx(content: bytes) -> List[Dict[str, str]]:
    """
    Hyperlinks from a .docx, in the order the document presents them.

    The URL comes from the relationship file and the label from the anchor text
    beside it in the body, which is where a name like "Khan Academy: Exponent
    properties" comes from.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                return []
            document = archive.read("word/document.xml").decode("utf-8", "ignore")
            rels = (
                archive.read("word/_rels/document.xml.rels").decode("utf-8", "ignore")
                if "word/_rels/document.xml.rels" in names
                else ""
            )
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        logger.debug(f"Not a readable docx while looking for links: {e}")
        return []

    # Relationship id -> external target, restricted to hyperlinks so external
    # images and embedded objects are not mistaken for reading material.
    targets: Dict[str, str] = {}
    for element in re.findall(r"<Relationship\b[^>]*/?>", rels):
        if "hyperlink" not in element.lower():
            continue
        rel_id = re.search(r'\bId="([^"]+)"', element)
        target = re.search(r'\bTarget="([^"]+)"', element)
        if not rel_id or not target:
            continue
        url = _clean_url(unescape(target.group(1)))
        if url:
            targets[rel_id.group(1)] = url

    if not targets:
        return []

    found: List[Dict[str, str]] = []
    seen: set[str] = set()

    # Anchor text, in document order, for each hyperlink that has a known target.
    for match in re.finditer(
        r"<w:hyperlink\b[^>]*r:id=\"([^\"]+)\"[^>]*>(.*?)</w:hyperlink>", document, re.S
    ):
        url = targets.get(match.group(1))
        if not url or url in seen:
            continue
        seen.add(url)

        anchor = unescape(
            " ".join(re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", match.group(2), re.S))
        ).strip()
        # An anchor showing the raw URL is no more useful than the URL itself.
        if not anchor or anchor.lower().startswith(("http://", "https://")):
            anchor = label_for_url(url)

        found.append({"url": url, "label": anchor, "kind": kind_for_url(url)})

    # Targets that exist but are not anchored anywhere in the body still belong
    # to the document, so they are kept rather than dropped.
    for url in targets.values():
        if url not in seen:
            seen.add(url)
            found.append({"url": url, "label": label_for_url(url), "kind": kind_for_url(url)})

    return found


def links_from_pdf(content: bytes) -> List[Dict[str, str]]:
    """Link annotations in a PDF, which are also invisible in the text layer."""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - declared dependency
        return []

    found: List[Dict[str, str]] = []
    seen: set[str] = set()

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for link in getattr(page, "hyperlinks", []) or []:
                    url = _clean_url(str(link.get("uri") or ""))
                    if url and url not in seen:
                        seen.add(url)
                        found.append(
                            {
                                "url": url,
                                "label": label_for_url(url),
                                "kind": kind_for_url(url),
                            }
                        )
    except Exception as e:
        logger.debug(f"Could not read PDF link annotations: {e}")

    return found


def links_from_text(text: Optional[str]) -> List[Dict[str, str]]:
    """
    URLs written out in the text itself.

    Covers pasted worksheets and documents that print their links rather than
    hiding them behind anchor text.
    """
    if not text:
        return []

    found: List[Dict[str, str]] = []
    seen: set[str] = set()

    for raw in _TEXT_URL.findall(text):
        url = _clean_url(raw)
        if url and url not in seen:
            seen.add(url)
            found.append({"url": url, "label": label_for_url(url), "kind": kind_for_url(url)})

    return found


def extract_links(
    file_contents: Optional[Dict[str, bytes]] = None,
    text: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Every instructional link an upload carries, deduplicated by URL.

    File-derived links come first and in document order: they are the ones with
    real labels, and a link repeated in the text adds nothing.
    """
    collected: List[Dict[str, str]] = []

    for filename, content in (file_contents or {}).items():
        lowered = filename.lower()
        if lowered.endswith(".docx"):
            collected.extend(links_from_docx(content))
        elif lowered.endswith(".pdf"):
            collected.extend(links_from_pdf(content))

    collected.extend(links_from_text(text))

    deduped: List[Dict[str, str]] = []
    seen: set[str] = set()
    for link in collected:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        deduped.append(link)

    if deduped:
        logger.info(f"Extracted {len(deduped)} link(s) from the upload")

    return deduped


def merge_extracted(
    extracted: Iterable[Dict[str, str]], manual: Iterable[Dict[str, str]]
) -> List[Dict[str, str]]:
    """
    The document's own links, then anything added by hand.

    The document's come first because they are part of the material and already
    in a sensible order; manual ones are additions to it.
    """
    return list(extracted) + list(manual)
