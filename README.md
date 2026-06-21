# AIML Department Intelligence Hub

The **AIML Department Intelligence Hub** is a Python & Streamlit application designed for the Department of Artificial Intelligence & Machine Learning. It provides tailored workspace dashboards for Faculty, Students, and the Head of Department (HoD).

## Project Structure

```
├── app.py                     # Main Streamlit entry point
├── agents/                    # AI Agent definitions
│   ├── __init__.py
│   ├── intake_agent.py        # Student/Faculty query intake agent
│   └── report_agent.py        # Department report generator agent
├── utils/                     # Utility and helper modules
│   ├── __init__.py
│   ├── db.py                  # Firestore connection helpers
│   ├── storage.py             # Firebase Storage helpers (file uploads)
│   ├── validators.py          # Input validation helpers
│   ├── sanitizer.py           # Input sanitization helpers
│   ├── auth.py                # Authentication & password hashing helpers
│   ├── audit.py               # Audit logging helpers
│   ├── prompt_guard.py        # Prompt injection protection helpers
│   └── export.py              # PDF and Excel export helpers
├── .streamlit/
│   └── secrets.toml.example   # Streamlit credentials secrets template
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation
```

## Installation & Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure secrets**:
   Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and populate the required configuration values:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

3. **Run the application**:
   ```bash
   streamlit run app.py
   ```

## Key Modules

- **`agents/`**: Handles AI-driven behaviors, using Gemini via ADK / GenAI SDKs.
- **`utils/db.py` & `utils/storage.py`**: Integration with Firestore & Firebase Storage.
- **`utils/prompt_guard.py`**: Safety guardrail module ensuring inputs are clean before processing by LLM agents.
- **`utils/export.py`**: Exports department records and analytics reports to PDF and Excel formats.
