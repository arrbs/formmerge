import hashlib
import uuid
from datetime import datetime
from typing import List, Tuple

import fitz
import streamlit as st
from streamlit_sortables import sort_items

st.set_page_config(page_title="Form Merge", layout="centered")

def init_state() -> None:
    """Initializes session state variables."""
    if "pdf_files" not in st.session_state:
        st.session_state["pdf_files"] = []
    if "last_output" not in st.session_state:
        st.session_state["last_output"] = None

def cache_uploaded_files(uploaded_files: List[st.runtime.uploaded_file_manager.UploadedFile]) -> None:
    """Adds new files to session state, avoiding duplicates."""
    existing_hashes = {item["checksum"] for item in st.session_state.get("pdf_files", [])}
    for uploaded in uploaded_files:
        file_bytes = uploaded.getvalue()
        checksum = hashlib.sha1(file_bytes).hexdigest()
        if checksum in existing_hashes:
            continue
        
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                page_count = len(doc)
        except Exception as exc:
            st.warning(f"Skipping '{uploaded.name}': Not a valid PDF. ({exc})")
            continue

        st.session_state["pdf_files"].append({
            "id": str(uuid.uuid4()),
            "name": uploaded.name,
            "data": file_bytes,
            "checksum": checksum,
            "pages": page_count,
        })

def flatten_pdfs(file_entries: List[dict]) -> bytes:
    """
    Flattens a list of PDF files by rendering each page as an image.
    This preserves form fields, signatures, and other annotations.
    """
    output_doc = fitz.open()
    # Use a fixed DPI and JPEG quality for consistent output and smaller file sizes.
    dpi = 200
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    jpeg_quality = 85

    for entry in file_entries:
        with fitz.open(stream=entry["data"], filetype="pdf") as src_doc:
            for page in src_doc:
                pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
                image_bytes = pix.tobytes("jpeg", jpg_quality=jpeg_quality)
                
                page_width = pix.width * 72.0 / dpi
                page_height = pix.height * 72.0 / dpi
                rect = fitz.Rect(0, 0, page_width, page_height)

                new_page = output_doc.new_page(width=page_width, height=page_height)
                new_page.insert_image(rect, stream=image_bytes)
    
    return output_doc.tobytes()

def main() -> None:
    """Main function to run the Streamlit application."""
    init_state()

    st.title("📄 Form Merge")
    st.write(
        "Merge multiple fillable PDFs into a single, flattened file. "
        "This preserves form data, signatures, and checkboxes that are often lost."
    )

    # --- 1. File Uploader ---
    with st.container(border=True):
        st.subheader("1. Upload PDFs")
        uploaded_files = st.file_uploader(
            "Select one or more PDF files",
            type=["pdf"],
            accept_multiple_files=True,
        )
        if uploaded_files:
            cache_uploaded_files(uploaded_files)

    # --- 2. File Reordering ---
    if st.session_state.pdf_files:
        with st.container(border=True):
            st.subheader("2. Arrange Files")
            st.write("Drag and drop the files to set the merge order.")
            
            # Create a list of strings (labels) for the sortable component
            display_labels = [
                f"{item['name']} ({item['pages']} pages)"
                for item in st.session_state.pdf_files
            ]
            
            # When multi_containers is False, sort_items expects a list of strings
            sorted_labels = sort_items(display_labels)

            # If the order has changed, update the session state
            if sorted_labels and sorted_labels != display_labels:
                original_map = {f"{item['name']} ({item['pages']} pages)": item for item in st.session_state.pdf_files}
                st.session_state.pdf_files = [original_map[label] for label in sorted_labels]
                st.rerun()

            if st.button("Clear All Files", use_container_width=False):
                st.session_state.pdf_files = []
                st.session_state.last_output = None
                st.rerun()

    # --- 3. Merge and Download ---
    can_merge = bool(st.session_state.pdf_files)
    
    st.header("3. Merge & Download")
    merge_button = st.button(
        "Create Flattened PDF",
        type="primary",
        disabled=not can_merge,
        use_container_width=True
    )

    if merge_button:
        with st.spinner("Flattening and merging PDFs... This may take a moment."):
            try:
                merged_bytes = flatten_pdfs(st.session_state.pdf_files)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                output_name = f"merged-form-{timestamp}.pdf"
                st.session_state.last_output = {"bytes": merged_bytes, "name": output_name}
            except Exception as e:
                st.error(f"An error occurred during merging: {e}")
    
    if st.session_state.last_output:
        output = st.session_state.last_output
        size_mb = len(output["bytes"]) / (1024 * 1024)
        st.success(f"✅ Merge complete! Your file is {size_mb:.2f} MB.")
        st.download_button(
            label=f"Download '{output['name']}'",
            data=output["bytes"],
            file_name=output["name"],
            mime="application/pdf",
            use_container_width=True,
        )

if __name__ == "__main__":
    main()
