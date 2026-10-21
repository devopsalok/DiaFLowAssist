import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ui.doctor import render_doctor_overview
from ui.patient import render_patient_intake
from ui.queue import render_queue_overview


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

render_patient_intake(
    emergency_trigger_reasons,
    add_patient_to_queue,
    accept_emergency_patient,
    bypass_emergency_patient,
)

patient_options, patient_by_id, patient_id_by_label = (
    render_queue_overview(st.session_state.queue.copy(), classify_risk)
)
render_doctor_overview(
    patient_options,
    patient_by_id,
    patient_id_by_label,
    archive_patient_after_consultation,
)
