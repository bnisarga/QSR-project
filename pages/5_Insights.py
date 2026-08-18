import streamlit as st
import plotly.express as px

import db

st.set_page_config(page_title="Insights", page_icon="📊", layout="wide")
db.seed_if_empty()

st.title("📊 Business Insights")
st.caption("How sales are trending, which channel and platform they're coming from, and where food waste risk is concentrated.")

if st.button("🔄 Refresh"):
    st.rerun()

st.subheader("Summary")
for line in db.get_summary_lines():
    st.markdown(f"- {line}")

st.divider()

st.subheader("Sales Timeline — Dine-in vs Online")
st.caption(
    "Daily order volume over the last 30 days. Use this to compare how the two channels "
    "are trending relative to each other, or to spot unusual spikes/dips on specific days. "
    "If this looks empty, use **'Simulate order history'** in the sidebar on the Place Order page."
)

trend_df = db.get_daily_sales_trend_df(days=30)
if trend_df.empty:
    st.info("No order history in the last 30 days yet.")
else:
    fig = px.line(
        trend_df, x="date", y="total_qty", color="channel_group",
        markers=True,
        labels={"date": "Date", "total_qty": "Items sold", "channel_group": "Channel"},
        color_discrete_map={"Dine-in": "#1e6f5c", "Online": "#e0a326"},
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Best-Selling Menu Items")
    st.caption("Total quantity sold in the last 7 days, dine-in and online combined.")
    best_sellers_df = db.get_best_sellers_df()
    if best_sellers_df.empty:
        st.info("No orders yet.")
    else:
        fig = px.bar(
            best_sellers_df.sort_values("total_sold"),
            x="total_sold", y="menu_item_name", orientation="h",
            labels={"total_sold": "Units sold (last 7 days)", "menu_item_name": ""},
            color_discrete_sequence=["#3f7cd6"],
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Dine-in vs Online — by Item")
    st.caption("Which items sell better through which channel.")
    channel_item_df = db.get_channel_by_item_df()
    if channel_item_df.empty:
        st.info("No orders yet.")
    else:
        fig = px.bar(
            channel_item_df,
            x="menu_item_name", y="qty", color="channel_group",
            barmode="stack",
            labels={"menu_item_name": "", "qty": "Units sold", "channel_group": "Channel"},
            color_discrete_map={"Dine-in": "#1e6f5c", "Online": "#e0a326"},
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Which Online Platform Sells the Most")
st.caption("Among online orders only — own website vs. each delivery app, over the last 7 days.")
platform_df = db.get_platform_breakdown_df()
if platform_df.empty:
    st.info("No online orders yet.")
else:
    fig = px.bar(
        platform_df,
        x="platform", y="total_items",
        labels={"platform": "Platform", "total_items": "Items sold"},
        color_discrete_sequence=["#e0a326"],
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Estimated Waste Value at Risk")
st.caption("Cost of ingredient batches currently flagged HIGH or MEDIUM expiry risk, by ingredient (in €, using each ingredient's unit cost).")

waste_df = db.get_waste_value_df()
if waste_df.empty:
    st.success("Nothing at risk right now.")
else:
    fig = px.bar(
        waste_df,
        x="name", y="value_at_risk",
        labels={"name": "Ingredient", "value_at_risk": "Value at risk (€)"},
        color_discrete_sequence=["#d64545"],
    )
    st.plotly_chart(fig, use_container_width=True)
