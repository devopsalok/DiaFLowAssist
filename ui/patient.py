import streamlit as st


@st.dialog("Emergency alert", width="large")
def emergency_alert_dialog(
    reasons: list[str], accept_callback, bypass_callback
) -> None:
    st.error(
        "**EMERGENCY CRITERIA DETECTED — ordinary queue assignment is disabled.**"
    )
    st.markdown(f"**Patient:** {st.session_state.patient_name.strip()}")
    st.markdown(f"**Flag(s):** {', '.join(reasons)}")
    vital_cols = st.columns(3)
    vital_cols[0].metric(
        "CBG",
        "Not recorded"
        if st.session_state.cbg is None
        else f"{st.session_state.cbg} mg/dL",
    )
    vital_cols[1].metric(
        "SBP",
        "Not recorded"
        if st.session_state.systolic_bp is None
        else f"{st.session_state.systolic_bp} mmHg",
    )
    vital_cols[2].metric(
        "Respiratory rate",
        "Not recorded"
        if st.session_state.respiratory_rate is None
        else f"{st.session_state.respiratory_rate} /min",
    )
    st.caption(
        "This workflow flag is based on entered symptoms and vitals; it is not a diagnosis."
    )
    accept_col, bypass_col = st.columns(2)
    accept_col.button(
        "Accept — assign Emergency priority",
        type="primary",
        key="accept_emergency",
        on_click=accept_callback,
        width="stretch",
    )
    bypass_col.button(
        "Bypass — add to routine queue",
        key="bypass_emergency",
        on_click=bypass_callback,
        width="stretch",
    )


def render_patient_intake(
    emergency_trigger_reasons,
    add_patient_callback,
    accept_emergency_callback,
    bypass_emergency_callback,
) -> None:
    with st.sidebar:
        st.header("Add patient")
        st.text_input("Patient name", key="patient_name")
        st.number_input("Age", min_value=0, max_value=120, key="patient_age")
        st.selectbox(
            "Glycemic control",
            [
                "Controlled (<7.5%)",
                "Suboptimal (7.5-9%)",
                "Uncontrolled (>9% or hypos)",
            ],
            key="glycemic_control",
        )
        st.selectbox(
            "Regimen", ["Lifestyle/Oral", "Multi-oral", "Insulin"], key="regimen"
        )
        st.multiselect(
            "Overdue preventive checks",
            ["uACR", "Foot exam", "Eye exam"],
            key="preventive_checks",
        )
        st.selectbox(
            "eGFR (mL/min)",
            [None, 120, 90, 75, 58, 45, 30, 15],
            format_func=lambda value: "Not recorded" if value is None else str(value),
            key="egfr",
        )
        st.selectbox(
            "Last kidney check",
            [None, 1, 3, 6, 12, 14, 24],
            format_func=lambda months: (
                "Not recorded"
                if months is None
                else f"{months} month{'s' if months != 1 else ''} ago"
            ),
            key="months_since_egfr_check",
        )
        st.checkbox("Acute complaint / symptoms", key="acute_complaint")
        if st.session_state.acute_complaint:
            st.multiselect(
                "Emergency symptoms (select all that apply)",
                [
                    "Chest pain",
                    "Severe hypo (CBG < 70 mg/dL)",
                    "Marked hyper (CBG > 300 mg/dL)",
                    "Hypotension (SBP < 90 mmHg)",
                    "Altered sensorium",
                    "Tachypnea (RR > 20/min)",
                    "Intractable vomiting",
                ],
                key="emergency_symptoms",
            )
            st.selectbox(
                "CBG (mg/dL)",
                [None, 40, 60, 69, 70, 80, 100, 150, 200, 250, 300, 301, 350, 400],
                format_func=lambda value: (
                    "Not recorded" if value is None else str(value)
                ),
                key="cbg",
            )
            st.selectbox(
                "SBP (mmHg)",
                [None, 60, 80, 89, 90, 100, 120, 140, 160, 180],
                format_func=lambda value: (
                    "Not recorded" if value is None else str(value)
                ),
                key="systolic_bp",
            )
            st.selectbox(
                "RR (breaths/min)",
                [None, 8, 12, 16, 20, 21, 24, 30, 40],
                format_func=lambda value: (
                    "Not recorded" if value is None else str(value)
                ),
                key="respiratory_rate",
            )
        else:
            st.session_state.emergency_symptoms = []
            st.session_state.cbg = None
            st.session_state.systolic_bp = None
            st.session_state.respiratory_rate = None
        st.selectbox(
            "Queue status", ["Waiting", "Checked-in", "In triage"], key="status"
        )
        st.number_input(
            "Wait time (minutes)", min_value=0, max_value=300, key="wait_minutes"
        )

        alert_reasons = (
            emergency_trigger_reasons(
                st.session_state.emergency_symptoms,
                st.session_state.cbg,
                st.session_state.systolic_bp,
                st.session_state.respiratory_rate,
            )
            if st.session_state.acute_complaint
            else []
        )
        is_emergency = bool(alert_reasons)
        emergency_details_complete = bool(
            st.session_state.patient_name.strip()
        ) and all(
            value is not None
            for value in (
                st.session_state.cbg,
                st.session_state.systolic_bp,
                st.session_state.respiratory_rate,
            )
        )
        acute_kidney_details_complete = (
            not st.session_state.acute_complaint
            or (
                st.session_state.egfr is not None
                and st.session_state.months_since_egfr_check is not None
            )
        )
        if not st.session_state.acute_complaint:
            st.session_state.emergency_dialog_dismissed = False
        if (
            is_emergency
            and emergency_details_complete
            and acute_kidney_details_complete
            and not st.session_state.emergency_dialog_dismissed
        ):
            st.error(
                "**EMERGENCY CRITERIA DETECTED — ordinary queue assignment is disabled.**"
            )
            emergency_alert_dialog(
                alert_reasons, accept_emergency_callback, bypass_emergency_callback
            )
        elif is_emergency:
            st.warning(
                "Emergency criteria detected. Enter the patient name, select CBG, SBP, "
                "RR, eGFR, and the last kidney check to show the doctor alert. "
                "Ordinary queue assignment is disabled."
            )
        elif (
            st.session_state.acute_complaint
            and not acute_kidney_details_complete
        ):
            st.warning(
                "For acute complaints, select eGFR and the last kidney check before "
                "adding the patient to the queue."
            )

        st.button(
            "Add patient to queue",
            type="primary",
            key="add_patient_to_queue",
            disabled=is_emergency
            or (
                st.session_state.acute_complaint
                and not acute_kidney_details_complete
            ),
            on_click=add_patient_callback,
            width="stretch",
        )