"""Form Merge — merge fillable PDFs into a single non-modifiable PDF.

Per file, we:
  1. Repair PDF Expert damage (relink radio kids, fix subset ZapfDingbats)
  2. Bake — flatten widgets and annotations into page content
  3. Clean content streams to remove MuPDF bake artifacts

Then concatenate the flattened inputs. Output has no live form fields.
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import fitz
import streamlit as st
from streamlit_sortables import sort_items

from repair import FontFixReport, FullRepairReport, RelinkReport, repair_document

st.set_page_config(page_title="Form Merge", page_icon="📄", layout="centered")

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 900px; }
    /* Make sortable items a bit roomier */
    .sortable-component > div { padding: 0.6rem 0.9rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------- state ------------------------------------------------------------


@dataclass
class PDFEntry:
    id: str
    name: str
    data: bytes
    checksum: str
    pages: int
    size_bytes: int
    has_sig: bool  # cryptographic /FT /Sig field — bake destroys crypto


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("files", [])
    ss.setdefault("uploader_salt", 0)
    ss.setdefault("last_output", None)


def _label(entry: PDFEntry) -> str:
    kb = entry.size_bytes / 1024
    size = f"{kb:.0f} KB" if kb < 1024 else f"{kb/1024:.1f} MB"
    return f"{entry.name}  ·  {entry.pages} pages  ·  {size}"


def _entry_from_label(label: str) -> Optional[PDFEntry]:
    for f in st.session_state.files:
        if _label(f) == label:
            return f
    return None


# --------- file ingest ------------------------------------------------------


_SIG_RE = re.compile(r"/FT\s*/Sig\b")


def _has_cryptographic_sig(doc: fitz.Document) -> bool:
    """True if any field is /FT /Sig (cryptographic, not just a drawn signature)."""
    for i in range(1, doc.xref_length()):
        try:
            body = doc.xref_object(i)
        except Exception:
            continue
        if _SIG_RE.search(body):
            return True
    return False


def _ingest(uploads) -> None:
    existing = {f.checksum for f in st.session_state.files}
    new_uploads = [u for u in uploads if hashlib.sha1(u.getvalue()).hexdigest() not in existing]
    if not new_uploads:
        return

    with st.status(f"Parsing {len(new_uploads)} file(s)...", expanded=False) as status:
        for i, up in enumerate(new_uploads, 1):
            status.update(label=f"Parsing {i} of {len(new_uploads)}: {up.name}")
            data = up.getvalue()
            csum = hashlib.sha1(data).hexdigest()
            try:
                with fitz.open(stream=data, filetype="pdf") as d:
                    pages = len(d)
                    has_sig = _has_cryptographic_sig(d)
            except Exception as exc:
                st.warning(f"Skipping **{up.name}** — not a valid PDF ({exc}).")
                continue
            st.session_state.files.append(
                PDFEntry(
                    id=str(uuid.uuid4()),
                    name=up.name,
                    data=data,
                    checksum=csum,
                    pages=pages,
                    size_bytes=len(data),
                    has_sig=has_sig,
                )
            )
            existing.add(csum)
        status.update(label=f"Parsed {len(new_uploads)} file(s)", state="complete")


# --------- merge ------------------------------------------------------------


def _repair_and_bake(entry: PDFEntry, combined: FullRepairReport) -> bytes:
    """Repair, flatten, and clean one PDF. Returns the flattened bytes."""
    with fitz.open(stream=entry.data, filetype="pdf") as src:
        report = repair_document(src)
        combined.relink.relinked += report.relink.relinked
        combined.relink.skipped_no_page += report.relink.skipped_no_page
        combined.relink.details.extend(report.relink.details)
        combined.fonts.streams_patched += report.fonts.streams_patched
        combined.fonts.fonts_retargeted += report.fonts.fonts_retargeted
        combined.fonts.dr_retargeted += report.fonts.dr_retargeted

        src.bake()
        for page in src:
            page.clean_contents()

        return src.tobytes(deflate=True, garbage=3, clean=True)


def _merge(entries: List[PDFEntry], progress) -> tuple[bytes, FullRepairReport]:
    combined = FullRepairReport(relink=RelinkReport(), fonts=FontFixReport())
    flat_bytes: List[bytes] = []

    total = len(entries)
    for i, entry in enumerate(entries, 1):
        progress.update(label=f"Repairing & flattening {i} of {total}: {entry.name}")
        flat_bytes.append(_repair_and_bake(entry, combined))

    progress.update(label="Merging flattened pages...")
    out_doc = fitz.open()
    for b in flat_bytes:
        with fitz.open(stream=b, filetype="pdf") as src:
            out_doc.insert_pdf(src)

    out = out_doc.tobytes(deflate=True, garbage=3)
    out_doc.close()
    return out, combined


# --------- UI ---------------------------------------------------------------


def _render_header() -> None:
    st.title("Form Merge")
    st.caption(
        "Repairs PDF Expert damage, flattens form fields, and merges into one "
        "non-modifiable PDF."
    )


def _render_uploader() -> None:
    uploads = st.file_uploader(
        "Drop PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_salt}",
        label_visibility="collapsed",
    )
    if uploads:
        _ingest(uploads)


def _render_file_list() -> None:
    files: List[PDFEntry] = st.session_state.files
    if not files:
        return

    total_pages = sum(f.pages for f in files)
    total_mb = sum(f.size_bytes for f in files) / (1024 * 1024)
    st.write(f"**{len(files)}** file(s) · **{total_pages}** pages · **{total_mb:.1f} MB**")

    if any(f.has_sig for f in files):
        sig_names = ", ".join(f.name for f in files if f.has_sig)
        st.warning(
            f"Cryptographic signature detected in: {sig_names}. "
            "Flattening keeps the visible signature but breaks crypto validation."
        )

    labels = [_label(f) for f in files]
    ordered = sort_items(labels, direction="vertical", key="file_order")
    if ordered != labels:
        new_files = [_entry_from_label(lbl) for lbl in ordered]
        if all(new_files):
            st.session_state.files = new_files
            st.rerun()

    st.caption("Drag to reorder. Pages are merged top → bottom.")

    with st.expander("Remove individual files"):
        for f in list(files):
            c1, c2 = st.columns([4, 1])
            c1.write(_label(f))
            if c2.button("Remove", key=f"rm_{f.id}", use_container_width=True):
                st.session_state.files = [x for x in files if x.id != f.id]
                st.rerun()

    if st.button("Clear all", use_container_width=True):
        st.session_state.files = []
        st.session_state.uploader_salt += 1
        st.session_state.last_output = None
        st.rerun()


def _render_action() -> None:
    if not st.session_state.files:
        return
    if st.button("Repair, flatten & merge", type="primary", use_container_width=True):
        with st.status("Starting...", expanded=False) as progress:
            try:
                data, report = _merge(st.session_state.files, progress)
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                st.session_state.last_output = {
                    "bytes": data,
                    "name": f"merged-{ts}.pdf",
                    "report": report,
                }
                progress.update(label="Done", state="complete")
            except Exception as exc:
                progress.update(label=f"Failed: {exc}", state="error")
                st.session_state.last_output = None


def _render_output() -> None:
    out = st.session_state.last_output
    if not out:
        return

    size_mb = len(out["bytes"]) / (1024 * 1024)
    st.success(f"Done · {size_mb:.2f} MB · non-modifiable")

    report: Optional[FullRepairReport] = out.get("report")
    if report is not None:
        c1, c2, c3 = st.columns(3)
        c1.metric("Widgets relinked", report.relink.relinked)
        c2.metric("Appearance streams patched", report.fonts.streams_patched)
        c3.metric("Font refs retargeted", report.fonts.fonts_retargeted + report.fonts.dr_retargeted)

    st.download_button(
        label=f"Download {out['name']}",
        data=out["bytes"],
        file_name=out["name"],
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )


def main() -> None:
    _init_state()
    _render_header()
    st.divider()
    _render_uploader()
    _render_file_list()
    if st.session_state.files:
        st.divider()
        _render_action()
    _render_output()


if __name__ == "__main__":
    main()
