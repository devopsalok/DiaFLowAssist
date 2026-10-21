import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="DiaFlowAssist", layout="wide")

APPOINTMENT_CSV = Path(__file__).resolve().parent / "data" / "appointment.csv"
PATIENT_CSV = Path(__file__).resolve().parent / "data" / "patient.csv"
VITAL_CSV = Path(__file__).resolve().parent / "data" / "vital.csv"
QUEUE_LIST_COLUMNS = ("drivers", "preventive_checks", "emergency_reasons")


def classify_risk(score: float) -> str:
    if score >= 66:
        return "High"
    if score >= 31:
        return "Moderate"
    return "Low"


def allocated_slot_minutes(triage_level: str) -> int:
    return {"Low": 10, "Moderate": 15, "High": 25}[triage_level]


def calculate_risk_score(
    glycemic_control: str,
    regimen: str,
    preventive_checks: list[str],
    acute_symptoms: bool,
) -> int:
    glycemic_points = {
        "Controlled (<7.5%)": 0,
        "Suboptimal (7.5-9%)": 15,
        "Uncontrolled (>9% or hypos)": 30,
    }[glycemic_control]
    regimen_points = {
        "Lifestyle/Oral": 0,
        "Multi-oral": 10,
        "Insulin": 25,
    }[regimen]
    return (
        glycemic_points
        + regimen_points
        + (15 if preventive_checks else 0)
        + (15 if acute_symptoms else 0)
    )


def build_complexity_drivers(
    glycemic_control: str,
    regimen: str,
    preventive_checks: list[str],
    acute_symptoms: bool,
) -> list[str]:
    drivers = []
    if glycemic_control == "Suboptimal (7.5-9%)":
        drivers.append("Suboptimal glycemic control (HbA1c 7.5-9%)")
    elif glycemic_control == "Uncontrolled (>9% or hypos)":
        drivers.append("Uncontrolled HbA1c (>9%) or hypoglycemia")
    if regimen == "Multi-oral":
        drivers.append("Multi-oral medication regimen")
    elif regimen == "Insulin":
        drivers.append("Insulin regimen")
    if preventive_checks and acute_symptoms:
        drivers.append("Overdue preventive checks and acute symptoms")
    elif preventive_checks:
        drivers.append("Overdue annual preventive checks")
    elif acute_symptoms:
        drivers.append("Acute complaint or symptoms")
    return drivers or ["No elevated-complexity factors reported"]


def status_for_triage(triage_level: str, requested_status: str) -> str:
    return "Urgent" if triage_level == "High" else requested_status


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


def emergency_trigger_reasons(
    symptoms: list[str],
    cbg: int | None,
    systolic_bp: int | None,
    respiratory_rate: int | None,
) -> list[str]:
    reasons = list(symptoms)
    if cbg is not None and cbg < 70:
        reasons.append("Severe hypo (CBG < 70 mg/dL)")
    if cbg is not None and cbg > 300:
        reasons.append("Marked hyper (CBG > 300 mg/dL)")
    if systolic_bp is not None and systolic_bp < 90:
        reasons.append("Hypotension (SBP < 90 mmHg)")
    if respiratory_rate is not None and respiratory_rate > 20:
        reasons.append("Tachypnea (RR > 20/min)")
    return list(dict.fromkeys(reasons))


def reset_patient_form() -> None:
    st.session_state.patient_name = ""
    st.session_state.patient_age = 30
    st.session_state.glycemic_control = "Controlled (<7.5%)"
    st.session_state.regimen = "Lifestyle/Oral"
    st.session_state.preventive_checks = []
    st.session_state.egfr = None
    st.session_state.months_since_egfr_check = None
    st.session_state.acute_complaint = False
    st.session_state.emergency_symptoms = []
    st.session_state.cbg = None
    st.session_state.systolic_bp = None
    st.session_state.respiratory_rate = None
    st.session_state.status = "Waiting"
    st.session_state.wait_minutes = 0


def create_patient_record(emergency: bool) -> dict:
    queue = st.session_state.queue
    patient_numbers = pd.to_numeric(queue["id"].str[2:], errors="coerce").dropna()
    last_patient_number = patient_numbers.max() if not patient_numbers.empty else 100
    patient_id = f"P-{int(last_patient_number) + 1}"
    glycemic_control = st.session_state.glycemic_control
    regimen = st.session_state.regimen
    preventive_checks = st.session_state.preventive_checks
    acute_symptoms = st.session_state.acute_complaint
    risk_score = calculate_risk_score(
        glycemic_control, regimen, preventive_checks, acute_symptoms
    )
    reasons = []
    if acute_symptoms:
        reasons = emergency_trigger_reasons(
            st.session_state.emergency_symptoms,
            st.session_state.cbg,
            st.session_state.systolic_bp,
            st.session_state.respiratory_rate,
        )
    drivers = build_complexity_drivers(
        glycemic_control, regimen, preventive_checks, acute_symptoms
    )
    if emergency:
        drivers.append(f"Emergency criteria met: {', '.join(reasons)}")

    return {
        "id": patient_id,
        "patient": st.session_state.patient_name.strip(),
        "age": int(st.session_state.patient_age),
        "risk_score": risk_score,
        "status": (
            "Emergency"
            if emergency
            else status_for_triage(classify_risk(risk_score), st.session_state.status)
        ),
        "wait_minutes": int(st.session_state.wait_minutes),
        "glycemic_control": glycemic_control,
        "regimen": regimen,
        "acute_symptoms": acute_symptoms,
        "drivers": drivers,
        "preventive_checks": preventive_checks,
        "egfr": st.session_state.egfr,
        "months_since_egfr_check": st.session_state.months_since_egfr_check,
        "emergency": emergency,
        "priority_override": emergency,
        "queue_type": "Emergency" if emergency else "Routine",
        "emergency_reasons": reasons,
        "cbg": st.session_state.cbg,
        "systolic_bp": st.session_state.systolic_bp,
        "respiratory_rate": st.session_state.respiratory_rate,
    }


def add_patient_to_queue(emergency: bool = False) -> None:
    patient_name = st.session_state.patient_name.strip()
    if not patient_name:
        st.session_state.patient_notice = ("error", "Enter a patient name.")
        return
    if st.session_state.acute_complaint and (
        st.session_state.egfr is None
        or st.session_state.months_since_egfr_check is None
    ):
        st.session_state.patient_notice = (
            "error",
            "Select eGFR and the last kidney check for acute complaints.",
        )
        return

    record = create_patient_record(emergency)
    updated_queue = pd.concat(
        [st.session_state.queue, pd.DataFrame([record])],
        ignore_index=True,
    )
    save_queue_data(updated_queue)
    if record["acute_symptoms"] or any(
        record[column] is not None
        for column in ("cbg", "systolic_bp", "respiratory_rate")
    ):
        save_vital_record(record)
    st.session_state.queue = updated_queue
    st.session_state.pending_selected_patient_id = record["id"]
    st.session_state.patient_notice = (
        "success",
        f"Added {patient_name} with Emergency priority."
        if emergency
        else f"Added {patient_name} to the queue.",
    )
    reset_patient_form()
    st.session_state.emergency_dialog_dismissed = True


def bypass_patient_queue() -> None:
    add_patient_to_queue()


def accept_emergency_patient() -> None:
    add_patient_to_queue(emergency=True)
    st.rerun()


def bypass_emergency_patient() -> None:
    bypass_patient_queue()
    st.rerun()


def delete_patient_from_queue(patient_id: str) -> None:
    updated_queue = st.session_state.queue.loc[
        st.session_state.queue["id"] != patient_id
    ].copy()
    save_queue_data(updated_queue)
    st.session_state.queue = updated_queue
    st.session_state.consultations.pop(patient_id, None)
    update_selected_patient_after_removal(updated_queue, patient_id)
    st.session_state.patient_notice = (
        "success",
        f"Deleted patient {patient_id} from the queue.",
    )


def shift_patient_to_ward(patient_id: str) -> None:
    updated_queue = st.session_state.queue.copy()
    updated_queue.loc[updated_queue["id"] == patient_id, "status"] = (
        "Shifted to ward"
    )
    save_queue_data(updated_queue)
    st.session_state.queue = updated_queue
    st.session_state.consultations.pop(patient_id, None)
    update_selected_patient_after_removal(updated_queue, patient_id)
    st.session_state.patient_notice = (
        "success",
        f"Patient {patient_id} shifted to ward and removed from the active queue.",
    )


def archive_patient_after_consultation(
    patient_id: str, consultation: dict, ended_at: float
) -> None:
    patient_row = st.session_state.queue.loc[
        st.session_state.queue["id"] == patient_id
    ]
    if patient_row.empty:
        raise ValueError(f"Cannot archive missing patient {patient_id}.")

    patient_record = patient_row.iloc[0].to_dict()
    patient_record["status"] = "Consultation complete"
    patient_record["consultation_started_at"] = pd.to_datetime(
        consultation["started_at"], unit="s"
    ).isoformat()
    patient_record["consultation_ended_at"] = pd.to_datetime(
        ended_at, unit="s"
    ).isoformat()
    patient_record["consultation_duration_seconds"] = int(
        ended_at - consultation["started_at"]
    )
    patient_history = (
        pd.read_csv(PATIENT_CSV)
        if PATIENT_CSV.exists() and PATIENT_CSV.stat().st_size
        else pd.DataFrame()
    )
    if not patient_history.empty and "id" not in patient_history:
        raise ValueError("Patient history CSV must include an id column.")
    if "id" in patient_history:
        patient_history = patient_history.loc[patient_history["id"] != patient_id]
    updated_history = pd.concat(
        [patient_history, pd.DataFrame([patient_record])],
        ignore_index=True,
    )
    save_table_data(updated_history, PATIENT_CSV)

    updated_queue = st.session_state.queue.loc[
        st.session_state.queue["id"] != patient_id
    ].copy()
    save_queue_data(updated_queue)
    st.session_state.queue = updated_queue
    st.session_state.consultations.pop(patient_id, None)
    update_selected_patient_after_removal(
        updated_queue, patient_id, defer_until_rerun=True
    )
    st.session_state.patient_notice = (
        "success",
        f"Consultation complete. {patient_id} moved to patient history.",
    )


def update_selected_patient_after_removal(
    queue: pd.DataFrame,
    removed_patient_id: str,
    defer_until_rerun: bool = False,
) -> None:
    if st.session_state.get("selected_patient_id") != removed_patient_id:
        return

    active_ids = queue.loc[queue["status"] != "Shifted to ward", "id"]
    next_patient_id = active_ids.iloc[0] if not active_ids.empty else None
    if defer_until_rerun:
        st.session_state.pending_selected_patient_id = next_patient_id
        return

    if active_ids.empty:
        st.session_state.pop("selected_patient_id", None)
    else:
        st.session_state.selected_patient_id = next_patient_id


@st.dialog("Emergency alert", width="large")
def emergency_alert_dialog(reasons: list[str]) -> None:
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
        on_click=accept_emergency_patient,
        width="stretch",
    )
    bypass_col.button(
        "Bypass — add to routine queue",
        key="bypass_emergency",
        on_click=bypass_emergency_patient,
        width="stretch",
    )


@st.cache_data
def load_demo_queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "P-101",
                "patient": "Aisha Khan",
                "age": 42,
                "risk_score": 85,
                "status": "Urgent",
                "wait_minutes": 15,
                "glycemic_control": "Uncontrolled (>9% or hypos)",
                "regimen": "Insulin",
                "acute_symptoms": True,
                "drivers": [
                    "Uncontrolled HbA1c (>9%) or hypoglycemia",
                    "Insulin regimen",
                    "Overdue annual preventive checks",
                    "Acute complaint or symptoms",
                ],
                "preventive_checks": ["uACR", "Foot exam"],
                "egfr": 58,
                "months_since_egfr_check": 14,
                "emergency": False,
                "priority_override": False,
                "queue_type": "Routine",
                "emergency_reasons": [],
                "cbg": None,
                "systolic_bp": None,
                "respiratory_rate": None,
            },
            {
                "id": "P-102",
                "patient": "Rahul Mehta",
                "age": 36,
                "risk_score": 40,
                "status": "In triage",
                "wait_minutes": 9,
                "glycemic_control": "Suboptimal (7.5-9%)",
                "regimen": "Multi-oral",
                "acute_symptoms": False,
                "drivers": [
                    "Suboptimal glycemic control (HbA1c 7.5-9%)",
                    "Multi-oral medication regimen",
                    "Overdue annual preventive checks",
                ],
                "preventive_checks": ["uACR"],
                "egfr": 92,
                "months_since_egfr_check": 8,
                "emergency": False,
                "priority_override": False,
                "queue_type": "Routine",
                "emergency_reasons": [],
                "cbg": None,
                "systolic_bp": None,
                "respiratory_rate": None,
            },
            {
                "id": "P-103",
                "patient": "Nina Smith",
                "age": 51,
                "risk_score": 0,
                "status": "Checked-in",
                "wait_minutes": 5,
                "glycemic_control": "Controlled (<7.5%)",
                "regimen": "Lifestyle/Oral",
                "acute_symptoms": False,
                "drivers": ["No elevated-complexity factors reported"],
                "preventive_checks": [],
                "egfr": 105,
                "months_since_egfr_check": 4,
                "emergency": False,
                "priority_override": False,
                "queue_type": "Routine",
                "emergency_reasons": [],
                "cbg": None,
                "systolic_bp": None,
                "respiratory_rate": None,
            },
            {
                "id": "P-104",
                "patient": "Daniel Lee",
                "age": 67,
                "risk_score": 85,
                "status": "Urgent",
                "wait_minutes": 3,
                "glycemic_control": "Uncontrolled (>9% or hypos)",
                "regimen": "Insulin",
                "acute_symptoms": True,
                "drivers": [
                    "Uncontrolled HbA1c (>9%) or hypoglycemia",
                    "Insulin regimen",
                    "Overdue annual preventive checks",
                    "Acute complaint or symptoms",
                ],
                "preventive_checks": ["uACR", "Eye exam"],
                "egfr": 58,
                "months_since_egfr_check": 14,
                "emergency": False,
                "priority_override": False,
                "queue_type": "Routine",
                "emergency_reasons": [],
                "cbg": None,
                "systolic_bp": None,
                "respiratory_rate": None,
            },
        ]
    )


def save_queue_data(queue: pd.DataFrame) -> None:
    save_table_data(queue, APPOINTMENT_CSV)


def save_table_data(table: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_queue = table.copy()
    for column in QUEUE_LIST_COLUMNS:
        if column in csv_queue:
            csv_queue[column] = csv_queue[column].map(
                lambda value: json.dumps(value)
                if isinstance(value, (list, tuple))
                else value
            )

    temporary_path = path.with_suffix(".csv.tmp")
    csv_queue.to_csv(temporary_path, index=False)
    temporary_path.replace(path)


def save_vital_record(patient: dict) -> None:
    vital_record = {
        "patient_id": patient["id"],
        "patient": patient["patient"],
        "acute_complaint": patient["acute_symptoms"],
        "emergency_symptoms": json.dumps(
            st.session_state.emergency_symptoms
            if patient["acute_symptoms"]
            else []
        ),
        "emergency_reasons": json.dumps(patient["emergency_reasons"]),
        "cbg_mg_dl": patient["cbg"],
        "systolic_bp_mmhg": patient["systolic_bp"],
        "respiratory_rate_per_min": patient["respiratory_rate"],
        "recorded_at": pd.Timestamp.now().isoformat(),
    }
    vital_history = (
        pd.read_csv(VITAL_CSV)
        if VITAL_CSV.exists() and VITAL_CSV.stat().st_size
        else pd.DataFrame()
    )
    if not vital_history.empty and "patient_id" not in vital_history:
        raise ValueError("Vital history CSV must include a patient_id column.")
    if "patient_id" in vital_history:
        vital_history = vital_history.loc[
            vital_history["patient_id"] != patient["id"]
        ]
    updated_history = pd.concat(
        [vital_history, pd.DataFrame([vital_record])],
        ignore_index=True,
    )
    save_table_data(updated_history, VITAL_CSV)


def load_queue_data() -> pd.DataFrame:
    if not APPOINTMENT_CSV.exists() or APPOINTMENT_CSV.stat().st_size == 0:
        queue = load_demo_queue()
        save_queue_data(queue)
        return queue

    queue = pd.read_csv(APPOINTMENT_CSV)
    defaults = {
        "emergency": False,
        "priority_override": False,
        "queue_type": "Routine",
        "emergency_reasons": [],
        "cbg": None,
        "systolic_bp": None,
        "respiratory_rate": None,
    }
    for column, default in defaults.items():
        if column not in queue:
            queue[column] = [
                default.copy() if isinstance(default, list) else default
                for _ in range(len(queue))
            ]

    for column in QUEUE_LIST_COLUMNS:
        queue[column] = queue[column].map(
            lambda value: json.loads(value) if isinstance(value, str) else []
        )
    for column in ("emergency", "priority_override"):
        queue[column] = queue[column].map(
            lambda value: str(value).strip().lower() in {"true", "1"}
        )
    return queue


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
            ended_at = time.time()
            archive_patient_after_consultation(
                patient_id, consultation, ended_at
            )
            st.rerun()
    else:
        st.metric("Consultation duration", format_duration(elapsed_seconds))
        st.caption("Consultation complete.")


if "queue" not in st.session_state:
    st.session_state.queue = load_queue_data()
if "patient_age" not in st.session_state:
    st.session_state.patient_age = 30
if "wait_minutes" not in st.session_state:
    st.session_state.wait_minutes = 0
for column, default in {
    "emergency": False,
    "emergency_reasons": [],
    "cbg": None,
    "systolic_bp": None,
    "respiratory_rate": None,
}.items():
    if column not in st.session_state.queue:
        st.session_state.queue[column] = [
            default.copy() if isinstance(default, list) else default
            for _ in range(len(st.session_state.queue))
        ]
if "consultations" not in st.session_state:
    st.session_state.consultations = {}
if "emergency_dialog_dismissed" not in st.session_state:
    st.session_state.emergency_dialog_dismissed = False


st.title("DiaFlowAssist")
st.caption("A 10-second clinical brief for the next consultation · Demo patient data")

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
    emergency_details_complete = bool(st.session_state.patient_name.strip()) and all(
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
        emergency_alert_dialog(alert_reasons)
    elif is_emergency:
        st.warning(
            "Emergency criteria detected. Enter the patient name, select CBG, SBP, "
            "RR, eGFR, and the last kidney check to show the doctor alert. "
            "Ordinary queue assignment is disabled."
        )
    elif st.session_state.acute_complaint and not acute_kidney_details_complete:
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
        on_click=add_patient_to_queue,
        width="stretch",
    )


queue_df = st.session_state.queue.copy()
active_queue = queue_df[queue_df["status"] != "Shifted to ward"].copy()
active_queue["triage_level"] = active_queue["risk_score"].apply(classify_risk)
active_queue.loc[active_queue["emergency"], "triage_level"] = "High"
active_queue = active_queue.sort_values(
    ["emergency", "risk_score", "wait_minutes"],
    ascending=[False, False, True],
)
emergency_queue = active_queue[active_queue["emergency"]]
routine_queue = active_queue[~active_queue["emergency"]]
patient_options = active_queue["id"].tolist()
patient_by_id = active_queue.set_index("id")
patient_label_by_id = {
    patient_id: (
        f"{patient_by_id.loc[patient_id, 'patient']} · "
        f"{patient_by_id.loc[patient_id, 'triage_level']} priority ({patient_id})"
    )
    for patient_id in patient_options
}
patient_id_by_label = {
    label: patient_id for patient_id, label in patient_label_by_id.items()
}
if "pending_selected_patient_id" in st.session_state:
    pending_patient_id = st.session_state.pop("pending_selected_patient_id")
    st.session_state.pop("selected_patient_id", None)
    if pending_patient_id in patient_options:
        st.session_state.selected_patient_label = patient_label_by_id[
            pending_patient_id
        ]

metric_cols = st.columns(4)
metric_cols[0].metric("Patients in queue", len(active_queue))
metric_cols[1].metric(
    "High triage",
    int((active_queue["triage_level"] == "High").sum()),
)
metric_cols[2].metric(
    "Median wait",
    f"{active_queue['wait_minutes'].median():.0f} min"
    if not active_queue.empty
    else "—",
)
metric_cols[3].metric(
    "Urgent cases",
    int(active_queue["status"].isin(["Urgent", "Emergency"]).sum()),
)

notice = st.session_state.pop("patient_notice", None)
if notice:
    level, message = notice
    getattr(st, level)(message)

st.subheader("Emergency priority queue")
if emergency_queue.empty:
    st.info("No patients currently have Emergency priority.")
else:
    emergency_display = emergency_queue[
        [
            "id",
            "patient",
            "age",
            "risk_score",
            "triage_level",
            "status",
            "emergency",
            "wait_minutes",
        ]
    ].copy()
    emergency_display["emergency"] = emergency_display["emergency"].map(
        {True: "🚨 EMERGENCY", False: ""}
    )
    st.dataframe(emergency_display, width="stretch", hide_index=True)

st.subheader("Routine queue overview")
display_df = routine_queue[
    [
        "id",
        "patient",
        "age",
        "risk_score",
        "triage_level",
        "status",
        "emergency",
        "wait_minutes",
    ]
].copy()
display_df["emergency"] = display_df["emergency"].map(
    {True: "🚨 EMERGENCY", False: ""}
)
st.dataframe(display_df, width="stretch", hide_index=True)

st.subheader("Doctor's summary")
if not patient_options:
    st.info("No active patients in the queue.")
else:
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
        consultation_controls(selected_patient_id, slot_minutes)
