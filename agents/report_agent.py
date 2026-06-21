import os
import asyncio
from datetime import datetime
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import utils.db as db

# 1. Tool Function: get_faculty_data
def get_faculty_data(collection: str) -> list:
    """
    Fetches all records from a faculty collection.
    Allowed collections are: faculty_fdp, faculty_publications, faculty_workshops.
    
    Args:
        collection: The name of the faculty collection to fetch.
        
    Returns:
        A list of record dictionaries.
    """
    allowed = ["faculty_fdp", "faculty_publications", "faculty_workshops"]
    if collection not in allowed:
        return [{"error": f"Collection '{collection}' is not a valid faculty collection. Allowed: {allowed}"}]
    return db.get_all_records(collection)

# 2. Tool Function: get_student_data
def get_student_data(collection: str) -> list:
    """
    Fetches all records from a student collection.
    Allowed collections are: student_hackathons, student_competitions, student_certifications.
    
    Args:
        collection: The name of the student collection to fetch.
        
    Returns:
        A list of record dictionaries.
    """
    allowed = ["student_hackathons", "student_competitions", "student_certifications"]
    if collection not in allowed:
        return [{"error": f"Collection '{collection}' is not a valid student collection. Allowed: {allowed}"}]
    return db.get_all_records(collection)

# 3. Tool Function: get_count_by_field
def get_count_by_field(collection: str, group_field: str) -> dict:
    """
    Groups and counts the number of records in a collection by a specified field.
    
    Args:
        collection: The Firestore collection name.
        group_field: The field name to group by.
        
    Returns:
        A dictionary mapping group values to counts.
    """
    records = db.get_all_records(collection)
    counts = {}
    for r in records:
        val = str(r.get(group_field, "Unknown"))
        counts[val] = counts.get(val, 0) + 1
    return counts

# 4. Tool Function: filter_records
def filter_records(collection: str, filters: dict) -> list:
    """
    Filters records in a collection matching multiple criteria.
    Filters can include fields like: year, month, level, result, indexed_in, role.
    
    Args:
        collection: The Firestore collection name.
        filters: A dictionary of key-value criteria to filter by.
        
    Returns:
        A list of filtered record dictionaries.
    """
    records = db.get_all_records(collection)
    filtered = []
    for r in records:
        match = True
        for k, v in filters.items():
            # Check for substring or strict equality case-insensitively
            r_val = str(r.get(k, "")).lower()
            v_val = str(v).lower()
            if v_val not in r_val:
                match = False
                break
        if match:
            filtered.append(r)
    return filtered

# 5. Tool Function: get_all_collections_summary
def get_all_collections_summary() -> dict:
    """
    Returns the total active document counts across all 6 primary department collections.
    
    Returns:
        A dictionary containing collection names and their document counts.
    """
    collections = [
        "faculty_fdp", "faculty_publications", "faculty_workshops",
        "student_hackathons", "student_competitions", "student_certifications"
    ]
    summary = {}
    for col in collections:
        summary[col] = db.get_count(col)
    return summary

# 6. Tool Function: search_by_name
def search_by_name(collection: str, name: str) -> list:
    """
    Performs a case-insensitive partial substring search for a name in a collection.
    Checks common fields like 'name', 'student', 'author', 'speaker', and 'posted_by'.
    
    Args:
        collection: The Firestore collection name.
        name: The name or partial string to search for.
        
    Returns:
        A list of matching record dictionaries.
    """
    records = db.get_all_records(collection)
    name_lower = name.lower()
    results = []
    
    name_fields = ["name", "student", "author", "speaker", "posted_by"]
    for r in records:
        found = False
        for field in name_fields:
            if field in r and r[field] and name_lower in str(r[field]).lower():
                found = True
                break
        if found:
            results.append(r)
    return results

# Wrap functions in ADK FunctionTool
get_faculty_data_tool = FunctionTool(get_faculty_data)
get_student_data_tool = FunctionTool(get_student_data)
get_count_by_field_tool = FunctionTool(get_count_by_field)
filter_records_tool = FunctionTool(filter_records)
get_all_collections_summary_tool = FunctionTool(get_all_collections_summary)
search_by_name_tool = FunctionTool(search_by_name)

# Define system instruction
SYSTEM_INSTRUCTION = """You are the HoD's intelligent report assistant for an AIML department.
You answer natural language questions about faculty and student activities.
You fetch real data from Firestore and generate structured, formatted responses.
You understand NAAC, NBA, and AICTE reporting requirements.
Always provide counts, percentages, and specific names when available.
Format your responses clearly with sections, bullet points, and summaries.
Never reveal raw database IDs or internal system details."""

# Instantiate the ADK Agent
report_assistant = Agent(
    name="report_assistant",
    model="gemini-2.0-flash",
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        get_faculty_data_tool,
        get_student_data_tool,
        get_count_by_field_tool,
        filter_records_tool,
        get_all_collections_summary_tool,
        search_by_name_tool
    ]
)

# Wrapper class to match original scaffold interface
class ReportAgent:
    def __init__(self):
        self.name = "report_agent"
        self.adk_agent = report_assistant

    def generate_report(self, report_type: str) -> str:
        """
        Runs the ReportAgent with the report type as the prompt.
        """
        return run_report_agent(f"Generate a report for: {report_type}", "hod")

async def _run_report_async(prompt: str, username: str) -> str:
    """
    Asynchronous runner executing the ADK session loop for ReportAgent.
    """
    session_service = InMemorySessionService()
    session_id = f"session_{os.urandom(4).hex()}"
    await session_service.create_session(app_name="app", user_id=username, session_id=session_id)
    
    runner = Runner(agent=report_assistant, app_name="app", session_service=session_service)
    
    response_text = ""
    async for event in runner.run_async(
        user_id=username,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                response_text = event.content.parts[0].text
            break
            
    if not response_text:
        response_text = "The report agent did not return a response."
        
    # Append the required data source and timestamp suffix
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    response_text += f"\n\nReport generated on {timestamp} | Data source: Firestore"
    
    return response_text

def run_report_agent(prompt: str, username: str) -> str:
    """
    Exposed function to run the ReportAgent synchronously.
    The response must always end with: "Report generated on {datetime} | Data source: Firestore"
    """
    import streamlit as st
    from utils.prompt_guard import is_safe_prompt, validate_agent_output
    from utils.audit import log_event
    
    actual_username = st.session_state.get("username", username)
    role = st.session_state.get("role", "HoD")
    
    # 1. Call is_safe_prompt() on the HoD prompt
    safe_res = is_safe_prompt(prompt)
    if not safe_res.get("safe", True):
        # 2. If unsafe: log SUSPICIOUS_INPUT, return "Invalid query detected. Please rephrase."
        log_event("SUSPICIOUS_INPUT", actual_username, role, f"Blocked report query: {prompt}. Reason: {safe_res.get('reason')}")
        return "Invalid query detected. Please rephrase."
        
    # 3. Rate limit: max 50 report queries per user per session
    if "report_queries_tracker" not in st.session_state:
        st.session_state.report_queries_tracker = {}
        
    user_queries = st.session_state.report_queries_tracker.get(actual_username, 0)
    if user_queries >= 50:
        log_event("RATE_LIMIT_HIT", actual_username, role, f"User {actual_username} hit session limit of 50 report queries")
        return "Rate limit exceeded. Maximum 50 report queries per user per session."
        
    # Increment counter
    st.session_state.report_queries_tracker[actual_username] = user_queries + 1
    
    # Call the actual agent
    response = asyncio.run(_run_report_async(prompt, username))
    
    # 4. After agent responds: call validate_agent_output() to redact any sensitive data
    clean_response = validate_agent_output(response)
    
    # 5. Log REPORT_GENERATED with first 100 chars of prompt
    log_event("REPORT_GENERATED", actual_username, role, f"Report query: {prompt[:100]}")
    
    return clean_response

