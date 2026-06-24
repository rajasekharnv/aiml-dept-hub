import os
import asyncio
import streamlit as st
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from utils.validators import validate_entry
from utils.db import check_duplicate, save_entry, generate_reference_id

# Wrap function tools for the ADK agent
validate_tool = FunctionTool(validate_entry)
duplicate_tool = FunctionTool(check_duplicate)
save_tool = FunctionTool(save_entry)
generate_id_tool = FunctionTool(generate_reference_id)

# Define System Instruction
SYSTEM_INSTRUCTION = """You are a data intake assistant for an AIML department at an engineering college.
Your job is to receive faculty and student activity submissions, validate all fields,
check for duplicate entries, generate a unique reference ID, save metadata to Firestore,
and confirm the submission with a friendly summary. Always address the user by name.
If data is missing or invalid, clearly ask for the specific missing information."""

# Instantiate the ADK Agent
intake_assistant = Agent(
    name="intake_assistant",
    model="gemini-flash-lite-latest",
    instruction=SYSTEM_INSTRUCTION,
    tools=[validate_tool, duplicate_tool, save_tool, generate_id_tool]
)

# Wrapper class to match scaffold interface if required
class IntakeAgent:
    def __init__(self):
        self.name = "intake_agent"
        self.adk_agent = intake_assistant

    def process_query(self, query: str, user_role: str) -> str:
        """
        Fallback simple query processing.
        """
        return run_intake_agent(user_role, {"query": query}, "user")

async def _run_agent_async(entry_type: str, data_dict: dict, username: str) -> str:
    """
    Asynchronous runner executing the ADK session loop.
    """
    session_service = InMemorySessionService()
    session_id = f"session_{os.urandom(4).hex()}"
    await session_service.create_session(app_name="app", user_id=username, session_id=session_id)
    
    runner = Runner(agent=intake_assistant, app_name="app", session_service=session_service)
    
    prompt = f"User '{username}' is submitting an activity of type '{entry_type}' with data: {data_dict}."
    
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
            
    # Default fallback if agent didn't return text
    if not response_text:
        response_text = "The intake agent successfully processed your request."
        
    return response_text

def run_intake_agent(entry_type: str, data_dict: dict, username: str) -> str:
    """
    Exposed function to run the IntakeAgent synchronously.
    The file upload URL should already be in data_dict as 'file_url' before calling this agent.
    """
    from utils.prompt_guard import is_safe_prompt
    from utils.audit import log_event
    from datetime import date, datetime, timedelta
    
    actual_username = st.session_state.get("username", username)
    role = st.session_state.get("role", "Student" if actual_username.startswith("stu_") else "Faculty")
    
    # 1. Call is_safe_prompt() on all text fields combined
    text_fields = []
    for k, v in data_dict.items():
        if isinstance(v, str):
            text_fields.append(v)
    combined_text = " ".join(text_fields)
    
    safe_res = is_safe_prompt(combined_text)
    # 2. If unsafe: log SUSPICIOUS_INPUT to audit, show red warning, return without calling agent
    if not safe_res.get("safe", True):
        log_event("SUSPICIOUS_INPUT", actual_username, role, f"Intake query blocked. Reason: {safe_res.get('reason')}. Data: {data_dict}")
        st.error(f"⚠️ Unsafe input detected: {safe_res.get('reason')}")
        return "Submission blocked due to suspicious input validation failure."
        
    # 3. Rate limit: track in session_state — max 30 submissions per user per day
    if "submissions_tracker" not in st.session_state:
        st.session_state.submissions_tracker = {}
        
    today_str = str(date.today())
    user_tracker = st.session_state.submissions_tracker.get(actual_username, {"date": today_str, "count": 0})
    
    if user_tracker.get("date") != today_str:
        user_tracker = {"date": today_str, "count": 0}
        
    if user_tracker.get("count", 0) >= 30:
        log_event("RATE_LIMIT_HIT", actual_username, role, f"User {actual_username} hit daily submission limit (30)")
        
        tomorrow = date.today() + timedelta(days=1)
        reset_time = datetime.combine(tomorrow, datetime.min.time())
        reset_time_str = reset_time.strftime("%Y-%m-%d %H:%M:%S")
        st.warning(f"⚠️ Daily submission limit exceeded (max 30/day). Resets at {reset_time_str}")
        return "Submission blocked due to daily rate limit."
        
    # Increment count
    user_tracker["count"] += 1
    st.session_state.submissions_tracker[actual_username] = user_tracker
    
    # Call the actual agent
    response = asyncio.run(_run_agent_async(entry_type, data_dict, username))
    
    # Log success
    log_event("DATA_SUBMITTED", actual_username, role, f"Intake submission of type '{entry_type}' succeeded")
    
    return response

