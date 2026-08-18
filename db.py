"""
db.py — all data access and business logic for the QSR inventory app.

Order channels model a real setup:
- Dine-in orders come from the in-restaurant POS terminal.
- Online orders can come from several delivery platforms (own website,
  Uber Eats, Zomato, Swiggy, DoorDash) -- every one of them feeds the
  same central inventory, exactly like a real multi-outlet chain.

Every order -- whichever channel it came from -- goes through place_order(),
which is the single source of truth for stock deduction (FIFO by expiry).
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

random.seed(42)

INGREDIENTS = [
    ("ING001", "Lettuce", "g", "perishable", 8, 0.005),
    ("ING002", "Tomato", "g", "perishable", 6, 0.004),
    ("ING003", "Chicken Breast", "g", "perishable", 2, 0.012),
    ("ING004", "Burger Bun", "unit", "semi-perishable", 5, 0.15),
    ("ING005", "Cheese Slice", "unit", "semi-perishable", 14, 0.10),
    ("ING006", "Onion", "g", "dry", 30, 0.002),
    ("ING007", "Sauce", "ml", "dry", 45, 0.003),
]

RECIPES = [
    ("MENU01", "Classic Burger", "ING003", 150),
    ("MENU01", "Classic Burger", "ING004", 1),
    ("MENU01", "Classic Burger", "ING001", 20),
    ("MENU01", "Classic Burger", "ING002", 25),
    ("MENU01", "Classic Burger", "ING007", 15),
    ("MENU02", "Cheese Burger", "ING003", 150),
    ("MENU02", "Cheese Burger", "ING004", 1),
    ("MENU02", "Cheese Burger", "ING005", 1),
    ("MENU02", "Cheese Burger", "ING006", 10),
    ("MENU03", "Veg Wrap", "ING001", 40),
    ("MENU03", "Veg Wrap", "ING002", 30),
    ("MENU03", "Veg Wrap", "ING006", 15),
]

OUTLETS = ["OUT01", "OUT02"]

# Real QSR chains take online orders from several delivery platforms at once,
# on top of their own website -- not just a generic "Online" bucket.
ONLINE_PLATFORMS = ["Own Website", "Uber Eats", "Zomato", "Swiggy", "DoorDash"]
DINE_IN_LABEL = "Dine-in (POS)"

# Selling prices (€) -- editable later via the Channel Profitability page.
DEFAULT_MENU_PRICES = {
    "MENU01": 8.50,  # Classic Burger
    "MENU02": 9.50,  # Cheese Burger
    "MENU03": 7.00,  # Veg Wrap
}

# Commission each channel takes out of revenue before the restaurant sees it.
# Dine-in and the restaurant's own website effectively cost nothing extra;
# third-party delivery apps typically charge 15-30% per order.
DEFAULT_COMMISSION_RATES = {
    DINE_IN_LABEL: 0.00,
    "Online - Own Website": 0.02,   # payment processing fee only
    "Online - Uber Eats": 0.28,
    "Online - Zomato": 0.22,
    "Online - Swiggy": 0.22,
    "Online - DoorDash": 0.27,
}


def channel_group(order_type: str) -> str:
    """Buckets a specific order_type (e.g. 'Online - Uber Eats') into the
    high-level channel used for Dine-in vs Online comparisons."""
    return "Dine-in" if order_type == DINE_IN_LABEL else "Online"


def platform_label(order_type: str) -> str:
    """Returns just the platform name for online orders, or 'POS' for dine-in."""
    if order_type == DINE_IN_LABEL:
        return "POS (in-restaurant)"
    return order_type.replace("Online - ", "")


# ---------------------------------------------------------------------------
# Connection + schema
# ---------------------------------------------------------------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS ingredients (
        ingredient_id TEXT PRIMARY KEY,
        name TEXT,
        unit TEXT,
        category TEXT,
        shelf_life_days INTEGER,
        cost_per_unit REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS recipes (
        menu_item_id TEXT,
        menu_item_name TEXT,
        ingredient_id TEXT,
        qty_per_item REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS inventory (
        batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_id TEXT,
        outlet_id TEXT,
        qty_remaining REAL,
        received_date TEXT,
        expiry_date TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_item_id TEXT,
        outlet_id TEXT,
        quantity INTEGER,
        order_type TEXT DEFAULT 'Dine-in (POS)',
        order_time TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS menu_prices (
        menu_item_id TEXT PRIMARY KEY,
        price REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS platform_commissions (
        order_type TEXT PRIMARY KEY,
        commission_rate REAL
    )""")

    conn.commit()
    conn.close()


def seed_if_empty():
    """Populate starting data only if the ingredients table is empty, so this
    is safe to call on every app start without wiping real usage."""
    init_db()
    conn = get_connection()
    c = conn.cursor()

    count = c.execute("SELECT COUNT(*) as cnt FROM ingredients").fetchone()["cnt"]
    if count > 0:
        conn.close()
        return

    c.executemany(
        "INSERT INTO ingredients (ingredient_id, name, unit, category, shelf_life_days, cost_per_unit) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        INGREDIENTS,
    )
    c.executemany(
        "INSERT INTO recipes (menu_item_id, menu_item_name, ingredient_id, qty_per_item) VALUES (?, ?, ?, ?)",
        RECIPES,
    )

    today = datetime.now()
    for outlet in OUTLETS:
        for ing_id, name, unit, category, shelf_life, cost in INGREDIENTS:
            for batch_offset in [-4, -1, 1]:
                received_date = today + timedelta(days=batch_offset)
                jitter = random.uniform(-1, 1)
                expiry_date = received_date + timedelta(days=max(1, shelf_life + jitter))
                qty_received = round(random.uniform(1500, 4000), 0)
                c.execute(
                    """INSERT INTO inventory (ingredient_id, outlet_id, qty_remaining, received_date, expiry_date)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ing_id, outlet, qty_received, received_date.strftime("%Y-%m-%d"), expiry_date.strftime("%Y-%m-%d")),
                )

    conn.commit()
    conn.close()

    _seed_pricing_if_empty()


def _seed_pricing_if_empty():
    """Separate from the main seed check so an existing database.db created
    before the profitability feature was added still gets these two new
    tables populated on next launch, without wiping any real order history."""
    conn = get_connection()
    c = conn.cursor()

    price_count = c.execute("SELECT COUNT(*) as cnt FROM menu_prices").fetchone()["cnt"]
    if price_count == 0:
        c.executemany(
            "INSERT INTO menu_prices (menu_item_id, price) VALUES (?, ?)",
            list(DEFAULT_MENU_PRICES.items()),
        )

    comm_count = c.execute("SELECT COUNT(*) as cnt FROM platform_commissions").fetchone()["cnt"]
    if comm_count == 0:
        c.executemany(
            "INSERT INTO platform_commissions (order_type, commission_rate) VALUES (?, ?)",
            list(DEFAULT_COMMISSION_RATES.items()),
        )

    conn.commit()
    conn.close()


def reset_data():
    """Wipe and re-seed everything -- used by the 'Reset demo data' button."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM ingredients")
    c.execute("DELETE FROM recipes")
    c.execute("DELETE FROM inventory")
    c.execute("DELETE FROM orders")
    c.execute("DELETE FROM menu_prices")
    c.execute("DELETE FROM platform_commissions")
    conn.commit()
    conn.close()
    seed_if_empty()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
def get_menu_items():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT menu_item_id, menu_item_name FROM recipes").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_outlets():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT outlet_id FROM inventory ORDER BY outlet_id").fetchall()
    conn.close()
    return [r["outlet_id"] for r in rows]


def get_ingredients():
    conn = get_connection()
    rows = conn.execute("SELECT ingredient_id, name, unit, shelf_life_days FROM ingredients ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Orders -- the single entry point for stock deduction, no matter which
# channel or platform the order came from.
# ---------------------------------------------------------------------------
def place_order(menu_item_id, outlet_id, quantity, order_type, order_time=None):
    """order_time defaults to now(); it can be overridden (as an ISO string)
    only by the historical order simulator, so demo data can span a real
    timeline without every order timestamping to the same second."""
    conn = get_connection()
    c = conn.cursor()

    ts = order_time or datetime.now().isoformat()

    c.execute(
        "INSERT INTO orders (menu_item_id, outlet_id, quantity, order_type, order_time) VALUES (?, ?, ?, ?, ?)",
        (menu_item_id, outlet_id, quantity, order_type, ts),
    )

    recipe_rows = c.execute(
        "SELECT ingredient_id, qty_per_item FROM recipes WHERE menu_item_id=?", (menu_item_id,)
    ).fetchall()

    if not recipe_rows:
        conn.commit()
        conn.close()
        return {"status": "error", "message": "No recipe found for this menu item."}

    shortages = []
    for row in recipe_rows:
        ingredient_id = row["ingredient_id"]
        deduction_needed = row["qty_per_item"] * quantity

        batches = c.execute(
            """SELECT batch_id, qty_remaining FROM inventory
               WHERE ingredient_id=? AND outlet_id=? AND qty_remaining > 0
               ORDER BY expiry_date ASC""",
            (ingredient_id, outlet_id),
        ).fetchall()

        for batch in batches:
            if deduction_needed <= 0:
                break
            deduct = min(batch["qty_remaining"], deduction_needed)
            new_qty = batch["qty_remaining"] - deduct
            c.execute("UPDATE inventory SET qty_remaining=? WHERE batch_id=?", (new_qty, batch["batch_id"]))
            deduction_needed -= deduct

        if deduction_needed > 0:
            name_row = c.execute(
                "SELECT name, unit FROM ingredients WHERE ingredient_id=?", (ingredient_id,)
            ).fetchone()
            shortages.append({
                "name": name_row["name"] if name_row else ingredient_id,
                "short_by": round(deduction_needed, 1),
                "unit": name_row["unit"] if name_row else "",
            })

    conn.commit()
    conn.close()

    if shortages:
        readable = ", ".join(f"{s['name']} (short by {s['short_by']} {s['unit']})" for s in shortages)
        return {
            "status": "warning",
            "message": f"Order placed, but insufficient stock for: {readable}. "
                       f"Go to 'Receive Stock' to top these up at outlet {outlet_id}.",
        }

    return {"status": "success", "message": "Order placed, stock updated."}


def generate_simulated_orders(days=14, min_per_day=15, max_per_day=40):
    """Backfills realistic-looking order history across the given number of
    past days, spread across both outlets, dine-in, and every online
    platform -- so charts and timeline comparisons have something real to
    show instead of a single manual test order.

    This ONLY inserts into the orders table for trend/insight purposes; it
    deliberately does NOT deduct from today's live inventory, because stock
    levels from days ago aren't what's on the shelf right now -- exactly
    like how a real POS system's sales history and current stock snapshot
    are two different things.
    """
    conn = get_connection()
    c = conn.cursor()

    menu_ids = [r["menu_item_id"] for r in c.execute("SELECT DISTINCT menu_item_id FROM recipes").fetchall()]
    if not menu_ids:
        conn.close()
        return {"status": "error", "message": "No menu items found."}

    channel_pool = [DINE_IN_LABEL] * 3 + [f"Online - {p}" for p in ONLINE_PLATFORMS]  # dine-in weighted higher

    inserted = 0
    now = datetime.now()
    for day_offset in range(days, 0, -1):
        day = now - timedelta(days=day_offset)
        num_orders = random.randint(min_per_day, max_per_day)
        for _ in range(num_orders):
            menu_item_id = random.choice(menu_ids)
            outlet_id = random.choice(OUTLETS)
            order_type = random.choice(channel_pool)
            quantity = random.randint(1, 4)
            order_hour = random.randint(8, 22)
            order_minute = random.randint(0, 59)
            order_time = day.replace(hour=order_hour, minute=order_minute, second=0).isoformat()

            c.execute(
                "INSERT INTO orders (menu_item_id, outlet_id, quantity, order_type, order_time) VALUES (?, ?, ?, ?, ?)",
                (menu_item_id, outlet_id, quantity, order_type, order_time),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Added {inserted} simulated historical orders across the last {days} days."}


# ---------------------------------------------------------------------------
# Receiving stock (new deliveries)
# ---------------------------------------------------------------------------
def receive_stock(ingredient_id, outlet_id, quantity, received_date_str, expiry_date_str=None):
    conn = get_connection()
    c = conn.cursor()

    ing_row = c.execute(
        "SELECT name, unit, shelf_life_days FROM ingredients WHERE ingredient_id=?", (ingredient_id,)
    ).fetchone()

    if not ing_row:
        conn.close()
        return {"status": "error", "message": "Unknown ingredient."}

    if not expiry_date_str:
        received_date = datetime.strptime(received_date_str, "%Y-%m-%d")
        expiry_date_str = (received_date + timedelta(days=ing_row["shelf_life_days"])).strftime("%Y-%m-%d")

    c.execute(
        """INSERT INTO inventory (ingredient_id, outlet_id, qty_remaining, received_date, expiry_date)
           VALUES (?, ?, ?, ?, ?)""",
        (ingredient_id, outlet_id, quantity, received_date_str, expiry_date_str),
    )
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Added {quantity:g} {ing_row['unit']} of {ing_row['name']} to {outlet_id}, expiring {expiry_date_str}.",
    }


# ---------------------------------------------------------------------------
# Stock / expiry / reorder views (return pandas DataFrames for easy display)
# ---------------------------------------------------------------------------
def get_inventory_df():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT i.batch_id, ing.name, ing.unit, i.outlet_id, i.qty_remaining, i.received_date, i.expiry_date
        FROM inventory i JOIN ingredients ing ON i.ingredient_id = ing.ingredient_id
        WHERE i.qty_remaining > 0
        ORDER BY i.expiry_date ASC
    """, conn)
    conn.close()
    return df


def get_stock_summary_df():
    """Returns total remaining stock per ingredient, with a 'display_qty' and
    'display_unit' already converted to human units (kg/L for weight/volume,
    raw count for countable items) so charts don't mix incomparable scales."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT ing.name, ing.unit, ing.category, SUM(i.qty_remaining) as total_qty
        FROM inventory i JOIN ingredients ing ON i.ingredient_id = ing.ingredient_id
        WHERE i.qty_remaining > 0
        GROUP BY ing.name, ing.unit, ing.category
        ORDER BY ing.name
    """, conn)
    conn.close()

    if df.empty:
        return df

    def display_qty(row):
        if row["unit"] in ("g", "ml") and row["total_qty"] >= 1000:
            return round(row["total_qty"] / 1000, 2)
        return round(row["total_qty"], 1)

    def display_unit(row):
        if row["unit"] == "g" and row["total_qty"] >= 1000:
            return "kg"
        if row["unit"] == "ml" and row["total_qty"] >= 1000:
            return "L"
        return row["unit"]

    df["display_qty"] = df.apply(display_qty, axis=1)
    df["display_unit"] = df.apply(display_unit, axis=1)
    # Split ingredients into weight/volume vs countable, since kg and "units"
    # are not comparable on the same bar chart axis.
    df["measure_group"] = df["unit"].apply(lambda u: "Weight / Volume (kg, L)" if u in ("g", "ml") else "Count (units)")
    return df


def get_expiry_risk_df():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT i.batch_id, ing.name, ing.unit, i.outlet_id, i.qty_remaining, i.expiry_date,
               julianday(i.expiry_date) - julianday('now') AS days_left
        FROM inventory i JOIN ingredients ing ON i.ingredient_id = ing.ingredient_id
        WHERE i.qty_remaining > 0
        ORDER BY days_left ASC
    """, conn)
    conn.close()

    def risk_level(days):
        if days <= 2:
            return "HIGH"
        elif days <= 5:
            return "MEDIUM"
        return "LOW"

    if not df.empty:
        df["risk_level"] = df["days_left"].apply(risk_level)
    return df


def get_reorder_df():
    conn = get_connection()

    stock_df = pd.read_sql_query("""
        SELECT ing.ingredient_id, ing.name, ing.unit, i.outlet_id, SUM(i.qty_remaining) as current_stock
        FROM inventory i JOIN ingredients ing ON i.ingredient_id = ing.ingredient_id
        GROUP BY ing.ingredient_id, i.outlet_id
    """, conn)

    usage_df = pd.read_sql_query("""
        SELECT r.ingredient_id, o.outlet_id, SUM(o.quantity * r.qty_per_item) / 7.0 AS avg_daily_usage
        FROM orders o JOIN recipes r ON o.menu_item_id = r.menu_item_id
        WHERE o.order_time >= datetime('now', '-7 days')
        GROUP BY r.ingredient_id, o.outlet_id
    """, conn)
    conn.close()

    merged = stock_df.merge(usage_df, on=["ingredient_id", "outlet_id"], how="left")
    merged["avg_daily_usage"] = merged["avg_daily_usage"].fillna(0)

    lead_time_days = 2
    safety_factor = 1.2

    def compute_row(row):
        if row["avg_daily_usage"] > 0:
            days_left = row["current_stock"] / row["avg_daily_usage"]
            needs_reorder = days_left <= lead_time_days
            rec_qty = max(0, (row["avg_daily_usage"] * lead_time_days * safety_factor) - row["current_stock"]) if needs_reorder else 0
        else:
            days_left = None
            needs_reorder = row["current_stock"] < 500
            rec_qty = max(0, 1000 - row["current_stock"]) if needs_reorder else 0
        return pd.Series({"days_of_stock_left": days_left, "needs_reorder": needs_reorder, "recommended_qty": round(rec_qty, 1)})

    if not merged.empty:
        extra = merged.apply(compute_row, axis=1)
        merged = pd.concat([merged, extra], axis=1)

    return merged


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------
def _orders_with_channel_df(days=7):
    """Pulls raw orders (with menu item name + channel group + platform
    label already attached) for the last N days -- the shared base for
    several insight views below."""
    conn = get_connection()
    orders = pd.read_sql_query(f"""
        SELECT menu_item_id, outlet_id, quantity, order_type, order_time
        FROM orders
        WHERE order_time >= datetime('now', '-{int(days)} days')
    """, conn)
    names = pd.read_sql_query("SELECT DISTINCT menu_item_id, menu_item_name FROM recipes", conn)
    conn.close()

    if orders.empty:
        return orders

    orders = orders.merge(names, on="menu_item_id", how="left")
    orders["channel_group"] = orders["order_type"].apply(channel_group)
    orders["platform"] = orders["order_type"].apply(platform_label)
    orders["date"] = pd.to_datetime(orders["order_time"]).dt.date
    return orders


def get_channel_summary_df():
    orders = _orders_with_channel_df(days=7)
    if orders.empty:
        return pd.DataFrame(columns=["channel_group", "order_count", "total_items"])
    grouped = orders.groupby("channel_group").agg(
        order_count=("quantity", "count"), total_items=("quantity", "sum")
    ).reset_index()
    return grouped


def get_platform_breakdown_df():
    """Among online orders only, which specific platform (Uber Eats, Zomato,
    own website, etc.) is bringing in the most volume."""
    orders = _orders_with_channel_df(days=7)
    if orders.empty:
        return pd.DataFrame(columns=["platform", "total_items"])
    online = orders[orders["channel_group"] == "Online"]
    if online.empty:
        return pd.DataFrame(columns=["platform", "total_items"])
    grouped = online.groupby("platform")["quantity"].sum().reset_index()
    grouped.columns = ["platform", "total_items"]
    return grouped.sort_values("total_items", ascending=False)


def get_best_sellers_df():
    orders = _orders_with_channel_df(days=7)
    if orders.empty:
        return pd.DataFrame(columns=["menu_item_name", "total_sold"])
    grouped = orders.groupby("menu_item_name")["quantity"].sum().reset_index()
    grouped.columns = ["menu_item_name", "total_sold"]
    return grouped.sort_values("total_sold", ascending=False)


def get_channel_by_item_df():
    orders = _orders_with_channel_df(days=7)
    if orders.empty:
        return pd.DataFrame(columns=["menu_item_name", "channel_group", "qty"])
    grouped = orders.groupby(["menu_item_name", "channel_group"])["quantity"].sum().reset_index()
    grouped.columns = ["menu_item_name", "channel_group", "qty"]
    return grouped


def get_daily_sales_trend_df(days=30):
    """Daily order volume over time, split by Dine-in vs Online -- lets you
    see whether sales (and the online/dine-in mix) are trending up or down."""
    orders = _orders_with_channel_df(days=days)
    if orders.empty:
        return pd.DataFrame(columns=["date", "channel_group", "total_qty"])
    grouped = orders.groupby(["date", "channel_group"])["quantity"].sum().reset_index()
    grouped.columns = ["date", "channel_group", "total_qty"]
    return grouped.sort_values("date")


def get_waste_value_df():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT ing.name, ing.cost_per_unit,
               julianday(i.expiry_date) - julianday('now') AS days_left,
               i.qty_remaining
        FROM inventory i JOIN ingredients ing ON i.ingredient_id = ing.ingredient_id
        WHERE i.qty_remaining > 0
    """, conn)
    conn.close()

    if df.empty:
        return pd.DataFrame(columns=["name", "value_at_risk"])

    at_risk = df[df["days_left"] <= 5].copy()
    if at_risk.empty:
        return pd.DataFrame(columns=["name", "value_at_risk"])

    at_risk["value"] = at_risk["qty_remaining"] * at_risk["cost_per_unit"]
    result = at_risk.groupby("name")["value"].sum().reset_index()
    result.columns = ["name", "value_at_risk"]
    result["value_at_risk"] = result["value_at_risk"].round(2)
    return result.sort_values("value_at_risk", ascending=False)


def get_summary_lines():
    orders = _orders_with_channel_df(days=7)
    conn = get_connection()

    high_risk_count = conn.execute("""
        SELECT COUNT(*) as cnt FROM inventory
        WHERE qty_remaining > 0 AND julianday(expiry_date) - julianday('now') <= 2
    """).fetchone()["cnt"]
    conn.close()

    lines = []
    if orders.empty:
        lines.append(
            "No orders in the last 7 days yet — place a few orders, or use "
            "**'Simulate order history'** in the sidebar to see the full picture."
        )
    else:
        top = orders.groupby("menu_item_name")["quantity"].sum().idxmax()
        top_qty = orders.groupby("menu_item_name")["quantity"].sum().max()
        lines.append(f"Your best-selling item in the last 7 days is **{top}** ({int(top_qty)} sold).")

        channel_totals = orders.groupby("channel_group")["quantity"].sum()
        parts = [f"{ch}: {int(qty)} items" for ch, qty in channel_totals.items()]
        lines.append("Channel split — " + ", ".join(parts) + ".")

        online = orders[orders["channel_group"] == "Online"]
        if not online.empty:
            top_platform = online.groupby("platform")["quantity"].sum().idxmax()
            lines.append(f"Among online orders, **{top_platform}** brings in the most volume.")

    if high_risk_count > 0:
        lines.append(f"⚠️ **{high_risk_count}** ingredient batch(es) are at HIGH risk of expiring within 2 days — check the Expiry Risk page.")
    else:
        lines.append("✅ No ingredient batches are currently at HIGH expiry risk.")

    return lines


# ---------------------------------------------------------------------------
# Channel Profitability — food cost, delivery-platform commission, and
# net margin per menu item per channel. This is what tells you whether an
# item is actually worth selling on a given platform, not just how many of
# it you sold.
# ---------------------------------------------------------------------------
def get_food_cost_df():
    """True ingredient cost per menu item, derived from the recipe (BOM) ×
    each ingredient's cost_per_unit -- the same recipe data used for stock
    deduction, just multiplied by cost instead of summed as usage."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT r.menu_item_id, SUM(r.qty_per_item * ing.cost_per_unit) as food_cost
        FROM recipes r JOIN ingredients ing ON r.ingredient_id = ing.ingredient_id
        GROUP BY r.menu_item_id
    """, conn)
    conn.close()
    return df


def get_menu_pricing_df():
    """One row per menu item: selling price, computed food cost, and the
    resulting gross margin (before any platform commission)."""
    conn = get_connection()
    prices = pd.read_sql_query("SELECT menu_item_id, price FROM menu_prices", conn)
    names = pd.read_sql_query("SELECT DISTINCT menu_item_id, menu_item_name FROM recipes", conn)
    conn.close()

    food_cost = get_food_cost_df()

    df = names.merge(prices, on="menu_item_id", how="left").merge(food_cost, on="menu_item_id", how="left")
    df["price"] = df["price"].fillna(0)
    df["food_cost"] = df["food_cost"].fillna(0)
    df["gross_margin"] = df["price"] - df["food_cost"]
    df["gross_margin_pct"] = df.apply(
        lambda r: round((r["gross_margin"] / r["price"]) * 100, 1) if r["price"] > 0 else 0, axis=1
    )
    return df


def update_menu_price(menu_item_id, price):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO menu_prices (menu_item_id, price) VALUES (?, ?)", (menu_item_id, price))
    conn.commit()
    conn.close()


def get_commission_rates_df():
    """One row per channel (Dine-in + every online platform) with its
    commission rate and a human-readable platform label."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT order_type, commission_rate FROM platform_commissions", conn)
    conn.close()
    if not df.empty:
        df["platform"] = df["order_type"].apply(platform_label)
    return df


def update_commission_rate(order_type, rate):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO platform_commissions (order_type, commission_rate) VALUES (?, ?)",
        (order_type, rate),
    )
    conn.commit()
    conn.close()


def _profitability_base_df(days=7):
    """Every order in the window, with price / food cost / commission rate
    already attached and revenue, commission, food cost, and net margin
    computed per order row. The two public functions below just group this
    differently (by item+platform, or by platform only)."""
    orders = _orders_with_channel_df(days=days)
    if orders.empty:
        return pd.DataFrame()

    pricing = get_menu_pricing_df()[["menu_item_id", "price", "food_cost"]]
    commission_df = get_commission_rates_df()[["order_type", "commission_rate"]]

    merged = orders.merge(pricing, on="menu_item_id", how="left").merge(commission_df, on="order_type", how="left")
    merged["price"] = merged["price"].fillna(0)
    merged["food_cost"] = merged["food_cost"].fillna(0)
    merged["commission_rate"] = merged["commission_rate"].fillna(0)

    merged["revenue"] = merged["price"] * merged["quantity"]
    merged["commission"] = merged["revenue"] * merged["commission_rate"]
    merged["food_cost_total"] = merged["food_cost"] * merged["quantity"]
    merged["net_margin"] = merged["revenue"] - merged["commission"] - merged["food_cost_total"]
    return merged


def get_channel_profitability_df(days=7):
    """Net margin per menu item, broken down by platform -- the view that
    answers 'should we stop selling the Veg Wrap on Uber Eats.'"""
    base = _profitability_base_df(days=days)
    if base.empty:
        return pd.DataFrame(columns=[
            "menu_item_name", "platform", "quantity", "revenue", "commission",
            "food_cost_total", "net_margin", "margin_pct", "net_margin_per_order",
        ])

    grouped = base.groupby(["menu_item_name", "platform"]).agg(
        quantity=("quantity", "sum"),
        revenue=("revenue", "sum"),
        commission=("commission", "sum"),
        food_cost_total=("food_cost_total", "sum"),
        net_margin=("net_margin", "sum"),
    ).reset_index()

    grouped["margin_pct"] = grouped.apply(
        lambda r: round((r["net_margin"] / r["revenue"]) * 100, 1) if r["revenue"] > 0 else 0, axis=1
    )
    grouped["net_margin_per_order"] = (grouped["net_margin"] / grouped["quantity"]).round(2)
    grouped["is_loss_making"] = grouped["net_margin"] < 0

    return grouped.sort_values("net_margin")


def get_platform_profitability_df(days=7):
    """Net margin aggregated per channel/platform only -- the view that
    answers 'which platform is actually worth the commission we pay it.'"""
    base = _profitability_base_df(days=days)
    if base.empty:
        return pd.DataFrame(columns=["platform", "revenue", "commission", "food_cost_total", "net_margin", "margin_pct"])

    grouped = base.groupby("platform").agg(
        revenue=("revenue", "sum"),
        commission=("commission", "sum"),
        food_cost_total=("food_cost_total", "sum"),
        net_margin=("net_margin", "sum"),
    ).reset_index()

    grouped["margin_pct"] = grouped.apply(
        lambda r: round((r["net_margin"] / r["revenue"]) * 100, 1) if r["revenue"] > 0 else 0, axis=1
    )
    return grouped.sort_values("net_margin")


def get_loss_making_flags(days=7):
    """Plain-English list of specific item+platform combinations that are
    losing money, with the exact per-order loss -- the actionable output of
    this whole feature."""
    df = get_channel_profitability_df(days=days)
    if df.empty:
        return []

    losers = df[df["is_loss_making"]].sort_values("net_margin_per_order")
    flags = []
    for _, row in losers.iterrows():
        flags.append(
            f"You lose **€{abs(row['net_margin_per_order']):.2f}** on every **{row['menu_item_name']}** "
            f"sold via **{row['platform']}** ({row['margin_pct']:.0f}% margin, {int(row['quantity'])} sold "
            f"in the last {days} days)."
        )
    return flags

