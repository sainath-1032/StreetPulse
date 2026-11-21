import os
import json
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types


# =====================================
# CONFIGURATION
# =====================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.7-flash"


# =====================================
# DEPARTMENT MAPPING
# =====================================

DEPARTMENTS = {
    "Roads": "Roads & Engineering",
    "Waste": "Sanitation",
    "Water": "Water Supply",
    "Electricity": "Electrical Department",
    "Trees": "Parks & Horticulture",
    "Drainage": "Stormwater / Drainage",
    "Other": "Manual Review Desk"
}

CATEGORIES = [
    "Roads",
    "Waste",
    "Water",
    "Electricity",
    "Trees",
    "Drainage",
    "Other"
]

SEVERITIES = [
    "Low",
    "Medium",
    "High",
    "Critical"
]


# =====================================
# GEMINI CLIENT WITH TIMEOUT
# =====================================

def get_ai_client():

    if not API_KEY:
        raise ValueError(
            "Gemini API key missing. Check your .env file."
        )

    return genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(
            timeout=45000,
            retry_options=types.HttpRetryOptions(
                attempts=1
            )
        )
    )


# =====================================
# AI ANALYSIS PROMPT
# =====================================

ANALYSIS_PROMPT = """
You are StreetPulse, an AI-powered civic complaint
intelligence assistant.

Understand complaints written in English or Indian
regional languages, including Kannada, Hindi, Tamil,
Telugu, Malayalam and Marathi.

Analyse the complaint text and photograph together
when a photograph is provided.

Do not invent details that are not present in the
complaint or visible in the photograph.

CATEGORIES:
Choose exactly one:

Roads, Waste, Water, Electricity, Trees, Drainage, Other.

SEVERITY:

Low:
Minor inconvenience without immediate danger.

Medium:
A problem affecting residents that needs attention.

High:
Serious infrastructure damage, significant disruption,
or a substantial safety concern.

Critical:
Immediate threat to life or serious physical harm.

Examples:
- Dangerous pothole near a school: High.
- Exposed sparking electrical wire near people: Critical.
- Imminent structural collapse threatening people: Critical.

Do not assign Critical just because a complaint sounds urgent.
Severity must be based on the individual complaint.
Repeated reports must never change individual severity.

CONFIDENCE:
Return a number between 0 and 1.

HUMAN REVIEW:
Set needs_review to true if the complaint is unclear,
classification is uncertain, or information is insufficient.

Return ONLY valid JSON in this exact format:

{
  "category": "Roads",
  "severity": "High",
  "explanation": "A dangerous pothole creates a road safety risk.",
  "confidence": 0.95,
  "needs_review": false
}
"""


# =====================================
# RESPONSE PARSING
# =====================================

def parse_ai_response(response_text):

    if not response_text:
        raise ValueError(
            "Gemini returned an empty response."
        )

    cleaned = response_text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    try:
        return json.loads(cleaned)

    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid JSON."
        ) from error


def parse_boolean(value):

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in [
            "true", "yes", "1"
        ]

    if isinstance(value, (int, float)):
        return value != 0

    return False


# =====================================
# MAIN COMPLAINT ANALYSIS
# =====================================

def analyze_complaint(complaint_text, image=None):

    if not complaint_text or not complaint_text.strip():
        raise ValueError(
            "Complaint text cannot be empty."
        )

    client = get_ai_client()

    contents = [
        ANALYSIS_PROMPT,
        "CITIZEN COMPLAINT:\n" + complaint_text.strip()
    ]

    if image is not None:
        contents.append(image)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config={
            "response_mime_type": "application/json"
        }
    )

    result = parse_ai_response(response.text)

    # Validate category
    category_lookup = {
        item.lower(): item
        for item in CATEGORIES
    }

    category = category_lookup.get(
        str(result.get("category", "Other")).strip().lower(),
        "Other"
    )

    # Validate severity
    severity_lookup = {
        item.lower(): item
        for item in SEVERITIES
    }

    severity = severity_lookup.get(
        str(result.get("severity", "Medium")).strip().lower(),
        "Medium"
    )

    # Explanation
    explanation = str(
        result.get(
            "explanation",
            "Human review required."
        )
    ).strip()

    if not explanation:
        explanation = "Human review required."

    # Confidence
    try:
        confidence = float(
            result.get("confidence", 0)
        )
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(
        0.0,
        min(1.0, confidence)
    )

    # Human review
    needs_review = (
        parse_boolean(
            result.get("needs_review", False)
        )
        or confidence < 0.70
        or category == "Other"
    )

    # Department routing is controlled by our code.
    department = DEPARTMENTS[category]

    return {
        "category": category,
        "severity": severity,
        "explanation": explanation,
        "department": department,
        "confidence": confidence,
        "needs_review": needs_review
    }