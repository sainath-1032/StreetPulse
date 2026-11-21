import sqlite3
import re
from difflib import SequenceMatcher
from datetime import datetime

DB_NAME = "streetpulse.db"


# =====================================
# DATABASE CONNECTION
# =====================================

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# =====================================
# DATABASE INITIALIZATION
# =====================================

def initialize_database():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_name TEXT,
            complaint_text TEXT NOT NULL,
            photo_path TEXT,
            ward TEXT,
            location TEXT,
            landmark TEXT,

            category TEXT DEFAULT 'Other',
            severity TEXT DEFAULT 'Medium',
            severity_explanation TEXT,
            department TEXT DEFAULT 'Manual Review Desk',

            confidence REAL DEFAULT 0,
            needs_review INTEGER DEFAULT 1,
            human_corrected INTEGER DEFAULT 0,

            status TEXT DEFAULT 'New',
            similar_count INTEGER DEFAULT 1,
            attention_score INTEGER DEFAULT 0,

            created_at TEXT
        )
    """)

    # Add missing columns safely if an older database exists.
    existing_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(complaints)"
        ).fetchall()
    }

    required_columns = {
        "citizen_name": "TEXT",
        "complaint_text": "TEXT NOT NULL DEFAULT ''",
        "photo_path": "TEXT",
        "ward": "TEXT",
        "location": "TEXT",
        "landmark": "TEXT",
        "category": "TEXT DEFAULT 'Other'",
        "severity": "TEXT DEFAULT 'Medium'",
        "severity_explanation": "TEXT",
        "department": "TEXT DEFAULT 'Manual Review Desk'",
        "confidence": "REAL DEFAULT 0",
        "needs_review": "INTEGER DEFAULT 1",
        "human_corrected": "INTEGER DEFAULT 0",
        "status": "TEXT DEFAULT 'New'",
        "similar_count": "INTEGER DEFAULT 1",
        "attention_score": "INTEGER DEFAULT 0",
        "created_at": "TEXT"
    }

    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE complaints ADD COLUMN "
                f"{column_name} {column_type}"
            )

    conn.commit()
    conn.close()


# =====================================
# ADD COMPLAINT
# =====================================

def add_complaint(
    citizen_name,
    complaint_text,
    photo_path=None,
    ward=None,
    location=None,
    landmark=None
):
    conn = get_connection()

    cursor = conn.execute("""
        INSERT INTO complaints (
            citizen_name,
            complaint_text,
            photo_path,
            ward,
            location,
            landmark,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        citizen_name,
        complaint_text,
        photo_path,
        ward,
        location,
        landmark,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    complaint_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return complaint_id


# =====================================
# GET ALL COMPLAINTS
# =====================================

def get_all_complaints():
    conn = get_connection()

    complaints = conn.execute("""
        SELECT * FROM complaints
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return [dict(row) for row in complaints]


# =====================================
# SAVE AI ANALYSIS
# =====================================

def update_ai_analysis(
    complaint_id,
    category,
    severity,
    explanation,
    department,
    confidence,
    needs_review
):
    conn = get_connection()

    conn.execute("""
        UPDATE complaints
        SET category = ?,
            severity = ?,
            severity_explanation = ?,
            department = ?,
            confidence = ?,
            needs_review = ?
        WHERE id = ?
    """, (
        category,
        severity,
        explanation,
        department,
        confidence,
        int(needs_review),
        complaint_id
    ))

    conn.commit()
    conn.close()


# =====================================
# UPDATE COMPLAINT STATUS
# =====================================

def update_status(complaint_id, new_status):

    allowed_statuses = [
        "New",
        "Assigned",
        "In Progress",
        "Resolved"
    ]

    if new_status not in allowed_statuses:
        raise ValueError("Invalid complaint status")

    conn = get_connection()

    conn.execute("""
        UPDATE complaints
        SET status = ?
        WHERE id = ?
    """, (
        new_status,
        complaint_id
    ))

    conn.commit()
    conn.close()


# =====================================
# HUMAN REVIEW / CORRECTION
# =====================================

def human_correct_complaint(
    complaint_id,
    category,
    severity,
    department
):
    conn = get_connection()

    conn.execute("""
        UPDATE complaints
        SET category = ?,
            severity = ?,
            department = ?,
            human_corrected = 1,
            needs_review = 0
        WHERE id = ?
    """, (
        category,
        severity,
        department,
        complaint_id
    ))

    conn.commit()
    conn.close()


# =====================================
# NEIGHBOURHOOD ECHO HELPERS
# =====================================

def normalize_text(value):
    """
    Normalize text while preserving regional-language characters.
    """
    value = str(value or "").lower()

    value = re.sub(
        r"[^\w\s]",
        " ",
        value,
        flags=re.UNICODE
    )

    return " ".join(value.split())


def same_area(first, second):
    """
    Two complaints belong to the same area when at least
    one provided ward, location, or landmark matches.
    """

    fields = [
        "ward",
        "location",
        "landmark"
    ]

    for field in fields:

        first_value = normalize_text(first[field])
        second_value = normalize_text(second[field])

        if (
            first_value
            and second_value
            and first_value == second_value
        ):
            return True

    return False


def similar_complaint_text(first_text, second_text):
    """
    Compare complaint wording using text similarity.
    """

    first_text = normalize_text(first_text)
    second_text = normalize_text(second_text)

    if not first_text or not second_text:
        return False

    sequence_score = SequenceMatcher(
        None,
        first_text,
        second_text
    ).ratio()

    first_words = set(first_text.split())
    second_words = set(second_text.split())

    combined_words = first_words | second_words

    if combined_words:
        overlap_score = (
            len(first_words & second_words)
            / len(combined_words)
        )
    else:
        overlap_score = 0

    return (
        sequence_score >= 0.38
        or overlap_score >= 0.25
    )


# =====================================
# NEIGHBOURHOOD ECHO
# =====================================

def update_neighbourhood_echo(complaint_id):
    """
    Detect similar complaints from the same neighbourhood.

    Similar reports increase attention priority.

    IMPORTANT:
    This function never changes category or severity.
    A Critical report always retains its Critical severity.
    """

    conn = get_connection()

    current = conn.execute("""
        SELECT * FROM complaints
        WHERE id = ?
    """, (complaint_id,)).fetchone()

    if current is None:
        conn.close()
        return 1

    other_complaints = conn.execute("""
        SELECT * FROM complaints
        WHERE id != ?
    """, (complaint_id,)).fetchall()

    related_ids = []

    for other in other_complaints:

        area_matches = same_area(
            current,
            other
        )

        if not area_matches:
            continue

        text_matches = similar_complaint_text(
            current["complaint_text"],
            other["complaint_text"]
        )

        if text_matches:
            related_ids.append(other["id"])

    group_count = len(related_ids) + 1

    # Each additional related report increases attention.
    # Severity is never modified here.
    attention_score = (group_count - 1) * 10

    conn.execute("""
        UPDATE complaints
        SET similar_count = ?,
            attention_score = ?
        WHERE id = ?
    """, (
        group_count,
        attention_score,
        complaint_id
    ))

    # Update attention information for related reports.
    # Do not alter their AI classification or severity.
    for related_id in related_ids:

        conn.execute("""
            UPDATE complaints
            SET similar_count = ?,
                attention_score = ?
            WHERE id = ?
        """, (
            group_count,
            attention_score,
            related_id
        ))

    conn.commit()
    conn.close()

    return group_count


# =====================================
# DIRECT DATABASE INITIALIZATION
# =====================================

if __name__ == "__main__":
    initialize_database()
    print("StreetPulse database initialized successfully!")