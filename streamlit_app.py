import streamlit as st
import os
import base64
import json
import time
import re
import pandas as pd
from mistral_client import Mistral
from auth import get_app_password, is_valid_password

def markdown_table_to_dataframe(table_lines):
    """Convert markdown table lines to a pandas DataFrame."""
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    headers = rows[0]
    # Skip separator rows (e.g. |---|:---:|---:|)
    data_rows = [r for r in rows[1:] if not all(re.match(r'^[-:]+$', c) for c in r)]
    if not data_rows:
        return None
    # Ensure unique column names to avoid PyArrow ValueError
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}" if h else f"_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    num_cols = len(unique_headers)
    data_rows = [r[:num_cols] + [''] * (num_cols - len(r)) for r in data_rows]
    return pd.DataFrame(data_rows, columns=unique_headers)


_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')


def replace_images_in_markdown(markdown_text, images):
    """Replace image filename references in markdown with actual base64 data URIs."""
    if not images:
        return markdown_text
    for img in images:
        img_id = img.id if hasattr(img, 'id') else img.get('id', '')
        img_data = img.image_base64 if hasattr(img, 'image_base64') else img.get('image_base64', '')
        if img_id and img_data:
            markdown_text = markdown_text.replace(f"]({img_id})", f"]({img_data})")
    return markdown_text


def _flush_markdown_with_images(buffer):
    """Render markdown lines, displaying embedded base64 images with st.image()."""
    text_lines = []
    for line in buffer:
        m = _IMAGE_RE.search(line)
        if m:
            if text_lines:
                st.markdown("\n".join(text_lines))
                text_lines = []
            img_src = m.group(2)
            caption = m.group(1) or None
            if img_src.startswith("data:"):
                _, b64_data = img_src.split(",", 1)
                st.image(base64.b64decode(b64_data), caption=caption)
            else:
                st.image(img_src, caption=caption)
        else:
            text_lines.append(line)
    if text_lines:
        st.markdown("\n".join(text_lines))


def parse_and_display_ocr(text):
    """Parse OCR markdown output and display tables interactively, other content as markdown."""
    lines = text.split("\n")
    buffer = []
    table_lines = []
    in_table = False

    for line in lines:
        is_table_line = line.strip().startswith("|") and line.strip().endswith("|")
        if is_table_line:
            if not in_table:
                # Flush any non-table text
                if buffer:
                    _flush_markdown_with_images(buffer)
                    buffer = []
                in_table = True
            table_lines.append(line)
        else:
            if in_table:
                # End of a table block — render it
                df = markdown_table_to_dataframe(table_lines)
                if df is not None:
                    st.data_editor(
                        df,
                        disabled=True,
                        hide_index=True,
                        use_container_width=True,
                        num_rows="fixed",
                    )
                else:
                    st.markdown("\n".join(table_lines))
                table_lines = []
                in_table = False
            buffer.append(line)

    # Flush remaining content
    if in_table and table_lines:
        df = markdown_table_to_dataframe(table_lines)
        if df is not None:
            st.data_editor(
                df,
                disabled=True,
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
            )
        else:
            st.markdown("\n".join(table_lines))
    if buffer:
        _flush_markdown_with_images(buffer)


st.set_page_config(layout="wide", page_title="Tuber Tracker", page_icon="🥔")
st.title("Tater Tracker OCR App")
with st.expander("Expand Me"):
    st.markdown("""
    This application allows you to extract information from pdf/images, and convert them into an Excel-like format.
    """)

# 1. API Key from environment variable or Streamlit secrets
api_key = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["MISTRAL_API_KEY"]
    except (KeyError, FileNotFoundError):
        api_key = None
if not api_key:
    st.error("MISTRAL_API_KEY is not set. Please set it as an environment variable or in Streamlit secrets before running the app.")
    st.stop()

# Initialize session state variables for persistence
if "ocr_result" not in st.session_state:
    st.session_state["ocr_result"] = []
if "preview_src" not in st.session_state:
    st.session_state["preview_src"] = []
if "image_bytes" not in st.session_state:
    st.session_state["image_bytes"] = []
if "is_authenticated" not in st.session_state:
    st.session_state["is_authenticated"] = False

if not st.session_state["is_authenticated"]:
    app_password = get_app_password()
    if not app_password:
        st.error("Application is not properly configured. Please contact the administrator.")
        st.stop()

    with st.form("unlock_form"):
        entered_password = st.text_input("Application Password", type="password")
        unlock_clicked = st.form_submit_button("Unlock")
    if unlock_clicked:
        if is_valid_password(entered_password, app_password):
            st.session_state["is_authenticated"] = True
            st.rerun()
        else:
            st.error("Authentication failed.")
    st.stop()

# 2. Choose file type: PDF or Image
file_type = st.radio("Select file type", ("PDF", "Image"))

# 3. Select source type: URL or Local Upload
source_type = st.radio("Select source type", ("Local Upload", "URL"))

input_url = ""
uploaded_files = []

if source_type == "URL":
    input_url = st.text_area("Enter one or multiple URLs (separate with new lines)")
else:
    uploaded_files = st.file_uploader("Upload one or more files", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)

# 4. Process Button & OCR Handling
if st.button("Process"):
    if source_type == "URL" and not input_url.strip():
        st.error("Please enter at least one valid URL.")
    elif source_type == "Local Upload" and not uploaded_files:
        st.error("Please upload at least one file.")
    else:
        client = Mistral(api_key=api_key)
        st.session_state["ocr_result"] = []
        st.session_state["preview_src"] = []
        st.session_state["image_bytes"] = []
        
        sources = input_url.split("\n") if source_type == "URL" else uploaded_files
        
        for idx, source in enumerate(sources):
            if file_type == "PDF":
                if source_type == "URL":
                    document = {"type": "document_url", "document_url": source.strip()}
                    preview_src = source.strip()
                else:
                    file_bytes = source.read()
                    encoded_pdf = base64.b64encode(file_bytes).decode("utf-8")
                    document = {"type": "document_url", "document_url": f"data:application/pdf;base64,{encoded_pdf}"}
                    preview_src = f"data:application/pdf;base64,{encoded_pdf}"
            else:
                if source_type == "URL":
                    document = {"type": "image_url", "image_url": source.strip()}
                    preview_src = source.strip()
                else:
                    file_bytes = source.read()
                    mime_type = source.type
                    encoded_image = base64.b64encode(file_bytes).decode("utf-8")
                    document = {"type": "image_url", "image_url": f"data:{mime_type};base64,{encoded_image}"}
                    preview_src = f"data:{mime_type};base64,{encoded_image}"
                    st.session_state["image_bytes"].append(file_bytes)
            
            with st.spinner(f"Processing {source if source_type == 'URL' else source.name}..."):
                try:
                    ocr_response = client.ocr.process(model="mistral-ocr-latest", document=document, include_image_base64=True)
                    time.sleep(1)  # wait 1 second between request to prevent rate limit exceeding
                    
                    pages = ocr_response.pages if hasattr(ocr_response, "pages") else (ocr_response if isinstance(ocr_response, list) else [])
                    page_markdowns = []
                    for page in pages:
                        md = page.markdown
                        if hasattr(page, 'images') and page.images:
                            md = replace_images_in_markdown(md, page.images)
                        page_markdowns.append(md)
                    result_text = "\n\n".join(page_markdowns) or "No result found."
                except Exception as e:
                    result_text = f"Error extracting result: {e}"
                
                st.session_state["ocr_result"].append(result_text)
                st.session_state["preview_src"].append(preview_src)

# 5. Display Preview and OCR Results if available
if st.session_state["ocr_result"]:
    for idx, result in enumerate(st.session_state["ocr_result"]):
        st.subheader(f"OCR Results {idx+1}")
        if file_type != "PDF":
            if source_type == "Local Upload" and st.session_state["image_bytes"]:
                st.image(st.session_state["image_bytes"][idx])
            else:
                st.image(st.session_state["preview_src"][idx])

        def create_download_link(data, filetype, filename):
            b64 = base64.b64encode(data.encode()).decode()
            href = f'<a href="data:{filetype};base64,{b64}" download="{filename}">Download {filename}</a>'
            st.markdown(href, unsafe_allow_html=True)

        json_data = json.dumps({"ocr_result": result}, ensure_ascii=False, indent=2)
        create_download_link(json_data, "application/json", f"Output_{idx+1}.json") # json output
        create_download_link(result, "text/plain", f"Output_{idx+1}.txt") # plain text output
        create_download_link(result, "text/markdown", f"Output_{idx+1}.md") # markdown output

        parse_and_display_ocr(result)
