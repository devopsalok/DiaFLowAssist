import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(page_title="DiaFlowAssist", layout="wide")


def classify_risk(score: float) -> str:
    if score >= 75:
        return "High"
    if score >= 45:
        return "Moderate"
    return "Low"


@st.cache_data
def load_demo_queue() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": "P-101", "patient": "Aisha Khan", "age": 42, "risk_score": 82, "status": "Waiting", "wait_minutes": 15},
            {"id": "P-102", "patient": "Rahul Mehta", "age": 36, "risk_score": 58, "status": "In triage", "wait_minutes": 9},
            {"id": "P-103", "patient": "Nina Smith", "age": 51, "risk_score": 27, "status": "Checked-in", "wait_minutes": 5},
            {"id": "P-104", "patient": "Daniel Lee", "age": 67, "risk_score": 91, "status": "Urgent", "wait_minutes": 3},
        ]
    )


if "queue" not in st.session_state:
    st.session_state.queue = load_demo_queue()


st.title("DiaFlowAssist")
st.caption("Queue triage and clinical workflow dashboard")

with st.sidebar:
    st.header("Add patient")
    with st.form("patient_form", clear_on_submit=True):
        patient_name = st.text_input("Patient name")
        patient_age = st.number_input("Age", min_value=0, max_value=120, value=30)
        risk_score = st.slider("Risk score", 0, 100, 50)
        status = st.selectbox("Current status", ["Waiting", "Checked-in", "In triage", "Urgent"])
        wait_minutes = st.number_input("Wait time (minutes)", min_value=0, max_value=300, value=0)
        submitted = st.form_submit_button("Add patient")

        if submitted and patient_name:
            new_patient = {
                "id": f"P-{len(st.session_state.queue) + 101}",
                "patient": patient_name,
                "age": int(patient_age),
                "risk_score": int(risk_score),
                "status": status,
                "wait_minutes": int(wait_minutes),
            }
            st.session_state.queue = pd.concat(
                [st.session_state.queue, pd.DataFrame([new_patient])], ignore_index=True
            )
            st.success(f"Added {patient_name} to the queue.")


queue_df = st.session_state.queue.copy()
queue_df["risk_level"] = queue_df["risk_score"].apply(classify_risk)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total patients", len(queue_df))
col2.metric("High risk", int((queue_df["risk_level"] == "High").sum()))
col3.metric("Median wait", f"{queue_df['wait_minutes'].median():.0f} min")
col4.metric("Urgent cases", int((queue_df["status"] == "Urgent").sum()))

chart_col, table_col = st.columns([1.2, 1.8])

with chart_col:
    risk_chart = px.bar(
        queue_df,
        x="patient",
        y="risk_score",
        color="risk_level",
        color_discrete_map={"High": "#d32f2f", "Moderate": "#f9a825", "Low": "#2e7d32"},
        title="Patient risk scores",
    )
    risk_chart.update_layout(height=350, margin={"l": 20, "r": 20, "t": 40, "b": 20})
    st.plotly_chart(risk_chart, use_container_width=True)

with table_col:
    st.subheader("Queue overview")
    display_df = queue_df[["id", "patient", "age", "risk_score", "risk_level", "status", "wait_minutes"]].copy()
    display_df = display_df.sort_values(["risk_score", "wait_minutes"], ascending=[False, True])
    st.dataframe(display_df, use_container_width=True, hide_index=True)

st.subheader("Summary")
summary_text = (
    f"Current queue contains {len(queue_df)} patients. "
    f"{int((queue_df['risk_level'] == 'High').sum())} are flagged as high risk and require prompt attention. "
    f"The longest waiting patient has been queued for {queue_df['wait_minutes'].max()} minutes."
)
st.info(summary_text)
