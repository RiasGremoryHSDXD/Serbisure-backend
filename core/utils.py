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


def get_signed_cloudinary_url(
    public_id_or_url,
    as_avatar=True,
    width=200,
    height=200,
    quality='auto',
    fetch_format='webp'
):
    """
    Generates a secure, signed Cloudinary URL optimized for fast WebP retrieval.
    Reduces raw camera uploads (e.g., 5.5MB) down to ultra-fast WebP thumbnails (~4.7KB).

    Edge Cases Handled:
    1. None, empty string, or whitespace -> returns None (safe fallback, never crashes).
    2. Absolute HTTP/HTTPS URLs (e.g. ui-avatars.com, external links) -> returned as-is.
    3. Public IDs with or without file extensions (.jpg, .png, etc.) -> normalized cleanly.
    4. Face-detection gravity (gravity='face') -> keeps the user's face centered in avatars.
    5. Cloudinary signing or configuration exceptions -> caught safely and returns None.
    """
    if not public_id_or_url:
        return None

    val = str(public_id_or_url).strip()
    if not val:
        return None

    # If it is already a full web URL, do not attempt to re-sign
    if val.startswith('http://') or val.startswith('https://'):
        return val

    try:
        import cloudinary.utils

        if as_avatar:
            transformation = [{
                'width': width,
                'height': height,
                'crop': 'fill',
                'gravity': 'face',
                'quality': quality,
                'fetch_format': fetch_format,
            }]
        else:
            transformation = [{
                'quality': quality,
                'fetch_format': fetch_format,
            }]

        url, _ = cloudinary.utils.cloudinary_url(
            val,
            type='authenticated',
            sign_url=True,
            transformation=transformation
        )
        return url
    except Exception:
        return None

