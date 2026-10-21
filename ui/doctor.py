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
    st.subheader("Doctor's summary")
    if not patient_options:
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

    with st.container(border=True):
        st.subheader("10-second clinical summary")
        if patient["emergency"]:
            st.error(
                "**EMERGENCY PRIORITY — follow your clinical emergency protocol.**"
            )
            st.markdown(
                f"**Emergency flags:** {', '.join(patient['emergency_reasons'])}"
            )
            emergency_vitals = st.columns(3)
            emergency_vitals[0].metric(
                "CBG",
                "Not recorded"
                if pd.isna(patient["cbg"])
                else f"{int(patient['cbg'])} mg/dL",
            )
            emergency_vitals[1].metric(
                "SBP",
                "Not recorded"
                if pd.isna(patient["systolic_bp"])
                else f"{int(patient['systolic_bp'])} mmHg",
            )
            emergency_vitals[2].metric(
                "Respiratory rate",
                "Not recorded"
                if pd.isna(patient["respiratory_rate"])
                else f"{int(patient['respiratory_rate'])} /min",
            )

        header_cols = st.columns([3, 1, 1, 1])
        header_cols[0].markdown(f"### {patient['patient']}")
        header_cols[0].caption(f"Patient ID · {selected_patient_id}")
        header_cols[1].metric("Age", f"{patient['age']} years")
        header_cols[2].metric("Triage", patient["triage_level"])
        header_cols[3].metric("Allocated slot", f"{slot_minutes} min")

        st.markdown("**Complexity drivers**")
        drivers = patient["drivers"]
        driver_cols = st.columns(max(1, len(drivers)))
        for index, driver in enumerate(drivers):
            driver_cols[index].markdown(
                f"<div style='background:#f1f5f9;border-left:4px solid #2563eb;"
                f"border-radius:6px;padding:12px;min-height:58px'>"
                f"<strong>{index + 1}.</strong> {driver}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("**Preventive checks**")
        preventive_checks = patient["preventive_checks"]
        if preventive_checks:
            badges = "".join(
                f"<span style='display:inline-block;background:#991b1b;color:#fff;"
                f"font-weight:700;padding:8px 12px;border-radius:999px;margin:0 8px 8px 0'>"
                f"⚠️ {check} Due</span>"
                for check in preventive_checks
            )
            st.markdown(badges, unsafe_allow_html=True)
        else:
            st.success("No overdue annual checks flagged.")

        st.markdown("**Kidney function**")
        kidney_summary, kidney_overdue = format_kidney_summary(
            patient["egfr"], patient["months_since_egfr_check"]
        )
        if kidney_overdue:
            st.warning(kidney_summary)
        else:
            st.info(kidney_summary)

        st.markdown("**Consultation timer**")
        consultation_controls(selected_patient_id, slot_minutes, archive_callback)