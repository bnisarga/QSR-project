import streamlit as st
import plotly.express as px

import db

st.set_page_config(page_title="QSR Inventory — Place Order", page_icon="🍔", layout="wide")
db.seed_if_empty()

st.title("🍔 Place an Order")
st.caption(
    "This mimics how a real QSR outlet takes orders: a **POS terminal** for dine-in, and "
    "several **online platforms** for delivery — every one of them writes to the same "
    "central inventory, exactly like a real chain's back-end would."
)

menu_items = db.get_menu_items()
outlets = db.get_outlets()

if not menu_items or not outlets:
    st.warning("No menu items or outlets found. Try 'Reset demo data' in the sidebar.")
else:
    menu_lookup = {m["menu_item_name"]: m["menu_item_id"] for m in menu_items}

    with st.form("order_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            menu_choice = st.selectbox("Menu Item", list(menu_lookup.keys()))
        with col2:
            outlet_choice = st.selectbox("Outlet", outlets)
        with col3:
            quantity = st.number_input("Quantity", min_value=1, value=1, step=1)

        st.markdown("**Where is this order coming from?**")
        source_col1, source_col2 = st.columns(2)
        with source_col1:
            source = st.radio("Order source", ["Dine-in (POS)", "Online"], horizontal=True, label_visibility="collapsed")
        with source_col2:
            platform = None
            if source == "Online":
                platform = st.selectbox("Delivery platform", db.ONLINE_PLATFORMS)

        submitted = st.form_submit_button("Place Order", type="primary")

    if submitted:
        order_type = db.DINE_IN_LABEL if source == "Dine-in (POS)" else f"Online - {platform}"
        result = db.place_order(menu_lookup[menu_choice], outlet_choice, int(quantity), order_type)
        if result["status"] == "success":
            st.success(result["message"])
        elif result["status"] == "warning":
            st.warning(result["message"])
        else:
            st.error(result["message"])

st.divider()
st.subheader("Orders by Channel (last 7 days)")
st.caption("Every dine-in and online order — regardless of which delivery platform it came through — lands in the same inventory.")

channel_df = db.get_channel_summary_df()
if channel_df.empty:
    st.info("No orders placed yet in the last 7 days. Try the order form above, or use **'Simulate order history'** in the sidebar to populate realistic demo data across the last 30 days.")
else:
    fig = px.pie(
        channel_df,
        names="channel_group",
        values="total_items",
        color="channel_group",
        color_discrete_map={"Dine-in": "#1e6f5c", "Online": "#e0a326"},
        hole=0.35,
    )
    fig.update_traces(textinfo="label+percent+value")
    st.plotly_chart(fig, use_container_width=True)

with st.sidebar:
    st.markdown("### About this app")
    st.write(
        "A local prototype for expiry-aware inventory management in a multi-outlet QSR chain. "
        "Dine-in and every online platform write to the same live stock, using FIFO by expiry date."
    )

    st.markdown("### Demo data")
    st.caption(
        "Placing orders one at a time is realistic, but slow for seeing trends. "
        "This backfills the last 30 days with realistic order volume across both outlets, "
        "dine-in, and every online platform, so the Insights timeline has something to show."
    )
    if st.button("📈 Simulate order history (last 30 days)"):
        result = db.generate_simulated_orders(days=30)
        st.success(result["message"])
        st.rerun()

    st.divider()
    if st.button("🔄 Reset demo data"):
        db.reset_data()
        st.success("Data reset to the original starting state.")
        st.rerun()
