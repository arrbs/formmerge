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
        --blue-light: #E8EDF5;
    }
    
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(to bottom, #FAFBFC 0%, var(--blue-light) 100%);
    }
    
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }
    
    .block-container {
        max-width: 960px;
        padding: 2.5rem 1.5rem;
    }
    
    h1 {
        color: var(--blue);
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    .subtitle {
        color: #5B6B7D;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    
    .panel {
        background: white;
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0, 0, 32, 0.08);
        margin-bottom: 1rem;
    }
    
    .panel-title {
        color: var(--blue);
        font-weight: 600;
        font-size: 1.1rem;
        margin-bottom: 0.5rem;
    }
    
    .panel-text {
        color: #5B6B7D;
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }
    
    .sortable-container {
        background: #F8F9FA;
        border-radius: 12px;
        padding: 0.75rem;
        max-height: 280px;
        overflow-y: auto;
    }
    
    .sortable-item {
        background: white;
        border: 1px solid #E1E4E8;
        border-radius: 8px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        color: var(--blue);
        font-weight: 500;
        font-size: 0.9rem;
    }
    
    .sortable-item:last-child {
        margin-bottom: 0;
    }
    
    .info-text {
        color: #5B6B7D;
        font-size: 0.85rem;
        margin-top: 0.5rem;
    }
    
    .empty-state {
        background: #F8F9FA;
        border: 1px dashed #D1D5DB;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        color: #8B95A5;
    }
    
    .stButton>button, .stDownloadButton>button {
        background: var(--orange);
        border: none;
        color: white;
        border-radius: 24px;
        font-weight: 600;
        padding: 0.65rem 2rem;
        box-shadow: 0 4px 12px rgba(255, 65, 0, 0.25);
    }
    
    .stButton>button:hover, .stDownloadButton>button:hover {
        background: #E63A00;
        box-shadow: 0 6px 16px rgba(255, 65, 0, 0.35);
    }
    
    .stButton>button:disabled {
        background: #E1E4E8 !important;
        color: #8B95A5 !important;
        box-shadow: none;
    }
    
    [data-testid="stFileUploaderDropzone"] {
        border: 2px dashed #D1D5DB !important;
        background: #FAFBFC !important;
        border-radius: 12px !important;
    }
    
    div[data-baseweb="select"] > div {
        background: white !important;
        border: 1px solid #E1E4E8 !important;
        border-radius: 8px !important;
    }
    
    ::-webkit-scrollbar {
        width: 6px;
    }
    
    ::-webkit-scrollbar-track {
        background: #F0F0F0;
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
        f"<div class='panel-text'>{len(files)} files · {total_pages} pages total</div>",
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

    st.markdown("<div class='info-text'>Drag to reorder</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        option_pairs = [
            (f"{index + 1}. {item['name']}", item["id"])
            for index, item in enumerate(files)
        ]
        option_labels = [label for label, _ in option_pairs]
        selected_label = st.selectbox(
            "Remove",
            ["—"] + option_labels,
            index=0,
            label_visibility="collapsed",
            key="remove-select",
        )
        if selected_label != "—":
            chosen_map = {label: value for label, value in option_pairs}
            remove_item(chosen_map[selected_label])
            st.rerun()
    
    with col2:
        if st.button("Clear All", use_container_width=True, key="clear-list"):
            st.session_state["pdf_files"] = []
            st.session_state["last_output"] = None
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

    col1, col2 = st.columns(2, gap="medium")

    with col1:
        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-title'>Upload</div>", unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "Upload PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded_files:
            cache_uploaded_files(uploaded_files)
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
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
