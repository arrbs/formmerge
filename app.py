import hashlib
import uuid
from datetime import datetime
from typing import List, Tuple

import fitz
import streamlit as st
from streamlit_sortables import sort_items

st.set_page_config(page_title="Obsidian Merge Studio", layout="wide")

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
        background-color: var(--fuselage-grey);
        color: var(--obsidian-blue);
    }
    [data-testid="stSidebar"] {
        background-color: var(--warm-grey);
    }
    [data-testid="stSidebar"] * {
        color: var(--obsidian-blue) !important;
    }
    h1, h2, h3, h4, h5, h6, label, p, span {
        color: var(--obsidian-blue);
    }
    .stButton>button, .stDownloadButton>button {
        background-color: var(--essential-orange);
        border: none;
        color: white;
        border-radius: 6px;
        font-weight: 600;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background-color: #cc3300;
        color: white;
    }
    [data-testid="stSlider"] [data-baseweb="slider"] > div > div {
        background-color: var(--essential-orange);
    }
    [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
        background-color: white;
        border: 2px solid var(--essential-orange);
    }
    .block-container {
        padding-top: 2rem;
    }
    .sortable-container {
        background-color: white;
        border-radius: 8px;
        padding: 1rem;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    }
    .sortable-item {
        border: 1px solid rgba(0, 0, 50, 0.15);
        border-radius: 6px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        background-color: var(--fuselage-grey);
        color: var(--obsidian-blue);
        font-weight: 500;
    }
    .sortable-item:last-child {
        margin-bottom: 0;
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
    if not st.session_state["pdf_files"]:
        st.info("Upload one or more PDFs to begin. Files stay in memory only for your current session.")
        return
    st.subheader("Arrange & Review PDFs")

    files = st.session_state["pdf_files"]
    display_labels = [
        f"{item['name']} — {item['pages']} pages — {human_file_size(item['size'])} (#{item['id'][:8]})"
        for item in files
    ]
    st.markdown('<div class="sortable-container">', unsafe_allow_html=True)
    reordered = sort_items(display_labels, direction="vertical", key="pdf-order")
    st.markdown('</div>', unsafe_allow_html=True)

    if reordered and reordered != display_labels:
        mapping = {label: entry for label, entry in zip(display_labels, files)}
        st.session_state["pdf_files"] = [mapping[label] for label in reordered]
        st.rerun()

    st.caption("Drag the items above to change their order. Use the selector below to remove a file.")

    options = {f"{item['name']} ({item['pages']} pages)": item["id"] for item in files}
    choice = st.selectbox("Remove a PDF", ["Keep all"] + list(options.keys()), index=0)
    if choice != "Keep all":
        remove_item(options[choice])
        st.rerun()

    st.divider()


def main() -> None:
    init_state()

    st.title("Obsidian Merge Studio")
    st.title("Obsidian Merge Studio")
    st.markdown(
        """
        <div style='background:#FFFFFF;border-left:6px solid #FF4100;padding:1rem 1.5rem;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,0.06);'>
            Preserve the fidelity of every checkbox, signature, and handwritten note by rendering PDFs into true image layers before combining them.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Palette: Fuselage Grey, Warm Grey, Essential Orange, Obsidian Blue")

    with st.sidebar:
        st.header("Workflow")
        st.write("1. Upload fillable PDFs.")
        st.write("2. Arrange their order.")
        st.write("3. Generate a flattened merged PDF.")
        dpi = st.slider("Render DPI", min_value=150, max_value=400, value=300, step=25)
        image_format = st.radio(
            "Image Encoding",
            options=["JPEG", "PNG"],
            format_func=lambda value: "JPEG (smaller, recommended)" if value == "JPEG" else "PNG (lossless, largest)",
        )
        jpeg_quality = 85
        if image_format == "JPEG":
            jpeg_quality = st.slider("JPEG Quality", min_value=60, max_value=95, value=85, step=5)
        if st.button("Clear All"):
            st.session_state["pdf_files"] = []
            st.session_state["last_output"] = None
            st.rerun()

    uploaded_files = st.file_uploader(
        "Upload one or more PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        help="Choose PDFs from your device. Files stay local on this machine while the app is running.",
    )

    if uploaded_files:
        cache_uploaded_files(uploaded_files)

    render_uploaded_list()

    can_merge = bool(st.session_state["pdf_files"])
    merge_button = st.button("Create Flattened PDF", disabled=not can_merge)

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
