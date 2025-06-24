# ------------------------------------------------------------------
# Google Video Intelligence client - works locally *and* on Streamlit Cloud
# ------------------------------------------------------------------
import streamlit as st
from google.cloud import videointelligence
from google.oauth2 import service_account
import requests
import base64
import tempfile
import os

@st.cache_resource
def get_video_client():
    # ---- Option A: full service-account JSON in st.secrets ----------
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return videointelligence.VideoIntelligenceServiceClient(credentials=creds)

    # ---- Option B: plain API key in st.secrets ----------------------
    if "gcp" in st.secrets and "api_key" in st.secrets["gcp"]:
        class VideoIntelligenceViaREST:
            """Wrapper that uses Video Intelligence API via REST with API key"""
            def annotate_video(self, request):
                # Convert video content to base64
                video_content = base64.b64encode(request.input_content).decode()
                
                body = {
                    "input_content": video_content,
                    "features": ["TEXT_DETECTION"]
                }
                
                url = (f"https://videointelligence.googleapis.com/v1/videos:annotate"
                       f"?key={st.secrets['gcp']['api_key']}")
                
                r = requests.post(url, json=body, timeout=60)
                r.raise_for_status()
                return r.json()
        return VideoIntelligenceViaREST()

    # ---- Fallback: default application creds (local dev) -----------
    return videointelligence.VideoIntelligenceServiceClient()

client = get_video_client()

# --------------------------------------------------
# Simple UI layout
# --------------------------------------------------
st.title("Video OCR with Google Cloud Video Intelligence")

st.markdown(
    "1. Upload a video file\n"
    "2. Click **Process Video** to extract text\n"
    "3. View the OCR results"
)

# Video uploader
uploaded_file = st.file_uploader(
    "Upload a video file",
    type=["mp4", "mov", "avi", "mkv", "webm"],
    accept_multiple_files=False,
)

# --------------------------------------------------
# Video OCR routine
# --------------------------------------------------
def process_video_ocr(video_bytes: bytes) -> str:
    """Extract text from video using Google Cloud Video Intelligence API."""
    try:
        # Create the request
        request = videointelligence.AnnotateVideoRequest(
            input_content=video_bytes,
            features=[videointelligence.Feature.TEXT_DETECTION],
        )
        
        # Make the request
        operation = client.annotate_video(request=request)
        
        # Wait for the operation to complete
        st.info("Processing video... This may take a few minutes.")
        result = operation.result(timeout=300)  # 5 minute timeout
        
        # Extract text annotations
        text_annotations = result.annotation_results[0].text_annotations
        
        if not text_annotations:
            return "No text detected in the video."
        
        # Collect all detected text
        detected_texts = []
        for text_annotation in text_annotations:
            text = text_annotation.text
            detected_texts.append(text)
        
        # Return concatenated text
        return "\n".join(detected_texts)
        
    except Exception as e:
        st.error(f"Error processing video: {str(e)}")
        return ""

def process_video_ocr_rest(video_bytes: bytes) -> str:
    """Extract text from video using REST API with API key."""
    try:
        # Convert video content to base64
        video_content = base64.b64encode(video_bytes).decode()
        
        body = {
            "input_content": video_content,
            "features": ["TEXT_DETECTION"]
        }
        
        url = (f"https://videointelligence.googleapis.com/v1/videos:annotate"
               f"?key={st.secrets['gcp']['api_key']}")
        
        st.info("Processing video... This may take a few minutes.")
        r = requests.post(url, json=body, timeout=300)
        r.raise_for_status()
        
        response = r.json()
        
        # Check if operation is complete or get operation name for polling
        if "name" in response:
            # Poll for completion
            operation_name = response["name"]
            operation_url = f"https://videointelligence.googleapis.com/v1/{operation_name}?key={st.secrets['gcp']['api_key']}"
            
            while True:
                op_response = requests.get(operation_url, timeout=30)
                op_response.raise_for_status()
                op_data = op_response.json()
                
                if op_data.get("done", False):
                    if "error" in op_data:
                        return f"Error: {op_data['error']}"
                    
                    # Extract text from response
                    annotation_results = op_data.get("response", {}).get("annotationResults", [])
                    if not annotation_results:
                        return "No text detected in the video."
                    
                    text_annotations = annotation_results[0].get("textAnnotations", [])
                    if not text_annotations:
                        return "No text detected in the video."
                    
                    detected_texts = [annotation.get("text", "") for annotation in text_annotations]
                    return "\n".join(detected_texts)
                
                # Wait before polling again
                st.info("Still processing...")
                time.sleep(5)
        
        return "Unexpected response format."
        
    except Exception as e:
        st.error(f"Error processing video: {str(e)}")
        return ""

# --------------------------------------------------
# Process video when uploaded
# --------------------------------------------------
if uploaded_file is not None:
    if st.button("Process Video"):
        video_bytes = uploaded_file.getvalue()
        
        with st.spinner("Processing video with OCR..."):
            if hasattr(client, 'annotate_video'):
                # Using the official client
                detected_text = process_video_ocr(video_bytes)
            else:
                # Using REST API wrapper
                detected_text = process_video_ocr_rest(video_bytes)
        
        st.subheader("OCR Results:")
        if detected_text:
            st.text_area("Detected Text:", value=detected_text, height=200)
            
            # Option to download the results
            st.download_button(
                "Download OCR Results",
                detected_text,
                file_name="video_ocr_results.txt",
                mime="text/plain"
            )
        else:
            st.warning("No text was detected in the video.")

# --------------------------------------------------
# Usage notes
# --------------------------------------------------
st.subheader("Notes:")
st.markdown("""
- Video processing can take several minutes depending on video length
- Supported formats: MP4, MOV, AVI, MKV, WebM
- The API works best with clear, readable text in the video
- For freezer inventory, try to keep the camera steady and focus on labels
""")