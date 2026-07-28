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
