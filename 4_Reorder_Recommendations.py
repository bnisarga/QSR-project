import streamlit as st

import db

st.set_page_config(page_title="Reorder Recommendations", page_icon="🔁", layout="wide")
db.seed_if_empty()

st.title("🔁 Reorder Recommendations")
st.caption(
    "Based on average daily usage (derived from ALL orders — dine-in and online combined — × recipe) "
    "over the last 7 days, versus current stock and a 2-day lead time. "
    "Flagged something? Log the new delivery on **Receive Stock**."
)

if st.button("🔄 Refresh"):
    st.rerun()

reorder_df = db.get_reorder_df()

if reorder_df.empty:
    st.info("No data yet — place a few orders first so there's usage history to work from.")
else:
    def format_qty(qty, unit):
        if unit in ("g", "ml") and qty >= 1000:
            converted = "kg" if unit == "g" else "L"
            return f"{qty/1000:.2f} {converted}"
        if unit == "unit":
            r = round(qty)
            return f"{r} {'unit' if r == 1 else 'units'}"
        return f"{round(qty)} {unit}"

    display_df = reorder_df.copy()
    display_df["Current Stock"] = display_df.apply(lambda r: format_qty(r["current_stock"], r["unit"]), axis=1)
    display_df["Avg Daily Usage"] = display_df.apply(lambda r: format_qty(r["avg_daily_usage"], r["unit"]) + "/day", axis=1)
    display_df["Days of Stock Left"] = display_df["days_of_stock_left"].apply(
        lambda d: "N/A" if d is None else f"{d:.1f} days"
    )
    display_df["Needs Reorder?"] = display_df["needs_reorder"].apply(lambda x: "🔴 YES" if x else "No")
    display_df["Recommended Qty"] = display_df.apply(lambda r: format_qty(r["recommended_qty"], r["unit"]), axis=1)

    display_df = display_df.rename(columns={"name": "Ingredient", "outlet_id": "Outlet"})[
        ["Ingredient", "Outlet", "Current Stock", "Avg Daily Usage", "Days of Stock Left", "Needs Reorder?", "Recommended Qty"]
    ]

    # Show items that need reordering first
    display_df = display_df.sort_values("Needs Reorder?", ascending=False)

    st.dataframe(display_df, use_container_width=True, hide_index=True)
