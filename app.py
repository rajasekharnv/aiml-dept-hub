import streamlit as st
import pandas as pd

# Monkeypatch pandas to_excel to automatically strip timezones from all datetime columns and index
_original_to_excel = pd.DataFrame.to_excel

def _patched_to_excel(self, *args, **kwargs):
    df_clean = self.copy()
    if isinstance(df_clean.index, pd.DatetimeIndex) and df_clean.index.tz is not None:
        df_clean.index = df_clean.index.tz_localize(None)
        
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            if hasattr(df_clean[col].dt, "tz") and df_clean[col].dt.tz is not None:
                try:
                    df_clean[col] = df_clean[col].dt.tz_localize(None)
                except Exception:
                    try:
                        df_clean[col] = df_clean[col].dt.tz_convert(None).dt.tz_localize(None)
                    except Exception:
                        pass
        else:
            def make_tz_unaware(val):
                if hasattr(val, "tzinfo") and val.tzinfo is not None:
                    try:
                        return val.replace(tzinfo=None)
                    except Exception:
                        return str(val)
                return val
            df_clean[col] = df_clean[col].apply(make_tz_unaware)
            
    return _original_to_excel(df_clean, *args, **kwargs)

pd.DataFrame.to_excel = _patched_to_excel

from datetime import datetime
import json
import os

# Import our utility modules
from utils.auth import require_auth, show_user_info, logout, secrets_check
from utils.validators import validate_email, validate_password_strength
from utils.sanitizer import sanitize_text, sanitize_input
from utils.storage import upload_file, validate_file, secure_upload, check_uploaded_file_ui
from utils.audit import log_event
from utils.prompt_guard import is_safe_prompt
from utils.export import export_to_excel, export_to_pdf, generate_pdf_report, generate_excel_report, export_my_records_excel
from agents.intake_agent import IntakeAgent
from agents.report_agent import ReportAgent

# Page configuration
st.set_page_config(
    page_title="AIML Department Intelligence Hub",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling using CSS
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    
    * {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Main App Background & Text Override */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }
    
    /* Ensure all text labels and headings have dark slate colors for high readability */
    h1, h2, h3, h4, h5, h6, p, span, li {
        color: #0f172a !important;
    }
    
    label, [data-testid="stWidgetLabel"] p, .stWidgetLabel {
        color: #334155 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }

    /* Title and header styles */
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #4f46e5 0%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
        padding-bottom: 5px;
    }
    
    .subtitle {
        font-size: 1.3rem;
        color: #64748b !important;
        font-weight: 400;
        margin-top: 0px;
        margin-bottom: 2rem;
    }
    
    /* Card design */
    .glass-card {
        background: rgba(255, 255, 255, 0.7) !important;
        border: 1px solid rgba(226, 232, 240, 0.8) !important;
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
    }
    
    .stat-number {
        font-size: 2.2rem;
        font-weight: 800;
        color: #4f46e5 !important;
        margin: 5px 0px;
    }
    
    .stat-label {
        font-size: 0.9rem;
        color: #64748b !important;
        text-transform: uppercase;
        letter-spacing: 0.1rem;
    }
    
    /* Utility badge */
    .badge {
        padding: 4px 8px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    
    .badge-primary {
        background: rgba(79, 70, 229, 0.08) !important;
        color: #4f46e5 !important;
        border: 1px solid rgba(79, 70, 229, 0.2) !important;
    }
    
    .badge-secondary {
        background: rgba(6, 182, 212, 0.08) !important;
        color: #06b6d4 !important;
        border: 1px solid rgba(6, 182, 212, 0.2) !important;
    }

    /* Streamlit Metrics Override */
    [data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.85) !important;
        border: 1px solid rgba(226, 232, 240, 0.8) !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.05) !important;
        backdrop-filter: blur(8px) !important;
        -webkit-backdrop-filter: blur(8px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    [data-testid="metric-container"]:hover {
        background: #ffffff !important;
        border-color: rgba(79, 70, 229, 0.4) !important;
        transform: translateY(-4px) !important;
        box-shadow: 0 10px 25px rgba(79, 70, 229, 0.08) !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #475569 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08rem !important;
    }

    /* Buttons Override */
    button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 10px 24px !important;
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.25) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4) !important;
        opacity: 0.95 !important;
    }
    button[kind="secondary"] {
        background: #ffffff !important;
        color: #334155 !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 12px !important;
        padding: 10px 24px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    button[kind="secondary"]:hover {
        background: #f8fafc !important;
        border: 1px solid #4f46e5 !important;
        color: #4f46e5 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
    }

    /* Form Fields & Options styling with high-visibility dark text */
    div[data-baseweb="input"], div[data-baseweb="select"], textarea {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
        transition: all 0.3s ease !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within, textarea:focus {
        border-color: #4f46e5 !important;
        box-shadow: 0 0 0 1px #4f46e5, 0 0 12px rgba(79, 70, 229, 0.15) !important;
    }
    
    /* Input/Textarea/Select text visibility */
    div[data-baseweb="input"] input, textarea, div[data-baseweb="select"] * {
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
    }
    
    /* Style the selectbox dropdown menus to be clean white popups */
    div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"], [role="listbox"] ul {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08) !important;
    }
    li[role="option"], div[role="option"], [data-baseweb="menu"] li {
        background-color: #ffffff !important;
        color: #0f172a !important;
        padding: 10px 16px !important;
        transition: all 0.2s ease !important;
    }
    li[role="option"]:hover, div[role="option"]:hover,
    li[role="option"][aria-selected="true"], div[role="option"][aria-selected="true"] {
        background-color: #f1f5f9 !important;
        color: #4f46e5 !important;
    }

    /* Tab bar override */
    button[data-baseweb="tab"] {
        color: #475569 !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
        border-bottom: 2px solid transparent !important;
        padding-bottom: 8px !important;
    }
    button[data-baseweb="tab"]:hover {
        color: #4f46e5 !important;
    }
    button[aria-selected="true"] {
        color: #4f46e5 !important;
        border-bottom: 2px solid #4f46e5 !important;
    }

    /* Sidebar Background & Border */
    [data-testid="stSidebar"] {
        background-color: #f1f5f9 !important;
        border-right: 1px solid #e2e8f0 !important;
    }
    
    /* Expander Override */
    div[data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02) !important;
        margin-bottom: 1rem !important;
        transition: border-color 0.3s ease !important;
    }
    div[data-testid="stExpander"]:hover {
        border-color: rgba(79, 70, 229, 0.3) !important;
    }
    
    /* File upload dashed container overrides for light theme */
    div[style*="dashed"] {
        border: 2px dashed rgba(79, 70, 229, 0.3) !important;
        background-color: rgba(79, 70, 229, 0.03) !important;
    }
    div[style*="dashed"] span {
        color: #4f46e5 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize Session State Variables for Mock Data
if "session_id" not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())

if "announcements" not in st.session_state:
    st.session_state.announcements = [
        {"id": 1, "title": "Grand AI Hackathon 2026", "content": "Registration open for the National AIML Innovation Hackathon. Deadline: July 15, 2026.", "posted_by": "Dr. Sarah Jenkins", "date": "2026-06-20"},
        {"id": 2, "title": "GPU Cluster Access Guidelines", "content": "New guidelines for requesting reservation slots on the H100 Node Cluster.", "posted_by": "Prof. Alan Turing", "date": "2026-06-18"}
    ]
if "requests" not in st.session_state:
    st.session_state.requests = [
        {"id": 101, "student": "Grace Hopper", "email": "student@aiml.edu", "topic": "GPU Slot Request", "description": "Need access to the GPU Cluster for training LLM embeddings.", "status": "Pending", "date": "2026-06-21"}
    ]

# Instantiate agents
intake_agent = IntakeAgent()
report_agent = ReportAgent()

def sanitize_df_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures that all datetime columns are timezone-unaware before exporting to Excel.
    """
    df_clean = df.copy()
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            try:
                df_clean[col] = df_clean[col].dt.tz_localize(None)
            except TypeError:
                try:
                    df_clean[col] = df_clean[col].dt.tz_convert(None).dt.tz_localize(None)
                except Exception:
                    pass
        else:
            def make_tz_unaware(val):
                if hasattr(val, "tzinfo") and val.tzinfo is not None:
                    try:
                        return val.replace(tzinfo=None)
                    except Exception:
                        return str(val)
                return val
            df_clean[col] = df_clean[col].apply(make_tz_unaware)
    return df_clean

# Helper to check for duplicate entry title in real-time
def check_title_duplicate(collection: str, key_state: str):
    title_value = st.session_state.get(key_state, "").strip()
    if not title_value:
        st.session_state[f"{key_state}_dup_ref"] = ""
        return
        
    from utils.db import get_records_by_field
    records = get_records_by_field(collection, "title", title_value)
    if records:
        ref_id = records[0].get("reference_id", "Unknown")
        st.session_state[f"{key_state}_dup_ref"] = ref_id
    else:
        st.session_state[f"{key_state}_dup_ref"] = ""


# --- DASHBOARD: HOD ---
# --- DASHBOARD: HOD ---
def render_hod_dashboard():
    require_auth(allowed_roles=["HoD"])
    
    # 1. Custom Premium Welcome Banner
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(79, 70, 229, 0.06) 0%, rgba(6, 182, 212, 0.06) 100%); 
                    border: 1px solid rgba(79, 70, 229, 0.12); 
                    border-radius: 16px; padding: 24px; margin-bottom: 25px; display: flex; align-items: center; justify-content: space-between;">
            <div>
                <h2 style="margin: 0px; font-weight: 800; color: #0f172a;">Welcome, {st.session_state.user_display_name} 👋</h2>
                <p style="margin: 5px 0px 0px 0px; color: #475569; font-size: 0.95rem;">
                    Role: <span style="color: #4f46e5; font-weight: bold;">Head of Department (HoD)</span> | Department of AIML
                </p>
            </div>
            <div style="font-size: 2.5rem; filter: drop-shadow(0 4px 10px rgba(79,70,229,0.15));">📊</div>
        </div>
    """, unsafe_allow_html=True)
    
    # 2. Live Metrics Section
    import utils.db as db
    from utils.db import get_all_records
    from utils.db import (FACULTY_FDP, FACULTY_PUBLICATIONS, 
        FACULTY_WORKSHOPS, STUDENT_HACKATHONS, 
        STUDENT_COMPETITIONS, STUDENT_CERTIFICATIONS)
    from utils.audit import log_event
    from utils.export import export_to_pdf, export_to_excel, generate_pdf_report, generate_excel_report, export_my_records_excel

    @st.cache_data(ttl=30)
    def get_live_counts():
        counts = {}
        collections = {
            "FDP": FACULTY_FDP,
            "Publications": FACULTY_PUBLICATIONS, 
            "Workshops": FACULTY_WORKSHOPS,
            "Hackathons": STUDENT_HACKATHONS,
            "Competitions": STUDENT_COMPETITIONS,
            "Certifications": STUDENT_CERTIFICATIONS
        }
        for label, col in collections.items():
            records = get_all_records(col)
            counts[label] = len(records)
        return counts

    counts = get_live_counts()

    # Preserve variables for visual charts and features
    fdp_count = counts.get("FDP", 0)
    pub_count = counts.get("Publications", 0)
    wks_count = counts.get("Workshops", 0)
    hack_count = counts.get("Hackathons", 0)
    comp_count = counts.get("Competitions", 0)
    cert_count = counts.get("Certifications", 0)

    # Metric header and refresh button
    metric_hdr_col, refresh_btn_col = st.columns([5, 1])
    with metric_hdr_col:
        st.markdown("### 📈 Live Department Metrics")
    with refresh_btn_col:
        if st.button("🔄 Refresh Data", key="hod_top_refresh_btn", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Show metrics in 3x2 grid
    col1, col2, col3 = st.columns(3)
    col1.metric("📚 FDPs", fdp_count)
    col2.metric("📄 Publications", pub_count)
    col3.metric("🔧 Workshops", wks_count)

    col4, col5, col6 = st.columns(3)
    col4.metric("💻 Hackathons", hack_count)
    col5.metric("🏆 Competitions", comp_count)
    col6.metric("📜 Certifications", cert_count)

    st.markdown("---")

    # 3. Global Search Section
    st.markdown("### 🔍 Global Search (Across All Collections)")
    global_search = st.text_input("Enter Faculty or Student Name to search across all databases:", key="hod_global_search_input", placeholder="Type name...")
    
    if global_search.strip():
        search_term = global_search.strip().lower()
        
        collections_map = {
            "faculty_fdp": "Faculty FDPs",
            "faculty_publications": "Research Publications",
            "faculty_workshops": "Workshops / Seminars",
            "student_hackathons": "Student Hackathons",
            "student_competitions": "Student Competitions",
            "student_certifications": "Course Certifications"
        }
        
        results = {}
        for col_key, col_label in collections_map.items():
            recs = db.get_all_records(col_key)
            matches = []
            for r in recs:
                name_val = r.get("faculty_name") or r.get("student_name") or r.get("student")
                if name_val and search_term in str(name_val).lower():
                    matches.append(r)
            if matches:
                results[col_key] = matches
                
        if results:
            st.markdown(f"Found matches across **{len(results)}** collections:")
            for col_key, matches in results.items():
                col_label = collections_map[col_key]
                st.markdown(f"**{col_label} ({len(matches)} matches)**")
                
                unique_names = list(set(
                    str(r.get("faculty_name") or r.get("student_name") or r.get("student") or "Unknown")
                    for r in matches
                ))
                
                cols = st.columns(min(len(unique_names), 4))
                for i, name in enumerate(unique_names):
                    col_idx = i % 4
                    with cols[col_idx]:
                        if st.button(f"👉 {name}", key=f"global_jump_{col_key}_{i}", use_container_width=True):
                            st.session_state["hod_selected_collection"] = col_key
                            st.session_state["hod_search_query_input"] = name
                            st.rerun()
        else:
            st.info("No matching records found across any collections.")
        st.markdown("---")

    # 4. Visual Analytics side-by-side
    st.markdown("### 📊 Visual Analytics & Trends")
    
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        with st.container(border=True):
            st.markdown("#### 📚 Faculty Activity Overview")
            faculty_activity_df = pd.DataFrame({
                "Activity Type": ["Faculty FDPs", "Research Publications", "Workshops / Seminars"],
                "Submission Count": [fdp_count, pub_count, wks_count]
            })
            st.bar_chart(faculty_activity_df, x="Activity Type", y="Submission Count")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 Refresh Faculty Chart", key="refresh_fac_chart"):
                    st.rerun()
            with c2:
                fac_excel = export_to_excel(faculty_activity_df.to_dict("records"))
                st.download_button(
                    label="📥 Download Excel",
                    data=fac_excel,
                    file_name="faculty_activity_summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_fac_chart_excel",
                    use_container_width=True,
                    on_click=lambda: log_event("EXPORT_GENERATED", st.session_state.username, st.session_state.role, "Exported Faculty Activity Chart Data")
                )
                
    with chart_col2:
        with st.container(border=True):
            st.markdown("#### 🎓 Student Participation by Semester")
            s_hack_recs = db.get_all_records("student_hackathons")
            s_comp_recs = db.get_all_records("student_competitions")
            
            semester_participation = {s: 0 for s in range(1, 9)}
            for r in s_hack_recs:
                try:
                    sem = int(r.get("semester"))
                    if 1 <= sem <= 8:
                        semester_participation[sem] += 1
                except (ValueError, TypeError):
                    pass
            for r in s_comp_recs:
                try:
                    sem = int(r.get("semester"))
                    if 1 <= sem <= 8:
                        semester_participation[sem] += 1
                except (ValueError, TypeError):
                    pass
                    
            student_sem_df = pd.DataFrame({
                "Semester": [f"Semester {s}" for s in range(1, 9)],
                "Participation Count": [semester_participation[s] for s in range(1, 9)]
            })
            st.bar_chart(student_sem_df, x="Semester", y="Participation Count")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 Refresh Semester Chart", key="refresh_sem_chart"):
                    st.rerun()
            with c2:
                sem_excel = export_to_excel(student_sem_df.to_dict("records"))
                st.download_button(
                    label="📥 Download Excel",
                    data=sem_excel,
                    file_name="student_semester_participation.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_sem_chart_excel",
                    use_container_width=True,
                    on_click=lambda: log_event("EXPORT_GENERATED", st.session_state.username, st.session_state.role, "Exported Student Semester Chart Data")
                )
                
    with st.container(border=True):
        st.markdown("#### 📈 Monthly Submission Timeline")
        months_list = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly_submission_counts = {m: 0 for m in months_list}
        
        all_cols = [
            "faculty_fdp", "faculty_publications", "faculty_workshops",
            "student_hackathons", "student_competitions", "student_certifications"
        ]
        for col in all_cols:
            recs = db.get_all_records(col)
            for r in recs:
                c_at = r.get("created_at")
                if c_at:
                    if hasattr(c_at, "month"):
                        m_idx = c_at.month - 1
                    else:
                        try:
                            dt = datetime.fromisoformat(str(c_at))
                            m_idx = dt.month - 1
                        except Exception:
                            continue
                    monthly_submission_counts[months_list[m_idx]] += 1
                    
        academic_year_months = ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May"]
        timeline_df = pd.DataFrame({
            "Month": academic_year_months,
            "Submission Count": [monthly_submission_counts[m] for m in academic_year_months]
        })
        st.line_chart(timeline_df, x="Month", y="Submission Count")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 Refresh Timeline Chart", key="refresh_timeline_chart"):
                st.rerun()
        with c2:
            timeline_excel = export_to_excel(timeline_df.to_dict("records"))
            st.download_button(
                label="📥 Download Excel",
                data=timeline_excel,
                file_name="monthly_submission_timeline.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_timeline_chart_excel",
                use_container_width=True,
                on_click=lambda: log_event("EXPORT_GENERATED", st.session_state.username, st.session_state.role, "Exported Timeline Chart Data")
            )

    st.markdown("---")

    # 5. AI Report Generator
    st.markdown("### 🤖 AI Department Report Generator")
    st.markdown("""
        <div style="background-color: rgba(56, 189, 248, 0.03); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 12px; padding: 20px; margin-bottom: 20px;">
            <h4 style="margin-top: 0px; color: #38bdf8; font-weight: 600;">Ask anything about your AIML department</h4>
            <p style="font-size: 0.9rem; color: #94a3b8; margin-bottom: 15px;">Pose natural language queries regarding faculty activities, student publications, hackathons, or criteria summary reports. The Report Agent will fetch live data to format your response.</p>
        </div>
    """, unsafe_allow_html=True)
    
    chips = [
        "How many FDPs were conducted this academic year?",
        "List all Scopus-indexed publications from 2024",
        "Which students won prizes in national-level hackathons?",
        "Generate NAAC Criterion 3 summary for faculty development",
        "Show faculty who haven't submitted any activity this semester",
        "How many students completed NPTEL certifications?",
        "Compare student hackathon participation: 2023 vs 2024",
        "List all international-level activities by faculty",
        "Generate NBA report for faculty qualification criterion",
        "Which faculty published in SCI journals this year?"
    ]
    
    st.write("💡 **Example Prompt Chips (click to fill):**")
    chip_cols = st.columns(2)
    for i, chip_text in enumerate(chips):
        with chip_cols[i % 2]:
            if st.button(f"📌 {chip_text}", key=f"hod_chip_{i}", use_container_width=True):
                st.session_state["hod_report_prompt"] = chip_text
                st.rerun()
                
    if "hod_report_prompt" not in st.session_state:
        st.session_state["hod_report_prompt"] = ""
        
    prompt_input = st.text_area(
        "Your Query:",
        height=120,
        key="hod_report_prompt"
    )
    
    if st.button("Generate Report", type="primary", key="hod_generate_report_btn", use_container_width=True):
        if not prompt_input.strip():
            st.error("Please enter a query or select an example prompt.")
        else:
            from utils.prompt_guard import is_safe_prompt
            safe_res = is_safe_prompt(prompt_input)
            if not safe_res.get("safe", True):
                st.error("⚠️ Invalid query detected. Please rephrase.")
                log_event("SUSPICIOUS_INPUT", st.session_state.username, st.session_state.role, f"Blocked report query: {prompt_input}. Reason: {safe_res.get('reason')}")
            else:
                with st.spinner("🤖 Report Agent is compiling Firestore data and generating report..."):
                    from agents.report_agent import run_report_agent
                    report_out = run_report_agent(prompt_input, st.session_state.username)
                    st.session_state["hod_report_result"] = report_out
                    
    if st.session_state.get("hod_report_result"):
        report_output = st.session_state["hod_report_result"]
        st.markdown("#### 📄 Generated Report:")
        st.info(report_output)
        
        pdf_bytes = generate_pdf_report(
            "AIML Department Performance Audit Report",
            report_output,
            {"generated_by": st.session_state.user_display_name}
        )
        
        records_dict = {
            "FDP": db.get_all_records("faculty_fdp"),
            "Publications": db.get_all_records("faculty_publications"),
            "Workshops": db.get_all_records("faculty_workshops"),
            "Hackathons": db.get_all_records("student_hackathons"),
            "Competitions": db.get_all_records("student_competitions"),
            "Certifications": db.get_all_records("student_certifications")
        }
        excel_bytes = generate_excel_report(records_dict, "AIML Department Report")
        
        act_col1, act_col2, act_col3 = st.columns(3)
        with act_col1:
            _is_pdf = isinstance(pdf_bytes, (bytes, bytearray)) and pdf_bytes[:4] == b"%PDF"
            st.download_button(
                label="📥 Download as PDF" if _is_pdf else "📥 Download Report (TXT)",
                data=pdf_bytes,
                file_name="aiml_department_report.pdf" if _is_pdf else "aiml_department_report.txt",
                mime="application/pdf" if _is_pdf else "text/plain",
                key="dl_report_pdf_btn",
                use_container_width=True,
                on_click=lambda: log_event("RECORD_DOWNLOADED", st.session_state.username, st.session_state.role, "Downloaded AI report as PDF")
            )
        with act_col2:
            st.download_button(
                label="📥 Download as Excel",
                data=excel_bytes,
                file_name="aiml_department_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_report_excel_btn",
                use_container_width=True,
                on_click=lambda: log_event("RECORD_DOWNLOADED", st.session_state.username, st.session_state.role, "Downloaded AI report as Excel")
            )
        with act_col3:
            import json
            escaped_report = json.dumps(report_output)
            st.components.v1.html(f"""
                <button id="copyReportBtn" style="
                    background-color: #38bdf8;
                    color: #0f172a;
                    border: none;
                    padding: 8px 16px;
                    font-size: 14px;
                    font-weight: bold;
                    border-radius: 8px;
                    cursor: pointer;
                    width: 100%;
                    height: 38px;
                    font-family: 'Outfit', sans-serif;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                ">📋 Copy to Clipboard</button>
                <script>
                document.getElementById("copyReportBtn").addEventListener("click", () => {{
                    const el = document.createElement('textarea');
                    el.value = {escaped_report};
                    document.body.appendChild(el);
                    el.select();
                    document.execCommand('copy');
                    document.body.removeChild(el);
                    alert('Copied to clipboard!');
                }});
                </script>
            """, height=42)

    # 6. Browse All Records & Management (Utility expanders at bottom)
    st.markdown("---")
    with st.expander("📂 Browse All Department Records", expanded=False):
        collections_map = {
            "faculty_fdp": "Faculty FDPs",
            "faculty_publications": "Research Publications",
            "faculty_workshops": "Workshops / Seminars",
            "student_hackathons": "Student Hackathons",
            "student_competitions": "Student Competitions",
            "student_certifications": "Course Certifications"
        }
        
        default_idx = 0
        if st.session_state.get("hod_selected_collection") in collections_map:
            default_idx = list(collections_map.keys()).index(st.session_state["hod_selected_collection"])
            
        selected_col = st.selectbox(
            "Select Department Collection:",
            options=list(collections_map.keys()),
            format_func=lambda x: collections_map[x],
            index=default_idx,
            key="hod_selected_collection_select"
        )
        
        st.session_state["hod_selected_collection"] = selected_col
        
        filter_option = st.radio(
            "Filter Records:",
            options=["Show All", "Verified Only", "Flagged Only", "With Certificates"],
            horizontal=True,
            key="hod_browse_filter_option"
        )
        
        search_query = st.text_input("🔍 Search records by name (Faculty Name / Student Name / Speaker / Author):", key="hod_search_query_input")
        
        raw_records = db.get_all_records(selected_col)
        
        filtered_records = []
        for r in raw_records:
            match = True
            if search_query.strip():
                name_found = False
                for field in ["faculty_name", "student_name", "author", "speaker", "student"]:
                    if field in r and r[field] and search_query.lower() in str(r[field]).lower():
                        name_found = True
                        break
                if not name_found:
                    match = False
                    
            if match:
                if filter_option == "Verified Only" and not r.get("verified", False):
                    match = False
                elif filter_option == "Flagged Only" and not r.get("flagged", False):
                    match = False
                elif filter_option == "With Certificates" and not r.get("file_url"):
                    match = False
                    
            if match:
                filtered_records.append(r)
                
        if not filtered_records:
            st.info("No matching records found in this collection.")
        else:
            df_browse = pd.DataFrame(filtered_records)
            if "verified" not in df_browse.columns:
                df_browse["verified"] = False
            if "flagged" not in df_browse.columns:
                df_browse["flagged"] = False
                
            column_config = {
                "verified": st.column_config.CheckboxColumn("✓ Verified"),
                "flagged": st.column_config.CheckboxColumn("🚩 Flagged")
            }
            if "file_url" in df_browse.columns:
                column_config["file_url"] = st.column_config.LinkColumn("View Certificate", display_text="Open Link")
                
            st.dataframe(df_browse, column_config=column_config, use_container_width=True, hide_index=True)
            
            st.markdown("#### 📄 Row-Level Actions (First 10 matches):")
            for idx, r in enumerate(filtered_records[:10]):
                ref_id = r.get("reference_id", "N/A")
                title = r.get("title", "Untitled")
                name_val = r.get("faculty_name") or r.get("student_name") or r.get("author") or r.get("speaker") or "Unknown"
                file_url = r.get("file_url")
                is_verified = r.get("verified", False)
                is_flagged = r.get("flagged", False)
                
                status_icons = ""
                if is_verified:
                    status_icons += " <span style='color: #4ade80; font-weight: bold; margin-left: 5px;'>✓ Verified</span>"
                if is_flagged:
                    status_icons += " <span style='color: #fbbf24; font-weight: bold; margin-left: 5px;'>🚩 Flagged</span>"
                    
                col_info, col_verify, col_flag, col_view, col_dl = st.columns([3.5, 1.2, 1.2, 1.2, 1.2])
                with col_info:
                    st.markdown(f"**{ref_id}** | {title} (by *{name_val}*){status_icons}", unsafe_allow_html=True)
                with col_verify:
                    verified_val = st.toggle("Verify", value=is_verified, key=f"v_tgl_{selected_col}_{ref_id}")
                    if verified_val != is_verified:
                        db.update_record(selected_col, r["doc_id"], {"verified": verified_val})
                        log_event("DATA_SUBMITTED", st.session_state.username, st.session_state.role, f"Toggled verification for {ref_id} to {verified_val}")
                        st.rerun()
                with col_flag:
                    flag_label = "Unflag 🏳️" if is_flagged else "Flag 🚩"
                    if st.button(flag_label, key=f"f_btn_{selected_col}_{ref_id}", use_container_width=True):
                        db.update_record(selected_col, r["doc_id"], {"flagged": not is_flagged})
                        log_event("DATA_SUBMITTED", st.session_state.username, st.session_state.role, f"Toggled flag status for {ref_id} to {not is_flagged}")
                        st.rerun()
                with col_view:
                    if file_url:
                        st.link_button("👁️ View", file_url, key=f"view_cert_{selected_col}_{idx}", use_container_width=True)
                    else:
                        st.button("No Proof", key=f"no_cert_view_{selected_col}_{idx}", disabled=True, use_container_width=True)
                with col_dl:
                    if file_url:
                        st.link_button("📥 Download", file_url, key=f"dl_cert_{selected_col}_{idx}", use_container_width=True)
                    else:
                        st.button("N/A", key=f"no_cert_dl_{selected_col}_{idx}", disabled=True, use_container_width=True)
                        
            st.markdown("---")
            col_export_bytes = export_to_excel(filtered_records)
            st.download_button(
                label=f"📥 Export Entire {collections_map[selected_col]} Collection to Excel",
                data=col_export_bytes,
                file_name=f"aiml_dept_{selected_col}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_entire_collection_btn",
                use_container_width=True,
                on_click=lambda: log_event("EXPORT_GENERATED", st.session_state.username, st.session_state.role, f"Exported entire {selected_col} collection to Excel")
            )

    with st.expander("📢 Student Requests & Announcement Management", expanded=False):
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            st.markdown("#### 📋 Student Requests Management")
            if not st.session_state.requests:
                st.info("No requests pending.")
            else:
                df_requests = pd.DataFrame(st.session_state.requests)
                st.dataframe(df_requests, use_container_width=True)
                
                st.write("##### Moderate Request")
                req_ids = [r["id"] for r in st.session_state.requests if r["status"] == "Pending"]
                if req_ids:
                    selected_id = st.selectbox("Select Request ID", req_ids)
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("Approve Request", use_container_width=True):
                            for r in st.session_state.requests:
                                if r["id"] == selected_id:
                                    r["status"] = "Approved"
                                    log_event("DATA_SUBMITTED", st.session_state.username, st.session_state.role, f"Moderated request ID {selected_id}: Approved")
                            st.success(f"Request {selected_id} approved!")
                            st.rerun()
                    with col_btn2:
                        if st.button("Reject Request", use_container_width=True):
                            for r in st.session_state.requests:
                                if r["id"] == selected_id:
                                    r["status"] = "Rejected"
                                    log_event("DATA_SUBMITTED", st.session_state.username, st.session_state.role, f"Moderated request ID {selected_id}: Rejected")
                            st.warning(f"Request {selected_id} rejected.")
                            st.rerun()
                else:
                    st.success("All current requests have been moderated!")

        with col_right:
            st.markdown("#### 📢 Post Announcement")
            new_title = st.text_input("Announcement Title")
            new_content = st.text_area("Announcement Description")
            if st.button("Post Announcement", use_container_width=True):
                if new_title and new_content:
                    st.session_state.announcements.insert(0, {
                        "id": len(st.session_state.announcements) + 1,
                        "title": sanitize_text(new_title),
                        "content": sanitize_text(new_content),
                        "posted_by": st.session_state.username,
                        "date": datetime.now().strftime("%Y-%m-%d")
                    })
                    log_event("DATA_SUBMITTED", st.session_state.username, st.session_state.role, f"Posted announcement: {new_title}")
                    st.success("Announcement posted successfully!")
                    st.rerun()
                else:
                    st.warning("Please enter both title and content.")

            # Show registered accounts
            st.markdown("#### 👤 Registered User Registry")
            user_list = [
                {"Username": "hod_aiml", "Name": "Head of Department", "Role": "HoD"},
                {"Username": "fac_turing", "Name": "Alan Turing", "Role": "Faculty"},
                {"Username": "stu_hopper", "Name": "Grace Hopper", "Role": "Student"}
            ]
            st.table(pd.DataFrame(user_list))

def get_latest_submission_ref_id(collection: str, id_field: str, id_val: str) -> str:
    import utils.db as db
    records = db.get_records_by_field(collection, id_field, id_val)
    if not records:
        return "AIML-TEMP"
    
    # Safely convert created_at to timestamp float for comparison
    def get_time_key(r):
        t = r.get("created_at")
        if t is None:
            return 0.0
        if hasattr(t, "timestamp"):
            return t.timestamp()
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t).timestamp()
            except Exception:
                return 0.0
        return 0.0

    records = sorted(records, key=get_time_key, reverse=True)
    return records[0].get("reference_id", "AIML-TEMP")

def render_submission_receipt(ref_id: str, entry_type_label: str, faculty_name: str, file_uploaded: bool, file_name: str):
    date_submitted = datetime.now().strftime("%Y-%m-%d")
    st.markdown(f"""
        <div style="background-color: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); padding: 1.5rem; border-radius: 12px; margin-top: 1rem; color: #e2e8f0; font-family: sans-serif;">
            <h4 style="margin-top: 0px; color: #4ade80; font-weight: 600;">✅ Submission Receipt</h4>
            <div style="font-size: 0.9rem; color: #94a3b8;">Reference ID</div>
            <div style="font-size: 2rem; font-weight: 800; color: #4ade80; margin: 5px 0px 15px 0px; letter-spacing: 1px;">{ref_id}</div>
            <div style="margin-bottom: 8px;"><strong>Entry Type:</strong> {entry_type_label}</div>
            <div style="margin-bottom: 8px;"><strong>Faculty Name:</strong> {faculty_name}</div>
            <div style="margin-bottom: 8px;"><strong>Date Submitted:</strong> {date_submitted}</div>
            {"<div style='margin-top: 10px; padding: 6px 12px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 6px; display: inline-block; font-size: 0.85rem; color: #38bdf8;'>📎 <strong>Certificate uploaded:</strong> " + file_name + "</div>" if file_uploaded else ""}
        </div>
    """, unsafe_allow_html=True)
    
    # Copy Reference ID block
    st.write("📋 **Copy Reference ID:**")
    st.code(ref_id, language="text")
    
    # Download receipt
    receipt_text = f"""AIML Department Intelligence Hub - Submission Receipt
==================================================
Reference ID: {ref_id}
Entry Type: {entry_type_label}
Faculty Name: {faculty_name}
Date Submitted: {date_submitted}
Uploaded Certificate: {file_name if file_uploaded else "None"}
Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    st.download_button(
        label="📥 Download Receipt (TXT)",
        data=receipt_text,
        file_name=f"receipt_{ref_id}.txt",
        mime="text/plain",
        key=f"dl_receipt_{ref_id}_{os.urandom(2).hex()}"
    )

# --- SUBMISSION REMINDER HELPER ---
def check_last_submission_date():
    import utils.db as db
    from datetime import datetime, timedelta
    
    if "username" not in st.session_state or "role" not in st.session_state:
        return False
        
    email_val = f"{st.session_state.username}@aiml.edu"
    role = st.session_state.role
    
    recs = []
    if role == "Faculty":
        recs += db.get_records_by_field("faculty_fdp", "email", email_val)
        recs += db.get_records_by_field("faculty_publications", "email", email_val)
        recs += db.get_records_by_field("faculty_workshops", "email", email_val)
    elif role == "Student":
        recs += db.get_records_by_field("student_hackathons", "email", email_val)
        recs += db.get_records_by_field("student_competitions", "email", email_val)
        recs += db.get_records_by_field("student_certifications", "email", email_val)
        
    if not recs:
        return True
        
    latest_date = None
    for r in recs:
        c_at = r.get("created_at")
        if c_at:
            if not isinstance(c_at, datetime):
                try:
                    c_at = datetime.fromisoformat(str(c_at))
                except Exception:
                    continue
            if c_at.tzinfo is not None:
                c_at = c_at.replace(tzinfo=None)
                
            if latest_date is None or c_at > latest_date:
                latest_date = c_at
                
    if latest_date is None:
        return True
        
    diff = datetime.now() - latest_date
    if diff > timedelta(days=30):
        return True
    return False


def show_my_submissions(username):
    from utils.db import get_all_records
    from utils.db import FACULTY_FDP, FACULTY_PUBLICATIONS, FACULTY_WORKSHOPS
    
    collections = {
        "FDP": FACULTY_FDP,
        "Publications": FACULTY_PUBLICATIONS,
        "Workshops": FACULTY_WORKSHOPS
    }
    
    found_any = False
    clean_user = username.lower().replace("fac_", "").replace("stu_", "").replace("_", " ").strip()
    display_name_clean = st.session_state.get("user_display_name", "").lower().replace("faculty", "").replace("student", "").strip()
    
    for label, collection in collections.items():
        # Fetch ALL records and filter client-side
        all_records = get_all_records(collection)
        print(f"DEBUG: {collection} has {len(all_records)} total records")
        
        # Filter by any name-like field matching username
        my_records = []
        for r in all_records:
            # Check multiple possible field names
            name_fields = [
                "faculty_name", "name", "employee_id", 
                "submitted_by", "username", "user", "email"
            ]
            for field in name_fields:
                val = str(r.get(field, "")).lower().strip()
                if not val:
                    continue
                if (username.lower() in val or 
                    val in username.lower() or
                    st.session_state.get("username","").lower() in val or
                    (clean_user and clean_user in val) or
                    (display_name_clean and display_name_clean in val) or
                    (val in display_name_clean)):
                    my_records.append(r)
                    break
        
        if my_records:
            found_any = True
            st.subheader(f"📋 My {label} Submissions ({len(my_records)})")
            for record in my_records:
                with st.container():
                    col1, col2 = st.columns([3,1])
                    with col1:
                        # Show title field - try multiple field names
                        title = (record.get("fdp_title") or 
                                record.get("paper_title") or
                                record.get("workshop_name") or
                                record.get("title") or
                                record.get("name") or
                                "Untitled")
                        ref_id = record.get("reference_id", "N/A")
                        date = record.get("start_date") or record.get("date") or record.get("created_at", "")
                        st.write(f"**{title}**")
                        st.caption(f"Ref: {ref_id} | Date: {date}")
                    with col2:
                        file_url = record.get("file_url")
                        if file_url:
                            st.link_button("📄 View Certificate", file_url)
    
    if not found_any:
        # Show ALL records as debug
        st.warning("No submissions found for your account.")
        with st.expander("🔍 Debug: All records in Firestore"):
            for label, collection in collections.items():
                all_r = get_all_records(collection)
                st.write(f"{label}: {len(all_r)} total records")
                if all_r:
                    st.json(all_r[0])  # show first record structure


def show_student_submissions(username):
    from utils.db import get_all_records
    from utils.db import STUDENT_HACKATHONS, STUDENT_COMPETITIONS, STUDENT_CERTIFICATIONS
    
    collections = {
        "Hackathons": STUDENT_HACKATHONS,
        "Competitions": STUDENT_COMPETITIONS,
        "Certifications": STUDENT_CERTIFICATIONS
    }
    
    found_any = False
    clean_user = username.lower().replace("fac_", "").replace("stu_", "").replace("_", " ").strip()
    display_name_clean = st.session_state.get("user_display_name", "").lower().replace("faculty", "").replace("student", "").strip()
    
    for label, collection in collections.items():
        all_records = get_all_records(collection)
        print(f"DEBUG: {collection} has {len(all_records)} total records")
        
        my_records = []
        for r in all_records:
            # Check multiple possible field names
            name_fields = [
                "student_name", "name", "register_number", 
                "submitted_by", "username", "email"
            ]
            for field in name_fields:
                val = str(r.get(field, "")).lower().strip()
                if not val:
                    continue
                if (username.lower() in val or 
                    val in username.lower() or
                    st.session_state.get("username","").lower() in val or
                    (clean_user and clean_user in val) or
                    (display_name_clean and display_name_clean in val) or
                    (val in display_name_clean)):
                    my_records.append(r)
                    break
        
        if my_records:
            found_any = True
            st.subheader(f"📋 My {label} Submissions ({len(my_records)})")
            for record in my_records:
                with st.container():
                    col1, col2 = st.columns([3,1])
                    with col1:
                        title = (record.get("hackathon_name") or 
                                record.get("event_name") or
                                record.get("course_title") or
                                record.get("title") or
                                record.get("name") or
                                "Untitled")
                        ref_id = record.get("reference_id", "N/A")
                        date = record.get("start_date") or record.get("date") or record.get("created_at", "")
                        st.write(f"**{title}**")
                        st.caption(f"Ref: {ref_id} | Date: {date}")
                    with col2:
                        file_url = record.get("file_url")
                        if file_url:
                            st.link_button("📄 View Certificate", file_url)
                            
    if not found_any:
        st.warning("No submissions found for your account.")
        with st.expander("🔍 Debug: All records in Firestore"):
            for label, collection in collections.items():
                all_r = get_all_records(collection)
                st.write(f"{label}: {len(all_r)} total records")
                if all_r:
                    st.json(all_r[0])  # show first record structure


# --- DASHBOARD: FACULTY ---
def render_faculty_dashboard():
    # Call require_auth at the top
    require_auth(allowed_roles=["Faculty", "HoD"])
    
    if check_last_submission_date():
        st.warning(
            "📢 Reminder: You haven't submitted any activity in the last 30 days. "
            "Don't forget to log your recent FDPs, publications, or competitions."
        )
        
    st.write(f"Welcome, **{st.session_state.user_display_name}** | Role: **Faculty**")
    
    # Render tabs
    tab_fdp, tab_pub, tab_wks = st.tabs(["FDP", "Publications", "Workshops"])
    
    with tab_fdp:
        st.markdown("### 📚 Faculty Development Program (FDP) Submission")
        
        # Standard input fields grouped in columns
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            faculty_name = st.text_input("Faculty Name*", value=st.session_state.user_display_name, key="fdp_fac_name")
        with col_f2:
            employee_id = st.text_input("Employee ID*", key="fdp_emp_id")
            
        col_f3, col_f4 = st.columns(2)
        with col_f3:
            fdp_title = st.text_input("FDP Title*", key="fdp_title", on_change=check_title_duplicate, args=("faculty_fdp", "fdp_title"))
        with col_f4:
            organizing_institution = st.text_input("Organizing Institution*", key="fdp_org")
            
        if st.session_state.get("fdp_title_dup_ref"):
            st.warning(f"⚠️ Warning: A record with this title already exists (Ref ID: {st.session_state['fdp_title_dup_ref']}). You can still submit if this is a different entry.")
            
        col_date1, col_date2, col_dur = st.columns(3)
        with col_date1:
            start_date = st.date_input("Start Date*", key="fdp_start_date")
        with col_date2:
            end_date = st.date_input("End Date*", key="fdp_end_date")
        with col_dur:
            duration_days = (end_date - start_date).days + 1 if end_date >= start_date else 0
            st.number_input("Duration (Days)", value=duration_days, disabled=True, key="fdp_dur")
            
        col_m, col_l, col_fun = st.columns(3)
        with col_m:
            mode = st.selectbox("Mode*", ["Online", "Offline", "Hybrid"], key="fdp_mode")
        with col_l:
            level = st.selectbox("Level*", ["Institution", "State", "National", "International"], key="fdp_level")
        with col_fun:
            funding = st.selectbox("Funding", ["Self-funded", "AICTE", "Institution", "Industry"], key="fdp_funding")
            
        topic_domain = st.text_input("Topic/Domain*", key="fdp_topic")
        brief_description = st.text_area("Brief Description (optional, max 300 chars)", max_chars=300, key="fdp_desc")
        
        # File Upload section with a dotted border box
        st.markdown("""
            <div style="border: 2px dashed rgba(56, 189, 248, 0.4); border-radius: 12px; padding: 15px; margin-bottom: 10px; background-color: rgba(255, 255, 255, 0.01);">
                <span style="font-weight: 600; color: #38bdf8;">📂 File Upload: Upload Certificate / Proof Document (Max 5MB)</span>
            </div>
            """, unsafe_allow_html=True)
            
        uploaded_file = st.file_uploader(
            "Upload Certificate / Proof Document", 
            type=["pdf", "jpg", "jpeg", "png"], 
            key="fdp_file_input",
            label_visibility="collapsed"
        )
        
        if uploaded_file is not None:
            val_res = check_uploaded_file_ui(uploaded_file)
            if not val_res["valid"]:
                st.markdown(f"❌ **Invalid File:** {uploaded_file.name} | Size: {uploaded_file.size / 1024:.2f} KB | Type: {uploaded_file.type}")
                st.error(val_res["error"])
            else:
                st.markdown(f"✅ **Valid File:** {uploaded_file.name} | Size: {uploaded_file.size / 1024:.2f} KB ({uploaded_file.size / (1024*1024):.2f} MB) | Type: {uploaded_file.type}")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, width=200)
                else:
                    st.info(f"📄 PDF selected: {uploaded_file.name}")
                    
        if st.button("Submit FDP", type="primary", key="fdp_submit_btn"):
            if not employee_id or not fdp_title or not organizing_institution or not topic_domain:
                st.error("Please fill in all required fields marked with *.")
            elif end_date < start_date:
                st.error("End Date cannot be before Start Date.")
            else:
                with st.spinner("Validating your submission..."):
                    # Sanitize
                    s_name = sanitize_input(faculty_name, "text")
                    s_emp_id = sanitize_input(employee_id, "text")
                    s_title = sanitize_input(fdp_title, "text")
                    s_org = sanitize_input(organizing_institution, "text")
                    s_topic = sanitize_input(topic_domain, "text")
                    s_desc = sanitize_input(brief_description, "text") if brief_description else {"clean": "", "warnings": []}
                    
                    all_warnings = s_name["warnings"] + s_emp_id["warnings"] + s_title["warnings"] + s_org["warnings"] + s_topic["warnings"] + s_desc["warnings"]
                    for w in all_warnings:
                        st.warning(w)
                        
                    dup_ref = st.session_state.get("fdp_title_dup_ref")
                    if dup_ref:
                        log_event("DUPLICATE_DETECTED", st.session_state.username, st.session_state.role, f"FDP duplicate title submitted: '{s_title['clean']}'. Existing Ref ID: {dup_ref}")
                        
                    file_url = ""
                    file_name = ""
                    if uploaded_file is not None:
                        with st.spinner("Uploading file securely..."):
                             try:
                                 from utils.db import generate_reference_id
                                 temp_ref = generate_reference_id("faculty_fdp")
                                 upload_res = secure_upload(uploaded_file, temp_ref, "faculty_fdp")
                                 if not upload_res["success"]:
                                     log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload FDP certificate: {uploaded_file.name}. Error: {upload_res['error']}")
                                     st.error(f"File upload failed: {upload_res['error']}")
                                     st.stop()
                                 
                                 file_url = upload_res["url"]
                                 file_name = upload_res["safe_filename"]
                                 log_event("FILE_UPLOADED", st.session_state.username, st.session_state.role, f"Uploaded FDP certificate: {file_name}")
                             except Exception as upload_err:
                                 log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload FDP certificate: {uploaded_file.name}. Error: {upload_err}")
                                 st.error(f"File upload failed: {upload_err}")
                                 st.stop()
                             
                    data = {
                        "title": s_title["clean"],
                        "organizer": s_org["clean"],
                        "start_date": str(start_date),
                        "end_date": str(end_date),
                        "email": f"{st.session_state.username}@aiml.edu",
                        "employee_id": s_emp_id["clean"],
                        "faculty_name": s_name["clean"],
                        "duration_days": duration_days,
                        "mode": mode,
                        "topic_domain": s_topic["clean"],
                        "level": level,
                        "funding": funding,
                        "description": s_desc["clean"],
                        "file_url": file_url,
                        "file_name": file_name
                    }
                    
                    from agents.intake_agent import run_intake_agent
                    agent_res = run_intake_agent("faculty_fdp", data, st.session_state.username)
                    
                    st.success(f"🤖 **Intake Agent Response:** {agent_res}")
                    
                    # Clear duplicate warning after successful submit
                    if "fdp_title_dup_ref" in st.session_state:
                        st.session_state["fdp_title_dup_ref"] = ""
                        
                    latest_ref = get_latest_submission_ref_id("faculty_fdp", "employee_id", s_emp_id["clean"])
                    render_submission_receipt(
                        ref_id=latest_ref,
                        entry_type_label="Faculty Development Program (FDP)",
                        faculty_name=s_name["clean"],
                        file_uploaded=(uploaded_file is not None),
                        file_name=file_name
                    )

    with tab_pub:
        st.markdown("### 📄 Research Publication Submission")
        
        # Standard input fields grouped in columns
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            faculty_name_pub = st.text_input("Faculty Name*", value=st.session_state.user_display_name, key="pub_fac_name")
        with col_p2:
            employee_id_pub = st.text_input("Employee ID*", key="pub_emp_id")
            
        col_p3, col_p4 = st.columns(2)
        with col_p3:
            paper_title = st.text_input("Paper Title*", key="pub_title", on_change=check_title_duplicate, args=("faculty_publications", "pub_title"))
        with col_p4:
            journal_name = st.text_input("Journal/Conference Name*", key="pub_journal")
            
        if st.session_state.get("pub_title_dup_ref"):
            st.warning(f"⚠️ Warning: A record with this title already exists (Ref ID: {st.session_state['pub_title_dup_ref']}). You can still submit if this is a different entry.")
            
        col_p5, col_p6 = st.columns(2)
        with col_p5:
            publication_type = st.selectbox("Publication Type*", ["Journal", "Conference", "Book Chapter", "Patent"], key="pub_type")
        with col_p6:
            publisher = st.text_input("Publisher*", key="pub_publisher")
            
        col_p7, col_p8 = st.columns(2)
        with col_p7:
            publication_date = st.date_input("Publication Date*", key="pub_date")
        with col_p8:
            issn_isbn = st.text_input("ISSN/ISBN", key="pub_issn")
            
        col_p9, col_p10 = st.columns(2)
        with col_p9:
            doi_link = st.text_input("DOI Link", key="pub_doi")
        with col_p10:
            impact_factor = st.number_input("Impact Factor", min_value=0.0, max_value=50.0, step=0.1, key="pub_impact")
            
        col_p11, col_p12 = st.columns(2)
        with col_p11:
            indexed_in = st.multiselect("Indexed In*", ["SCI", "Scopus", "UGC Care", "Web of Science", "DBLP", "Other"], key="pub_indexed")
        with col_p12:
            co_authors = st.text_input("Co-Authors (comma-separated)", key="pub_authors")
            
        abstract = st.text_area("Abstract (optional, max 500 chars)", max_chars=500, key="pub_abstract")
        
        # File Upload section with dotted border box
        st.markdown("""
            <div style="border: 2px dashed rgba(56, 189, 247, 0.4); border-radius: 12px; padding: 15px; margin-bottom: 10px; background-color: rgba(255, 255, 255, 0.01);">
                <span style="font-weight: 600; color: #38bdf8;">📄 File Upload: Upload Paper PDF or Acceptance Letter (PDF Only, Max 5MB)</span>
            </div>
            """, unsafe_allow_html=True)
            
        uploaded_file_pub = st.file_uploader(
            "Upload Paper PDF or Acceptance Letter", 
            type=["pdf"], 
            key="pub_file_input",
            label_visibility="collapsed"
        )
        
        if uploaded_file_pub is not None:
            val_res_pub = check_uploaded_file_ui(uploaded_file_pub)
            if not val_res_pub["valid"]:
                st.markdown(f"❌ **Invalid File:** {uploaded_file_pub.name} | Size: {uploaded_file_pub.size / 1024:.2f} KB | Type: {uploaded_file_pub.type}")
                st.error(val_res_pub["error"])
            else:
                st.markdown(f"✅ **Valid File:** {uploaded_file_pub.name} | Size: {uploaded_file_pub.size / 1024:.2f} KB ({uploaded_file_pub.size / (1024*1024):.2f} MB) | Type: {uploaded_file_pub.type}")
                st.info(f"📄 PDF selected: {uploaded_file_pub.name}")
                
        if st.button("Submit Publication", type="primary", key="pub_submit_btn"):
            if not employee_id_pub or not paper_title or not journal_name or not publisher or not indexed_in:
                st.error("Please fill in all required fields marked with *.")
            elif doi_link and not doi_link.startswith("https://"):
                st.error("DOI Link must start with https://")
            else:
                with st.spinner("Validating your submission..."):
                    # Sanitize
                    s_name = sanitize_input(faculty_name_pub, "text")
                    s_emp_id = sanitize_input(employee_id_pub, "text")
                    s_title = sanitize_input(paper_title, "text")
                    s_journal = sanitize_input(journal_name, "text")
                    s_pub = sanitize_input(publisher, "text")
                    s_issn = sanitize_input(issn_isbn, "text") if issn_isbn else {"clean": "", "warnings": []}
                    s_doi = sanitize_input(doi_link, "url") if doi_link else {"clean": "", "warnings": []}
                    s_authors = sanitize_input(co_authors, "text") if co_authors else {"clean": "", "warnings": []}
                    s_abs = sanitize_input(abstract, "text") if abstract else {"clean": "", "warnings": []}
                    
                    all_warnings = s_name["warnings"] + s_emp_id["warnings"] + s_title["warnings"] + s_journal["warnings"] + s_pub["warnings"] + s_issn["warnings"] + s_doi["warnings"] + s_authors["warnings"] + s_abs["warnings"]
                    for w in all_warnings:
                        st.warning(w)
                        
                    dup_ref = st.session_state.get("pub_title_dup_ref")
                    if dup_ref:
                        log_event("DUPLICATE_DETECTED", st.session_state.username, st.session_state.role, f"Publication duplicate title submitted: '{s_title['clean']}'. Existing Ref ID: {dup_ref}")
                        
                    file_url = ""
                    file_name = ""
                    if uploaded_file_pub is not None:
                        with st.spinner("Uploading file securely..."):
                            try:
                                from utils.db import generate_reference_id
                                temp_ref = generate_reference_id("faculty_publications")
                                upload_res = secure_upload(uploaded_file_pub, temp_ref, "faculty_publications")
                                if not upload_res["success"]:
                                    log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload paper: {uploaded_file_pub.name}. Error: {upload_res['error']}")
                                    st.error(f"File upload failed: {upload_res['error']}")
                                    st.stop()
                                
                                file_url = upload_res["url"]
                                file_name = upload_res["safe_filename"]
                                log_event("FILE_UPLOADED", st.session_state.username, st.session_state.role, f"Uploaded paper: {file_name}")
                            except Exception as upload_err:
                                log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload paper: {uploaded_file_pub.name}. Error: {upload_err}")
                                st.error(f"File upload failed: {upload_err}")
                                st.stop()
                            
                    data = {
                        "title": s_title["clean"],
                        "author": s_name["clean"],
                        "journal": s_journal["clean"],
                        "year": str(publication_date.year),
                        "employee_id": s_emp_id["clean"],
                        "publication_type": publication_type,
                        "publisher": s_pub["clean"],
                        "issn_isbn": s_issn["clean"],
                        "doi_link": s_doi["clean"],
                        "publication_date": str(publication_date),
                        "impact_factor": impact_factor,
                        "indexed_in": indexed_in,
                        "co_authors": s_authors["clean"],
                        "abstract": s_abs["clean"],
                        "file_url": file_url,
                        "file_name": file_name
                    }
                    
                    from agents.intake_agent import run_intake_agent
                    agent_res = run_intake_agent("faculty_publications", data, st.session_state.username)
                    
                    st.success(f"🤖 **Intake Agent Response:** {agent_res}")
                    
                    # Clear duplicate warning after successful submit
                    if "pub_title_dup_ref" in st.session_state:
                        st.session_state["pub_title_dup_ref"] = ""
                        
                    latest_ref = get_latest_submission_ref_id("faculty_publications", "employee_id", s_emp_id["clean"])
                    render_submission_receipt(
                        ref_id=latest_ref,
                        entry_type_label="Research Publication",
                        faculty_name=s_name["clean"],
                        file_uploaded=(uploaded_file_pub is not None),
                        file_name=file_name
                    )

    with tab_wks:
        st.markdown("### 🛠️ Workshops / Seminars Submission")
        
        # Standard input fields grouped in columns
        col_w1, col_w2 = st.columns(2)
        with col_w1:
            faculty_name_wks = st.text_input("Faculty Name*", value=st.session_state.user_display_name, key="wks_fac_name")
        with col_w2:
            employee_id_wks = st.text_input("Employee ID*", key="wks_emp_id")
            
        col_w3, col_w4 = st.columns(2)
        with col_w3:
            workshop_name = st.text_input("Workshop/Conference Name*", key="wks_name", on_change=check_title_duplicate, args=("faculty_workshops", "wks_name"))
        with col_w4:
            organizer = st.text_input("Organizer*", key="wks_org")
            
        if st.session_state.get("wks_name_dup_ref"):
            st.warning(f"⚠️ Warning: A record with this title already exists (Ref ID: {st.session_state['wks_name_dup_ref']}). You can still submit if this is a different entry.")
            
        col_w5, col_w6, col_w7 = st.columns(3)
        with col_w5:
            workshop_date = st.date_input("Date*", key="wks_date")
        with col_w6:
            duration = st.text_input("Duration*", key="wks_dur")
        with col_w7:
            certificate_number = st.text_input("Certificate Number (optional)", key="wks_cert_num")
            
        col_w8, col_w9, col_w10 = st.columns(3)
        with col_w8:
            mode_wks = st.selectbox("Mode*", ["Online", "Offline", "Hybrid"], key="wks_mode")
        with col_w9:
            role_wks = st.selectbox("Role*", ["Attended", "Resource Person", "Organizer", "Keynote Speaker"], key="wks_role")
        with col_w10:
            level_wks = st.selectbox("Level*", ["Institution", "State", "National", "International"], key="wks_level")
            
        topic = st.text_input("Topic*", key="wks_topic")
        
        # File Upload section with dotted border box
        st.markdown("""
            <div style="border: 2px dashed rgba(168, 85, 247, 0.4); border-radius: 12px; padding: 15px; margin-bottom: 10px; background-color: rgba(255, 255, 255, 0.01);">
                <span style="font-weight: 600; color: #a855f7;">📂 File Upload: Upload Certificate / Brochure / Invitation Letter (Max 5MB)</span>
            </div>
            """, unsafe_allow_html=True)
            
        uploaded_file_wks = st.file_uploader(
            "Upload Certificate / Brochure / Invitation Letter", 
            type=["pdf", "jpg", "jpeg", "png"], 
            key="wks_file_input",
            label_visibility="collapsed"
        )
        
        if uploaded_file_wks is not None:
            val_res_wks = check_uploaded_file_ui(uploaded_file_wks)
            if not val_res_wks["valid"]:
                st.markdown(f"❌ **Invalid File:** {uploaded_file_wks.name} | Size: {uploaded_file_wks.size / 1024:.2f} KB | Type: {uploaded_file_wks.type}")
                st.error(val_res_wks["error"])
            else:
                st.markdown(f"✅ **Valid File:** {uploaded_file_wks.name} | Size: {uploaded_file_wks.size / 1024:.2f} KB ({uploaded_file_wks.size / (1024*1024):.2f} MB) | Type: {uploaded_file_wks.type}")
                if uploaded_file_wks.type.startswith("image/"):
                    st.image(uploaded_file_wks, width=200)
                else:
                    st.info(f"📄 PDF selected: {uploaded_file_wks.name}")
                    
        if st.button("Submit Workshop", type="primary", key="wks_submit_btn"):
            if not employee_id_wks or not workshop_name or not organizer or not duration or not topic:
                st.error("Please fill in all required fields marked with *.")
            else:
                with st.spinner("Validating your submission..."):
                    # Sanitize
                    s_name = sanitize_input(faculty_name_wks, "text")
                    s_emp_id = sanitize_input(employee_id_wks, "text")
                    s_title = sanitize_input(workshop_name, "text")
                    s_org = sanitize_input(organizer, "text")
                    s_dur = sanitize_input(duration, "text")
                    s_topic = sanitize_input(topic, "text")
                    s_cert = sanitize_input(certificate_number, "text") if certificate_number else {"clean": "", "warnings": []}
                    
                    all_warnings = s_name["warnings"] + s_emp_id["warnings"] + s_title["warnings"] + s_org["warnings"] + s_dur["warnings"] + s_topic["warnings"] + s_cert["warnings"]
                    for w in all_warnings:
                        st.warning(w)
                        
                    dup_ref = st.session_state.get("wks_name_dup_ref")
                    if dup_ref:
                        log_event("DUPLICATE_DETECTED", st.session_state.username, st.session_state.role, f"Workshop duplicate title submitted: '{s_title['clean']}'. Existing Ref ID: {dup_ref}")
                        
                    file_url = ""
                    file_name = ""
                    if uploaded_file_wks is not None:
                        with st.spinner("Uploading file securely..."):
                            try:
                                from utils.db import generate_reference_id
                                temp_ref = generate_reference_id("faculty_workshops")
                                upload_res = secure_upload(uploaded_file_wks, temp_ref, "faculty_workshops")
                                if not upload_res["success"]:
                                    log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload workshop certificate: {uploaded_file_wks.name}. Error: {upload_res['error']}")
                                    st.error(f"File upload failed: {upload_res['error']}")
                                    st.stop()
                                
                                file_url = upload_res["url"]
                                file_name = upload_res["safe_filename"]
                                log_event("FILE_UPLOADED", st.session_state.username, st.session_state.role, f"Uploaded workshop certificate: {file_name}")
                            except Exception as upload_err:
                                log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload workshop certificate: {uploaded_file_wks.name}. Error: {upload_err}")
                                st.error(f"File upload failed: {upload_err}")
                                st.stop()
                            
                    data = {
                        "title": s_title["clean"],
                        "speaker": s_name["clean"],
                        "date": str(workshop_date),
                        "venue": s_org["clean"],
                        "employee_id": s_emp_id["clean"],
                        "duration": s_dur["clean"],
                        "mode": mode_wks,
                        "role": role_wks,
                        "topic": s_topic["clean"],
                        "level": level_wks,
                        "certificate_number": s_cert["clean"],
                        "file_url": file_url,
                        "file_name": file_name
                    }
                    
                    from agents.intake_agent import run_intake_agent
                    agent_res = run_intake_agent("faculty_workshops", data, st.session_state.username)
                    
                    st.success(f"🤖 **Intake Agent Response:** {agent_res}")
                    
                    # Clear duplicate warning after successful submit
                    if "wks_name_dup_ref" in st.session_state:
                        st.session_state["wks_name_dup_ref"] = ""
                        
                    latest_ref = get_latest_submission_ref_id("faculty_workshops", "employee_id", s_emp_id["clean"])
                    render_submission_receipt(
                        ref_id=latest_ref,
                        entry_type_label="Workshop / Seminar Submission",
                        faculty_name=s_name["clean"],
                        file_uploaded=(uploaded_file_wks is not None),
                        file_name=file_name
                    )

    # --- TRACK MY SUBMISSIONS ---
    st.markdown("---")
    st.markdown("### 🔍 Track My Submissions")
    
    with st.expander("My Submissions", expanded=False):
        show_my_submissions(st.session_state.username)


# --- DASHBOARD: STUDENT ---
# --- DASHBOARD: STUDENT ---
def render_student_dashboard():
    # Call require_auth at the top
    require_auth(allowed_roles=["Student", "HoD"])
    
    if check_last_submission_date():
        st.warning(
            "📢 Reminder: You haven't submitted any activity in the last 30 days. "
            "Don't forget to log your recent FDPs, publications, or competitions."
        )
        
    st.write(f"Welcome, **{st.session_state.user_display_name}** | Role: **Student**")
    
    # 3 Tabs: Hackathons, Competitions, Certifications
    tab_hack, tab_comp, tab_cert = st.tabs(["Hackathons", "Competitions", "Certifications"])
    
    with tab_hack:
        st.markdown("### 🏆 Hackathon Submission Portal")
        
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            student_name = st.text_input("Student Name*", value=st.session_state.user_display_name, key="hack_stud_name")
        with col_h2:
            register_number = st.text_input("Register Number*", key="hack_reg_num")
            
        col_h3, col_h4 = st.columns(2)
        with col_h3:
            semester = st.selectbox("Semester*", list(range(1, 9)), key="hack_sem")
        with col_h4:
            section = st.text_input("Section*", key="hack_sec")
            
        col_h5, col_h6 = st.columns(2)
        with col_h5:
            hackathon_name = st.text_input("Hackathon Name*", key="hack_name", on_change=check_title_duplicate, args=("student_hackathons", "hack_name"))
        with col_h6:
            team_name = st.text_input("Team Name*", key="hack_team_name")
            
        if st.session_state.get("hack_name_dup_ref"):
            st.warning(f"⚠️ Warning: A record with this title already exists (Ref ID: {st.session_state['hack_name_dup_ref']}). You can still submit if this is a different entry.")
            
        col_h7, col_h8 = st.columns(2)
        with col_h7:
            organizer = st.text_input("Organizer*", key="hack_org")
        with col_h8:
            platform = st.text_input("Platform (e.g. Devfolio, HackerEarth, direct)", key="hack_platform")
            
        col_h9, col_h10 = st.columns(2)
        with col_h9:
            team_size = st.number_input("Team Size*", min_value=1, max_value=5, value=1, key="hack_team_size")
        with col_h10:
            level = st.selectbox("Level*", ["Institution", "State", "National", "International", "Global"], key="hack_level")
            
        col_h11, col_h12 = st.columns(2)
        with col_h11:
            hack_date = st.date_input("Date*", key="hack_date")
        with col_h12:
            duration = st.text_input("Duration* (e.g. 24 Hours, 48 Hours, 7 Days)", key="hack_duration")
            
        col_h13, col_h14 = st.columns(2)
        with col_h13:
            result = st.selectbox("Result*", ["Winner", "Runner-up", "Top 5", "Top 10", "Finalist", "Participant"], key="hack_result")
        with col_h14:
            prize_amount = st.number_input("Prize Amount (number in ₹, optional)", min_value=0, value=0, key="hack_prize")
            
        col_h15, col_h16 = st.columns(2)
        with col_h15:
            project_title = st.text_input("Project Title*", key="hack_proj_title")
        with col_h16:
            github_link = st.text_input("GitHub/Demo Link (optional)", key="hack_git_link")
            
        team_members = st.text_input("Team Members (comma-separated names, optional)", key="hack_teammates")
        project_description = st.text_area("Project Description (optional, max 400 chars)", max_chars=400, key="hack_proj_desc")
        
        # Winner / Runner-up note
        if result in ["Winner", "Runner-up"]:
            st.info("⭐ **Please upload prize certificate**")
            
        # File Upload section with a dotted border box
        st.markdown("""
            <div style="border: 2px dashed rgba(56, 189, 248, 0.4); border-radius: 12px; padding: 15px; margin-bottom: 10px; background-color: rgba(255, 255, 255, 0.01);">
                <span style="font-weight: 600; color: #38bdf8;">📂 File Upload: Upload Prize Certificate / Participation Certificate / Screenshot (Max 5MB)</span>
            </div>
            """, unsafe_allow_html=True)
            
        uploaded_file = st.file_uploader(
            "Upload Prize Certificate / Participation Certificate / Screenshot", 
            type=["pdf", "jpg", "jpeg", "png"], 
            key="hack_file_input",
            label_visibility="collapsed"
        )
        
        if uploaded_file is not None:
            val_res = check_uploaded_file_ui(uploaded_file)
            if not val_res["valid"]:
                st.markdown(f"❌ **Invalid File:** {uploaded_file.name} | Size: {uploaded_file.size / 1024:.2f} KB | Type: {uploaded_file.type}")
                st.error(val_res["error"])
            else:
                st.markdown(f"✅ **Valid File:** {uploaded_file.name} | Size: {uploaded_file.size / 1024:.2f} KB ({uploaded_file.size / (1024*1024):.2f} MB) | Type: {uploaded_file.type}")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, width=200)
                else:
                    st.info(f"📄 PDF selected: {uploaded_file.name}")
                    
        if st.button("Submit Hackathon", type="primary", key="hack_submit_btn"):
            if not register_number or not section or not hackathon_name or not organizer or not team_name or not duration or not project_title:
                st.error("Please fill in all required fields marked with *.")
            elif github_link and not github_link.startswith("https://"):
                st.error("GitHub/Demo Link must start with https://")
            else:
                with st.spinner("Validating your submission..."):
                    # Sanitize
                    s_name = sanitize_input(student_name, "text")
                    s_reg = sanitize_input(register_number, "text")
                    s_sec = sanitize_input(section, "text")
                    s_hack = sanitize_input(hackathon_name, "text")
                    s_org = sanitize_input(organizer, "text")
                    s_platform = sanitize_input(platform, "text") if platform else {"clean": "", "warnings": []}
                    s_team = sanitize_input(team_name, "text")
                    s_dur = sanitize_input(duration, "text")
                    s_proj_title = sanitize_input(project_title, "text")
                    s_proj_desc = sanitize_input(project_description, "text") if project_description else {"clean": "", "warnings": []}
                    s_git = sanitize_input(github_link, "url") if github_link else {"clean": "", "warnings": []}
                    s_members = sanitize_input(team_members, "text") if team_members else {"clean": "", "warnings": []}
                    
                    all_warnings = s_name["warnings"] + s_reg["warnings"] + s_sec["warnings"] + s_hack["warnings"] + s_org["warnings"] + s_platform["warnings"] + s_team["warnings"] + s_dur["warnings"] + s_proj_title["warnings"] + s_proj_desc["warnings"] + s_git["warnings"] + s_members["warnings"]
                    for w in all_warnings:
                        st.warning(w)
                        
                    dup_ref = st.session_state.get("hack_name_dup_ref")
                    if dup_ref:
                        log_event("DUPLICATE_DETECTED", st.session_state.username, st.session_state.role, f"Hackathon duplicate title submitted: '{s_hack['clean']}'. Existing Ref ID: {dup_ref}")
                        
                    file_url = ""
                    file_name = ""
                    if uploaded_file is not None:
                        with st.spinner("Uploading file securely..."):
                            try:
                                from utils.db import generate_reference_id
                                temp_ref = generate_reference_id("student_hackathons")
                                upload_res = secure_upload(uploaded_file, temp_ref, "student_hackathons")
                                if not upload_res["success"]:
                                    log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload Hackathon certificate: {uploaded_file.name}. Error: {upload_res['error']}")
                                    st.error(f"File upload failed: {upload_res['error']}")
                                    st.stop()
                                
                                file_url = upload_res["url"]
                                file_name = upload_res["safe_filename"]
                                log_event("FILE_UPLOADED", st.session_state.username, st.session_state.role, f"Uploaded Hackathon certificate: {file_name}")
                            except Exception as upload_err:
                                log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload Hackathon certificate: {uploaded_file.name}. Error: {upload_err}")
                                st.error(f"File upload failed: {upload_err}")
                                st.stop()
                            
                    data = {
                        "title": s_hack["clean"],
                        "team_name": s_team["clean"],
                        "rank": result,
                        "date": str(hack_date),
                        "email": f"{st.session_state.username}@aiml.edu",
                        "student_name": s_name["clean"],
                        "register_number": s_reg["clean"],
                        "semester": int(semester),
                        "section": s_sec["clean"],
                        "organizer": s_org["clean"],
                        "platform": s_platform["clean"],
                        "team_size": int(team_size),
                        "duration": s_dur["clean"],
                        "level": level,
                        "prize_amount": float(prize_amount),
                        "project_title": s_proj_title["clean"],
                        "project_description": s_proj_desc["clean"],
                        "github_link": s_git["clean"],
                        "team_members": s_members["clean"],
                        "file_url": file_url,
                        "file_name": file_name
                    }
                    
                    from agents.intake_agent import run_intake_agent
                    agent_res = run_intake_agent("student_hackathons", data, st.session_state.username)
                    
                    st.success(f"🤖 **Intake Agent Response:** {agent_res}")
                    
                    # Clear duplicate warning after successful submit
                    if "hack_name_dup_ref" in st.session_state:
                        st.session_state["hack_name_dup_ref"] = ""
                        
                    latest_ref = get_latest_submission_ref_id("student_hackathons", "register_number", s_reg["clean"])
                    render_submission_receipt(
                        ref_id=latest_ref,
                        entry_type_label="Hackathon Participation",
                        faculty_name=s_name["clean"],
                        file_uploaded=(uploaded_file is not None),
                        file_name=file_name
                    )

    with tab_comp:
        st.markdown("### 🏆 Competitions Submission Portal")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            student_name_comp = st.text_input("Student Name*", value=st.session_state.user_display_name, key="comp_stud_name")
        with col_c2:
            register_number_comp = st.text_input("Register Number*", key="comp_reg_num")
            
        col_c3, col_c4 = st.columns(2)
        with col_c3:
            semester_comp = st.selectbox("Semester*", list(range(1, 9)), key="comp_sem")
        with col_c4:
            section_comp = st.text_input("Section*", key="comp_sec")
            
        col_c5, col_c6 = st.columns(2)
        with col_c5:
            competition_name = st.text_input("Competition Name*", key="comp_name", on_change=check_title_duplicate, args=("student_competitions", "comp_name"))
        with col_c6:
            organizer_comp = st.text_input("Organizer*", key="comp_org")
            
        if st.session_state.get("comp_name_dup_ref"):
            st.warning(f"⚠️ Warning: A record with this title already exists (Ref ID: {st.session_state['comp_name_dup_ref']}). You can still submit if this is a different entry.")
            
        col_c7, col_c8 = st.columns(2)
        with col_c7:
            category = st.multiselect("Category*", ["Technical", "Coding", "Design", "Business", "Cultural", "Sports", "Quiz", "Other"], key="comp_cat")
        with col_c8:
            venue = st.text_input("Venue (optional)", key="comp_venue")
            
        col_c9, col_c10 = st.columns(2)
        with col_c9:
            comp_date = st.date_input("Date*", key="comp_date")
        with col_c10:
            level_comp = st.selectbox("Level*", ["Institution", "State", "National", "International"], key="comp_level")
            
        col_c11, col_c12 = st.columns(2)
        with col_c11:
            result_comp = st.selectbox("Result*", ["Winner", "Runner-up", "Top 3", "Top 10", "Participant"], key="comp_result")
        with col_c12:
            prize_amount_comp = st.number_input("Prize Amount (number in ₹, optional)", min_value=0, value=0, key="comp_prize")
            
        description_comp = st.text_area("Description (optional)", key="comp_desc")
        
        # File Upload section with dotted border box
        st.markdown("""
            <div style="border: 2px dashed rgba(56, 189, 248, 0.4); border-radius: 12px; padding: 15px; margin-bottom: 10px; background-color: rgba(255, 255, 255, 0.01);">
                <span style="font-weight: 600; color: #38bdf8;">📂 File Upload: Upload Certificate / Award Photo (Max 5MB)</span>
            </div>
            """, unsafe_allow_html=True)
            
        uploaded_file_comp = st.file_uploader(
            "Upload Certificate / Award Photo", 
            type=["pdf", "jpg", "jpeg", "png"], 
            key="comp_file_input",
            label_visibility="collapsed"
        )
        
        if uploaded_file_comp is not None:
            val_res_comp = check_uploaded_file_ui(uploaded_file_comp)
            if not val_res_comp["valid"]:
                st.markdown(f"❌ **Invalid File:** {uploaded_file_comp.name} | Size: {uploaded_file_comp.size / 1024:.2f} KB | Type: {uploaded_file_comp.type}")
                st.error(val_res_comp["error"])
            else:
                st.markdown(f"✅ **Valid File:** {uploaded_file_comp.name} | Size: {uploaded_file_comp.size / 1024:.2f} KB ({uploaded_file_comp.size / (1024*1024):.2f} MB) | Type: {uploaded_file_comp.type}")
                if uploaded_file_comp.type.startswith("image/"):
                    st.image(uploaded_file_comp, width=200)
                else:
                    st.info(f"📄 PDF selected: {uploaded_file_comp.name}")
                    
        if st.button("Submit Competition", type="primary", key="comp_submit_btn"):
            if not register_number_comp or not section_comp or not competition_name or not category or not organizer_comp:
                st.error("Please fill in all required fields marked with *.")
            else:
                with st.spinner("Validating your submission..."):
                    # Sanitize
                    s_name = sanitize_input(student_name_comp, "text")
                    s_reg = sanitize_input(register_number_comp, "text")
                    s_sec = sanitize_input(section_comp, "text")
                    s_comp = sanitize_input(competition_name, "text")
                    s_org = sanitize_input(organizer_comp, "text")
                    s_venue = sanitize_input(venue, "text") if venue else {"clean": "", "warnings": []}
                    s_desc = sanitize_input(description_comp, "text") if description_comp else {"clean": "", "warnings": []}
                    
                    all_warnings = s_name["warnings"] + s_reg["warnings"] + s_sec["warnings"] + s_comp["warnings"] + s_org["warnings"] + s_venue["warnings"] + s_desc["warnings"]
                    for w in all_warnings:
                        st.warning(w)
                        
                    dup_ref = st.session_state.get("comp_name_dup_ref")
                    if dup_ref:
                        log_event("DUPLICATE_DETECTED", st.session_state.username, st.session_state.role, f"Competition duplicate title submitted: '{s_comp['clean']}'. Existing Ref ID: {dup_ref}")
                        
                    file_url = ""
                    file_name = ""
                    if uploaded_file_comp is not None:
                        with st.spinner("Uploading file securely..."):
                            try:
                                from utils.db import generate_reference_id
                                temp_ref = generate_reference_id("student_competitions")
                                upload_res = secure_upload(uploaded_file_comp, temp_ref, "student_competitions")
                                if not upload_res["success"]:
                                    log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload Competition certificate: {uploaded_file_comp.name}. Error: {upload_res['error']}")
                                    st.error(f"File upload failed: {upload_res['error']}")
                                    st.stop()
                                
                                file_url = upload_res["url"]
                                file_name = upload_res["safe_filename"]
                                log_event("FILE_UPLOADED", st.session_state.username, st.session_state.role, f"Uploaded Competition certificate: {file_name}")
                            except Exception as upload_err:
                                log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload Competition certificate: {uploaded_file_comp.name}. Error: {upload_err}")
                                st.error(f"File upload failed: {upload_err}")
                                st.stop()
                            
                    data = {
                        "title": s_comp["clean"],
                        "organizer": s_org["clean"],
                        "date": str(comp_date),
                        "prize": float(prize_amount_comp),
                        "email": f"{st.session_state.username}@aiml.edu",
                        "student_name": s_name["clean"],
                        "register_number": s_reg["clean"],
                        "semester": int(semester_comp),
                        "section": s_sec["clean"],
                        "category": category,
                        "venue": s_venue["clean"],
                        "level": level_comp,
                        "result": result_comp,
                        "description": s_desc["clean"],
                        "file_url": file_url,
                        "file_name": file_name
                    }
                    
                    from agents.intake_agent import run_intake_agent
                    agent_res = run_intake_agent("student_competitions", data, st.session_state.username)
                    
                    st.success(f"🤖 **Intake Agent Response:** {agent_res}")
                    
                    # Clear duplicate warning after successful submit
                    if "comp_name_dup_ref" in st.session_state:
                        st.session_state["comp_name_dup_ref"] = ""
                        
                    latest_ref = get_latest_submission_ref_id("student_competitions", "register_number", s_reg["clean"])
                    render_submission_receipt(
                        ref_id=latest_ref,
                        entry_type_label="Competition Submission",
                        faculty_name=s_name["clean"],
                        file_uploaded=(uploaded_file_comp is not None),
                        file_name=file_name
                    )

    with tab_cert:
        st.markdown("### 🎓 Course Certification Submission Portal")
        
        col_ce1, col_ce2 = st.columns(2)
        with col_ce1:
            student_name_cert = st.text_input("Student Name*", value=st.session_state.user_display_name, key="cert_stud_name")
        with col_ce2:
            register_number_cert = st.text_input("Register Number*", key="cert_reg_num")
            
        col_ce3, col_ce4 = st.columns(2)
        with col_ce3:
            semester_cert = st.selectbox("Semester*", list(range(1, 9)), key="cert_sem")
        with col_ce4:
            certification_name = st.text_input("Certification Name*", key="cert_name", on_change=check_title_duplicate, args=("student_certifications", "cert_name"))
            
        if st.session_state.get("cert_name_dup_ref"):
            st.warning(f"⚠️ Warning: A record with this title already exists (Ref ID: {st.session_state['cert_name_dup_ref']}). You can still submit if this is a different entry.")
            
        col_ce5, col_ce6 = st.columns(2)
        with col_ce5:
            issuing_platform = st.selectbox("Issuing Platform*", ["Coursera", "NPTEL", "Udemy", "Google", "Microsoft", "AWS", "IBM", "Oracle", "Cisco", "edX", "LinkedIn Learning", "Other"], key="cert_platform")
        with col_ce6:
            course_duration = st.number_input("Course Duration* (in hours)", min_value=1, value=10, key="cert_dur")
            
        col_ce7, col_ce8 = st.columns(2)
        with col_ce7:
            start_date_cert = st.date_input("Start Date (optional)", value=None, key="cert_start_date")
        with col_ce8:
            completion_date = st.date_input("Completion Date*", key="cert_comp_date")
            
        col_ce9, col_ce10 = st.columns(2)
        with col_ce9:
            certificate_id = st.text_input("Certificate ID (optional — for verification)", key="cert_id")
        with col_ce10:
            grade_score = st.text_input("Grade/Score (optional: e.g. 95%, With Distinction, Pass)", key="cert_grade")
            
        skills_covered = st.text_input("Skills Covered* (comma-separated: e.g. Python, ML, Deep Learning)", key="cert_skills")
        verified = st.checkbox("I confirm this is my original certificate", key="cert_verified")
        
        # File Upload section with dotted border box
        st.markdown("""
            <div style="border: 2px dashed rgba(56, 189, 248, 0.4); border-radius: 12px; padding: 15px; margin-bottom: 10px; background-color: rgba(255, 255, 255, 0.01);">
                <span style="font-weight: 600; color: #38bdf8;">📂 File Upload: Upload Certificate PDF or Screenshot (Max 5MB)</span>
            </div>
            """, unsafe_allow_html=True)
            
        uploaded_file_cert = st.file_uploader(
            "Upload Certificate PDF or Screenshot", 
            type=["pdf", "jpg", "jpeg", "png"], 
            key="cert_file_input",
            label_visibility="collapsed"
        )
        
        st.markdown("<p style='font-size:0.8rem; color:#94a3b8;'>Your certificate will be stored securely and used for department records only.</p>", unsafe_allow_html=True)
        
        if uploaded_file_cert is not None:
            val_res_cert = check_uploaded_file_ui(uploaded_file_cert)
            if not val_res_cert["valid"]:
                st.markdown(f"❌ **Invalid File:** {uploaded_file_cert.name} | Size: {uploaded_file_cert.size / 1024:.2f} KB | Type: {uploaded_file_cert.type}")
                st.error(val_res_cert["error"])
            else:
                st.markdown(f"✅ **Valid File:** {uploaded_file_cert.name} | Size: {uploaded_file_cert.size / 1024:.2f} KB ({uploaded_file_cert.size / (1024*1024):.2f} MB) | Type: {uploaded_file_cert.type}")
                if uploaded_file_cert.type.startswith("image/"):
                    st.image(uploaded_file_cert, width=200)
                else:
                    st.info(f"📄 PDF selected: {uploaded_file_cert.name}")
                    
        if st.button("Submit Certification", type="primary", key="cert_submit_btn"):
            if not register_number_cert or not certification_name or not skills_covered or not verified:
                st.error("Please fill in all required fields marked with * and check the verification box.")
            else:
                with st.spinner("Validating your submission..."):
                    # Sanitize
                    s_name = sanitize_input(student_name_cert, "text")
                    s_reg = sanitize_input(register_number_cert, "text")
                    s_cert = sanitize_input(certification_name, "text")
                    s_id = sanitize_input(certificate_id, "text") if certificate_id else {"clean": "", "warnings": []}
                    s_grade = sanitize_input(grade_score, "text") if grade_score else {"clean": "", "warnings": []}
                    s_skills = sanitize_input(skills_covered, "text")
                    
                    all_warnings = s_name["warnings"] + s_reg["warnings"] + s_cert["warnings"] + s_id["warnings"] + s_grade["warnings"] + s_skills["warnings"]
                    for w in all_warnings:
                        st.warning(w)
                        
                    dup_ref = st.session_state.get("cert_name_dup_ref")
                    if dup_ref:
                        log_event("DUPLICATE_DETECTED", st.session_state.username, st.session_state.role, f"Certification duplicate title submitted: '{s_cert['clean']}'. Existing Ref ID: {dup_ref}")
                        
                    file_url = ""
                    file_name = ""
                    if uploaded_file_cert is not None:
                        with st.spinner("Uploading file securely..."):
                            try:
                                from utils.db import generate_reference_id
                                temp_ref = generate_reference_id("student_certifications")
                                upload_res = secure_upload(uploaded_file_cert, temp_ref, "student_certifications")
                                if not upload_res["success"]:
                                    log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload Certification certificate: {uploaded_file_cert.name}. Error: {upload_res['error']}")
                                    st.error(f"File upload failed: {upload_res['error']}")
                                    st.stop()
                                
                                file_url = upload_res["url"]
                                file_name = upload_res["safe_filename"]
                                log_event("FILE_UPLOADED", st.session_state.username, st.session_state.role, f"Uploaded Certification certificate: {file_name}")
                            except Exception as upload_err:
                                log_event("FILE_UPLOAD_FAILED", st.session_state.username, st.session_state.role, f"Failed to upload Certification certificate: {uploaded_file_cert.name}. Error: {upload_err}")
                                st.error(f"File upload failed: {upload_err}")
                                st.stop()
                            
                    data = {
                        "title": s_cert["clean"],
                        "issuer": issuing_platform,
                        "date": str(completion_date),
                        "email": f"{st.session_state.username}@aiml.edu",
                        "student_name": s_name["clean"],
                        "register_number": s_reg["clean"],
                        "semester": int(semester_cert),
                        "course_duration_hours": float(course_duration),
                        "start_date": str(start_date_cert) if start_date_cert else "",
                        "certificate_id": s_id["clean"],
                        "grade_score": s_grade["clean"],
                        "skills_covered": s_skills["clean"],
                        "verified_original": bool(verified),
                        "file_url": file_url,
                        "file_name": file_name
                    }
                    
                    from agents.intake_agent import run_intake_agent
                    agent_res = run_intake_agent("student_certifications", data, st.session_state.username)
                    
                    st.success(f"🤖 **Intake Agent Response:** {agent_res}")
                    
                    # Clear duplicate warning after successful submit
                    if "cert_name_dup_ref" in st.session_state:
                        st.session_state["cert_name_dup_ref"] = ""
                        
                    latest_ref = get_latest_submission_ref_id("student_certifications", "register_number", s_reg["clean"])
                    render_submission_receipt(
                        ref_id=latest_ref,
                        entry_type_label="Course Certification",
                        faculty_name=s_name["clean"],
                        file_uploaded=(uploaded_file_cert is not None),
                        file_name=file_name
                    )

    # --- TRACK MY SUBMISSIONS ---
    st.markdown("---")
    st.markdown("### 🔍 Track My Submissions")
    
    with st.expander("My Submissions", expanded=False):
        show_student_submissions(st.session_state.username)



# --- UNIVERSAL VIEW & DOWNLOAD PAGE (MY RECORDS) ---
def render_my_records_page():
    require_auth(allowed_roles=["Faculty", "Student", "HoD"])
    st.write(f"Logged in as: **{st.session_state.user_display_name}** | Role: **{st.session_state.role}**")
    st.markdown("### 📁 My Submissions & Records")
    
    import utils.db as db
    import requests
    from utils.audit import log_event
    
    email_val = f"{st.session_state.username}@aiml.edu"
    role = st.session_state.role
    
    @st.cache_data(show_spinner=False)
    def get_url_file_bytes(url):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                return res.content
        except Exception:
            pass
        return b""
        
    if role == "Faculty":
        fdp_recs = db.get_records_by_field("faculty_fdp", "email", email_val)
        pub_recs = db.get_records_by_field("faculty_publications", "email", email_val)
        wks_recs = db.get_records_by_field("faculty_workshops", "email", email_val)
        
        all_recs = []
        for r in fdp_recs:
            all_recs.append((r, "Faculty Development Program (FDP)"))
        for r in pub_recs:
            all_recs.append((r, "Research Publication"))
        for r in wks_recs:
            all_recs.append((r, "Workshop / Seminar"))
            
        if not all_recs:
            st.info("No activity submissions found for your account.")
            return
            
        st.markdown(f"Total Submissions found: **{len(all_recs)}**")
        
        for r, cat in all_recs:
            ref_id = r.get("reference_id", "N/A")
            title = r.get("title", "Untitled")
            date = r.get("start_date") or r.get("publication_date") or r.get("date") or "N/A"
            status = r.get("status", "Submitted")
            file_url = r.get("file_url")
            file_name = r.get("file_name") or "certificate.pdf"
            
            is_verified = r.get("verified", False)
            is_flagged = r.get("flagged", False)
            
            with st.container(border=True):
                st.markdown(f"#### {title}")
                st.markdown(f"**Category:** `{cat}`")
                
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.markdown(f"**Reference ID:** `{ref_id}`")
                    st.markdown(f"**Date:** {date}")
                with col_info2:
                    status_badge = f"<span class='badge badge-primary'>{status}</span>"
                    if is_verified:
                        status_badge += " <span style='background-color: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 9999px; padding: 4px 8px; font-size: 0.8rem; font-weight: 600;'>✓ Verified</span>"
                    if is_flagged:
                        status_badge += " <span style='background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 9999px; padding: 4px 8px; font-size: 0.8rem; font-weight: 600;'>🚩 Flagged</span>"
                    st.markdown(f"**Status:** {status_badge}", unsafe_allow_html=True)
                
                if file_url:
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        st.link_button("📄 View Certificate", file_url, use_container_width=True, key=f"view_rec_{ref_id}")
                    with col_btn2:
                        file_bytes = get_url_file_bytes(file_url)
                        if file_bytes:
                            st.download_button(
                                label="⬇️ Download",
                                data=file_bytes,
                                file_name=file_name,
                                key=f"dl_fac_rec_{ref_id}",
                                use_container_width=True
                            )
                        else:
                            st.button("Download Unavailable", disabled=True, use_container_width=True, key=f"dl_fac_rec_err_{ref_id}")
                            
    elif role == "Student":
        hack_recs = db.get_records_by_field("student_hackathons", "email", email_val)
        comp_recs = db.get_records_by_field("student_competitions", "email", email_val)
        cert_recs = db.get_records_by_field("student_certifications", "email", email_val)
        
        all_recs = []
        for r in hack_recs:
            all_recs.append((r, "Hackathon Participation"))
        for r in comp_recs:
            all_recs.append((r, "Competition Entry"))
        for r in cert_recs:
            all_recs.append((r, "Course Certification"))
            
        if not all_recs:
            st.info("No submissions found for your account.")
            return
            
        st.markdown(f"Total Submissions found: **{len(all_recs)}**")
        stud_records = {
            "Hackathons": hack_recs,
            "Competitions": comp_recs,
            "Certifications": cert_recs
        }
        excel_bytes = export_my_records_excel(stud_records, st.session_state.user_display_name, st.session_state.username)
        st.download_button(
            label="⬇️ Download My Data (Excel)",
            data=excel_bytes,
            file_name=f"student_records_{st.session_state.username}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_stud_my_records_page_btn",
            use_container_width=True,
            on_click=lambda: log_event("EXPORT_GENERATED", st.session_state.username, st.session_state.role, f"Exported student data Excel via My Records page")
        )
        st.markdown("---")
        
        for r, cat in all_recs:
            ref_id = r.get("reference_id", "N/A")
            title = r.get("title", "Untitled")
            date = r.get("date", "N/A")
            status = r.get("status", "Submitted")
            file_url = r.get("file_url")
            file_name = r.get("file_name") or "certificate.pdf"
            
            is_verified = r.get("verified", False)
            is_flagged = r.get("flagged", False)
            
            rank_val = str(r.get("rank", "")).strip().lower()
            result_val = str(r.get("result", "")).strip().lower()
            is_winner = (rank_val == "winner" or result_val == "winner")
            
            with st.container(border=True):
                st.markdown(f"#### {title}")
                st.markdown(f"**Category:** `{cat}`")
                
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.markdown(f"**Reference ID:** `{ref_id}`")
                    st.markdown(f"**Date:** {date}")
                with col_info2:
                    status_badge = f"<span class='badge badge-primary'>{status}</span>"
                    if is_verified:
                        status_badge += " <span style='background-color: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 9999px; padding: 4px 8px; font-size: 0.8rem; font-weight: 600;'>✓ Verified</span>"
                    if is_flagged:
                        status_badge += " <span style='background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 9999px; padding: 4px 8px; font-size: 0.8rem; font-weight: 600;'>🚩 Flagged</span>"
                    if is_winner:
                        status_badge += " <span style='background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 9999px; padding: 4px 8px; font-size: 0.8rem; font-weight: 600;'>🏆 Result: Winner</span>"
                    st.markdown(f"**Status:** {status_badge}", unsafe_allow_html=True)
                
                if file_url:
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        st.link_button("📄 View Certificate", file_url, use_container_width=True, key=f"view_rec_{ref_id}")
                    with col_btn2:
                        file_bytes = get_url_file_bytes(file_url)
                        if file_bytes:
                            st.download_button(
                                label="⬇️ Download",
                                data=file_bytes,
                                file_name=file_name,
                                key=f"dl_stud_rec_{ref_id}",
                                use_container_width=True
                            )
                        else:
                            st.button("Download Unavailable", disabled=True, use_container_width=True, key=f"dl_stud_rec_err_{ref_id}")


# --- MAIN APP ROUTER ---
def main():
    # Verify all required secrets exist on app startup
    if not secrets_check():
        st.stop()

    # Run auth guard check first - handles login display, inactivity timeouts, and blocks unauthorized roles
    require_auth()

    # Render main dashboard layout
    st.markdown("<h1 class='main-title'>AIML Department Intelligence Hub</h1>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Department of Artificial Intelligence & Machine Learning</p>", unsafe_allow_html=True)

    # Render User Profile details and Logout button in sidebar
    show_user_info()

    st.sidebar.markdown("### ⚙️ Navigation Panel")
    
    # Sidebar Role Selector - allows navigating to other views if user has permission
    current_role = st.session_state.get("role", "Student")
    selected_role = st.sidebar.selectbox(
        "Access Dashboard Role",
        ["Faculty", "Student", "HoD"],
        index=["Faculty", "Student", "HoD"].index(current_role) if current_role in ["Faculty", "Student", "HoD"] else 1
    )
    
    # Page navigation item for Faculty/Student
    nav_item = "Dashboard"
    if selected_role in ["Faculty", "Student"]:
        nav_item = st.sidebar.radio("Select View", ["Dashboard", "My Records"], key="sidebar_nav_view")
    
    # In app.py sidebar (HoD only) — add Live Stats and Audit Log section
    if current_role == "HoD":
        # ----------------------------------------------------
        # SIDEBAR STATS (FEATURE 5)
        # ----------------------------------------------------
        import utils.db as db
        from datetime import datetime
        
        all_cols = [
            "faculty_fdp", "faculty_publications", "faculty_workshops",
            "student_hackathons", "student_competitions", "student_certifications"
        ]
        
        today_count = 0
        month_count = 0
        with_cert_count = 0
        total_count = 0
        
        faculty_submissions = {}
        
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)
        month_start = datetime(now.year, now.month, 1)
        
        for col in all_cols:
            recs = db.get_all_records(col)
            for r in recs:
                total_count += 1
                if r.get("file_url"):
                    with_cert_count += 1
                    
                c_at = r.get("created_at")
                if c_at:
                    if not isinstance(c_at, datetime):
                        try:
                            c_at = datetime.fromisoformat(str(c_at))
                        except Exception:
                            continue
                    if c_at.tzinfo is not None:
                        c_at = c_at.replace(tzinfo=None)
                        
                    if c_at >= today_start:
                        today_count += 1
                    if c_at >= month_start:
                        month_count += 1
                        
                if col.startswith("faculty_"):
                    fac_name = r.get("faculty_name")
                    if fac_name:
                        faculty_submissions[fac_name] = faculty_submissions.get(fac_name, 0) + 1
                        
        cert_percentage = 0
        if total_count > 0:
            cert_percentage = int((with_cert_count / total_count) * 100)
            
        most_active_faculty = "N/A"
        if faculty_submissions:
            most_active_faculty = max(faculty_submissions, key=faculty_submissions.get)
            
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📊 Live Activity Stats")
        st.sidebar.markdown(f"📅 **Today's Submissions:** `{today_count}`")
        st.sidebar.markdown(f"🗓️ **This Month:** `{month_count}`")
        st.sidebar.markdown(f"📄 **With Certificates:** `{cert_percentage}%` of total")
        st.sidebar.markdown(f"🏆 **Most Active Faculty:** *{most_active_faculty}*")
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🛡️ Audit Log")
        
        # Show last 100 audit events as a table
        import utils.db as db
        try:
            audit_events = db.get_all_records(db.AUDIT_LOG)
        except Exception as e:
            audit_events = []
            st.sidebar.error(f"Failed to fetch audit log: {e}")
            
        if audit_events:
            # Sort by timestamp desc
            audit_events = sorted(
                audit_events,
                key=lambda x: x.get("timestamp") or datetime.min,
                reverse=True
            )
            last_100 = audit_events[:100]
            
            # Create DataFrame
            df = pd.DataFrame(last_100)
            
            # Select columns
            cols = ["timestamp", "event_type", "username", "role", "details", "session_id"]
            for col in cols:
                if col not in df.columns:
                    df[col] = ""
            df = df[cols]
            
            # Format timestamp for display
            df["timestamp"] = df["timestamp"].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if hasattr(x, "strftime") else str(x)
            )
            
            # Color-code rows: red for FAILED/SUSPICIOUS, green for SUCCESS, amber for LIMIT events
            def style_rows(row):
                et = str(row["event_type"]).upper()
                if "FAILED" in et or "SUSPICIOUS" in et or "DENIED" in et:
                    return ["background-color: rgba(239, 68, 68, 0.2); color: #f87171;"] * len(row)
                elif "SUCCESS" in et or "SUBMITTED" in et or "UPLOADED" in et or "GENERATED" in et or "DOWNLOADED" in et:
                    return ["background-color: rgba(34, 197, 94, 0.2); color: #4ade80;"] * len(row)
                elif "LIMIT" in et:
                    return ["background-color: rgba(245, 158, 11, 0.2); color: #fbbf24;"] * len(row)
                return [""] * len(row)
                
            styled_df = df.style.apply(style_rows, axis=1)
            
            # Render table in sidebar
            st.sidebar.dataframe(styled_df, use_container_width=True, hide_index=True)
            
            # Export Audit Log button that downloads as CSV
            csv_data = df.to_csv(index=False).encode("utf-8")
            
            st.sidebar.download_button(
                label="📥 Export Audit Log (CSV)",
                data=csv_data,
                file_name="audit_log.csv",
                mime="text/csv",
                on_click=lambda: log_event("EXPORT_GENERATED", st.session_state.username, st.session_state.role, "Exported audit log to CSV"),
                use_container_width=True
            )
        else:
            st.sidebar.info("No audit logs found.")
    
    # Route based on selected dashboard role, enforcing credentials on each path
    if selected_role == "HoD":
        require_auth(allowed_roles=["HoD"])
        render_hod_dashboard()
    elif selected_role == "Faculty":
        require_auth(allowed_roles=["Faculty", "HoD"])
        if nav_item == "My Records":
            render_my_records_page()
        else:
            render_faculty_dashboard()
    else:
        require_auth(allowed_roles=["Student", "Faculty", "HoD"])
        if nav_item == "My Records":
            render_my_records_page()
        else:
            render_student_dashboard()


if __name__ == "__main__":
    main()
