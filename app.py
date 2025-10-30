import hashlib
import io
import uuid
from datetime import datetime
from typing import List, Tuple

import fitz
import streamlit as st

st.set_page_config(page_title="Reliable PDF Image Merger", layout="wide")


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


def move_item(current_index: int, direction: int) -> None:
    target_index = current_index + direction
    if target_index < 0 or target_index >= len(st.session_state["pdf_files"]):
        return
    files = st.session_state["pdf_files"]
    files[current_index], files[target_index] = files[target_index], files[current_index]


def remove_item(item_id: str) -> None:
    files = st.session_state["pdf_files"]
    filtered = [item for item in files if item["id"] != item_id]
    st.session_state["pdf_files"] = filtered


def flatten_pdfs(file_entries: List[dict], dpi: int) -> Tuple[bytes, int]:
    output_doc = fitz.open()
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    total_pages = 0
    for entry in file_entries:
        with fitz.open(stream=entry["data"], filetype="pdf") as src_doc:
            for page in src_doc:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                rect = page.rect
                new_page = output_doc.new_page(width=rect.width, height=rect.height)
                new_page.insert_image(rect, stream=pix.tobytes("png"))
                total_pages += 1
    output_bytes = output_doc.tobytes()
    output_doc.close()
    return output_bytes, total_pages


def render_uploaded_list() -> None:
    if not st.session_state["pdf_files"]:
        st.info("Upload one or more PDFs to begin. Files stay in memory only for your current session.")
        return
    st.subheader("Merge Order")
    for index, item in enumerate(st.session_state["pdf_files"]):
        col_main, col_up, col_down, col_remove = st.columns([6, 1, 1, 1])
        col_main.markdown(
            f"{index + 1}. **{item['name']}** — {item['pages']} pages — {human_file_size(item['size'])}"
        )
        if col_up.button("Move Up", key=f"up-{item['id']}"):
            move_item(index, -1)
            st.experimental_rerun()
        if col_down.button("Move Down", key=f"down-{item['id']}"):
            move_item(index, 1)
            st.experimental_rerun()
        if col_remove.button("Remove", key=f"remove-{item['id']}"):
            remove_item(item["id"])
            st.experimental_rerun()
    st.divider()


def main() -> None:
    init_state()

    st.title("Reliable Fillable PDF Merger")
    st.write(
        "This app flattens each page into a high-resolution image before merging, preserving checkboxes, signatures, and other form data."
    )

    with st.sidebar:
        st.header("Workflow")
        st.write("1. Upload fillable PDFs.")
        st.write("2. Arrange their order.")
        st.write("3. Generate a flattened merged PDF.")
        dpi = st.slider("Render DPI", min_value=150, max_value=400, value=300, step=25)
        if st.button("Clear All"):
            st.session_state["pdf_files"] = []
            st.session_state["last_output"] = None
            st.experimental_rerun()

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
                merged_bytes, total_pages = flatten_pdfs(st.session_state["pdf_files"], dpi)
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
        }
        st.success(f"Merged PDF ready. Total pages: {total_pages} at {dpi} DPI.")

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
