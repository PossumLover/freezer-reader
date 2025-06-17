# ------------------------------------------------------------------
# Google Vision client - works locally *and* on Streamlit Cloud
# ------------------------------------------------------------------
import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
from datetime import datetime
import requests, base64

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

client = get_vision_client()

# --------------------------------------------------
# 1. Session-state helpers
# --------------------------------------------------
if "log" not in st.session_state:
    st.session_state.log = []        # list of dicts: {"coord": "A1", "name": "...", "ts": ...}

# --------------------------------------------------
# 2. Simple UI layout
# --------------------------------------------------
st.title("−80 °C Freezer Inventory Helper")

st.markdown(
    "1. Select the box coordinate (row + column)\n"
    "2. Upload 1–2 photos of the vial/flask label\n"
    "3. Review / edit the recognised text\n"
    "4. Click **Add to table**\n"
    "5. When finished, download the CSV / Excel file"
)

# Coordinate selector
rows   = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")[:10]       # A … J by default
cols   = [str(i) for i in range(1, 11)]               # 1 … 10
row    = st.selectbox("Row", rows, key="row")
col    = st.selectbox("Column", cols, key="col")
coord  = f"{row}{col}"

# Image uploader
uploaded_files = st.file_uploader(
    "Upload 1–2 images of the same vial (hand-written text on curved surface)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

# --------------------------------------------------
# 3. OCR routine
# --------------------------------------------------
def ocr_bytes(image_bytes: bytes) -> str:
    """Return the full text detected in an image."""
    g_image   = vision.Image(content=image_bytes)
    response  = client.text_detection(image=g_image)
    if response.error.message:
        st.error(f"Google Vision error: {response.error.message}")
        return ""
    texts = response.text_annotations
    return texts[0].description.strip() if texts else ""

def run_ocr(files) -> str:
    """Concatenate OCR output from 1–2 images."""
    pieces = []
    for f in files:
        pieces.append(ocr_bytes(f.getvalue()))
    # Deduplicate newlines and extra whitespace
    final = " ".join([p.replace("\n", " ") for p in pieces]).strip()
    return " ".join(final.split())

# --------------------------------------------------
# 4. When images are uploaded, trigger OCR
# --------------------------------------------------
detected_text = ""
if uploaded_files:
    with st.spinner("Running OCR…"):
        detected_text = run_ocr(uploaded_files)
    st.success("OCR complete")

# Show editable text box
sample_name = st.text_input("Recognised text (edit if needed)", value=detected_text)

# --------------------------------------------------
# 5. Add to in-memory table
# --------------------------------------------------
if st.button("Add to table"):
    if not sample_name:
        st.warning("No text detected / entered.")
    else:
        st.session_state.log.append(
            {
                "Coordinate": coord,
                "SampleName": sample_name,
                "Timestamp": datetime.now().isoformat(timespec="seconds"),
            }
        )
        st.success(f"Added {coord} → {sample_name}")
        # Clear uploader & textbox for next entry
        uploaded_files.clear()
        st.experimental_rerun()

# --------------------------------------------------
# 6. Display current table
# --------------------------------------------------
if st.session_state.log:
    df = pd.DataFrame(st.session_state.log)
    st.subheader("Current inventory")
    st.dataframe(df, use_container_width=True)

    # Download buttons
    csv  = df.to_csv(index=False).encode("utf-8")
    xlsx = df.to_excel(io.BytesIO(), index=False, sheet_name="Inventory")  # returns None
    xlsx_bytes = io.BytesIO()
    with pd.ExcelWriter(xlsx_bytes, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Inventory")
    st.download_button("⬇️ Download CSV",  csv,  "freezer_inventory.csv",  "text/csv")
    st.download_button("⬇️ Download Excel", xlsx_bytes.getvalue(), "freezer_inventory.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --------------------------------------------------
# 7. Optional: clear / undo
# --------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    if st.button("Undo last entry") and st.session_state.log:
        popped = st.session_state.log.pop()
        st.info(f"Removed {popped['Coordinate']} – {popped['SampleName']}")
with col2:
    if st.button("Clear all") and st.session_state.log:
        st.session_state.log.clear()
        st.info("Table cleared")
