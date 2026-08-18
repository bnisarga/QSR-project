import streamlit as st
import plotly.express as px

import db

st.set_page_config(page_title="Stock Levels", page_icon="📦", layout="wide")
db.seed_if_empty()

st.title("📦 Current Stock Levels")
st.caption(
    "Live inventory across all outlets, sorted by soonest expiry. Just received a delivery? "
    "Log it on the **Receive Stock** page in the sidebar."
)

if st.button("🔄 Refresh"):
    st.rerun()

summary_df = db.get_stock_summary_df()

st.subheader("Stock Overview by Ingredient")
st.caption(
    "Split into two charts because weight/volume ingredients (kg, L) and countable ones "
    "(buns, cheese slices) aren't on the same scale — mixing them on one axis makes the "
    "smaller bars invisible."
)

if summary_df.empty:
    st.info("No stock remaining.")
else:
    weight_df = summary_df[summary_df["measure_group"] == "Weight / Volume (kg, L)"]
    count_df = summary_df[summary_df["measure_group"] == "Count (units)"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Weight / Volume ingredients**")
        if weight_df.empty:
            st.info("None in stock.")
        else:
            fig = px.bar(
                weight_df.sort_values("display_qty", ascending=False),
                x="name", y="display_qty",
                labels={"name": "Ingredient", "display_qty": "Total stock"},
                color_discrete_sequence=["#1e6f5c"],
                text=weight_df.sort_values("display_qty", ascending=False).apply(
                    lambda r: f"{r['display_qty']} {r['display_unit']}", axis=1
                ),
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(yaxis_title="kg / L")
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Countable ingredients**")
        if count_df.empty:
            st.info("None in stock.")
        else:
            fig = px.bar(
                count_df.sort_values("display_qty", ascending=False),
                x="name", y="display_qty",
                labels={"name": "Ingredient", "display_qty": "Total stock (units)"},
                color_discrete_sequence=["#3f7cd6"],
                text="display_qty",
            )
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

st.subheader("Batch-Level Detail")
inv_df = db.get_inventory_df()

if inv_df.empty:
    st.info("No stock remaining.")
else:
    def format_qty(row):
        qty, unit = row["qty_remaining"], row["unit"]
        if unit in ("g", "ml") and qty >= 1000:
            converted = "kg" if unit == "g" else "L"
            return f"{qty/1000:.2f} {converted}"
        if unit == "unit":
            r = round(qty)
            return f"{r} {'unit' if r == 1 else 'units'}"
        return f"{round(qty)} {unit}"

    display_df = inv_df.copy()
    display_df["Qty Remaining"] = display_df.apply(format_qty, axis=1)
    display_df = display_df.rename(columns={
        "name": "Ingredient", "outlet_id": "Outlet",
        "received_date": "Received", "expiry_date": "Expiry",
    })[["Ingredient", "Outlet", "Qty Remaining", "Received", "Expiry"]]

    st.dataframe(display_df, use_container_width=True, hide_index=True)
