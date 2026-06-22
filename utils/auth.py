import streamlit as st
import bcrypt
from datetime import datetime
from utils.audit import log_event

# 1. Credential store setup
DEFAULT_PASSWORD = "AIML@2024"
# Pre-hash the default password at startup/module load time to prevent runtime lags
DEFAULT_PASSWORD_HASH = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def get_display_name(username: str) -> str:
    """
    Helper function to get formatted display name from username.
    """
    if not username:
        return "User Info"
    u = username.strip().lower()
    if u == "hod_aiml":
        return "Head of Department"
    elif u.startswith("fac_"):
        return "Faculty " + u.replace("fac_", "").replace("_", " ").title()
    elif u.startswith("stu_"):
        return "Student " + u.replace("stu_", "").replace("_", " ").title()
    return "User Info"


def authenticate_user(username: str, password_raw: str) -> dict | None:
    """
    Checks the username and password against the demo credential rules.
    Returns a dictionary of user details on success, or None on failure.
    """
    if not username or not password_raw:
        return None
        
    username_clean = username.strip().lower()
    role = None
    display_name = ""
    
    if username_clean == "hod_aiml":
        role = "HoD"
        display_name = "Head of Department"
    elif username_clean.startswith("fac_"):
        role = "Faculty"
        # Extract display name suffix
        suffix = username_clean[4:].replace("_", " ").title()
        display_name = f"Faculty {suffix}" if suffix else "Faculty Member"
    elif username_clean.startswith("stu_"):
        role = "Student"
        # Extract display name suffix
        suffix = username_clean[4:].replace("_", " ").title()
        display_name = f"Student {suffix}" if suffix else "Student User"
        
    if role is not None:
        # Check password using bcrypt
        password_bytes = password_raw.encode('utf-8')
        hash_bytes = DEFAULT_PASSWORD_HASH.encode('utf-8')
        if bcrypt.checkpw(password_bytes, hash_bytes):
            return {
                "username": username_clean,
                "role": role,
                "display_name": display_name
            }
            
    return None

def login_page():
    """
    Renders a centered card layout login page with logo and credentials fields.
    """
    st.markdown("""
        <div style='text-align: center; margin-top: 1rem;'>
            <span style='font-size: 4.5rem; filter: drop-shadow(0 4px 10px rgba(79,70,229,0.15));'>🎓</span>
            <h2 style='margin-top: 0.5rem; font-weight: 800; color: #0f172a;'>AIML Intelligence Hub</h2>
            <p style='color: #475569; font-size: 0.95rem; margin-bottom: 2rem;'>Department of Artificial Intelligence & Machine Learning</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Check if there is an inactivity timeout or logout message to show
        if "auth_message" in st.session_state:
            st.warning(st.session_state["auth_message"])
            # Remove it so it doesn't persist forever
            del st.session_state["auth_message"]

        st.markdown("<div style='background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 2rem; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.05);'>", unsafe_allow_html=True)
        st.write("### Sign In")
        
        login_user = st.text_input("Username", placeholder="e.g. hod_aiml, fac_smith, stu_roberts")
        login_pass = st.text_input("Password", type="password", placeholder="Password")
        
        if st.button("Access Hub", use_container_width=True, type="primary"):
            user_info = authenticate_user(login_user, login_pass)
            if user_info:
                st.session_state["authenticated"] = True
                st.session_state["role"] = user_info["role"]
                st.session_state["username"] = user_info["username"]
                st.session_state["user_display_name"] = user_info["display_name"]
                st.session_state["login_time"] = datetime.now()
                st.session_state["last_active"] = datetime.now()
                
                # Persist session in query parameters
                st.query_params["user"] = user_info["username"]
                st.query_params["role"] = user_info["role"]
                
                log_event("LOGIN_SUCCESS", user_info["username"], user_info["role"], f"Successful login as {user_info['role']}")
                st.success("Login successful! Loading dashboard...")
                st.rerun()
            else:
                st.error("Invalid username or password.")
                log_event("LOGIN_FAILED", login_user or "unknown", "Guest", "Invalid credentials provided")
                
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Info box explaining credential formats
        st.markdown("""
            <div style='margin-top: 1.5rem; font-size: 0.85rem; color: #475569; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.2rem;'>
                <strong style="color: #0f172a;">🔑 Demo Credentials (Password: <code style="background:#e2e8f0; color:#0f172a; padding:2px 4px; border-radius:4px;">AIML@2024</code>)</strong><br>
                <div style="margin-top: 8px; line-height: 1.5;">
                    • HoD: <code style="background:#e2e8f0; color:#0f172a; padding:2px 4px; border-radius:4px;">hod_aiml</code><br>
                    • Faculty: usernames starting with <code style="background:#e2e8f0; color:#0f172a; padding:2px 4px; border-radius:4px;">fac_</code> (e.g. <code style="background:#e2e8f0; color:#0f172a; padding:2px 4px; border-radius:4px;">fac_john</code>)<br>
                    • Student: usernames starting with <code style="background:#e2e8f0; color:#0f172a; padding:2px 4px; border-radius:4px;">stu_</code> (e.g. <code style="background:#e2e8f0; color:#0f172a; padding:2px 4px; border-radius:4px;">stu_grace</code>)
                </div>
            </div>
        """, unsafe_allow_html=True)

def logout(message: str = None):
    """
    Clears all session state keys, sets an optional message, and reruns the app.
    """
    # Capture message to show after rerun if necessary
    for key in list(st.session_state.keys()):
        del st.session_state[key]
        
    st.query_params.clear()
        
    if message:
        st.session_state["auth_message"] = message
        
    st.rerun()

def require_auth(allowed_roles: list[str] = None):
    """
    Protects pages and dashboard views. Checks authentication, inactivity, and role access.
    Stops page execution if checks fail.
    """
    # Restore session from query parameters if missing but present in URL
    if not st.session_state.get("authenticated", False):
        if "user" in st.query_params and "role" in st.query_params:
            st.session_state["authenticated"] = True
            st.session_state["role"] = st.query_params["role"]
            st.session_state["username"] = st.query_params["user"]
            st.session_state["user_display_name"] = get_display_name(st.query_params["user"])
            st.session_state["login_time"] = datetime.now()
            st.session_state["last_active"] = datetime.now()

    # 1. Check if authenticated
    if not st.session_state.get("authenticated", False):
        login_page()
        st.stop()
        
    # 2. Check inactivity timeout (45 minutes = 2700 seconds)
    last_active = st.session_state.get("last_active")
    if last_active is not None:
        elapsed = (datetime.now() - last_active).total_seconds()
        if elapsed > 45 * 60:
            log_event(
                "SESSION_TIMEOUT",
                st.session_state.get("username", "unknown"),
                st.session_state.get("role", "Guest"),
                "Session timed out due to 45 minutes of inactivity"
            )
            logout(message="Session expired due to inactivity. Please log in again.")
            st.stop()
            
    # 3. Check role authorization
    user_role = st.session_state.get("role")
    if allowed_roles is not None and user_role not in allowed_roles:
        log_event(
            "ACCESS_DENIED",
            st.session_state.get("username", "unknown"),
            st.session_state.get("role", "Guest"),
            f"Unauthorized access attempt to resource requiring roles: {allowed_roles}"
        )
        st.markdown(f"""
            <div style='text-align: center; margin-top: 4rem;'>
                <span style='font-size: 4rem;'>🚫</span>
                <h2 style='color: #ef4444; font-weight: 800;'>Access Denied</h2>
                <p style='color: #94a3b8; font-size: 1.1rem; margin-bottom: 2rem;'>
                    You do not have authorization to view this panel.
                </p>
                <div style='background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 1.5rem; border-radius: 12px; display: inline-block; text-align: left; margin-bottom: 2rem;'>
                    <strong>Current Identity:</strong> {st.session_state.get("user_display_name")}<br>
                    <strong>Current Role:</strong> <span style='color: #a855f7;'>{user_role}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Add switch/logout options
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("Logout / Switch Account", use_container_width=True):
                logout()
        st.stop()
        
    # Update active timestamp
    st.session_state["last_active"] = datetime.now()

def show_user_info():
    """
    Renders user profile dashboard info, initials avatar, role badge, and logout in the sidebar.
    """
    st.sidebar.write("### 👤 User Profile")
    
    display_name = st.session_state.get("user_display_name", "User Info")
    role = st.session_state.get("role", "Student")
    login_time = st.session_state.get("login_time")
    
    # Initials generator for custom avatar
    parts = display_name.split()
    initials = "".join([p[0].upper() for p in parts if p])[:2] if parts else "U"
    
    # Custom circular initials avatar and badge markup
    role_color = "#38bdf8" if role == "Student" else "#a855f7" if role == "Faculty" else "#f43f5e"
    
    st.sidebar.markdown(f"""
        <div style='display: flex; align-items: center; gap: 12px; margin-bottom: 1.5rem;'>
            <div style='width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(135deg, #38bdf8 0%, #a855f7 100%); display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; font-size: 1.1rem; box-shadow: 0 4px 10px rgba(0,0,0,0.3);'>
                {initials}
            </div>
            <div>
                <div style='font-weight: 600; font-size: 0.95rem; line-height: 1.2;'>{display_name}</div>
                <div style='display: inline-block; margin-top: 4px; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: bold; background: rgba(255,255,255,0.05); border: 1px solid {role_color}; color: {role_color};'>
                    {role}
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    if login_time:
        formatted_time = login_time.strftime("%H:%M:%S")
        st.sidebar.markdown(f"""
            <div style='font-size: 0.8rem; color: #94a3b8; margin-bottom: 1.5rem;'>
                ⏱️ Session Logged in at: <strong>{formatted_time}</strong>
            </div>
        """, unsafe_allow_html=True)
        
    if st.sidebar.button("Logout 🚪", use_container_width=True, type="secondary"):
        logout()

def secrets_check() -> bool:
    """
    Verifies that all required st.secrets keys exist.
    Shows a red error box listing missing keys if any are absent.
    Returns False if any are missing.
    """
    required = [
        "GOOGLE_API_KEY",
        "FIREBASE_PROJECT_ID",
        "FIREBASE_CREDENTIALS_JSON",
        "FIREBASE_STORAGE_BUCKET"
    ]
    try:
        missing = [key for key in required if key not in st.secrets]
    except Exception:
        # If secrets.toml doesn't exist, st.secrets access raises an exception
        missing = required
        
    if missing:
        st.error(f"""
        ### 🚨 Configuration Error: Missing Secrets
        The following required keys are missing from `.streamlit/secrets.toml`:
        {', '.join([f'`{k}`' for k in missing])}
        
        Please copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in the missing keys.
        """)
        return False
    return True

