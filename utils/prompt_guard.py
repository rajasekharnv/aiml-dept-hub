import re

# Injection patterns as requested by the user
INJECTION_PATTERNS = [
    "ignore previous",
    "forget instructions",
    "you are now",
    "act as",
    "jailbreak",
    "system:",
    "###",
    ">>>",
    "<script",
    "DROP TABLE",
    "SELECT *",
    "rm -rf",
    "__import__"
]

def is_safe_prompt(user_input: str) -> dict:
    """
    Checks if a prompt contains potential injection keywords or exceeds character limits.
    Returns: {"safe": bool, "reason": str}
    """
    if not user_input:
        return {"safe": True, "reason": ""}
        
    # 1. Length check: reject if > 2000 characters
    if len(user_input) > 2000:
        return {
            "safe": False,
            "reason": f"Prompt length of {len(user_input)} exceeds the maximum limit of 2000 characters."
        }
        
    user_input_lower = user_input.lower()
    
    # 2. Check for injection patterns
    for pattern in INJECTION_PATTERNS:
        if pattern.lower() in user_input_lower:
            return {
                "safe": False,
                "reason": f"Potential prompt injection pattern detected: '{pattern}'"
            }
            
    return {"safe": True, "reason": ""}

def validate_agent_output(response_text: str) -> str:
    """
    Validates and cleans agent output by redacting sensitive data.
    - Redacts email patterns -> [EMAIL REDACTED]
    - Redacts phone patterns -> [PHONE REDACTED]
    - Redacts alphanumeric strings > 35 chars (API keys) -> [KEY REDACTED]
    """
    if not response_text:
        return ""
        
    cleaned = response_text
    
    # 1. Redact email patterns
    email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    cleaned = re.sub(email_regex, "[EMAIL REDACTED]", cleaned)
    
    # 2. Redact phone patterns
    # Matches various formats: +1-123-456-7890, 123-456-7890, 555-0199, +91 99999-99999 etc.
    phone_regex = r"\+?(?:\b\d{1,4}[-.\s]?)?\(?\d{2,5}\)?[-.\s]?\d{3,5}(?:[-.\s]?\d{3,5})?\b"
    cleaned = re.sub(phone_regex, "[PHONE REDACTED]", cleaned)
    
    # 3. Redact alphanumeric strings > 35 chars (possible API keys)
    # Match any word boundaries containing only letters and numbers of length 36 or more
    key_regex = r"\b[a-zA-Z0-9]{36,}\b"
    cleaned = re.sub(key_regex, "[KEY REDACTED]", cleaned)
    
    return cleaned
