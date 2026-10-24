import html
import time

import pandas as pd
import streamlit as st


def allocated_slot_minutes(triage_level: str) -> int:
    return {"Low": 10, "Moderate": 15, "High": 25}[triage_level]


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def format_kidney_summary(
    egfr: int | float | None, months_since_check: int | float | None
) -> tuple[str, bool]:
    details = []
    if pd.notna(egfr):
        details.append(f"eGFR {int(egfr)} mL/min")
    else:
        details.append("eGFR not recorded")

    if pd.notna(months_since_check):
        details.append(f"Last checked: {int(months_since_check)} mo ago")
    else:
        details.append("Last checked: not recorded")

    overdue = pd.notna(months_since_check) and months_since_check > 12
    status = " [OVERDUE]" if overdue else ""
    return f"Kidney: {' | '.join(details)}{status}", bool(overdue)


def _summary_card(title: str, qualifier: str, items: list[str]) -> str:
    safe_title = html.escape(title)
    safe_qualifier = html.escape(qualifier)
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return (
        f"<section class='cockpit-card'><h3>{safe_title}"
        f"<span> · {safe_qualifier}</span></h3><ul>{body}</ul></section>"
    )


def _patient_value(patient: pd.Series, column: str, fallback: str) -> str:
    value = patient.get(column)
    if value is None or pd.isna(value):
        return fallback
    return str(value)


def _measurement(patient: pd.Series, column: str, label: str, unit: str) -> str:
    value = patient.get(column)
    if value is None or pd.isna(value):
        return f"{label}: Not recorded"
    return f"{label}: {int(value)} {unit}"


@st.fragment(run_every="1s")
def consultation_controls(patient_id: str, slot_minutes: int, archive_callback) -> None:
    consultations = st.session_state.consultations
    consultation = consultations.get(patient_id)

    if consultation is None:
        if st.button(
            "Start Consultation",
            type="primary",
            key=f"start_consultation_{patient_id}",
            width="stretch",
        ):
            consultations[patient_id] = {
                "started_at": time.time(),
                "ended_at": None,
            }
            st.session_state.consultations = consultations
            st.rerun()
        st.caption(f"Starts a timer against the predicted {slot_minutes}-minute slot.")
        return

    ended_at = consultation["ended_at"]
    elapsed_seconds = (ended_at or time.time()) - consultation["started_at"]
    slot_seconds = slot_minutes * 60

    if ended_at is None:
        st.metric("Consultation duration", format_duration(elapsed_seconds))
        st.progress(
            min(elapsed_seconds / slot_seconds, 1.0),
            text=f"{slot_minutes}-minute predicted slot",
        )
        if elapsed_seconds > slot_seconds:
            st.warning(
                f"Predicted slot exceeded by {format_duration(elapsed_seconds - slot_seconds)}."
            )
        else:
            st.caption(
                f"{format_duration(slot_seconds - elapsed_seconds)} remaining in the predicted slot."
            )
        if st.button(
            "End Consultation",
            key=f"end_consultation_{patient_id}",
            width="stretch",
        ):
            archive_callback(patient_id, consultation, time.time())
            st.rerun()
    else:
        st.metric("Consultation duration", format_duration(elapsed_seconds))
        st.caption("Consultation complete.")


def render_doctor_overview(
    patient_options: list[str],
    patient_by_id: pd.DataFrame,
    patient_id_by_label: dict[str, str],
    archive_callback,
) -> None:
    if not patient_options:
        st.subheader("Doctor's summary")
        st.info("No active patients in the queue.")
        return

    selected_patient_label = st.selectbox(
        "Select a patient",
        list(patient_id_by_label),
        key="selected_patient_label",
    )
    selected_patient_id = patient_id_by_label[selected_patient_label]
    st.session_state.selected_patient_id = selected_patient_id
    patient = patient_by_id.loc[selected_patient_id]
    slot_minutes = allocated_slot_minutes(patient["triage_level"])

    if patient["emergency"]:
        st.error("**EMERGENCY PRIORITY — follow your clinical emergency protocol.**")
        emergency_reasons = patient.get("emergency_reasons", [])
        if isinstance(emergency_reasons, list) and emergency_reasons:
            st.markdown(
                f"**Entered emergency flags:** "
                f"{html.escape(', '.join(emergency_reasons))}"
            )

    st.markdown(
        """
        <style>
        .cockpit-heading { margin: 0 0 1.1rem; }
        .cockpit-eyebrow { color: #078b89; font-size: .8rem; font-weight: 800;
            letter-spacing: .16em; margin: 0 0 .25rem; }
        .cockpit-heading h1 { color: #17324d; font-family: Georgia, serif;
            font-size: 2.15rem; margin: 0; }
        .cockpit-patient { color: #64748b; font-size: .9rem; margin-top: .35rem; }
        .cockpit-disclaimer { background: #fff4eb; border: 1px solid #f4c9a8;
            border-radius: 9px; color: #945024; font-size: .88rem;
            font-weight: 600; line-height: 1.45; padding: 12px 15px; }
        .cockpit-banner { align-items: center; background: #112e4b;
            border-radius: 10px; color: white; display: flex; gap: 2rem;
            justify-content: space-between; margin: .4rem 0 1rem; padding: 14px 18px; }
        .cockpit-banner-group { display: flex; flex: 1; gap: 2.5rem; }
        .cockpit-banner-label { color: #8dd2ce; display: block; font-size: .77rem;
            font-weight: 800; letter-spacing: .08em; margin-bottom: 3px; }
        .cockpit-banner-value { font-size: 1rem; font-weight: 700; }
        .cockpit-slot { background: #c8733d; border-radius: 7px;
            min-width: 225px; padding: 8px 14px; }
        .cockpit-slot .cockpit-banner-label { color: #ffe3ce; }
        .cockpit-slot .cockpit-banner-value { font-size: 1.35rem; }
        .cockpit-card { background: #fff; border: 1px solid #e2e8f0;
            border-radius: 10px; margin: 0 0 10px; padding: 15px 16px; }
        .cockpit-card h3 { color: #17324d; font-size: .88rem; margin: 0 0 7px; }
        .cockpit-card h3 span { color: #9aa8b9; font-weight: 500; }
        .cockpit-card ul { color: #64748b; font-size: .84rem;
            line-height: 1.45; margin: 0; padding-left: 1.1rem; }
        .cockpit-card li { margin: 1px 0; }
        .cockpit-trends { align-items: center; display: flex; gap: 1.1rem;
            justify-content: space-between; }
        .cockpit-trends-label { color: #8291a6; flex: 1; font-size: .8rem;
            font-weight: 800; letter-spacing: .05em; }
        .cockpit-trend { color: #607086; font-size: .78rem; text-align: center; }
        .cockpit-trend strong { color: #bd5b3e; display: block; font-size: .86rem; }
        .cockpit-autonomy { background: #edf7f6; border: 1px solid #c6e6e3;
            border-radius: 8px; color: #25455b; font-size: .92rem;
            line-height: 1.5; margin: 4px 0 1rem; padding: 10px 14px; }
        @media (max-width: 700px) {
            .cockpit-banner { align-items: stretch; flex-direction: column; gap: 12px; }
            .cockpit-banner-group { flex-direction: column; gap: 10px; }
            .cockpit-slot { min-width: 0; }
            .cockpit-trends { align-items: flex-start; flex-wrap: wrap; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    heading, disclaimer = st.columns([2, 1])
    heading.markdown(
        # f"<div class='cockpit-heading'><div class='cockpit-eyebrow'>PRODUCT VIEW</div>"
        f"<h1>The Doctor Cockpit</h1><div class='cockpit-patient'>"
        f"{html.escape(str(patient['patient']))} · Patient ID "
        f"{html.escape(str(selected_patient_id))} · "
        f"{html.escape(str(patient['age']))} years</div></div>",
        unsafe_allow_html=True,
    )
    # disclaimer.markdown(
    #     "<div class='cockpit-disclaimer'>Administrative briefing only — "
    #     "not a diagnosis, risk score, or treatment recommendation. "
    #     "Organizes entered data prior to room entry.</div>",
    #     unsafe_allow_html=True,
    # )

    visit_type = "Emergency review" if patient["emergency"] else "Chronic-care follow-up"
    priority = "PRIORITY REVIEW" if patient["triage_level"] == "High" else "SCHEDULED"
    st.markdown(
        f"<div class='cockpit-banner'><div class='cockpit-banner-group'>"
        f"<div><span class='cockpit-banner-label'>CARE PATHWAY</span>"
        f"<span class='cockpit-banner-value'>Diabetes care</span></div>"
        f"<div><span class='cockpit-banner-label'>VISIT TYPE</span>"
        f"<span class='cockpit-banner-value'>{visit_type}</span></div></div>"
        f"<div class='cockpit-slot'><span class='cockpit-banner-label'>"
        f"SUGGESTED SLOT · {priority}</span><span class='cockpit-banner-value'>"
        f"{slot_minutes} min</span></div></div>",
        unsafe_allow_html=True,
    )

    emergency_reasons = patient.get("emergency_reasons", [])
    concerns = (
        [str(reason) for reason in emergency_reasons]
        if isinstance(emergency_reasons, list)
        else []
    )
    concerns.append(
        f"Glycemic control: {_patient_value(patient, 'glycemic_control', 'Not recorded')}"
    )
    concerns.append(
        f"Hypoglycemia frequency: "
        f"{_patient_value(patient, 'hypoglycemia_frequency', 'Not recorded')}"
    )
    if not patient["acute_symptoms"]:
        concerns.insert(0, "No acute complaint reported")

    measurements = [
        _measurement(patient, "systolic_bp", "SBP", "mmHg"),
        _measurement(patient, "cbg", "Glucose", "mg/dL"),
        _measurement(patient, "respiratory_rate", "Respiratory rate", "/min"),
        _measurement(patient, "egfr", "eGFR", "mL/min"),
    ]
    preventive_checks = patient.get("preventive_checks", [])
    renal_screening = _patient_value(patient, "renal_screening", "Not recorded")
    history = [
        f"Glycemic control: {_patient_value(patient, 'glycemic_control', 'Not recorded')}",
        f"Regimen: {_patient_value(patient, 'regimen', 'Not recorded')}",
        f"Renal screening: {renal_screening}",
    ]
    if isinstance(preventive_checks, list) and preventive_checks:
        history.append(f"Overdue preventive checks: {', '.join(preventive_checks)}")
    else:
        history.append("No overdue preventive checks reported")

    medication = [
        f"Current regimen: {_patient_value(patient, 'regimen', 'Not recorded')}",
        f"Missed doses: {_patient_value(patient, 'medication_adherence', 'Not recorded')}",
        f"Hypoglycemia frequency: "
        f"{_patient_value(patient, 'hypoglycemia_frequency', 'Not recorded')}",
    ]
    review_items = ["Current symptoms and entered concerns", "Recent measurements"]
    if _patient_value(patient, "medication_adherence", "None") != "None":
        review_items.append("Medication adherence")
    if renal_screening == "Overdue" or (
        isinstance(preventive_checks, list) and preventive_checks
    ):
        review_items.append("Renal screening / preventive checks")
    review_items.append("Clinician to determine whether further assessment is needed")

    left, right = st.columns(2)
    left.markdown(
        _summary_card("Key Concerns", "patient-reported / entered", concerns),
        unsafe_allow_html=True,
    )
    left.markdown(
        _summary_card("Recent Measurements", "entered data", measurements),
        unsafe_allow_html=True,
    )
    left.markdown(
        _summary_card("Relevant History", "care context", history),
        unsafe_allow_html=True,
    )
    right.markdown(
        _summary_card("Medication / Adherence", "entered data", medication),
        unsafe_allow_html=True,
    )
    right.markdown(
        "<section class='cockpit-card'><div class='cockpit-trends'>"
        "<div class='cockpit-trends-label'>DIRECTIONAL CHANGE VS. PRIOR VISIT</div>"
        "<div class='cockpit-trend'><strong>Symptoms</strong>Unavailable</div>"
        "<div class='cockpit-trend'><strong>Glucose</strong>Unavailable</div>"
        "<div class='cockpit-trend'><strong>Adherence</strong>Unavailable</div>"
        "</div></section>",
        unsafe_allow_html=True,
    )
    right.markdown(
        _summary_card("Items for Clinician Review", "clinical review", review_items),
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='cockpit-autonomy'><strong>Physician Autonomy:</strong> "
        "The clinician retains full control to accept, modify, or disregard this "
        "briefing and determine consultation timing. DiaFlow Assist does not "
        "diagnose or recommend treatment. Data shown is entered for workflow "
        "organization and requires clinician review.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("**Consultation timer**")
    consultation_controls(selected_patient_id, slot_minutes, archive_callback)