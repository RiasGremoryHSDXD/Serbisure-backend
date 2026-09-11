import re
import uuid

def convert_title(text):
    """
    Cleans and standardizes messy text by removing extra spaces and applying Title Case.

    Args:
        text (str): The raw string input from the user (e.g., " jUAn ").

    Returns:
        str: The cleaned, formatted string (e.g., "Juan"), or None if the input is empty.
    """
    if text:
        return text.strip().title()
    return text


def check_input_letters(text, text_minimum=3, text_maximum=50):
    """
    Validates that a string contains only alphabetical characters and spaces.

    Args:
        text (str): The string to validate.

    Returns:
        bool: True if the string contains only letters/spaces, False if it contains numbers/symbols.
    """

    if not text:
        return True
        
    if not all(char.isalpha() or char.isspace() for char in text):
        return False

    if not (text_minimum <= len(text) <= text_maximum):
        return False

    return True

def check_valid_uuid(id):
    """
    Checks if a string is a perfectly formatted UUID v4.
    Returns True if valid, False if invalid (e.g. "123" or "apple").
    """
    try:
        uuid.UUID(str(id), version=4)
        return True
    except ValueError:
        return False


def normalize_ph_phone_number(val):
    """
    Standardizes and normalizes any Philippine phone number variation into 
    canonical E.164 format (+639XXXXXXXXX).
    
    Accepts:
        - '+639123456789' (E.164 standard, 13 chars)
        - '09123456789'   (Standard PH local mobile, 11 chars)
        - '639123456789'  (International without +, 12 chars)
        - '9123456789'    (10-digit mobile number)
        - Numbers containing spaces, hyphens, or parentheses (e.g., '+63 912-345-6789')
        
    Returns:
        str: '+639XXXXXXXXX' (13 characters) if valid, or None if invalid.
    """
    if not val:
        return None

    raw = str(val).strip()
    # Strip spaces, dashes, parentheses, dots
    cleaned = re.sub(r'[\s\-\(\)\.]', '', raw)

    if cleaned.startswith('09') and len(cleaned) == 11 and cleaned[1:].isdigit():
        return '+63' + cleaned[1:]
    elif cleaned.startswith('639') and len(cleaned) == 12 and cleaned.isdigit():
        return '+' + cleaned
    elif cleaned.startswith('+639') and len(cleaned) == 13 and cleaned[1:].isdigit():
        return cleaned
    elif cleaned.startswith('9') and len(cleaned) == 10 and cleaned.isdigit():
        return '+63' + cleaned
    elif cleaned.startswith('+6309') and len(cleaned) == 14 and cleaned[1:].isdigit():
        return '+63' + cleaned[4:]

    return None

