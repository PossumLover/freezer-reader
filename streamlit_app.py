import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
import requests
import base64
import cv2
import tempfile
import os

@st.cache_resource
def get_vision_client():
    # ---- Option A: full service-account JSON in st.secrets ----------
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return vision.ImageAnnotatorClient(credentials=creds)

    # ---- Option B: plain API key in st.secrets ----------------------
    if "gcp" in st.secrets and "api_key" in st.secrets["gcp"]:
        class VisionViaREST:
            """Tiny wrapper that mimics .text_detection() using API-key REST"""
            def text_detection(self, image):
                img_content = base64.b64encode(image.content).decode()
                body = {"requests": [
                    {"image": {"content": img_content},
                     "features": [{"type": "TEXT_DETECTION"}]}]}
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
# OCR functions
# --------------------------------------------------
def ocr_frame(frame_bytes: bytes) -> str:
    """Return the full text detected in a frame."""
    g_image = vision.Image(content=frame_bytes)
    response = client.text_detection(image=g_image)
    if hasattr(response, 'error') and response.error.message:
        st.error(f"Google Vision error: {response.error.message}")
        return ""
    texts = response.text_annotations
    return texts[0].description.strip() if texts else ""

def extract_frames_and_ocr(video_file, frame_interval=30):
    """Extract frames from video and run OCR on each frame."""
    # Save uploaded video to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
        tmp_file.write(video_file.getvalue())
        tmp_path = tmp_file.name
    
    try:
        # Open video with OpenCV
        cap = cv2.VideoCapture(tmp_path)
        
        if not cap.isOpened():
            st.error("Could not open video file")
            return []
        
        frame_count = 0
        ocr_results = []
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process every nth frame
            if frame_count % frame_interval == 0:
                # Convert frame to bytes
                _, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                
                # Run OCR on frame
                text = ocr_frame(frame_bytes)
                if text.strip():  # Only add non-empty results
                    ocr_results.append({
                        'frame': frame_count,
                        'text': text
                    })
            
            frame_count += 1
        
        cap.release()
        return ocr_results
    
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# --------------------------------------------------
# Simple UI
# --------------------------------------------------
st.title("Video OCR")
st.write("Upload a video file to extract text from frames")

# Video uploader
uploaded_video = st.file_uploader(
    "Choose a video file",
    type=['mp4', 'avi', 'mov', 'mkv']
)

# Frame interval selector
frame_interval = st.slider(
    "Process every Nth frame (higher = faster, lower = more thorough)",
    min_value=1,
    max_value=60,
    value=30
)

# Process video
if uploaded_video is not None:
    if st.button("Extract Text from Video"):
        with st.spinner("Processing video..."):
            results = extract_frames_and_ocr(uploaded_video, frame_interval)
        
        if results:
            st.success(f"Found text in {len(results)} frames")
            
            # Display all OCR results
            for i, result in enumerate(results):
                st.write(f"**Frame {result['frame']}:**")
                st.write(result['text'])
                st.write("---")
                
            # Combined output
            st.subheader("All Text Combined:")
            all_text = "\n\n".join([result['text'] for result in results])
            st.text_area("Combined OCR Output", all_text, height=200)
            
        else:
            st.warning("No text found in video frames")