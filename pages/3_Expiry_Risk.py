import streamlit as st
import plotly.express as px

import db

st.set_page_config(page_title="Expiry Risk", page_icon="⏰", layout="wide")
db.seed_if_empty()

st.title("⏰ Expiration Risk")
st.caption("HIGH = expires within 2 days · MEDIUM = within 5 days · LOW = more than 5 days remaining.")

if st.button("🔄 Refresh"):
    st.rerun()

risk_df = db.get_expiry_risk_df()

if risk_df.empty:
    st.info("No stock remaining.")
else:
    counts = risk_df["risk_level"].value_counts().reindex(["HIGH", "MEDIUM", "LOW"], fill_value=0)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Risk Breakdown")
        fig = px.pie(
            names=counts.index,
            values=counts.values,
            color=counts.index,
            color_discrete_map={"HIGH": "#d64545", "MEDIUM": "#e0a326", "LOW": "#2f9e44"},
            hole=0.45,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("At a glance")
        st.metric("HIGH risk batches", int(counts["HIGH"]))
        st.metric("MEDIUM risk batches", int(counts["MEDIUM"]))
        st.metric("LOW risk batches", int(counts["LOW"]))

    st.subheader("Batch-Level Detail")

    def format_qty(row):
        qty, unit = row["qty_remaining"], row["unit"]
        if unit in ("g", "ml") and qty >= 1000:
            converted = "kg" if unit == "g" else "L"
            return f"{qty/1000:.2f} {converted}"
        if unit == "unit":
            r = round(qty)
            return f"{r} {'unit' if r == 1 else 'units'}"
        return f"{round(qty)} {unit}"

    def format_days(d):
        return "Expired" if d <= 0 else f"{d:.1f} days"

    display_df = risk_df.copy()
    display_df["Qty Remaining"] = display_df.apply(format_qty, axis=1)
    display_df["Days Left"] = display_df["days_left"].apply(format_days)
    display_df = display_df.rename(columns={
        "name": "Ingredient", "outlet_id": "Outlet",
        "expiry_date": "Expiry Date", "risk_level": "Risk",
    })[["Ingredient", "Outlet", "Qty Remaining", "Expiry Date", "Days Left", "Risk"]]

    def highlight_risk(row):
        color = {"HIGH": "#fde2e2", "MEDIUM": "#fdf1d6", "LOW": "#e3f3e3"}.get(row["Risk"], "")
        return [f"background-color: {color}"] * len(row)

    st.dataframe(display_df.style.apply(highlight_risk, axis=1), use_container_width=True, hide_index=True)
