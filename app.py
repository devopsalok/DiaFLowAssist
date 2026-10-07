import time

import pandas as pd
import streamlit as st


st.set_page_config(page_title="DiaFlowAssist", layout="wide")


def classify_risk(score: float) -> str:
    if score >= 75:
        return "High"
    if score >= 45:
        return "Mod"
    return "Low"


def allocated_slot_minutes(triage_level: str) -> int:
    return {"Low": 15, "Mod": 25, "High": 40}[triage_level]


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


@st.cache_data
def load_demo_queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "P-101",
                "patient": "Aisha Khan",
                "age": 42,
                "risk_score": 82,
                "status": "Waiting",
                "wait_minutes": 15,
                "drivers": [
                    "Uncontrolled HbA1c (9.2%)",
                    "Basal-bolus insulin regimen",
                    "Recent hypoglycemia symptoms",
                ],
                "preventive_checks": ["uACR Overdue", "Foot Exam Due"],
            },
            {
                "id": "P-102",
                "patient": "Rahul Mehta",
                "age": 36,
                "risk_score": 58,
                "status": "In triage",
                "wait_minutes": 9,
                "drivers": [
                    "HbA1c above target (8.1%)",
                    "Insulin titration needs review",
                ],
                "preventive_checks": ["uACR Overdue"],
            },
            {
                "id": "P-103",
                "patient": "Nina Smith",
                "age": 51,
                "risk_score": 27,
                "status": "Checked-in",
                "wait_minutes": 5,
                "drivers": [
                    "Stable glucose control reported",
                    "No recent hypoglycemia symptoms",
                ],
                "preventive_checks": [],
            },
            {
                "id": "P-104",
                "patient": "Daniel Lee",
                "age": 67,
                "risk_score": 91,
                "status": "Urgent",
                "wait_minutes": 3,
                "drivers": [
                    "Very high triage score (91/100)",
                    "Complex medication regimen",
                    "Recent glucose swings reported",
                ],
                "preventive_checks": ["uACR Overdue", "Foot Exam Due"],
            },
        ]
    )


@st.fragment(run_every="1s")
def consultation_controls(patient_id: str, slot_minutes: int) -> None:
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
            consultation["ended_at"] = time.time()
            consultations[patient_id] = consultation
            st.session_state.consultations = consultations
            st.rerun()
    else:
        st.metric("Consultation duration", format_duration(elapsed_seconds))
        st.caption("Consultation complete.")


if "queue" not in st.session_state:
    st.session_state.queue = load_demo_queue()
if "consultations" not in st.session_state:
    st.session_state.consultations = {}


st.title("DiaFlowAssist")
st.caption("A 10-second clinical brief for the next consultation · Demo patient data")

with st.sidebar:
    st.header("Add patient")
    with st.form("patient_form", clear_on_submit=True):
        patient_name = st.text_input("Patient name")
        patient_age = st.number_input("Age", min_value=0, max_value=120, value=30)
        risk_score = st.slider("Risk score", 0, 100, 50)
        status = st.selectbox(
            "Current status", ["Waiting", "Checked-in", "In triage", "Urgent"]
        )
        wait_minutes = st.number_input(
            "Wait time (minutes)", min_value=0, max_value=300, value=0
        )
        submitted = st.form_submit_button("Add patient")

        if submitted and patient_name.strip():
            new_patient = {
                "id": f"P-{len(st.session_state.queue) + 101}",
                "patient": patient_name.strip(),
                "age": int(patient_age),
                "risk_score": int(risk_score),
                "status": status,
                "wait_minutes": int(wait_minutes),
                "drivers": [
                    "Risk score entered at triage",
                    "Clinical details not yet recorded",
                ],
                "preventive_checks": None,
            }
            st.session_state.queue = pd.concat(
                [st.session_state.queue, pd.DataFrame([new_patient])],
                ignore_index=True,
            )
            st.success(f"Added {patient_name.strip()} to the queue.")


queue_df = st.session_state.queue.copy()
queue_df["triage_level"] = queue_df["risk_score"].apply(classify_risk)
priority_queue = queue_df.sort_values(
    ["risk_score", "wait_minutes"], ascending=[False, True]
)
patient_options = priority_queue["id"].tolist()
patient_by_id = queue_df.set_index("id")

selected_patient_id = st.selectbox(
    "Patient summary",
    patient_options,
    format_func=lambda patient_id: (
        f"{patient_by_id.loc[patient_id, 'patient']} · "
        f"{patient_by_id.loc[patient_id, 'triage_level']} priority"
    ),
)
patient = patient_by_id.loc[selected_patient_id]
slot_minutes = allocated_slot_minutes(patient["triage_level"])

metric_cols = st.columns(4)
metric_cols[0].metric("Patients in queue", len(queue_df))
metric_cols[1].metric(
    "High triage",
    int((queue_df["triage_level"] == "High").sum()),
)
metric_cols[2].metric(
    "Median wait",
    f"{queue_df['wait_minutes'].median():.0f} min",
)
metric_cols[3].metric(
    "Urgent cases",
    int((queue_df["status"] == "Urgent").sum()),
)

with st.container(border=True):
    st.subheader("10-second clinical summary")
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
    if preventive_checks is None:
        st.info("Annual check status not recorded.")
    elif preventive_checks:
        badges = "".join(
            f"<span style='display:inline-block;background:#991b1b;color:#fff;"
            f"font-weight:700;padding:8px 12px;border-radius:999px;margin:0 8px 8px 0'>"
            f"{check}</span>"
            for check in preventive_checks
        )
        st.markdown(badges, unsafe_allow_html=True)
    else:
        st.success("No overdue annual checks flagged.")

    st.markdown("**Consultation timer**")
    consultation_controls(selected_patient_id, slot_minutes)

with st.expander("Queue overview"):
    display_df = priority_queue[
        [
            "id",
            "patient",
            "age",
            "risk_score",
            "triage_level",
            "status",
            "wait_minutes",
        ]
    ].copy()
    st.dataframe(display_df, width="stretch", hide_index=True)
