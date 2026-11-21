import streamlit as st
from PIL import Image, UnidentifiedImageError
from pathlib import Path
from io import BytesIO
import uuid
import pandas as pd

from database import (
    initialize_database,
    add_complaint,
    get_all_complaints,
    update_ai_analysis,
    update_status,
    human_correct_complaint,
    update_neighbourhood_echo
)

from ai_engine import analyze_complaint


# =====================================
# CONFIGURATION
# =====================================

st.set_page_config(
    page_title="StreetPulse",
    page_icon="🏙️",
    layout="wide"
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

initialize_database()

CATEGORIES = [
    "Roads", "Waste", "Water", "Electricity",
    "Trees", "Drainage", "Other"
]

SEVERITIES = ["Low", "Medium", "High", "Critical"]

DEPARTMENTS = {
    "Roads": "Roads & Engineering",
    "Waste": "Sanitation",
    "Water": "Water Supply",
    "Electricity": "Electrical Department",
    "Trees": "Parks & Horticulture",
    "Drainage": "Stormwater / Drainage",
    "Other": "Manual Review Desk"
}

STATUSES = ["New", "Assigned", "In Progress", "Resolved"]

# Critical always ranks above High, regardless of duplicates.
SEVERITY_RANK = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1
}


# =====================================
# HEADER
# =====================================

st.title("🏙️ StreetPulse")
st.caption("AI-Powered Civic Complaint Intelligence System")

citizen_tab, admin_tab = st.tabs([
    "📝 Citizen Portal",
    "🛡️ Admin Dashboard"
])


# =====================================
# CITIZEN PORTAL
# =====================================

with citizen_tab:

    st.header("Submit a Civic Complaint")

    st.write(
        "Report neighbourhood problems in English "
        "or Indian regional languages."
    )

    with st.form("complaint_form"):

        citizen_name = st.text_input("Your name (optional)")

        complaint_text = st.text_area(
            "Describe your complaint",
            placeholder="Describe the civic problem...",
            height=130
        )

        col1, col2 = st.columns(2)

        with col1:
            ward = st.text_input("Ward number")
            location = st.text_input("Location")

        with col2:
            landmark = st.text_input("Nearby landmark")

            uploaded_photo = st.file_uploader(
                "Upload a photo (optional)",
                type=["jpg", "jpeg", "png", "webp"]
            )

        submitted = st.form_submit_button(
            "🚀 Submit Complaint",
            type="primary",
            use_container_width=True
        )

    if submitted:

        if not complaint_text.strip():
            st.error("Please describe your complaint.")

        else:

            image_for_ai = None
            photo_path = None

            if uploaded_photo is not None:

                try:
                    image_for_ai = Image.open(
                        BytesIO(uploaded_photo.getvalue())
                    ).convert("RGB")

                    filename = f"{uuid.uuid4().hex}.jpg"
                    saved_path = UPLOAD_DIR / filename

                    image_for_ai.save(
                        saved_path,
                        format="JPEG",
                        quality=85
                    )

                    photo_path = str(saved_path)

                except (UnidentifiedImageError, OSError):
                    st.error("Invalid image. Please upload another photo.")
                    st.stop()

            complaint_id = add_complaint(
                citizen_name=citizen_name.strip(),
                complaint_text=complaint_text.strip(),
                photo_path=photo_path,
                ward=ward.strip(),
                location=location.strip(),
                landmark=landmark.strip()
            )

            st.success(
                f"Complaint #{complaint_id} saved successfully!"
            )

            try:

                with st.spinner("Gemini AI is analysing your complaint..."):

                    result = analyze_complaint(
                        complaint_text,
                        image_for_ai
                    )

                    update_ai_analysis(
                        complaint_id=complaint_id,
                        category=result["category"],
                        severity=result["severity"],
                        explanation=result["explanation"],
                        department=result["department"],
                        confidence=result["confidence"],
                        needs_review=result["needs_review"]
                    )

                    # Find related reports from the same neighbourhood.
                    # This changes attention only, never AI severity.
                    echo_count = update_neighbourhood_echo(complaint_id)

                st.subheader("🤖 AI Analysis")

                a, b, c = st.columns(3)

                a.metric("Category", result["category"])
                b.metric("Severity", result["severity"])
                c.metric(
                    "Confidence",
                    f"{result['confidence'] * 100:.0f}%"
                )

                st.write("**Department:**", result["department"])
                st.write("**Explanation:**", result["explanation"])

                if echo_count > 1:
                    st.info(
                        f"Neighbourhood Echo found {echo_count - 1} "
                        f"similar report(s) from this area."
                    )
                else:
                    st.caption(
                        "Neighbourhood Echo: No similar reports found yet."
                    )

                if result["needs_review"]:
                    st.warning("Human review required.")
                else:
                    st.success("AI analysis completed.")

            except Exception as error:

                st.warning(
                    "Complaint saved, but AI analysis failed. "
                    "An administrator must review it."
                )

                st.caption(str(error))


# =====================================
# ADMIN DASHBOARD
# =====================================

with admin_tab:

    st.header("🛡️ Civic Administration Dashboard")

    if st.button("🔄 Refresh Dashboard"):
        st.rerun()

    complaints = get_all_complaints()

    if not complaints:

        st.info("No complaints submitted yet.")

    else:

        # Priority sorting:
        # Critical > High > Medium > Low
        complaints.sort(
            key=lambda x: (
                SEVERITY_RANK.get(x["severity"], 0),
                x.get("attention_score", 0),
                x["created_at"] or ""
            ),
            reverse=True
        )

        total = len(complaints)

        critical_count = sum(
            1 for x in complaints
            if x["severity"] == "Critical"
        )

        high_count = sum(
            1 for x in complaints
            if x["severity"] == "High"
        )

        pending_count = sum(
            1 for x in complaints
            if x["status"] != "Resolved"
        )

        review_count = sum(
            1 for x in complaints
            if x["needs_review"]
        )

        # Summary metrics

        m1, m2, m3, m4, m5 = st.columns(5)

        m1.metric("Total Reports", total)
        m2.metric("Critical", critical_count)
        m3.metric("High", high_count)
        m4.metric("Pending", pending_count)
        m5.metric("Needs Review", review_count)

        st.divider()

        # =====================================
        # CATEGORY AND SEVERITY ANALYTICS
        # =====================================

        st.subheader("📊 Civic Issue Analytics")

        chart1, chart2 = st.columns(2)

        with chart1:
            st.write("**Complaints by Category**")

            category_data = pd.DataFrame([
                {
                    "Category": category,
                    "Reports": sum(
                        1 for c in complaints
                        if c["category"] == category
                    )
                }
                for category in CATEGORIES
            ])

            st.bar_chart(
                category_data.set_index("Category")
            )

        with chart2:
            st.write("**Complaints by Severity**")

            severity_data = pd.DataFrame([
                {
                    "Severity": severity,
                    "Reports": sum(
                        1 for c in complaints
                        if c["severity"] == severity
                    )
                }
                for severity in ["Critical", "High", "Medium", "Low"]
            ])

            st.bar_chart(
                severity_data.set_index("Severity")
            )

        # =====================================
        # DEPARTMENT AND WARD ANALYTICS
        # =====================================

        st.subheader("🏢 Department Workload & Ward Hotspots")

        department_col, ward_col = st.columns(2)

        with department_col:
            st.write("**Complaints by Department**")

            department_data = pd.DataFrame([
                {
                    "Department": department,
                    "Reports": sum(
                        1 for complaint in complaints
                        if complaint["department"] == department
                    )
                }
                for department in sorted(
                    {
                        complaint["department"]
                        for complaint in complaints
                        if complaint["department"]
                    }
                )
            ])

            if not department_data.empty:
                st.bar_chart(
                    department_data.set_index("Department")
                )
            else:
                st.info("Department data is not available yet.")

        with ward_col:
            st.write("**Top 10 Wards by Complaint Count**")

            ward_data = pd.DataFrame([
                {
                    "Ward": str(ward_name),
                    "Reports": count
                }
                for ward_name, count in pd.Series([
                    str(complaint["ward"] or "Unknown")
                    for complaint in complaints
                ]).value_counts().head(10).items()
            ])

            if not ward_data.empty:
                st.bar_chart(
                    ward_data.set_index("Ward")
                )
            else:
                st.info("Ward data is not available yet.")

        st.divider()

        # =====================================
        # EXPORT REPORTS
        # =====================================

        st.subheader("📥 Export Complaint Reports")

        export_columns = [
            "id",
            "citizen_name",
            "complaint_text",
            "ward",
            "location",
            "landmark",
            "category",
            "severity",
            "severity_explanation",
            "department",
            "confidence",
            "needs_review",
            "status",
            "similar_count",
            "attention_score",
            "created_at"
        ]

        export_data = pd.DataFrame(complaints)

        export_data = export_data[export_columns]

        csv_file = export_data.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            label="⬇️ Download All Complaints (CSV)",
            data=csv_file,
            file_name="streetpulse_complaints.csv",
            mime="text/csv"
        )

        st.divider()

        # =====================================
        # COMPLAINT PRIORITY QUEUE
        # =====================================

        st.subheader(
            f"📋 Complaint Priority Queue ({len(complaints)})"
        )

        # Filters

        f1, f2, f3 = st.columns(3)

        with f1:
            category_filter = st.selectbox(
                "Category",
                ["All"] + CATEGORIES
            )

        with f2:
            severity_filter = st.selectbox(
                "Severity",
                ["All"] + SEVERITIES
            )

        with f3:
            status_filter = st.selectbox(
                "Status",
                ["All"] + STATUSES
            )

        filtered = complaints

        if category_filter != "All":
            filtered = [
                x for x in filtered
                if x["category"] == category_filter
            ]

        if severity_filter != "All":
            filtered = [
                x for x in filtered
                if x["severity"] == severity_filter
            ]

        if status_filter != "All":
            filtered = [
                x for x in filtered
                if x["status"] == status_filter
            ]

        st.subheader(
            f"Filtered Complaints ({len(filtered)})"
        )

        # Display complaints in priority order

        for complaint in filtered:

            severity = complaint["severity"]

            if severity == "Critical":
                icon = "🚨"
            elif severity == "High":
                icon = "🔴"
            elif severity == "Medium":
                icon = "🟠"
            else:
                icon = "🟢"

            title = (
                f"{icon} #{complaint['id']} — "
                f"{complaint['category']} / {severity}"
            )

            with st.expander(title):

                left, right = st.columns([2, 1])

                with left:

                    st.write(
                        "**Citizen:**",
                        complaint["citizen_name"] or "Anonymous"
                    )

                    st.write(
                        "**Complaint:**",
                        complaint["complaint_text"]
                    )

                    st.write(
                        "**Ward:**",
                        complaint["ward"] or "Not provided"
                    )

                    st.write(
                        "**Location:**",
                        complaint["location"] or "Not provided"
                    )

                    st.write(
                        "**Landmark:**",
                        complaint["landmark"] or "Not provided"
                    )

                    st.write(
                        "**Similar reports in this area:**",
                        complaint.get("similar_count", 1)
                    )

                    st.write(
                        "**Attention score:**",
                        complaint.get("attention_score", 0)
                    )

                    st.write(
                        "**Department:**",
                        complaint["department"]
                    )

                    st.write(
                        "**AI explanation:**",
                        complaint["severity_explanation"]
                        or "Awaiting analysis"
                    )

                    st.write(
                        "**AI confidence:**",
                        f"{(complaint['confidence'] or 0) * 100:.0f}%"
                    )

                    if complaint["needs_review"]:
                        st.warning("⚠️ Requires human review")

                    if complaint["human_corrected"]:
                        st.info("Human-reviewed classification")

                with right:

                    photo = complaint["photo_path"]

                    if photo and Path(photo).exists():
                        st.image(
                            photo,
                            caption="Citizen uploaded photo",
                            use_container_width=True
                        )

                    st.write(
                        "**Submitted:**",
                        complaint["created_at"]
                    )

                    st.write(
                        "**Current status:**",
                        complaint["status"]
                    )

                    # Status update

                    selected_status = st.selectbox(
                        "Update status",
                        STATUSES,
                        index=STATUSES.index(complaint["status"]),
                        key=f"status_{complaint['id']}"
                    )

                    if st.button(
                        "Save Status",
                        key=f"save_status_{complaint['id']}"
                    ):

                        update_status(
                            complaint["id"],
                            selected_status
                        )

                        st.success("Status updated!")
                        st.rerun()

                # Human review

                st.divider()
                st.markdown("**👨‍💼 Human Review / Correction**")

                with st.form(
                    f"review_{complaint['id']}"
                ):

                    corrected_category = st.selectbox(
                        "Correct category",
                        CATEGORIES,
                        index=CATEGORIES.index(
                            complaint["category"]
                            if complaint["category"] in CATEGORIES
                            else "Other"
                        ),
                        key=f"category_{complaint['id']}"
                    )

                    corrected_severity = st.selectbox(
                        "Correct severity",
                        SEVERITIES,
                        index=SEVERITIES.index(
                            complaint["severity"]
                            if complaint["severity"] in SEVERITIES
                            else "Medium"
                        ),
                        key=f"severity_{complaint['id']}"
                    )

                    st.caption(
                        "Department will automatically follow the corrected category."
                    )

                    review_submitted = st.form_submit_button(
                        "Save Human Correction"
                    )

                    if review_submitted:

                        human_correct_complaint(
                            complaint["id"],
                            corrected_category,
                            corrected_severity,
                            DEPARTMENTS[corrected_category]
                        )

                        st.success("Human correction saved!")
                        st.rerun()

        st.divider()

        st.caption(
            "StreetPulse | Human oversight + AI-powered civic intelligence"
        )