import hashlib
import uuid
from datetime import datetime
from typing import List, Tuple

import fitz
import streamlit as st
from streamlit_sortables import sort_items

st.set_page_config(page_title="THC Form Merge Tool", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --orange: #FF4100;
        --blue: #000032;
        --grey: #F5F5F5;
    }
    
    [data-testid="stAppViewContainer"] {
        background: var(--blue);
    }
    
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }
    
    .block-container {
        max-width: 700px;
        padding: 3rem 1.5rem;
    }
    
    h1 {
        color: white;
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    
    .subtitle {
        color: var(--grey);
        font-size: 1rem;
        margin-bottom: 2.5rem;
        text-align: center;
        opacity: 0.9;
    }
    
    .panel {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    
    .panel-title {
        color: var(--blue);
        font-weight: 600;
        font-size: 1rem;
        margin-bottom: 0.75rem;
    }
    
    .panel-text {
        color: #6B7280;
        font-size: 0.875rem;
        margin-bottom: 1rem;
    }
    
    .sortable-container {
        background: var(--grey);
        border-radius: 8px;
        padding: 0.5rem;
        max-height: 320px;
        overflow-y: auto;
    }
    
    .sortable-item {
        background: white;
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        color: var(--blue);
        font-weight: 500;
        font-size: 0.875rem;
        cursor: grab;
    }
    
    .sortable-item:last-child {
        margin-bottom: 0;
    }
    
    .sortable-item:hover {
        border-color: var(--orange);
    }
    
    .empty-state {
        background: var(--grey);
        border: 1px dashed #D1D5DB;
        border-radius: 8px;
        padding: 2rem;
        text-align: center;
        color: #9CA3AF;
        font-size: 0.875rem;
    }
    
    .stButton>button, .stDownloadButton>button {
        background: var(--orange) !important;
        border: none;
        color: white !important;
        border-radius: 6px;
        font-weight: 600;
        padding: 0.75rem 1.5rem;
        transition: all 0.2s;
    }
    
    .stButton>button:hover, .stDownloadButton>button:hover {
        background: #E63A00 !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255, 65, 0, 0.4);
    }
    
    .stButton>button:disabled {
        background: #6B7280 !important;
        color: #D1D5DB !important;
        cursor: not-allowed;
    }
    
    [data-testid="stFileUploaderDropzone"] {
        border: 2px dashed #D1D5DB !important;
        background: var(--grey) !important;
        border-radius: 8px !important;
    }
    
    ::-webkit-scrollbar {
        width: 6px;
    }
    
    ::-webkit-scrollbar-track {
        background: #E5E7EB;
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--orange);
        border-radius: 3px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state() -> None:
    if "pdf_files" not in st.session_state:
        st.session_state["pdf_files"] = []
    if "last_output" not in st.session_state:
        st.session_state["last_output"] = None


def human_file_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def cache_uploaded_files(uploaded_files: List[st.runtime.uploaded_file_manager.UploadedFile]) -> None:
    existing_hashes = {item["checksum"] for item in st.session_state["pdf_files"]}
    for uploaded in uploaded_files:
        file_bytes = uploaded.getvalue()
        checksum = hashlib.sha1(file_bytes).hexdigest()
        if checksum in existing_hashes:
            continue
        existing_hashes.add(checksum)
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                page_count = len(doc)
        except Exception as exc:  # pragma: no cover - guard against corrupt files
            st.warning(f"Skipping {uploaded.name}: {exc}")
            continue
        st.session_state["pdf_files"].append(
            {
                "id": str(uuid.uuid4()),
                "name": uploaded.name,
                "data": file_bytes,
                "checksum": checksum,
                "pages": page_count,
                "size": len(file_bytes),
            }
        )


def remove_item(item_id: str) -> None:
    files = st.session_state["pdf_files"]
    filtered = [item for item in files if item["id"] != item_id]
    st.session_state["pdf_files"] = filtered


DEFAULT_DPI = 200
DEFAULT_JPEG_QUALITY = 85


def flatten_pdfs(
    file_entries: List[dict], dpi: int, image_format: str, jpeg_quality: int
) -> Tuple[bytes, int]:
    output_doc = fitz.open()
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    total_pages = 0
    for entry in file_entries:
        with fitz.open(stream=entry["data"], filetype="pdf") as src_doc:
            for page in src_doc:
                pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
                if image_format == "JPEG":
                    # JPEG drastically reduces size while keeping content readable.
                    image_bytes = pix.tobytes("jpeg", jpg_quality=jpeg_quality)
                else:
                    image_bytes = pix.tobytes("png")

                page_width = pix.width * 72.0 / dpi
                page_height = pix.height * 72.0 / dpi
                rect = fitz.Rect(0, 0, page_width, page_height)
                new_page = output_doc.new_page(width=page_width, height=page_height)
                new_page.insert_image(rect, stream=image_bytes)
                total_pages += 1
    output_bytes = output_doc.tobytes()
    output_doc.close()
    return output_bytes, total_pages


def render_uploaded_list() -> None:
    st.markdown("<div class='panel-title'>Merge Order</div>", unsafe_allow_html=True)

    files = st.session_state["pdf_files"]
    if not files:
        st.markdown(
            "<div class='empty-state'>Upload PDFs to arrange them here</div>",
            unsafe_allow_html=True,
        )
        return

    total_pages = sum(item["pages"] for item in files)
    st.markdown(
        f"<div class='panel-text'>{len(files)} files · {total_pages} pages</div>",
        unsafe_allow_html=True,
    )

    display_labels = [
        f"{item['name']} — {item['pages']} pages"
        for item in files
    ]

    st.markdown('<div class="sortable-container">', unsafe_allow_html=True)
    reordered = sort_items(display_labels, direction="vertical", key="pdf-order")
    st.markdown('</div>', unsafe_allow_html=True)

    if reordered and reordered != display_labels:
        mapping = {label: entry for label, entry in zip(display_labels, files)}
        st.session_state["pdf_files"] = [mapping[label] for label in reordered]
        st.rerun()


def main() -> None:
    init_state()

    st.markdown("<h1>THC Form Merge Tool</h1>", unsafe_allow_html=True)
    st.markdown(
        "<div class='subtitle'>Flatten fillable PDFs to preserve every checkbox, signature, and annotation</div>",
        unsafe_allow_html=True,
    )

    dpi = DEFAULT_DPI
    image_format = "JPEG"
    jpeg_quality = DEFAULT_JPEG_QUALITY

    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-title'>Upload PDFs</div>", unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Upload PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded_files:
        cache_uploaded_files(uploaded_files)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state["pdf_files"]:
        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        render_uploaded_list()
        st.markdown("</div>", unsafe_allow_html=True)

    can_merge = bool(st.session_state["pdf_files"])
    
    if st.button("Create Flattened PDF", disabled=not can_merge, use_container_width=True, type="primary"):
        with st.spinner("Flattening..."):
            try:
                merged_bytes, total_pages = flatten_pdfs(
                    st.session_state["pdf_files"], dpi, image_format, jpeg_quality
                )
            except Exception as exc:
                st.error(f"Error: {exc}")
                return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_name = f"flattened-{timestamp}.pdf"
        st.session_state["last_output"] = {
            "bytes": merged_bytes,
            "pages": total_pages,
            "name": output_name,
            "dpi": dpi,
            "image_format": image_format,
            "quality": jpeg_quality,
        }
        size_mb = len(merged_bytes) / (1024 * 1024)
        st.success(f"Ready: {total_pages} pages, {size_mb:.1f} MB")

    if st.session_state["last_output"]:
        download = st.session_state["last_output"]
        st.download_button(
            label="Download PDF",
            data=download["bytes"],
            file_name=download["name"],
            mime="application/pdf",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
