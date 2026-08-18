from datetime import date, timedelta

import streamlit as st

import db

st.set_page_config(page_title="Receive Stock", page_icon="🚚", layout="wide")
db.seed_if_empty()

st.title("🚚 Receive Stock")
st.caption(
    "Log a new delivery. This adds a fresh batch to inventory — it doesn't overwrite what's "
    "already there, so older stock is still used first (FIFO) once orders are placed."
)

ingredients = db.get_ingredients()
outlets = db.get_outlets()

if not ingredients or not outlets:
    st.warning("No ingredients or outlets found. Try 'Reset demo data' on the Place Order page.")
else:
    ingredient_lookup = {f"{i['name']} ({i['unit']})": i for i in ingredients}

    # NOTE: these fields are deliberately OUTSIDE any st.form. Streamlit only
    # reruns the script for widgets inside a form when the submit button is
    # clicked, so a checkbox inside a form can't immediately enable/disable
    # another widget on the same render. Keeping them as plain widgets means
    # every click reruns the script right away, so the expiry override field
    # actually becomes editable the instant you tick the box.
    col1, col2 = st.columns(2)
    with col1:
        ingredient_choice_label = st.selectbox("Ingredient", list(ingredient_lookup.keys()))
        selected_ingredient = ingredient_lookup[ingredient_choice_label]
        outlet_choice = st.selectbox("Outlet", outlets)
        quantity = st.number_input(f"Quantity Received ({selected_ingredient['unit']})", min_value=0.0, step=1.0)

    with col2:
        received_date = st.date_input("Date Received", value=date.today())
        use_override = st.checkbox("Override expiry date manually")
        if use_override:
            expiry_override = st.date_input("Expiry Date (override)", value=date.today())
        else:
            auto_expiry = received_date + timedelta(days=selected_ingredient["shelf_life_days"])
            st.text_input("Expiry Date (auto-calculated)", value=auto_expiry.strftime("%Y-%m-%d"), disabled=True)
            expiry_override = None

    st.caption(
        f"Typical shelf life for **{selected_ingredient['name']}** is "
        f"**{selected_ingredient['shelf_life_days']} days** from the received date. "
        f"Tick the box above only if this specific batch is different (e.g. it arrived "
        f"already a bit older, or the supplier gave a different date)."
    )

    if st.button("Add to Inventory", type="primary"):
        if quantity <= 0:
            st.error("Enter a quantity greater than 0.")
        else:
            expiry_str = expiry_override.strftime("%Y-%m-%d") if use_override and expiry_override else None
            result = db.receive_stock(
                selected_ingredient["ingredient_id"],
                outlet_choice,
                quantity,
                received_date.strftime("%Y-%m-%d"),
                expiry_str,
            )
            if result["status"] == "success":
                st.success(result["message"])
            else:
                st.error(result["message"])
