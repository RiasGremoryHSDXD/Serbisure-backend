import os
import re
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime
from difflib import SequenceMatcher
from django.conf import settings

def _similarity(a: str, b: str) -> float:
    """Returns similarity ratio between two strings from 0.0 to 1.0"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()

def _call_google_vision_api(image_bytes: bytes) -> str:
    """
    Calls Google Cloud Vision API TEXT_DETECTION endpoint.
    Checks GOOGLE_VISION_API_KEY from environment or settings.
    Returns full raw text extracted by Google Vision.
    """
    api_key = os.getenv('GOOGLE_VISION_API_KEY') or getattr(settings, 'GOOGLE_VISION_API_KEY', None)
    
    if not api_key:
        # Check if GOOGLE_APPLICATION_CREDENTIALS exists for google-cloud-vision
        cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if cred_path and os.path.exists(cred_path):
            try:
                from google.cloud import vision
                client = vision.ImageAnnotatorClient()
                image = vision.Image(content=image_bytes)
                response = client.document_text_detection(image=image)
                if response.full_text_annotation:
                    return response.full_text_annotation.text
                elif response.text_annotations:
                    return response.text_annotations[0].description
            except Exception as e:
                print(f"[OCR Service] Google Cloud Vision client error: {e}")
        return ""

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    payload = {
        "requests": [
            {
                "image": {
                    "content": base64.b64encode(image_bytes).decode('utf-8')
                },
                "features": [
                    {"type": "DOCUMENT_TEXT_DETECTION"},
                    {"type": "TEXT_DETECTION"}
                ]
            }
        ]
    }

    try:
        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            res_json = json.loads(response.read().decode('utf-8'))
            responses = res_json.get('responses', [])
            if responses:
                first = responses[0]
                full_text = first.get('fullTextAnnotation', {}).get('text')
                if full_text:
                    return full_text
                text_annotations = first.get('textAnnotations', [])
                if text_annotations:
                    return text_annotations[0].get('description', '')
    except Exception as e:
        print(f"[OCR Service] Google Vision REST API call error: {e}")

    return ""


def _call_groq_ai_verification(raw_text: str, document_type: str, user_profile) -> dict | None:
    """
    Calls Groq AI with model openai/gpt-oss-120b to perform intelligent
    extraction, name matching (handling Filipino naming conventions),
    and discrepancy analysis.
    """
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        return None

    user_first = getattr(user_profile, 'first_name', '') or ''
    user_last = getattr(user_profile, 'last_name', '') or ''
    user_full_name = f"{user_first} {user_last}".strip()
    user_barangay = getattr(user_profile, 'city', '') or getattr(user_profile, 'street', '') or 'Pagatpat'

    system_prompt = (
        "You are an expert AI document verification specialist for SerbiSure (a domestic labor compliance platform in the Philippines). "
        "Analyze the raw OCR text extracted from a government-issued document (such as a Police Clearance, NBI Clearance, or National ID) "
        "and compare it thoroughly against the registered user's profile.\n"
        "Account for Philippine naming conventions (e.g. maternal middle names, abbreviations like Ma. for Maria, capitalization differences).\n"
        "Output ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "document_number": "Clearance/Certificate/Card Number found",\n'
        '  "full_name": "Full name printed on document",\n'
        '  "first_name": "First name printed on document",\n'
        '  "middle_name": "Middle name if found",\n'
        '  "last_name": "Last name printed on document",\n'
        '  "date_issued": "YYYY-MM-DD or readable date",\n'
        '  "valid_until": "YYYY-MM-DD or readable date",\n'
        '  "date_of_birth": "YYYY-MM-DD if found",\n'
        '  "barangay": "Barangay/City found on document",\n'
        '  "issuing_office": "Issuing agency (e.g. PHILIPPINE NATIONAL POLICE, NBI, PHILSYS)",\n'
        '  "match_score": 96.5,\n'
        '  "discrepancies": [\n'
        '    {\n'
        '      "field": "name|barangay|validity",\n'
        '      "severity": "low|medium|high",\n'
        '      "message": "Clear explanation of discrepancy",\n'
        '      "profile_value": "value from profile",\n'
        '      "document_value": "value from document"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    user_content = (
        f"Target Document Type: {document_type}\n"
        f"Registered Profile Name: {user_full_name}\n"
        f"Registered Barangay/City: {user_barangay}\n\n"
        f"Raw OCR Text Extracted by Google Vision:\n{raw_text[:2500]}"
    )

    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SerbiSure-Backend/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            content = data['choices'][0]['message']['content']
            return json.loads(content)
    except Exception as e:
        print(f"[OCR Service] Groq AI verification fallback note: {e}")
        return None


def parse_extracted_document(raw_text: str, document_type: str, user_profile) -> dict:
    """
    Parses key fields from document text and compares with the user's profile.
    Leverages Groq AI verification if configured, with regex/heuristic fallback.
    """
    user_first = getattr(user_profile, 'first_name', '') or ''
    user_last = getattr(user_profile, 'last_name', '') or ''
    user_full_name = f"{user_first} {user_last}".strip()
    user_barangay = getattr(user_profile, 'street', '') or getattr(user_profile, 'city', '') or 'Pagatpat'
    
    # 1. Try Groq AI Verification first if text is available
    if raw_text:
        groq_ai_result = _call_groq_ai_verification(raw_text, document_type, user_profile)
        if groq_ai_result:
            doc_num = (
                groq_ai_result.get('clearance_number') or
                groq_ai_result.get('philsys_number') or
                groq_ai_result.get('document_number') or
                f"DOC-{str(abs(hash(raw_text)))[:8]}"
            )
            match_score = float(groq_ai_result.get('match_score', 95.0))
            # Bound match score between 10.0 and 99.8
            match_score = max(min(match_score, 99.8), 10.0)
            
            return {
                "document_number": doc_num,
                "raw_text": raw_text,
                "extracted_data": groq_ai_result,
                "match_score": match_score,
                "discrepancies": groq_ai_result.get('discrepancies', []),
                "date_issued": groq_ai_result.get('date_issued'),
                "valid_until": groq_ai_result.get('valid_until')
            }

    # 2. Defaults / Heuristic fallback
    extracted_data = {
        "full_name": None,
        "document_number": None,
        "date_issued": None,
        "valid_until": None,
        "barangay": user_barangay,
        "city": getattr(user_profile, 'city', None) or 'Cagayan de Oro City',
        "document_type_label": document_type.replace('_', ' ').title()
    }
    discrepancies = []
    
    # If Google Vision did not return text, return empty detection with quality warning
    if not raw_text:
        return {
            "document_number": None,
            "raw_text": "",
            "extracted_data": extracted_data,
            "match_score": 0.0,
            "discrepancies": [{
                "field": "image_quality",
                "severity": "high",
                "message": "No readable text detected by Google Vision OCR. Please upload a clearer image."
            }],
            "date_issued": None,
            "valid_until": None
        }

    # 3. Regex / Heuristic Pattern Extraction
    doc_number = None
    if 'national_id' in document_type:
        pcn_match = re.search(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', raw_text)
        if pcn_match:
            doc_number = pcn_match.group(0).replace(' ', '-')
    elif 'police' in document_type:
        pol_match = re.search(r'(?:NO|CONTROL\s*(?:NO|KEY)|CERTIFICATE\s*NO)\.?\s*:?\s*([A-Z0-9-]+)', raw_text, re.IGNORECASE)
        if pol_match:
            doc_number = pol_match.group(1).strip()
    elif 'nbi' in document_type:
        nbi_match = re.search(r'(?:CLEARANCE\s*NO|ID\s*NO)\.?\s*:?\s*([A-Z0-9-]+)', raw_text, re.IGNORECASE)
        if nbi_match:
            doc_number = nbi_match.group(1).strip()
            
    if not doc_number:
        gen_match = re.search(r'\b[A-Z0-9]{4,6}-[A-Z0-9]{4,6}-[A-Z0-9]{4,6}\b', raw_text)
        if gen_match:
            doc_number = gen_match.group(0)
        else:
            num_match = re.search(r'\b\d{6,10}\b', raw_text)
            doc_number = num_match.group(0) if num_match else "DOC-" + str(abs(hash(raw_text)))[:8]

    extracted_data["document_number"] = doc_number

    # Name matching
    text_lower = raw_text.lower()
    first_name_match = (user_first.lower() in text_lower) if user_first else True
    last_name_match = (user_last.lower() in text_lower) if user_last else True
    
    name_similarity = 0.0
    lines = [line.strip() for line in raw_text.split('\n') if len(line.strip()) > 3]
    for line in lines:
        sim = _similarity(line, user_full_name)
        if sim > name_similarity:
            name_similarity = sim

    if first_name_match and last_name_match:
        name_score = max(name_similarity * 100, 95.0)
        extracted_data["full_name"] = user_full_name
    else:
        name_score = name_similarity * 100
        discrepancies.append({
            "field": "full_name",
            "profile_value": user_full_name,
            "document_value": "Not cleanly matched in document",
            "similarity": round(name_similarity, 2),
            "severity": "high" if name_score < 50 else "medium",
            "message": f"Profile name '{user_full_name}' differs from OCR detection."
        })

    # Dates extraction
    date_matches = re.findall(
        r'\b(?:\d{4}[-/.]\d{2}[-/.]\d{2}|\d{2}[-/.]\d{2}[-/.]\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b',
        raw_text,
        re.IGNORECASE
    )
    
    if len(date_matches) >= 1:
        extracted_data["date_issued"] = date_matches[0]
    if len(date_matches) >= 2:
        extracted_data["valid_until"] = date_matches[1]

    barangay_score = 100.0
    if user_barangay and user_barangay.lower() not in text_lower:
        barangay_score = 60.0
        discrepancies.append({
            "field": "barangay",
            "profile_value": user_barangay,
            "document_value": "Not found in text",
            "severity": "low",
            "message": f"Barangay '{user_barangay}' not explicitly detected in OCR text."
        })

    total_score = round((name_score * 0.7) + (barangay_score * 0.3), 1)
    total_score = max(min(total_score, 99.8), 20.0)

    return {
        "document_number": doc_number,
        "raw_text": raw_text,
        "extracted_data": extracted_data,
        "match_score": total_score,
        "discrepancies": discrepancies,
        "date_issued": None,
        "valid_until": None
    }


def process_document_ocr(image_bytes: bytes, document_type: str, user_profile) -> dict:
    """
    Main entry point for Google Vision OCR & AI Verification processing.
    """
    raw_text = _call_google_vision_api(image_bytes)
    return parse_extracted_document(raw_text, document_type, user_profile)
