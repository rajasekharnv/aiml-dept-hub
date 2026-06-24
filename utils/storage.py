import firebase_admin  # type: ignore
from firebase_admin import storage  # type: ignore
import streamlit as st
import os
import re
from datetime import datetime
from urllib.parse import urlparse, unquote

# Global bucket placeholder
_storage_bucket = None

def get_storage_bucket():
    """
    Initializes the Firebase App and returns the Firebase Storage bucket.
    Handles errors gracefully with st.error().
    """
    global _storage_bucket
    if _storage_bucket is not None:
        return _storage_bucket

    try:
        # Check if Firebase is already initialized
        firebase_admin.get_app()
    except ValueError:
        # Use our DB utility to initialize it from secrets
        from utils.db import get_db_client
        if get_db_client() is None:
            st.error("Failed to initialize Firebase app in DB utility.")
            return None

    try:
        if "FIREBASE_STORAGE_BUCKET" not in st.secrets:
            st.error("Missing FIREBASE_STORAGE_BUCKET in Streamlit secrets.")
            return None

        bucket_name = st.secrets["FIREBASE_STORAGE_BUCKET"]
        if not bucket_name:
            st.error("FIREBASE_STORAGE_BUCKET secret is empty.")
            return None

        _storage_bucket = storage.bucket(name=bucket_name)
        return _storage_bucket
    except Exception as e:
        st.error(f"Failed to retrieve Firebase Storage bucket: {e}")
        return None

def upload_file(file_bytes: bytes, filename: str, folder: str, content_type: str) -> str:
    """
    Uploads file bytes to the Firebase Storage bucket.
    Folder structure: uploads/{collection}/{year}/{month}/{filename}
    Returns the public download URL.
    """
    bucket = get_storage_bucket()
    if bucket is None:
        raise RuntimeError("Firebase Storage bucket is not initialized.")

    now = datetime.now()
    blob_path = f"uploads/{folder}/{now.year}/{now.month:02d}/{filename}"

    try:
        blob = bucket.blob(blob_path)
        blob.upload_from_string(file_bytes, content_type=content_type)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        st.error(f"Failed to upload file to storage: {e}")
        raise

def delete_file(file_url: str):
    """
    Deletes the file corresponding to the public URL from Firebase Storage.
    """
    bucket = get_storage_bucket()
    if bucket is None:
        raise RuntimeError("Firebase Storage bucket is not initialized.")

    try:
        parsed = urlparse(file_url)
        path = parsed.path
        
        # Check if it is a Firebase Storage API url
        if "firebasestorage.googleapis.com" in parsed.netloc:
            # Format: /v0/b/{bucket}/o/{blob_name}
            parts = path.split('/o/')
            if len(parts) > 1:
                blob_name = unquote(parts[1].split('?')[0])
            else:
                blob_name = unquote(path)
        else:
            # Format: https://storage.googleapis.com/{bucket}/{blob_name}
            blob_name = path.lstrip('/')
            bucket_name = bucket.name
            if blob_name.startswith(bucket_name + '/'):
                blob_name = blob_name[len(bucket_name) + 1:]
                
        blob = bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
        else:
            st.warning(f"File not found in storage: {blob_name}")
    except Exception as e:
        st.error(f"Failed to delete file from storage: {e}")
        raise

def generate_safe_filename(original_name: str, reference_id: str) -> str:
    """
    Sanitizes the original filename and prepends the reference_id.
    Format: {reference_id}_{sanitized_original_name}
    """
    base, ext = os.path.splitext(original_name)
    # Sanitize base filename: only letters, numbers, hyphens, and underscores
    sanitized_base = re.sub(r'[^a-zA-Z0-9\-_]', '_', base)
    # Remove duplicate underscores
    sanitized_base = re.sub(r'_+', '_', sanitized_base).strip('_')
    if not sanitized_base:
        sanitized_base = "file"
        
    return f"{reference_id}_{sanitized_base}{ext.lower()}"

def validate_file(file_obj) -> dict:
    """
    Validates a file object (e.g. Streamlit UploadedFile).
    Checks type (pdf, jpg, jpeg, png) using file header magic bytes and size (max 5MB).
    Returns {"valid": bool, "error": str}
    """
    # 1. Check size (max 5MB = 5 * 1024 * 1024 bytes)
    max_size = 5 * 1024 * 1024
    
    try:
        # Get file size
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(0)  # Reset pointer
        
        if size > max_size:
            return {"valid": False, "error": "File size exceeds the maximum limit of 5MB."}
            
        # 2. Check extension
        _, ext = os.path.splitext(file_obj.name.lower())
        allowed_exts = [".pdf", ".jpg", ".jpeg", ".png"]
        if ext not in allowed_exts:
            return {"valid": False, "error": f"Invalid file extension: {ext}. Only PDF, JPG, JPEG, and PNG are allowed."}
            
        # 3. Read first 8 bytes for signature check
        header = file_obj.read(8)
        file_obj.seek(0)  # Reset pointer
        
        # Detect type from header bytes
        detected_type = None
        if header.startswith(b'%PDF'):
            detected_type = "pdf"
        elif header.startswith(b'\xff\xd8\xff'):
            detected_type = "jpg"
        elif header.startswith(b'\x89PNG\r\n\x1a\n'):
            detected_type = "png"
            
        if detected_type is None:
            return {"valid": False, "error": "Invalid file type: File header does not match any allowed format (PDF, JPG, PNG)."}
            
        # 4. Cross-check extension against detected type
        if ext == ".pdf" and detected_type != "pdf":
            return {"valid": False, "error": "File content does not match the .pdf extension."}
        if ext in [".jpg", ".jpeg"] and detected_type != "jpg":
            return {"valid": False, "error": f"File content does not match the {ext} extension."}
        if ext == ".png" and detected_type != "png":
            return {"valid": False, "error": "File content does not match the .png extension."}
            
        return {"valid": True, "error": ""}
    except Exception as e:
        return {"valid": False, "error": f"Error validating file: {str(e)}"}

def secure_upload(uploaded_file, reference_id: str, collection_name: str) -> dict:
    """
    Hardened file upload handling using header magic bytes:
    1. Check filename for path traversal (reject if contains "..", "/", "\", "%")
    2. Call validate_file(uploaded_file)
    3. Scan first 512 bytes for embedded JavaScript in PDFs
    4. Upload to Firebase Storage and return metadata
    """
    try:
        # 1. Filename path traversal checks
        filename = uploaded_file.name
        if ".." in filename or "/" in filename or "\\" in filename or "%" in filename:
            return {"success": False, "url": "", "safe_filename": "", "file_size_kb": 0.0, "error": "Path traversal attempt detected in filename."}
            
        # 2. Call validate_file
        val = validate_file(uploaded_file)
        if not val["valid"]:
            return {"success": False, "url": "", "safe_filename": "", "file_size_kb": 0.0, "error": val["error"]}
            
        # 3. Get file bytes & size
        file_bytes = uploaded_file.getvalue()
        file_size_kb = round(len(file_bytes) / 1024.0, 2)
        
        # 4. Scan first 512 bytes for malware / scripts
        header = file_bytes[:512]
        _, ext = os.path.splitext(filename.lower())
        
        # Check PDF JS script
        if ext == ".pdf":
            if b'/JS' in header or b'/JavaScript' in header:
                return {"success": False, "url": "", "safe_filename": "", "file_size_kb": 0.0, "error": "Malware signature detected: Embedded JavaScript in PDF."}
                
        # Determine MIME type
        mime_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png"
        }
        mime = mime_map.get(ext, "application/octet-stream")
        
        # 5. Generate safe filename and upload
        safe_filename = generate_safe_filename(filename, reference_id)
        url = upload_file(file_bytes, safe_filename, collection_name, mime)
        
        return {
            "success": True,
            "url": url,
            "safe_filename": safe_filename,
            "file_size_kb": file_size_kb,
            "error": ""
        }
    except Exception as e:
        return {"success": False, "url": "", "safe_filename": "", "file_size_kb": 0.0, "error": f"Failed during secure upload process: {str(e)}"}

def check_uploaded_file_ui(uploaded_file) -> dict:
    """
    Runs security and validations on the file to show correctness in UI.
    """
    if uploaded_file is None:
        return {"valid": False, "error": ""}
        
    filename = uploaded_file.name
    if ".." in filename or "/" in filename or "\\" in filename or "%" in filename:
        return {"valid": False, "error": "Path traversal attempt detected in filename."}
        
    val = validate_file(uploaded_file)
    if not val["valid"]:
        return val
        
    try:
        file_bytes = uploaded_file.getvalue()
        header = file_bytes[:512]
        _, ext = os.path.splitext(filename.lower())
        if ext == ".pdf":
            if b'/JS' in header or b'/JavaScript' in header:
                return {"valid": False, "error": "Malware signature detected: Embedded JavaScript in PDF."}
    except Exception as e:
        return {"valid": False, "error": f"Error inspecting file: {str(e)}"}
        
    return {"valid": True, "error": ""}

