import hashlib
import uuid
from datetime import datetime
from typing import List, Tuple

import fitz
import streamlit as st
from streamlit_sortables import sort_items

st.set_page_config(page_title="Form Merge", layout="centered")

# Apply custom THC color theme
st.markdown("""
    <style>
    /* Primary color scheme */
    :root {
        --fuselage-grey: #F5F5F5;
        --warm-grey: #D2BEAA;
        --essential-orange: #FF4100;
        --obsidian-blue: #000032;
        --cool-gray-2: #E6E6E6;
        --brownish: #826450;
        --red: #EB1900;
        --warm-grey-1: #E1D7CD;
        --orange: #FF7D32;
        --blue: #0000B9;
    }
    
    /* Main app background */
    .stApp {
        background-color: #F5F5F5;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #000032 !important;
    }
    
    /* Primary buttons */
    .stButton > button[kind="primary"] {
        background-color: #FF4100 !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #EB1900 !important;
        border: none !important;
    }
    
    /* Secondary buttons */
    .stButton > button {
        background-color: #D2BEAA !important;
        color: #000032 !important;
        border: none !important;
    }
    
    .stButton > button:hover {
        background-color: #826450 !important;
        color: white !important;
    }
    
    /* Download button */
    .stDownloadButton > button {
        background-color: #FF4100 !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    
    .stDownloadButton > button:hover {
        background-color: #FF7D32 !important;
    }
    
    /* Containers with borders */
    [data-testid="stContainer"] {
        background-color: white;
        border: 2px solid #E6E6E6 !important;
        border-radius: 8px;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background-color: white !important;
        color: #000032 !important;
        border: 2px solid #E6E6E6 !important;
        border-radius: 8px !important;
    }
    
    /* Success message */
    .stSuccess {
        background-color: #E1D7CD !important;
        color: #000032 !important;
        border-left: 4px solid #FF4100 !important;
    }
    
    /* File uploader */
    [data-testid="stFileUploader"] {
        background-color: white;
        border: 2px dashed #D2BEAA !important;
        border-radius: 8px;
    }
    
    /* Text elements */
    p, .stText {
        color: #000032 !important;
    }
    </style>
""", unsafe_allow_html=True)

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
    with st.expander("1. Upload PDFs", expanded=not st.session_state.pdf_files):
        uploaded_files = st.file_uploader(
            "Select one or more PDF files",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        if uploaded_files:
            cache_uploaded_files(uploaded_files)

    # --- 2. File Reordering ---
    if st.session_state.pdf_files:
        with st.container(border=True):
            st.subheader("2. Arrange Files")
            st.write("Use the buttons to set the merge order.")

            for i, item in enumerate(st.session_state.pdf_files):
                col1, col2, col3 = st.columns([0.8, 0.1, 0.1])
                with col1:
                    st.text(f"{i+1}. {item['name']} ({item['pages']} pages)")
                with col2:
                    if st.button("⬆️", key=f"up_{i}", use_container_width=True, disabled=(i == 0)):
                        st.session_state.pdf_files.insert(i - 1, st.session_state.pdf_files.pop(i))
                        st.rerun()
                with col3:
                    if st.button("⬇️", key=f"down_{i}", use_container_width=True, disabled=(i == len(st.session_state.pdf_files) - 1)):
                        st.session_state.pdf_files.insert(i + 1, st.session_state.pdf_files.pop(i))
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
                st.session_state.show_download = True
            except Exception as e:
                st.error(f"An error occurred during merging: {e}")
    
    if st.session_state.last_output:
        output = st.session_state.last_output
        size_mb = len(output["bytes"]) / (1024 * 1024)
        st.success(f"✅ Merge complete! Your file is {size_mb:.2f} MB.")
        
        # Show download button with auto-trigger
        if st.session_state.get("show_download", False):
            st.download_button(
                label=f"⬇️ Download '{output['name']}'",
                data=output["bytes"],
                file_name=output["name"],
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
            st.session_state.show_download = False
        else:
            st.download_button(
                label=f"Download '{output['name']}'",
                data=output["bytes"],
                file_name=output["name"],
                mime="application/pdf",
                use_container_width=True,
            )
        
        # Add "Merge Another" button
        st.write("")  # Spacer
        if st.button("📄 Merge Another File", use_container_width=True):
            st.session_state.pdf_files = []
            st.session_state.last_output = None
            st.session_state.show_download = False
            st.rerun()

if __name__ == "__main__":
    main()
