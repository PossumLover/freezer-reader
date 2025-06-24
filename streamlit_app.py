# ------------------------------------------------------------------
# Google Vision client - works locally *and* on Streamlit Cloud
# ------------------------------------------------------------------
import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
from datetime import datetime
import requests, base64
import pandas as pd
import io
from openai import OpenAI

@st.cache_resource
def get_vision_client():
    # ---- Option A: full service-account JSON in st.secrets ----------
    if "gcp_service_account" in st.secrets:
        creds_dict  = st.secrets["gcp_service_account"]
        creds       = service_account.Credentials.from_service_account_info(creds_dict)
        return vision.ImageAnnotatorClient(credentials=creds)

    # ---- Option B: plain API key in st.secrets ----------------------
    if "gcp" in st.secrets and "api_key" in st.secrets["gcp"]:
        class VisionViaREST:
            """Tiny wrapper that mimics .text_detection() using API-key REST"""
            def text_detection(self, image):
                img_content = base64.b64encode(image.content).decode()
                body = {"requests":[
                    {"image":{"content":img_content},
                     "features":[{"type":"TEXT_DETECTION"}]}]}
                url = (f"https://vision.googleapis.com/v1/images:annotate"
                       f"?key={st.secrets['gcp']['api_key']}")
                r = requests.post(url, json=body, timeout=15)
                r.raise_for_status()
                return r.json()["responses"][0]
        return VisionViaREST()

    # ---- Fallback: default application creds (local dev) -----------
    return vision.ImageAnnotatorClient()

@st.cache_resource
def get_openai_client():
    """Initialize OpenAI client with API key from secrets"""
    if "openai_api_key" in st.secrets:
        return OpenAI(api_key=st.secrets["openai_api_key"])
    else:
        st.error("OpenAI API key not found in secrets. Please add 'openai_api_key' to your Streamlit secrets.")
        return None

client = get_vision_client()
openai_client = get_openai_client()

# --------------------------------------------------
# 1. Session-state helpers
# --------------------------------------------------
if "log" not in st.session_state:
    st.session_state.log = []        # list of dicts: {"Coordinate": "A1", "Description": "...", "Timestamp": ...}

# --------------------------------------------------
# 2. Simple UI layout
# --------------------------------------------------
st.title("−80 °C Freezer Inventory Helper")

st.markdown(
    "1. Enter the box coordinate (e.g., B2)\n"
    "2. Upload 1–2 photos of the vial/flask label\n"
    "3. The system will process images with OCR and generate a description\n"
    "4. Review and edit the description if needed\n"
    "5. Click **Add to inventory**\n"
    "6. Download the CSV file when finished"
)

# Coordinate input
coord = st.text_input("Coordinate (e.g., A1, B2, C10)", value="A1", key="coordinate")

# Image uploader
uploaded_files = st.file_uploader(
    "Upload 1–2 images of the same vial (hand-written text on curved surface)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key="image_uploader"
)

# --------------------------------------------------
# 3. OCR routine
# --------------------------------------------------
def ocr_bytes(image_bytes: bytes) -> str:
    """Return the full text detected in an image."""
    g_image = vision.Image(content=image_bytes)
    response = client.text_detection(image=g_image)
    
    # Handle both REST API response and gRPC response formats
    if hasattr(response, 'error') and response.error.message:
        st.error(f"Google Vision error: {response.error.message}")
        return ""
    elif isinstance(response, dict) and 'error' in response:
        st.error(f"Google Vision error: {response['error']}")
        return ""
    
    # Handle gRPC response
    if hasattr(response, 'text_annotations'):
        texts = response.text_annotations
        return texts[0].description.strip() if texts else ""
    # Handle REST API response
    elif isinstance(response, dict) and 'textAnnotations' in response:
        texts = response['textAnnotations']
        return texts[0]['description'].strip() if texts else ""
    
    return ""

def run_ocr(files) -> list:
    """Return OCR output from each image separately."""
    ocr_results = []
    for i, f in enumerate(files):
        st.write(f"Processing image {i+1}/{len(files)}...")
        text = ocr_bytes(f.getvalue())
        ocr_results.append(text)
        if text:
            st.write(f"**Image {i+1} OCR result:** {text}")
        else:
            st.write(f"**Image {i+1}:** No text detected")
    return ocr_results

def process_with_llm(ocr_results: list, coordinate: str) -> str:
    """Use OpenAI to process OCR results into a coherent description."""
    if not openai_client:
        # Fallback: just concatenate the OCR results
        return " | ".join([text for text in ocr_results if text.strip()])
    
    # Combine all OCR results
    combined_text = "\n".join([f"Image {i+1}: {text}" for i, text in enumerate(ocr_results) if text.strip()])
    
    if not combined_text.strip():
        return "No text detected in images"
    
    prompt = f"""
You are helping to catalog scientific samples in a -80°C freezer. 

I have OCR text from 1-2 images of a test tube/vial label at coordinate {coordinate}. The text may be handwritten, partially obscured, or contain errors due to curved surfaces.

OCR Results:
{combined_text}

Please provide a clear, concise description of what this sample appears to be. Focus on:
- Sample name/identifier
- Any dates visible
- Sample type (if identifiable)
- Any other relevant information

Keep the description under 100 words and make it suitable for inventory purposes.

If the text is unclear or contradictory between images, make your best interpretation and note any uncertainty.
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        # Fallback: return combined OCR text
        return " | ".join([text for text in ocr_results if text.strip()])

# --------------------------------------------------
# 4. Process images when uploaded
# --------------------------------------------------
processed_description = ""
if uploaded_files:
    with st.spinner("Running OCR on images..."):
        ocr_results = run_ocr(uploaded_files)
    
    if any(result.strip() for result in ocr_results):
        with st.spinner("Processing with AI to generate description..."):
            processed_description = process_with_llm(ocr_results, coord)
        st.success("Processing complete!")
    else:
        st.warning("No text detected in any of the uploaded images.")

# Show editable description
sample_description = st.text_area(
    "Generated description (edit if needed)", 
    value=processed_description,
    height=100,
    key="description_area"
)

# --------------------------------------------------
# 5. Add to in-memory table
# --------------------------------------------------
if st.button("Add to inventory"):
    if not coord.strip():
        st.warning("Please enter a coordinate.")
    elif not sample_description.strip():
        st.warning("Please add a description.")
    else:
        # Check if coordinate already exists
        existing_coords = [entry["Coordinate"] for entry in st.session_state.log]
        if coord in existing_coords:
            st.warning(f"Coordinate {coord} already exists in inventory. Use 'Update existing' if you want to replace it.")
        else:
            st.session_state.log.append({
                "Coordinate": coord,
                "Description": sample_description,
                "Timestamp": datetime.now().isoformat(timespec="seconds"),
            })
            st.success(f"Added {coord} → {sample_description[:50]}{'...' if len(sample_description) > 50 else ''}")
            
            # Clear form for next entry
            st.session_state.coordinate = ""
            st.session_state.description_area = ""
            st.rerun()

# Option to update existing coordinate
if st.button("Update existing coordinate"):
    if not coord.strip():
        st.warning("Please enter a coordinate.")
    elif not sample_description.strip():
        st.warning("Please add a description.")
    else:
        # Find and update existing entry
        updated = False
        for i, entry in enumerate(st.session_state.log):
            if entry["Coordinate"] == coord:
                st.session_state.log[i] = {
                    "Coordinate": coord,
                    "Description": sample_description,
                    "Timestamp": datetime.now().isoformat(timespec="seconds"),
                }
                updated = True
                break
        
        if updated:
            st.success(f"Updated {coord}")
            st.rerun()
        else:
            st.warning(f"Coordinate {coord} not found in inventory.")

# --------------------------------------------------
# 6. Display current table
# --------------------------------------------------
if st.session_state.log:
    df = pd.DataFrame(st.session_state.log)
    # Sort by coordinate for better organization
    df = df.sort_values('Coordinate').reset_index(drop=True)
    
    st.subheader(f"Current inventory ({len(df)} items)")
    st.dataframe(df, use_container_width=True)

    # Download CSV
    csv = df[["Coordinate", "Description"]].to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV", 
        csv, 
        "freezer_inventory.csv", 
        "text/csv"
    )

    # Also provide full data with timestamps
    csv_full = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV (with timestamps)", 
        csv_full, 
        "freezer_inventory_full.csv", 
        "text/csv"
    )

else:
    st.info("No items in inventory yet. Upload some images to get started!")

# --------------------------------------------------
# 7. Management options
# --------------------------------------------------
if st.session_state.log:
    st.subheader("Management")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Remove last entry"):
            if st.session_state.log:
                popped = st.session_state.log.pop()
                st.info(f"Removed {popped['Coordinate']} – {popped['Description'][:50]}{'...' if len(popped['Description']) > 50 else ''}")
                st.rerun()
    
    with col2:
        if st.button("Clear all entries"):
            if st.session_state.log:
                st.session_state.log.clear()
                st.info("All entries cleared")
                st.rerun()

# --------------------------------------------------
# 8. Setup instructions
# --------------------------------------------------
with st.expander("Setup Instructions"):
    st.markdown("""
    ### Required Streamlit Secrets
    
    Add these to your `.streamlit/secrets.toml` file:
    
    ```toml
    # OpenAI API Key (required)
    openai_api_key = "sk-your-openai-api-key-here"
    
    # Google Cloud Vision API - Option A: Service Account JSON
    [gcp_service_account]
    type = "service_account"
    project_id = "your-project-id"
    private_key_id = "your-private-key-id"
    private_key = "-----BEGIN PRIVATE KEY-----\\nYour private key here\\n-----END PRIVATE KEY-----\\n"
    client_email = "your-service-account@your-project.iam.gserviceaccount.com"
    client_id = "your-client-id"
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    
    # OR Option B: Simple API Key
    [gcp]
    api_key = "your-google-cloud-api-key"
    ```
    
    ### Features:
    - Upload 1-2 images per vial
    - OCR extracts text from all images
    - OpenAI processes OCR results into coherent descriptions
    - Simple coordinate-based organization
    - Export to CSV format
    - Update existing entries
    """)