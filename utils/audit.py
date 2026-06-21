import streamlit as st
from datetime import datetime
from utils.db import save_record, AUDIT_LOG

def log_event(event_type: str, username: str, role: str, details: str):
    """
    Saves an audit event to the Firestore 'audit_log' collection.
    
    Fields saved:
    - timestamp (datetime)
    - event_type (str)
    - username (str)
    - role (str)
    - details (str)
    - session_id (str, from session_state)
    """
    session_id = st.session_state.get("session_id", "no_session")
    
    event_data = {
        "timestamp": datetime.now(),
        "event_type": event_type,
        "username": username,
        "role": role,
        "details": details,
        "session_id": session_id
    }
    
    try:
        save_record(AUDIT_LOG, event_data)
    except Exception as e:
        # Fallback console log if firestore fails
        import logging
        logging.getLogger("audit").error(
            f"Firestore Audit Log Error: {e}. Event: {event_data}"
        )
