import streamlit as st
import plotly.express as px

import db

st.set_page_config(page_title="Channel Profitability", page_icon="💰", layout="wide")
db.seed_if_empty()

st.title("💰 Channel Profitability")
st.caption(
    "Delivery platforms typically charge 15-30% commission per order. Combined with food "
    "cost, some items can be selling at a loss on certain platforms without anyone noticing — "
    "this page makes that visible."
)

if st.button("🔄 Refresh"):
    st.rerun()

# ---------------------------------------------------------------------------
# Editable menu pricing
# ---------------------------------------------------------------------------
st.subheader("Menu Pricing & Food Cost")
st.caption(
    "Food cost is calculated automatically from the recipe (BOM) × each ingredient's cost — "
    "the same data used for stock deduction. Selling price is editable, since that's a "
    "business decision, not something derived from ingredients."
)

pricing_df = db.get_menu_pricing_df()

if pricing_df.empty:
    st.info("No menu items found.")
else:
    with st.form("pricing_form"):
        new_prices = {}
        cols = st.columns(len(pricing_df))
        for col, (_, row) in zip(cols, pricing_df.iterrows()):
            with col:
                st.markdown(f"**{row['menu_item_name']}**")
                st.caption(f"Food cost: €{row['food_cost']:.2f}")
                new_prices[row["menu_item_id"]] = st.number_input(
                    "Selling price (€)", min_value=0.0, value=float(row["price"]), step=0.10,
                    key=f"price_{row['menu_item_id']}",
                )

        save_prices = st.form_submit_button("Save Prices", type="primary")

    if save_prices:
        for menu_item_id, price in new_prices.items():
            db.update_menu_price(menu_item_id, price)
        st.success("Prices updated.")
        st.rerun()

    # Show gross margin (before commission) as a quick reference table
    st.dataframe(
        pricing_df.rename(columns={
            "menu_item_name": "Item", "price": "Price (€)", "food_cost": "Food Cost (€)",
            "gross_margin": "Gross Margin (€)", "gross_margin_pct": "Gross Margin %",
        })[["Item", "Price (€)", "Food Cost (€)", "Gross Margin (€)", "Gross Margin %"]].round(2),
        use_container_width=True, hide_index=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# Editable commission rates
# ---------------------------------------------------------------------------
st.subheader("Platform Commission Rates")
st.caption(
    "Dine-in and your own website cost little to nothing extra. Third-party delivery apps "
    "take a cut of every order — adjust these to match your actual negotiated rates."
)

commission_df = db.get_commission_rates_df()

if commission_df.empty:
    st.info("No commission data found.")
else:
    with st.form("commission_form"):
        new_rates = {}
        cols = st.columns(len(commission_df))
        for col, (_, row) in zip(cols, commission_df.iterrows()):
            with col:
                st.markdown(f"**{row['platform']}**")
                new_rates[row["order_type"]] = st.number_input(
                    "Commission %", min_value=0.0, max_value=100.0,
                    value=float(row["commission_rate"]) * 100, step=1.0,
                    key=f"comm_{row['order_type']}",
                )

        save_rates = st.form_submit_button("Save Commission Rates", type="primary")

    if save_rates:
        for order_type, rate_pct in new_rates.items():
            db.update_commission_rate(order_type, rate_pct / 100)
        st.success("Commission rates updated.")
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Profitability views
# ---------------------------------------------------------------------------
st.subheader("Net Margin by Platform (last 7 days)")
st.caption("Revenue minus commission minus food cost, per channel. Negative bars mean that channel is losing money overall.")

platform_profit_df = db.get_platform_profitability_df(days=7)
if platform_profit_df.empty:
    st.info("No order history in the last 7 days. Place some orders or use 'Simulate order history' on the Place Order page.")
else:
    platform_profit_df["color"] = platform_profit_df["net_margin"].apply(lambda x: "Profitable" if x >= 0 else "Loss-making")
    fig = px.bar(
        platform_profit_df, x="platform", y="net_margin", color="color",
        labels={"platform": "Channel", "net_margin": "Net margin (€)", "color": ""},
        color_discrete_map={"Profitable": "#2f9e44", "Loss-making": "#d64545"},
        text=platform_profit_df["net_margin"].round(2),
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        platform_profit_df.rename(columns={
            "platform": "Channel", "revenue": "Revenue (€)", "commission": "Commission Paid (€)",
            "food_cost_total": "Food Cost (€)", "net_margin": "Net Margin (€)", "margin_pct": "Margin %",
        })[["Channel", "Revenue (€)", "Commission Paid (€)", "Food Cost (€)", "Net Margin (€)", "Margin %"]].round(2),
        use_container_width=True, hide_index=True,
    )

st.divider()

st.subheader("Net Margin by Item × Platform (last 7 days)")
st.caption("The same item can be profitable on one platform and a loss on another, once commission is factored in.")

item_platform_df = db.get_channel_profitability_df(days=7)
if item_platform_df.empty:
    st.info("No order history in the last 7 days.")
else:
    item_platform_df["label"] = item_platform_df["menu_item_name"] + " — " + item_platform_df["platform"]
    item_platform_df["color"] = item_platform_df["net_margin"].apply(lambda x: "Profitable" if x >= 0 else "Loss-making")

    fig = px.bar(
        item_platform_df.sort_values("net_margin"),
        x="net_margin", y="label", orientation="h", color="color",
        labels={"net_margin": "Net margin (€)", "label": ""},
        color_discrete_map={"Profitable": "#2f9e44", "Loss-making": "#d64545"},
    )
    st.plotly_chart(fig, use_container_width=True)

    def highlight_loss(row):
        color = "#fde2e2" if row["is_loss_making"] else ""
        return [f"background-color: {color}"] * len(row)

    display_df = item_platform_df.rename(columns={
        "menu_item_name": "Item", "platform": "Platform", "quantity": "Qty Sold",
        "revenue": "Revenue (€)", "commission": "Commission (€)", "food_cost_total": "Food Cost (€)",
        "net_margin": "Net Margin (€)", "margin_pct": "Margin %", "net_margin_per_order": "Margin per Order (€)",
    })[["Item", "Platform", "Qty Sold", "Revenue (€)", "Commission (€)", "Food Cost (€)",
        "Net Margin (€)", "Margin %", "Margin per Order (€)", "is_loss_making"]].round(2)

    st.dataframe(display_df.style.apply(highlight_loss, axis=1), use_container_width=True, hide_index=True)

st.divider()

st.subheader("⚠️ Loss-Making Combinations")
flags = db.get_loss_making_flags(days=7)
if not flags:
    st.success("No item/platform combination is currently losing money.")
else:
    for flag in flags:
        st.markdown(f"- {flag}")
