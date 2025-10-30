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
        --fuselage-grey: #F5F5F5;
        --warm-grey: #D2BEAA;
        --essential-orange: #FF4100;
        --obsidian-blue: #000032;
    }
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at top left, rgba(0, 0, 72, 0.75), rgba(0, 0, 50, 0.95) 55%, #000022 100%);
        color: #F5F5F5;
        padding-bottom: 3rem;
    }
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }
    .block-container {
        max-width: 1120px;
        padding: 2rem 2.5rem 3.5rem;
        margin: 0 auto;
        background: transparent;
    }
    .hero-card {
        background: linear-gradient(132deg, rgba(0, 0, 90, 0.95) 0%, rgba(0, 0, 56, 0.82) 58%, rgba(255, 65, 0, 0.55) 100%);
        border-radius: 28px;
        padding: 2.6rem 3rem;
        box-shadow: 0 45px 85px rgba(0, 0, 0, 0.55);
        border: 1px solid rgba(255, 65, 0, 0.35);
        margin-bottom: 1.8rem;
    }
    .hero-title {
        margin: 0;
        font-size: 2.45rem;
        font-weight: 700;
        color: #FDFDFE;
    }
    .hero-body {
        margin-top: 0.75rem;
        font-size: 1.05rem;
        line-height: 1.7;
        color: rgba(245, 245, 255, 0.9);
        max-width: 720px;
    }
    .steps-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin: 0 0 2rem 0;
    }
    .steps-strip .step {
        display: inline-flex;
        align-items: center;
        gap: 0.65rem;
        background: rgba(255, 255, 255, 0.12);
        border: 1px solid rgba(255, 65, 0, 0.45);
        color: #FDFDFE;
        padding: 0.55rem 1.1rem;
        border-radius: 999px;
        font-weight: 600;
        letter-spacing: 0.01em;
    }
    .steps-strip .step span {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 999px;
        background: rgba(255, 65, 0, 0.92);
        color: #FFFFFF;
        font-weight: 700;
        font-size: 0.9rem;
        box-shadow: 0 0 12px rgba(255, 65, 0, 0.45);
    }
    .panel-card {
        background: #FFFFFF;
        border-radius: 22px;
        padding: 1.6rem 1.9rem 1.8rem;
        box-shadow: 0 32px 68px rgba(0, 0, 0, 0.28);
        border: 1px solid rgba(0, 0, 50, 0.08);
        position: relative;
    }
    .panel-card--order {
        background: rgba(255, 255, 255, 0.98);
    }
    .panel-title {
        font-size: 1.18rem;
        font-weight: 700;
        color: var(--obsidian-blue);
        margin-bottom: 0.2rem;
    }
    .panel-subtitle {
        font-size: 0.95rem;
        color: rgba(0, 0, 50, 0.62);
        margin-bottom: 1rem;
    }
    .panel-subtitle--label {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.78rem;
        font-weight: 700;
        color: rgba(0, 0, 50, 0.5);
        margin-bottom: 0.55rem;
    }
    .order-summary {
        margin-top: 0.65rem;
        font-weight: 600;
        color: rgba(0, 0, 50, 0.75);
    }
    .order-hint {
        margin-top: 0.25rem;
        font-size: 0.85rem;
        color: rgba(0, 0, 50, 0.5);
    }
    .empty-order {
        background: rgba(0, 0, 50, 0.05);
        border: 1px dashed rgba(0, 0, 50, 0.18);
        border-radius: 18px;
        padding: 2.15rem 1.8rem;
        text-align: center;
        color: rgba(0, 0, 50, 0.6);
        font-weight: 500;
    }
    .sortable-container {
        background: rgba(255, 255, 255, 0.94);
        border-radius: 12px;
        padding: 0.75rem 0.6rem 0.75rem 0.75rem;
        box-shadow: inset 0 0 0 1px rgba(0, 0, 50, 0.06);
        max-height: 300px;
        overflow-y: auto;
    }
    .sortable-item {
        border: 1px solid rgba(0, 0, 50, 0.24);
        border-radius: 10px;
        padding: 0.6rem 0.85rem;
        margin-bottom: 0.38rem;
        background: linear-gradient(100deg, rgba(210, 190, 170, 0.22) 0%, rgba(255, 255, 255, 0.93) 100%);
        color: var(--obsidian-blue);
        font-weight: 600;
        font-size: 0.9rem;
        transition: transform 0.1s ease, box-shadow 0.1s ease;
    }
    .sortable-item:last-child {
        margin-bottom: 0;
    }
    .sortable-item:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.08);
    }
    .steps-strip + .panel-row {
        margin-top: 1.4rem;
    }
    .stButton>button, .stDownloadButton>button {
        background: var(--essential-orange);
        border: none;
        color: #FFFFFF;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.95rem;
        padding: 0.75rem 1.8rem;
        box-shadow: 0 18px 35px rgba(255, 65, 0, 0.32);
        transition: transform 0.1s ease, box-shadow 0.1s ease;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background: #e63a00;
        box-shadow: 0 22px 44px rgba(255, 65, 0, 0.45);
        transform: translateY(-1px);
    }
    .stButton>button:disabled {
        background: rgba(255, 65, 0, 0.35) !important;
        box-shadow: none;
        color: rgba(255, 255, 255, 0.75);
    }
    [data-testid="stFileUploaderDropzone"] {
        border: 2px dashed rgba(0, 0, 50, 0.14) !important;
        background: rgba(255, 255, 255, 0.96) !important;
        border-radius: 18px !important;
    }
    [data-testid="stFileUploaderDropzone"] * {
        color: rgba(0, 0, 50, 0.72) !important;
    }
    div[data-baseweb="select"] > div {
        background: #FFFFFF !important;
        border-radius: 12px !important;
        border: 1px solid rgba(0, 0, 50, 0.12) !important;
        color: var(--obsidian-blue) !important;
        box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.03);
    }
    div[data-baseweb="select"] svg {
        color: rgba(0, 0, 50, 0.65);
    }
    .spacer-sm {
        height: 1.4rem;
    }
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: rgba(0, 0, 50, 0.08);
        border-radius: 999px;
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(255, 65, 0, 0.55);
        border-radius: 999px;
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
            "<div class='empty-order'>Upload PDFs on the left to arrange and flatten them here.</div>",
            unsafe_allow_html=True,
        )
        return

    total_pages = sum(item["pages"] for item in files)
    st.markdown(
        "<div class='panel-subtitle panel-subtitle--label'>Drag & drop to set the sequence</div>",
        unsafe_allow_html=True,
    )

    display_labels = [
        f"{item['name']} — {item['pages']} pages · #{item['id'][:4]}"
        for item in files
    ]

    col_sort, col_actions = st.columns([1.6, 1], gap="large")

    with col_sort:
        st.markdown('<div class="sortable-container">', unsafe_allow_html=True)
        reordered = sort_items(display_labels, direction="vertical", key="pdf-order")
        st.markdown('</div>', unsafe_allow_html=True)

        if reordered and reordered != display_labels:
            mapping = {label: entry for label, entry in zip(display_labels, files)}
            st.session_state["pdf_files"] = [mapping[label] for label in reordered]
            st.rerun()

        summary_text = f"{len(files)} file{'s' if len(files) != 1 else ''} · {total_pages} page{'s' if total_pages != 1 else ''}"
        st.markdown(f"<div class='order-summary'>{summary_text}</div>", unsafe_allow_html=True)
        st.markdown("<div class='order-hint'>Drag items above to refine the merge output.</div>", unsafe_allow_html=True)

    with col_actions:
        st.markdown("<div class='panel-subtitle panel-subtitle--label'>Quick actions</div>", unsafe_allow_html=True)
        option_pairs = [
            (f"{index + 1}. {item['name']} ({item['pages']} pages)", item["id"])
            for index, item in enumerate(files)
        ]
        option_labels = [label for label, _ in option_pairs]
        selected_label = st.selectbox(
            "Remove a PDF",
            ["Keep all"] + option_labels,
            index=0,
            label_visibility="collapsed",
            key="remove-select",
        )
        if selected_label != "Keep all":
            chosen_map = {label: value for label, value in option_pairs}
            remove_item(chosen_map[selected_label])
            st.rerun()

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
        if st.button("Clear List", use_container_width=True, key="clear-list"):
            st.session_state["pdf_files"] = []
            st.session_state["last_output"] = None
            st.rerun()


def main() -> None:
    init_state()

    st.markdown(
        """
        <section class="hero-card">
            <h1 class="hero-title">THC Form Merge Tool</h1>
            <p class="hero-body">Preserve every checkbox, signature, and annotation by rendering each page into a pristine image layer before you combine them into a single, shareable PDF.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="steps-strip">
            <div class="step"><span>1</span>Upload fillable PDFs</div>
            <div class="step"><span>2</span>Arrange the order</div>
            <div class="step"><span>3</span>Export the flattened copy</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    dpi = DEFAULT_DPI
    image_format = "JPEG"
    jpeg_quality = DEFAULT_JPEG_QUALITY

    upload_col, order_col = st.columns([1.25, 1], gap="large")

    with upload_col:
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-title'>Upload documents</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='panel-subtitle'>Drop your signed or fillable PDFs. They remain on this device for the duration of the session.</div>",
            unsafe_allow_html=True,
        )
        uploaded_files = st.file_uploader(
            "Upload PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="You can add multiple PDFs at once.",
        )
        if uploaded_files:
            cache_uploaded_files(uploaded_files)
        st.markdown("</div>", unsafe_allow_html=True)

    with order_col:
        st.markdown("<div class='panel-card panel-card--order'>", unsafe_allow_html=True)
        render_uploaded_list()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='spacer-sm'></div>", unsafe_allow_html=True)

    can_merge = bool(st.session_state["pdf_files"])
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        merge_button = st.button("Create Flattened PDF", disabled=not can_merge, use_container_width=True, type="primary")

    if merge_button and can_merge:
        with st.spinner("Rendering pages as images and merging..."):
            try:
                merged_bytes, total_pages = flatten_pdfs(
                    st.session_state["pdf_files"], dpi, image_format, jpeg_quality
                )
            except Exception as exc:  # pragma: no cover - safety for unexpected errors
                st.error(f"Failed to build merged PDF: {exc}")
                return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_name = f"flattened-merge-{timestamp}.pdf"
        st.session_state["last_output"] = {
            "bytes": merged_bytes,
            "pages": total_pages,
            "name": output_name,
            "dpi": dpi,
            "image_format": image_format,
            "quality": jpeg_quality,
        }
        size_mb = len(merged_bytes) / (1024 * 1024)
        st.success(
            f"Merged PDF ready. Total pages: {total_pages} at {dpi} DPI using {image_format}. Size: {size_mb:.2f} MB."
        )

    if st.session_state["last_output"]:
        download = st.session_state["last_output"]
        st.download_button(
            label="Download merged PDF",
            data=download["bytes"],
            file_name=download["name"],
            mime="application/pdf",
        )


if __name__ == "__main__":
    main()
