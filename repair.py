"""PDF form repair for damage introduced by PDF Expert's signing flow.

Two repairs:

1. ``relink_radio_kids`` — re-append radio/checkbox widget kids to their page's
   /Annots array so renderers that walk page annotations (Preview, poppler,
   browsers, Fleetplan) find them.

2. ``fix_zapfdingbats_appearance`` — replace the subset font
   ``AAAAAF+ZapfDingbatsITC`` (checkmark at char 0x21) in checkbox/radio
   on-state appearance streams with standard ZapfDingbats (checkmark at
   char 0x04).

Both operate on an open ``fitz.Document`` and mutate it in place. They
report what they changed so callers can surface that in the UI.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import fitz


# ---------- helpers ---------------------------------------------------------

_REF_RE = re.compile(r"(\d+)\s+0\s+R")
_ANNOTS_INDIRECT_RE = re.compile(r"/Annots\s+(\d+)\s+0\s+R")
_ANNOTS_INLINE_RE = re.compile(r"/Annots\s*\[([^\]]*)\]", re.DOTALL)


def _page_index_by_xref(doc: fitz.Document) -> Dict[int, int]:
    return {doc[i].xref: i for i in range(len(doc))}


def _read_annots(doc: fitz.Document, page_xref: int) -> Tuple[Optional[int], List[int]]:
    """Return (annots_array_xref_or_None, list_of_referenced_xrefs) for a page.

    If /Annots is an indirect reference to an array object, returns that xref.
    If /Annots is inline, returns (None, refs).
    If no /Annots, returns (None, []).
    """
    page_def = doc.xref_object(page_xref)
    m = _ANNOTS_INDIRECT_RE.search(page_def)
    if m:
        arr_xref = int(m.group(1))
        arr_body = doc.xref_object(arr_xref)
        return arr_xref, [int(x) for x in _REF_RE.findall(arr_body)]
    m = _ANNOTS_INLINE_RE.search(page_def)
    if m:
        return None, [int(x) for x in _REF_RE.findall(m.group(1))]
    return None, []


def _write_annots(doc: fitz.Document, page_xref: int, annots_xref: Optional[int], refs: List[int]) -> None:
    """Write refs back to the page's /Annots, preserving indirect/inline form."""
    body = "[ " + " ".join(f"{r} 0 R" for r in refs) + " ]"
    if annots_xref is not None:
        doc.update_object(annots_xref, body)
        return
    page_def = doc.xref_object(page_xref)
    if _ANNOTS_INLINE_RE.search(page_def):
        new_def = _ANNOTS_INLINE_RE.sub(f"/Annots {body}", page_def, count=1)
    else:
        new_def = page_def.rstrip()
        if new_def.endswith(">>"):
            new_def = new_def[:-2].rstrip() + f"\n  /Annots {body}\n>>"
        else:
            new_def = new_def + f" /Annots {body}"
    doc.update_object(page_xref, new_def)


def _acroform_field_xrefs(doc: fitz.Document) -> List[int]:
    """Return every terminal Widget xref reachable from /AcroForm /Fields."""
    catalog = doc.xref_object(doc.pdf_catalog())
    m = re.search(r"/AcroForm\s+(\d+)\s+0\s+R", catalog)
    if not m:
        return []
    acroform = doc.xref_object(int(m.group(1)))
    fields_m = re.search(r"/Fields\s*\[([^\]]*)\]", acroform, re.DOTALL)
    if not fields_m:
        return []

    terminals: List[int] = []
    stack: List[int] = [int(x) for x in _REF_RE.findall(fields_m.group(1))]
    seen: Set[int] = set()
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        obj = doc.xref_object(x)
        kids_m = re.search(r"/Kids\s*\[([^\]]*)\]", obj, re.DOTALL)
        if kids_m:
            stack.extend(int(y) for y in _REF_RE.findall(kids_m.group(1)))
            # A field can be both a terminal widget and have kids — rare; skip
            continue
        if "/Subtype /Widget" in obj or "/Subtype/Widget" in obj:
            terminals.append(x)
    return terminals


def _field_tree_parent_map(doc: fitz.Document) -> Dict[int, int]:
    """Map each kid xref → its parent field xref (for sibling-based fallback)."""
    catalog = doc.xref_object(doc.pdf_catalog())
    m = re.search(r"/AcroForm\s+(\d+)\s+0\s+R", catalog)
    if not m:
        return {}
    acroform = doc.xref_object(int(m.group(1)))
    fields_m = re.search(r"/Fields\s*\[([^\]]*)\]", acroform, re.DOTALL)
    if not fields_m:
        return {}
    parents: Dict[int, int] = {}
    stack: List[int] = [int(x) for x in _REF_RE.findall(fields_m.group(1))]
    seen: Set[int] = set()
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        obj = doc.xref_object(x)
        kids_m = re.search(r"/Kids\s*\[([^\]]*)\]", obj, re.DOTALL)
        if kids_m:
            for child in _REF_RE.findall(kids_m.group(1)):
                c = int(child)
                parents[c] = x
                stack.append(c)
    return parents


# ---------- repair 1: relink radio kids -------------------------------------


@dataclass
class RelinkReport:
    relinked: int = 0
    skipped_no_page: int = 0
    details: List[str] = field(default_factory=list)


def relink_radio_kids(doc: fitz.Document) -> RelinkReport:
    """Re-append AcroForm widget kids to their owning page's /Annots array.

    Strategy per widget:
      1. If widget has /P pointing at a page, use that.
      2. Else, find a sibling kid (same parent field) already present in some
         page's /Annots, and assume this widget belongs there.
      3. Else, skip with a warning.
    """
    report = RelinkReport()
    page_by_xref = _page_index_by_xref(doc)

    # Snapshot each page's annots
    page_state: Dict[int, Tuple[Optional[int], List[int]]] = {}
    xref_to_page_idx: Dict[int, int] = {}
    for i in range(len(doc)):
        px = doc[i].xref
        annots_xref, refs = _read_annots(doc, px)
        page_state[i] = (annots_xref, list(refs))
        for r in refs:
            xref_to_page_idx[r] = i

    terminals = _acroform_field_xrefs(doc)
    parents = _field_tree_parent_map(doc)

    # Build parent → [kid xrefs]
    siblings: Dict[int, List[int]] = {}
    for kid, parent in parents.items():
        siblings.setdefault(parent, []).append(kid)

    for widget_xref in terminals:
        if widget_xref in xref_to_page_idx:
            continue  # already linked

        target_page: Optional[int] = None

        # (1) /P back-ref
        wdef = doc.xref_object(widget_xref)
        pm = re.search(r"/P\s+(\d+)\s+0\s+R", wdef)
        if pm:
            p_xref = int(pm.group(1))
            if p_xref in page_by_xref:
                target_page = page_by_xref[p_xref]

        # (2) sibling already linked
        if target_page is None:
            parent = parents.get(widget_xref)
            if parent is not None:
                for sib in siblings.get(parent, []):
                    if sib != widget_xref and sib in xref_to_page_idx:
                        target_page = xref_to_page_idx[sib]
                        break

        if target_page is None:
            report.skipped_no_page += 1
            report.details.append(
                f"widget xref={widget_xref}: no /P, no linked sibling — left orphan"
            )
            continue

        annots_xref, refs = page_state[target_page]
        refs.append(widget_xref)
        page_state[target_page] = (annots_xref, refs)
        xref_to_page_idx[widget_xref] = target_page
        report.relinked += 1

    # Write back only pages that changed
    for i in range(len(doc)):
        annots_xref, refs = page_state[i]
        _, original_refs = _read_annots(doc, doc[i].xref)
        if refs != original_refs:
            _write_annots(doc, doc[i].xref, annots_xref, refs)

    return report


# ---------- repair 2: fix ZapfDingbats appearance ---------------------------


_STANDARD_ZAPF_OBJ = (
    "<<\n"
    "  /Type /Font\n"
    "  /Subtype /Type1\n"
    "  /BaseFont /ZapfDingbats\n"
    ">>"
)

# Subset producers that trigger the repair. The leading 6-letter tag varies,
# so we match the "+ZapfDingbats" suffix regardless of the random tag.
_SUBSET_ZAPF_RE = re.compile(r"/BaseFont\s+/[A-Z]{6}\+ZapfDingbats[A-Za-z]*")


@dataclass
class FontFixReport:
    streams_patched: int = 0
    fonts_retargeted: int = 0
    dr_retargeted: int = 0


def _ensure_standard_zapf(doc: fitz.Document) -> int:
    """Create (once per document) a standard ZapfDingbats Type1 font; return xref."""
    key = "_merger_std_zapf_xref"
    existing = doc.xref_get_key(doc.pdf_catalog(), key)
    # Streamlit /mupdf doesn't give us arbitrary catalog metadata easily; cache on object.
    cached = getattr(doc, "_merger_std_zapf_xref", None)
    if cached:
        return cached
    xref = doc.get_new_xref()
    doc.update_object(xref, _STANDARD_ZAPF_OBJ)
    setattr(doc, "_merger_std_zapf_xref", xref)
    return xref


def _is_subset_zapf(doc: fitz.Document, font_xref: int) -> bool:
    try:
        body = doc.xref_object(font_xref)
    except Exception:
        return False
    return bool(_SUBSET_ZAPF_RE.search(body))


def _rewrite_stream_checkmark(data: bytes) -> Tuple[bytes, bool]:
    """Rewrite the rendered char from '!' (0x21) to '4' (0x34).

    Standard ZapfDingbats maps ASCII '4' (0x34) to the heavy-checkmark glyph
    (PostScript name ``a20``), not the control char 0x04. Subset fonts that
    PDF Expert embeds put the checkmark at '!' (0x21) instead.
    """
    changed = False

    def repl(m: re.Match) -> bytes:
        nonlocal changed
        changed = True
        return b"(4) Tj"

    out = re.sub(rb"\(\s*!\s*\)\s*Tj", repl, data)
    return out, changed


def _xobject_stream_refs_from_widget(doc: fitz.Document, widget_xref: int) -> List[int]:
    """Return every XObject stream xref reachable from widget /AP (N and D)."""
    wdef = doc.xref_object(widget_xref)
    ap_m = re.search(r"/AP\s+(\d+)\s+0\s+R", wdef)
    if not ap_m:
        # inline /AP dict
        ap_inline = re.search(r"/AP\s*<<(.*?)>>", wdef, re.DOTALL)
        if not ap_inline:
            return []
        ap_body = ap_inline.group(1)
    else:
        ap_body = doc.xref_object(int(ap_m.group(1)))

    streams: List[int] = []
    for state in ("N", "D"):
        sm = re.search(rf"/{state}\s+(\d+)\s+0\s+R", ap_body)
        if not sm:
            # Could be a dict of states /N << /Yes 123 0 R /Off 456 0 R >>
            state_dict = re.search(rf"/{state}\s*<<(.*?)>>", ap_body, re.DOTALL)
            if state_dict:
                streams.extend(int(x) for x in _REF_RE.findall(state_dict.group(1)))
            continue
        target = int(sm.group(1))
        target_body = doc.xref_object(target)
        if "/Subtype /Form" in target_body or "/Subtype/Form" in target_body:
            streams.append(target)
        else:
            # It's a dict mapping state names → XObject refs
            streams.extend(int(x) for x in _REF_RE.findall(target_body))
    return streams


def _retarget_font_dict(
    doc: fitz.Document,
    font_dict_body: str,
    std_xref_factory,
) -> Tuple[str, int]:
    """Retarget subset ZapfDingbats entries in a /Font dict body to the standard font.

    ``std_xref_factory`` is a zero-arg callable that returns the standard font xref
    (lazy so we don't create the object unless something actually needs retargeting).
    """
    font_entries = re.findall(r"/(\w+)\s+(\d+)\s+0\s+R", font_dict_body)
    damaged = [fname for fname, fx in font_entries if _is_subset_zapf(doc, int(fx))]
    if not damaged:
        return font_dict_body, 0
    std_xref = std_xref_factory()
    new_body = font_dict_body
    for fname in damaged:
        new_body = re.sub(
            rf"/{fname}\s+\d+\s+0\s+R",
            f"/{fname} {std_xref} 0 R",
            new_body,
        )
    return new_body, len(damaged)


def _retarget_acroform_dr(doc: fitz.Document, std_xref_factory) -> int:
    """Retarget subset ZapfDingbats in /AcroForm /DR /Font. Returns # retargeted."""
    catalog = doc.xref_object(doc.pdf_catalog())
    m = re.search(r"/AcroForm\s+(\d+)\s+0\s+R", catalog)
    if not m:
        return 0
    acroform_xref = int(m.group(1))
    acroform = doc.xref_object(acroform_xref)

    # /DR can be indirect or inline.
    dr_m = re.search(r"/DR\s+(\d+)\s+0\s+R", acroform)
    if dr_m:
        dr_xref = int(dr_m.group(1))
        dr_body = doc.xref_object(dr_xref)
        dr_is_indirect = True
    else:
        dr_inline = re.search(r"/DR\s*<<(.*?)>>", acroform, re.DOTALL)
        if not dr_inline:
            return 0
        dr_body = dr_inline.group(1)
        dr_xref = None
        dr_is_indirect = False

    font_m = re.search(r"/Font\s*<<(.*?)>>", dr_body, re.DOTALL)
    if not font_m:
        return 0
    font_body = font_m.group(1)
    new_font_body, count = _retarget_font_dict(doc, font_body, std_xref_factory)
    if count == 0:
        return 0

    new_dr_body = dr_body.replace(font_body, new_font_body)
    if dr_is_indirect:
        doc.update_object(dr_xref, new_dr_body)
    else:
        new_acroform = acroform.replace(dr_body, new_dr_body)
        doc.update_object(acroform_xref, new_acroform)
    return count


def fix_zapfdingbats_appearance(doc: fitz.Document) -> FontFixReport:
    """Replace subset +ZapfDingbats in widget appearance streams with standard font."""
    report = FontFixReport()

    terminals = _acroform_field_xrefs(doc)
    if not terminals:
        return report

    patched_streams: Set[int] = set()
    std_xref_factory = lambda: _ensure_standard_zapf(doc)

    for widget_xref in terminals:
        # No /FT /Btn gate — /FT is typically inherited from /Parent and missing
        # on the widget itself. The subset-font check below is the real filter.
        for stream_xref in _xobject_stream_refs_from_widget(doc, widget_xref):
            if stream_xref in patched_streams:
                continue
            try:
                xo_dict = doc.xref_object(stream_xref)
            except Exception:
                continue

            # Locate /Resources → /Font dict
            res_m = re.search(r"/Resources\s+(\d+)\s+0\s+R", xo_dict)
            if res_m:
                res_xref = int(res_m.group(1))
                res_body = doc.xref_object(res_xref)
                res_is_indirect = True
            else:
                res_inline = re.search(r"/Resources\s*<<(.*?)>>", xo_dict, re.DOTALL)
                if not res_inline:
                    continue
                res_body = res_inline.group(1)
                res_xref = None
                res_is_indirect = False

            font_dict_m = re.search(r"/Font\s*<<(.*?)>>", res_body, re.DOTALL)
            if not font_dict_m:
                continue
            font_dict_body = font_dict_m.group(1)
            new_font_dict, retargeted = _retarget_font_dict(
                doc, font_dict_body, std_xref_factory
            )
            if retargeted == 0:
                continue
            report.fonts_retargeted += retargeted

            new_res_body = res_body.replace(font_dict_body, new_font_dict)
            if res_is_indirect:
                doc.update_object(res_xref, new_res_body)
            else:
                new_xo_dict = xo_dict.replace(res_body, new_res_body)
                doc.update_object(stream_xref, new_xo_dict)

            # Rewrite the stream char 0x21 → 0x04
            raw = doc.xref_stream(stream_xref)
            if raw is None:
                continue
            new_raw, changed = _rewrite_stream_checkmark(raw)
            if changed:
                doc.update_stream(stream_xref, new_raw)
                report.streams_patched += 1

            patched_streams.add(stream_xref)

    # /DA strings resolve font names through AcroForm /DR /Font. Retargeting
    # /DR to the standard font fixes any /DA that references the damaged font
    # without having to rewrite the /DA string itself.
    report.dr_retargeted = _retarget_acroform_dr(doc, std_xref_factory)

    return report


# ---------- repair 3: fix degenerate /Off appearance BBoxes ----------------


_ZERO_BBOX_RE = re.compile(
    r"/BBox\s*\[\s*0\s+0\s+0\s+0\s*\]"
)
_BBOX_RE = re.compile(r"/BBox\s*\[\s*([^\]]*?)\s*\]")


@dataclass
class BBoxFixReport:
    bboxes_fixed: int = 0


def fix_degenerate_bboxes(doc: fitz.Document) -> BBoxFixReport:
    """Replace /BBox [0 0 0 0] on widget appearance XObjects.

    PDF Expert writes /Off-state appearances with a zero-area BBox. When
    MuPDF's bake() scales the widget /Rect into that BBox, it divides by
    zero and emits FLT_MAX in the page's cm operator, scrambling every
    neighbouring widget invocation. Patching the BBox to match either the
    sibling /Yes state or the widget's /Rect dimensions fixes the scale.
    """
    report = BBoxFixReport()

    for widget_xref in _acroform_field_xrefs(doc):
        wdef = doc.xref_object(widget_xref)
        ap_m = re.search(r"/AP\s+(\d+)\s+0\s+R", wdef)
        if not ap_m:
            continue
        ap = doc.xref_object(int(ap_m.group(1)))

        # Widget /Rect gives us fallback dimensions.
        rect_m = re.search(
            r"/Rect\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]",
            wdef,
        )
        if not rect_m:
            continue
        x0, y0, x1, y1 = (float(rect_m.group(i)) for i in range(1, 5))
        rect_w, rect_h = abs(x1 - x0), abs(y1 - y0)
        if rect_w <= 0 or rect_h <= 0:
            continue

        # Walk /N (and /D) state dicts to collect XObject state xrefs.
        state_xrefs: List[int] = []
        for key in ("N", "D"):
            m = re.search(rf"/{key}\s+(\d+)\s+0\s+R", ap)
            if not m:
                continue
            target = int(m.group(1))
            body = doc.xref_object(target)
            if "/Subtype /Form" in body or "/Subtype/Form" in body:
                state_xrefs.append(target)
            else:
                state_xrefs.extend(int(x) for x in _REF_RE.findall(body))

        # Find a reference BBox from any non-degenerate sibling.
        ref_bbox: Optional[str] = None
        for sx in state_xrefs:
            try:
                sb = doc.xref_object(sx)
            except Exception:
                continue
            bbm = _BBOX_RE.search(sb)
            if bbm and not _ZERO_BBOX_RE.search(sb):
                ref_bbox = bbm.group(1).strip()
                break
        if ref_bbox is None:
            ref_bbox = f"0 0 {rect_w:g} {rect_h:g}"

        for sx in state_xrefs:
            try:
                sb = doc.xref_object(sx)
            except Exception:
                continue
            if not _ZERO_BBOX_RE.search(sb):
                continue
            new_sb = _ZERO_BBOX_RE.sub(f"/BBox [ {ref_bbox} ]", sb, count=1)
            doc.update_object(sx, new_sb)
            report.bboxes_fixed += 1

    return report


# ---------- convenience ------------------------------------------------------


@dataclass
class FullRepairReport:
    relink: RelinkReport
    fonts: FontFixReport
    bboxes: BBoxFixReport = field(default_factory=BBoxFixReport)


def repair_document(doc: fitz.Document) -> FullRepairReport:
    """Run all repairs on a document in place."""
    relink = relink_radio_kids(doc)
    fonts = fix_zapfdingbats_appearance(doc)
    bboxes = fix_degenerate_bboxes(doc)
    return FullRepairReport(relink=relink, fonts=fonts, bboxes=bboxes)
