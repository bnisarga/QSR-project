# QSR Expiry-Aware Inventory System — Streamlit Version

A working prototype of what a real QSR outlet's back-end could look like: a **POS terminal**
for dine-in orders and **several online delivery platforms** (own website, Uber Eats, Zomato,
Swiggy, DoorDash) — every one of them writes to the same live, central inventory. Stock
deducts FIFO by expiry date, expiry risk is tracked in real time, reorder recommendations are
based on actual usage, and the Insights page shows sales trends over time, not just a snapshot.

## Project structure

```
food-waste-streamlit/
├── Home.py                          # Entry point: Place Order (POS + online platforms)
├── db.py                             # All database logic (schema, seeding, orders, insights)
├── database.db                        # Auto-created SQLite file (already seeded for you)
├── requirements.txt
└── pages/
    ├── 1_Stock_Levels.py              # Stock overview (two charts: weight/volume vs count)
    ├── 2_Receive_Stock.py              # Log new deliveries, with a working manual expiry override
    ├── 3_Expiry_Risk.py                 # Risk breakdown + colour-coded table
    ├── 4_Reorder_Recommendations.py      # What needs restocking
    ├── 5_Insights.py                      # Timeline trend, best sellers, platform breakdown, waste value
    └── 6_Channel_Profitability.py          # Food cost, commission, and net margin per item/platform
```

## How to run in VS Code

```bash
cd food-waste-streamlit
pip install -r requirements.txt
streamlit run Home.py
```
Opens automatically at **http://localhost:8501**. Stop with **Ctrl+C** in the terminal.

## What changed from the earlier version (and why)

### 1. Orders now come from realistic sources, not a generic "Online" bucket
The order form has a **Dine-in (POS)** vs **Online** choice, and if Online, a dropdown of
actual delivery platforms (Own Website, Uber Eats, Zomato, Swiggy, DoorDash). This mirrors how
a real outlet actually receives orders — a chain doesn't have one "online" queue, it has
several platforms all feeding the same kitchen. Every source, whichever it is, goes through
the exact same `place_order()` function and deducts from the exact same live stock — there's
no special-casing per platform in the inventory logic, which is how a real POS/aggregator
integration should behave.

### 2. There's now a way to generate a realistic order history
Placing one order at a time is realistic for a live demo, but you need days of history before
trends mean anything. The sidebar on the Place Order page has **"Simulate order history (last
30 days)"** — it backfills ~15-40 orders per day across both outlets, dine-in, and every
platform, with randomised times throughout the day. This is what powers the new timeline chart
(see below). Note: this only adds to the sales **history** for trend analysis — it does not
touch today's live inventory, since stock levels from three weeks ago aren't what's on the
shelf right now. That's a deliberate, realistic distinction (a real POS system's sales
ledger and its current stock snapshot are two different data stores).

### 3. Fixed: the Stock Overview chart
Previously it mixed grams/ml (converted to kg/L) and countable items (units) on one bar chart
— since a "Cheese Slice" count (thousands of units) and a "Chicken Breast" weight (tens of kg)
aren't on comparable scales, one set of bars became invisible next to the other. It's now two
separate charts: **Weight / Volume ingredients** and **Countable ingredients**, each with
value labels on the bars.

### 4. Fixed: manual expiry override on Receive Stock
The override checkbox and date field were previously both inside an `st.form`, and Streamlit
only reruns the script for form widgets when the submit button is clicked — so ticking the
checkbox couldn't immediately enable the date field for editing. They're now regular widgets
outside a form, so the date field enables the instant you tick the box, and there's also a
read-only "auto-calculated expiry" preview shown when the box is unticked, so you always see
what will actually be saved.

### 5. New: Sales Timeline on Insights
A line chart of daily order volume over the last 30 days, split by Dine-in vs Online, so you
can compare how the two channels are trending relative to each other — growing, shrinking,
or shifting mix — rather than only seeing a single 7-day snapshot. There's also a new
**"Which Online Platform Sells the Most"** chart, since in a real setup you'd want to know
whether Uber Eats or your own website is actually driving volume.

### 6. New: Channel Profitability
The Insights page tells you which item sells the most, but not whether it's actually making
money once a delivery platform's commission is factored in. The new **Channel Profitability**
page adds:
- **Editable menu pricing**, alongside food cost computed automatically from the same
  recipe/BOM data used for stock deduction (`qty per recipe × ingredient cost_per_unit`).
- **Editable commission rates** per channel (Dine-in and own website cost little to nothing;
  Uber Eats/DoorDash/Zomato/Swiggy default to realistic 20-30% rates you can adjust).
- **Net margin by platform** and **net margin by item × platform**, both as charts and tables,
  colour-coded red/green for loss-making vs profitable.
- A plain-English **loss-making flags** list — e.g. *"You lose €0.13 on every Veg Wrap sold
  via Uber Eats (-45% margin, 42 sold in the last 7 days)"* — the concrete, actionable output
  a real manager would use to decide whether to raise a price, drop an item from a platform,
  or renegotiate commission.

This directly answers one of the most-cited real QSR problems: outlets often don't realise
certain items are unprofitable on certain delivery platforms because commission isn't visible
at the point of sale — only in the monthly settlement report from the platform, by which point
thousands of orders have already gone out at a loss.

## How to demo it

1. **Place Order** — place a couple of orders through different sources (try Dine-in, then
   Online via Uber Eats, then Online via your own Website). Then click **"Simulate order
   history"** in the sidebar to backfill 30 days of realistic volume.
2. **Stock Levels** — see the two clean, readable charts, plus the batch-level table.
3. **Receive Stock** — log a delivery; try ticking "Override expiry date manually" and confirm
   the date field becomes editable immediately.
4. **Expiry Risk** — HIGH/MEDIUM/LOW breakdown.
5. **Reorder Recommendations** — based on the last 7 days of usage across all channels.
6. **Insights** — the timeline chart is the headline: watch Dine-in vs Online volume move
   day by day, see which platform brings in the most online orders, and check which
   ingredients are carrying the most waste-risk value right now.
7. **Channel Profitability** — try lowering an item's price below its shown food cost and
   watch it flip to a loss-making red bar with a specific flag naming the exact platform and
   euro amount — then set it back and watch the flag disappear.

## Notes on the logic (for your report)

- **Order channel model**: `order_type` in the `orders` table stores the specific source
  (`"Dine-in (POS)"` or `"Online - <Platform>"`). `db.channel_group()` buckets these into
  Dine-in/Online for high-level comparisons; `db.platform_label()` extracts just the platform
  name for the platform-level breakdown. This two-level structure is what lets a real
  multi-platform QSR chain answer both "how's online doing vs dine-in" and "which specific
  app is worth the commission we're paying it."
- **Historical simulation vs live inventory** are intentionally separate: `generate_simulated_orders()`
  only inserts into `orders` (for trend analysis), it never touches `inventory`. This
  reflects how real systems work — a sales ledger spanning months and a live stock count are
  different tables serving different purposes.
- **Usage-based reorder logic** unchanged from before: derived from `quantity sold × qty per
  recipe`, summed across every channel and platform, over the last 7 days.
- **Shelf life** values are illustrative (typical FDA FoodKeeper-style ranges) — cite that as
  your source rather than presenting them as measured facts.

## Resetting the data

Click **"🔄 Reset demo data"** in the sidebar on the Place Order page — wipes all orders and
inventory changes and reseeds the original starting state (no simulated history).

## Next steps (optional, for the fuller academic project)

- Replace the simple 7-day average in `get_reorder_df()` with an actual Prophet/LSTM forecast
  fed by the timeline data now available in `get_daily_sales_trend_df()`.
- Add a per-platform commission-adjusted margin view once you have real or assumed commission
  rates per platform (Uber Eats/DoorDash typically charge 15-30%) — directly answers "is this
  platform actually profitable."
- Deploy for free on [Streamlit Community Cloud](https://streamlit.io/cloud) from a GitHub
  repo for a live link instead of a local screen-share.
