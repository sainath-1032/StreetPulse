# 🏙️ StreetPulse

### AI-Powered Civic Complaint Intelligence System

StreetPulse transforms unstructured citizen complaints into
actionable information for civic administrators.

## Problem

Citizens report civic issues in different languages and
formats. Manual complaint classification and prioritisation
can delay action on serious public safety problems.

## Solution

StreetPulse uses AI to analyse complaint descriptions and
uploaded photographs, classify civic problems, assess severity,
and route reports to the appropriate departments.

## Key Features

- Citizen complaint submission
- Multilingual complaint understanding
- AI-powered image and text analysis
- Seven civic issue categories
- Four severity levels
- Automatic department routing
- Admin priority dashboard
- Human review and correction
- Neighbourhood Echo for similar local reports
- Complaint status tracking
- Category, severity, department and ward analytics
- CSV report export

## Technology Stack

- Python
- Streamlit
- Google Gemini API
- SQLite
- Pandas
- Pillow

## Severity Priority

1. Critical
2. High
3. Medium
4. Low

Repeated reports can increase attention priority,
but never change an individual complaint's severity.

## Department Routing

| Category | Department |
|---|---|
| Roads | Roads & Engineering |
| Waste | Sanitation |
| Water | Water Supply |
| Electricity | Electrical Department |
| Trees | Parks & Horticulture |
| Drainage | Stormwater / Drainage |
| Other | Manual Review Desk |

## Run Locally

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1