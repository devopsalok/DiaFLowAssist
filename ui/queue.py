import pandas as pd
import streamlit as st


QUEUE_DISPLAY_COLUMNS = [
    "id",
    "patient",
    "age",
    "workload_index",
    "Workload_tier",
    "status",
    "emergency",
    "wait_minutes",
]


def _display_queue(queue: pd.DataFrame) -> pd.DataFrame:
    display = queue[QUEUE_DISPLAY_COLUMNS].copy()
    display["emergency"] = display["emergency"].map(
        {True: "🚨 EMERGENCY", False: ""}
    )
    return display


def render_queue_overview(
    queue: pd.DataFrame, classify_risk
) -> tuple[list[str], pd.DataFrame, dict[str, str]]:
    active_queue = queue[queue["status"] != "Shifted to ward"].copy()
    active_queue["Workload_tier"] = active_queue["workload_index"].apply(classify_risk)
    active_queue.loc[active_queue["emergency"], "Workload_tier"] = "High"
    active_queue = active_queue.sort_values(
        ["emergency", "workload_index", "wait_minutes"],
        ascending=[False, False, True],
    )
    emergency_queue = active_queue[active_queue["emergency"]]
    routine_queue = active_queue[~active_queue["emergency"]]
    patient_options = active_queue["id"].tolist()
    patient_by_id = active_queue.set_index("id")
    patient_label_by_id = {
        patient_id: (
            f"{patient_by_id.loc[patient_id, 'patient']} · "
            f"{patient_by_id.loc[patient_id, 'Workload_tier']} priority ({patient_id})"
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
        int((active_queue["Workload_tier"] == "High").sum()),
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
        st.dataframe(
            _display_queue(emergency_queue), width="stretch", hide_index=True
        )

    st.subheader("Routine queue overview")
    st.dataframe(_display_queue(routine_queue), width="stretch", hide_index=True)
    return patient_options, patient_by_id, patient_id_by_label