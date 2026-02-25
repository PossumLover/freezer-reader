import streamlit as st
import os
import base64
import json
import time
import re
import pandas as pd
from mistralai import Mistral

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
                    st.markdown("\n".join(buffer))
                    buffer = []
                in_table = True
            table_lines.append(line)
        else:
            if in_table:
                # End of a table block — render it
                df = markdown_table_to_dataframe(table_lines)
                if df is not None:
                    st.dataframe(
                        df,
                        use_container_width=True,
                        selection_mode=["multi-row", "multi-column"],
                        on_select="ignore",
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
            st.dataframe(
                df,
                use_container_width=True,
                selection_mode=["multi-row", "multi-column"],
                on_select="ignore",
            )
        else:
            st.markdown("\n".join(table_lines))
    if buffer:
        st.markdown("\n".join(buffer))


st.set_page_config(layout="wide", page_title="Mistral OCR App", page_icon="🖥️")
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

# 2. Choose file type: PDF or Image
file_type = st.radio("Select file type", ("PDF", "Image"))

# 3. Select source type: URL or Local Upload
source_type = st.radio("Select source type", ("URL", "Local Upload"))

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
                    result_text = "\n\n".join(page.markdown for page in pages) or "No result found."
                except Exception as e:
                    result_text = f"Error extracting result: {e}"
                
                st.session_state["ocr_result"].append(result_text)
                st.session_state["preview_src"].append(preview_src)

# 5. Display Preview and OCR Results if available
if st.session_state["ocr_result"]:
    for idx, result in enumerate(st.session_state["ocr_result"]):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"Input PDF {idx+1}")
            if file_type == "PDF":
                pdf_embed_html = f'<iframe src="{st.session_state["preview_src"][idx]}" width="100%" height="800" frameborder="0"></iframe>'
                st.markdown(pdf_embed_html, unsafe_allow_html=True)
            else:
                if source_type == "Local Upload" and st.session_state["image_bytes"]:
                    st.image(st.session_state["image_bytes"][idx])
                else:
                    st.image(st.session_state["preview_src"][idx])
        
        with col2:
            st.subheader(f"Download OCR results {idx+1}")
            
            def create_download_link(data, filetype, filename):
                b64 = base64.b64encode(data.encode()).decode()
                href = f'<a href="data:{filetype};base64,{b64}" download="{filename}">Download {filename}</a>'
                st.markdown(href, unsafe_allow_html=True)
            
            json_data = json.dumps({"ocr_result": result}, ensure_ascii=False, indent=2)
            create_download_link(json_data, "application/json", f"Output_{idx+1}.json") # json output
            create_download_link(result, "text/plain", f"Output_{idx+1}.txt") # plain text output
            create_download_link(result, "text/markdown", f"Output_{idx+1}.md") # markdown output

            # To preview results
            parse_and_display_ocr(result)
