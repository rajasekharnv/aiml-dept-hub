import re
from datetime import datetime, timedelta
import dateutil.parser

def sanitize_input(value, field_type: str) -> dict:
    """
    Sanitizes and validates an input value based on the specified field_type.
    Returns: {"clean": cleaned_value, "warnings": [list of warning strings]}
    """
    warnings = []
    cleaned_value = None
    
    if value is None:
        return {"clean": None, "warnings": ["Input value cannot be None."]}
        
    val_str = str(value)
    
    if field_type == "text":
        # 1. Strip whitespace
        val_str = val_str.strip()
        
        # 2. Remove HTML tags (regex)
        html_regex = re.compile(r'<[^>]*>')
        if html_regex.search(val_str):
            val_str = html_regex.sub('', val_str)
            warnings.append("HTML tags were removed from the input.")
            
        # 3. Remove control characters (ASCII 0-31 and 127-159)
        control_regex = re.compile(r'[\x00-\x1f\x7f-\x9f]')
        if control_regex.search(val_str):
            val_str = control_regex.sub('', val_str)
            warnings.append("Control characters were removed from the input.")
            
        # 4. Max 500 characters
        if len(val_str) > 500:
            val_str = val_str[:500]
            warnings.append("Input exceeded 500 characters and was truncated.")
            
        cleaned_value = val_str
        
    elif field_type == "url":
        val_str = val_str.strip()
        
        # Check scheme
        val_lower = val_str.lower()
        if val_lower.startswith("javascript:") or val_lower.startswith("data:"):
            warnings.append("Unsafe URL scheme (javascript: or data:) is rejected.")
            cleaned_value = None
        elif not val_str.startswith("https://"):
            warnings.append("URL must start with https://.")
            cleaned_value = None
        elif len(val_str) > 300:
            warnings.append("URL exceeds the maximum limit of 300 characters.")
            cleaned_value = None
        else:
            cleaned_value = val_str
            
    elif field_type == "number":
        try:
            val_num = float(value)
            if val_num < 0:
                val_num = 0.0
                warnings.append("Value must be positive. Coerced to 0.0.")
            elif val_num > 999999:
                val_num = 999999.0
                warnings.append("Value exceeds maximum allowed limit. Coerced to 999999.0.")
            cleaned_value = val_num
        except (ValueError, TypeError):
            warnings.append("Input is not a valid number.")
            cleaned_value = 0.0
            
    elif field_type == "date":
        val_str = val_str.strip()
        try:
            # Parse with dateutil
            parsed_dt = dateutil.parser.parse(val_str)
            parsed_date = parsed_dt.date()
            
            # Must be within last 10 years to today
            today = datetime.now().date()
            ten_years_ago = today - timedelta(days=10 * 365.25)
            
            if parsed_date < ten_years_ago:
                warnings.append("Date must be within the last 10 years.")
                cleaned_value = None
            elif parsed_date > today:
                warnings.append("Date cannot be in the future.")
                cleaned_value = None
            else:
                cleaned_value = parsed_date.isoformat()
        except Exception:
            warnings.append("Input is not a valid date format.")
            cleaned_value = None
            
    elif field_type == "email":
        val_str = val_str.strip().lower()
        
        # Basic regex check
        email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_regex, val_str):
            warnings.append("Invalid email address format.")
            
        cleaned_value = val_str
        
    elif field_type == "filename":
        val_str = val_str.strip()
        
        # Remove path separators and directories
        clean_name = val_str.replace('/', '').replace('\\', '').replace('..', '')
        if clean_name != val_str:
            warnings.append("Path traversal sequences were removed from the filename.")
            
        # Allow only alphanumeric + dash + dot + underscore
        sanitized = re.sub(r'[^a-zA-Z0-9\-\._]', '', clean_name)
        if sanitized != clean_name:
            warnings.append("Special characters were removed from the filename.")
            
        cleaned_value = sanitized
    else:
        warnings.append(f"Unknown field type: {field_type}.")
        cleaned_value = val_str

    return {"clean": cleaned_value, "warnings": warnings}

def sanitize_text(text: str) -> str:
    """
    Sanitizes plain text to prevent HTML/Script injection.
    """
    import html
    if not text:
        return ""
    return html.escape(text.strip())

