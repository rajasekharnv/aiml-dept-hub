import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import json
from datetime import datetime

# Define COLLECTION constants
FACULTY_FDP = "faculty_fdp"
FACULTY_PUBLICATIONS = "faculty_publications"
FACULTY_WORKSHOPS = "faculty_workshops"
STUDENT_HACKATHONS = "student_hackathons"
STUDENT_COMPETITIONS = "student_competitions"
STUDENT_CERTIFICATIONS = "student_certifications"
AUDIT_LOG = "audit_log"

# Global firestore client placeholder
_db_client = None

def get_db_client():
    """
    Initializes the Firebase App and returns the Firestore client.
    Handles errors gracefully with st.error().
    """
    global _db_client
    if _db_client is not None:
        return _db_client
        
    try:
        # Check if Firebase is already initialized
        firebase_admin.get_app()
    except ValueError:
        # Initialize Firebase App
        try:
            # 1. Check st.secrets for credentials
            if "FIREBASE_CREDENTIALS_JSON" not in st.secrets:
                st.error("Missing FIREBASE_CREDENTIALS_JSON in Streamlit secrets.")
                return None
                
            cred_str = st.secrets["FIREBASE_CREDENTIALS_JSON"]
            if not cred_str:
                st.error("FIREBASE_CREDENTIALS_JSON secret is empty.")
                return None
                
            # Parse the JSON string into a dict
            try:
                cred_dict = json.loads(cred_str)
            except Exception as parse_err:
                st.error(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {parse_err}")
                return None
                
            # Initialize with Certificate
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            
        except Exception as init_err:
            st.error(f"Failed to initialize Firebase App: {init_err}")
            return None
            
    # 2. Get Firestore client
    try:
        _db_client = firestore.client()
        return _db_client
    except Exception as client_err:
        st.error(f"Failed to get Firestore client: {client_err}")
        return None

def save_record(collection: str, data_dict: dict) -> str:
    """
    Adds a document to the specified collection.
    Returns the auto-generated doc_id.
    """
    db = get_db_client()
    if db is None:
        raise RuntimeError("Database client is not initialized.")
        
    # Ensure deleted_at is not in a new record or is None
    record = data_dict.copy()
    if "deleted_at" not in record:
        record["deleted_at"] = None
    record["created_at"] = datetime.now()
    
    doc_ref = db.collection(collection).document()
    doc_ref.set(record)
    return doc_ref.id

def get_all_records(collection: str) -> list[dict]:
    """
    Returns all non-deleted documents in the collection, with doc_id included.
    Filters out any records that have a soft-delete timestamp.
    """
    db = get_db_client()
    if db is None:
        return []
        
    try:
        docs = db.collection(collection).stream()
        records = []
        for doc in docs:
            data = doc.to_dict()
            # Filter out soft-deleted records locally to avoid Firestore index requirements
            if data.get("deleted_at") is None:
                data["doc_id"] = doc.id
                records.append(data)
        return records
    except Exception as e:
        st.error(f"Error fetching records from {collection}: {e}")
        return []

def get_records_by_field(collection: str, field: str, value) -> list[dict]:
    """
    Returns filtered documents in the collection matching field == value,
    excluding soft-deleted ones.
    """
    db = get_db_client()
    if db is None:
        return []
        
    try:
        # Perform query filter on the field
        docs = db.collection(collection).where(field, "==", value).stream()
        records = []
        for doc in docs:
            data = doc.to_dict()
            if data.get("deleted_at") is None:
                data["doc_id"] = doc.id
                records.append(data)
        return records
    except Exception as e:
        st.error(f"Error filtering records in {collection} by {field}: {e}")
        return []

def check_duplicate(collection: str, field: str, value) -> bool:
    """
    Checks if a non-soft-deleted document already exists with field == value.
    Returns True if exists, False otherwise.
    """
    records = get_records_by_field(collection, field, value)
    return len(records) > 0

def get_count(collection: str) -> int:
    """
    Returns the count of non-soft-deleted documents in the collection.
    """
    records = get_all_records(collection)
    return len(records)

def delete_record(collection: str, doc_id: str):
    """
    Performs a soft delete by setting the deleted_at field to the current timestamp.
    """
    db = get_db_client()
    if db is None:
        raise RuntimeError("Database client is not initialized.")
        
    doc_ref = db.collection(collection).document(doc_id)
    doc_ref.update({
        "deleted_at": datetime.now()
    })

def update_record(collection: str, doc_id: str, updates: dict):
    """
    Performs a partial update of a document.
    """
    db = get_db_client()
    if db is None:
        raise RuntimeError("Database client is not initialized.")
        
    doc_ref = db.collection(collection).document(doc_id)
    updates["updated_at"] = datetime.now()
    doc_ref.update(updates)

def generate_reference_id(entry_type: str) -> str:
    """
    Generates a unique reference ID.
    Format: AIML-{TYPE}-{YYYYMMDD}-{4random}
    """
    import random
    import string
    
    et_clean = entry_type.strip().lower()
    abbrev = "GEN"
    if "fdp" in et_clean:
        abbrev = "FDP"
    elif "publication" in et_clean or "pub" in et_clean:
        abbrev = "PUB"
    elif "workshop" in et_clean or "work" in et_clean:
        abbrev = "WKS"
    elif "hackathon" in et_clean or "hack" in et_clean:
        abbrev = "HAC"
    elif "competition" in et_clean or "comp" in et_clean:
        abbrev = "CMP"
    elif "certification" in et_clean or "cert" in et_clean:
        abbrev = "CRT"
        
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    
    return f"AIML-{abbrev}-{date_str}-{random_str}"

def save_entry(collection: str, data: dict) -> dict:
    """
    Saves an entry to the database, appending created_at and reference_id.
    Returns: {success: bool, doc_id: str, reference_id: str}
    """
    try:
        record = data.copy()
        if "reference_id" not in record or not record["reference_id"]:
            record["reference_id"] = generate_reference_id(collection)
            
        ref_id = record["reference_id"]
        doc_id = save_record(collection, record)
        
        return {
            "success": True,
            "doc_id": doc_id,
            "reference_id": ref_id
        }
    except Exception as e:
        st.error(f"Error saving entry to {collection}: {e}")
        return {
            "success": False,
            "doc_id": "",
            "reference_id": ""
        }


