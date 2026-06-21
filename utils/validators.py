import re

def validate_email(email: str) -> bool:
    """
    Validates email format.
    """
    if not email:
        return False
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(email_regex, email))

def validate_phone(phone: str) -> bool:
    """
    Validates phone number format (basic format check).
    """
    if not phone:
        return False
    phone_regex = r"^\+?[0-9]{10,15}$"
    return bool(re.match(phone_regex, phone))

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validates password strength (minimum 6 characters, at least one digit and one letter).
    """
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if not any(char.isdigit() for char in password):
        return False, "Password must contain at least one digit."
    if not any(char.isalpha() for char in password):
        return False, "Password must contain at least one letter."
    return True, "Password is strong."

def validate_entry(entry_type: str, data: dict) -> dict:
    """
    Validates entry data based on the entry_type.
    Returns: {"valid": bool, "missing_fields": list, "errors": list}
    """
    errors = []
    missing_fields = []
    
    # Standardize entry_type name
    et = entry_type.strip().lower()
    
    # Required fields mapping
    required_map = {
        "faculty_fdp": ["title", "organizer", "start_date", "end_date", "email"],
        "faculty_publications": ["title", "author", "journal", "year"],
        "faculty_workshops": ["title", "speaker", "date", "venue"],
        "student_hackathons": ["title", "team_name", "rank", "date"],
        "student_competitions": ["title", "organizer", "date", "prize"],
        "student_certifications": ["title", "issuer", "date"]
    }
    
    # Try finding with prefix
    req_fields = required_map.get(et)
    if req_fields is None:
        for prefix in ["faculty_", "student_"]:
            if required_map.get(prefix + et):
                req_fields = required_map.get(prefix + et)
                break
                
    if req_fields is None:
        errors.append(f"Unknown entry type: '{entry_type}'.")
        return {"valid": False, "missing_fields": [], "errors": errors}
        
    for field in req_fields:
        if field not in data or data[field] is None or str(data[field]).strip() == "":
            missing_fields.append(field)
            
    # Format checks
    if "email" in data and data["email"]:
        if not validate_email(str(data["email"])):
            errors.append(f"Invalid email format: '{data['email']}'")
            
    # Check if dates are in YYYY-MM-DD format
    date_fields = ["date", "start_date", "end_date"]
    for df in date_fields:
        if df in data and data[df] and df not in missing_fields:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(data[df])):
                errors.append(f"Invalid date format for '{df}': '{data[df]}'. Expected YYYY-MM-DD.")

    valid = len(missing_fields) == 0 and len(errors) == 0
    return {
        "valid": valid,
        "missing_fields": missing_fields,
        "errors": errors
    }

