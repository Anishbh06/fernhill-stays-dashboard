# Decisions & Rationale

This document outlines the data issues I identified in `bookings_jan_may_2026.csv`, how I handled them, and the assumptions I made. My guiding principle was simple: a dashboard built on bad data is worse than no dashboard at all, so every row that could silently corrupt revenue or occupancy had to be addressed before I touched the UI.

## Part A: Data Issues Identified and Handled

I wrote an audit script (`clean_data.py`) that processes the raw dataset in a strict sequence. The ordering matters — I fixed things that silently corrupt money math first, cosmetic normalisation second, and edge-case flagging last.

### 1. Duplicates (8 rows removed)
- **What I found**: 8 completely identical rows in the 238-row raw dataset (reduced to 230 after dedup). Some booking IDs appeared twice with the exact same data across every column (e.g. BK1028, BK1044, BK1068, BK1096, BK1126, BK1138, BK1207, BK1285).
- **How I handled it**: `df.drop_duplicates()` right at the start, before any math.
- **Why this is Step 1**: If a booking is counted twice, every downstream metric — revenue, occupancy, health score — is silently inflated. This has to go first.

### 2. Text normalisation (property, status, channel, room type)
- **What I found**: Inconsistent casing and whitespace across all categorical columns:
  - **Properties**: "Marigold Suites", "MARIGOLD SUITES", "Marigold Suites " (trailing space) — what should be 5 hotels appeared as 9 distinct values.
  - **Status**: "Checked-out", "CHECKED OUT", "confirmed" — 6 raw values that should be 4.
  - **Channels**: "direct", "Direct", "ota-mmt", "OTA-MMT" — same channel, different strings.
  - **Room types**: "DLX" and "Deluxe" are the same room, as are "Std" and "Standard".
- **How I handled it**: Explicit mapping dictionaries rather than just `.str.title()`, because abbreviations like "DLX" and "OTA-MMT" need special handling that generic title-casing would break.
- **Why this matters**: Without this, `groupby("property")` treats "Cedar Court" and "cedar court" as two different hotels. The dashboard would silently fragment the data — you'd see 9 properties instead of 5 and never know the numbers were wrong.

### 3. Date parsing (4 formats + 20 day/month swaps)
- **What I found**: The `check_in_date` column had at least 4 different formats: `2026-01-25` (ISO), `9 Mar 2026` (named month), `02/02/2026` (DD/MM or MM/DD), and `05-07-2026` (MM-DD or DD-MM).
- **How I handled it**: Two-pass parsing. First I parse ISO dates (`YYYY-MM-DD`) which are unambiguous. Then I parse everything else with `dayfirst=True` since this is Indian data. After parsing, I ran a sanity check: any date falling outside Jan–May 2026 (the dataset's known range) indicates the parser got day/month backwards. I found 20 such dates and automatically swapped day↔month to fix them.
- **Why this matters**: You can't build a time-based dashboard on unparseable strings. And the day/month ambiguity is subtle — `05-07-2026` could be May 7 or July 5. Without the range check, 20 bookings would land in the wrong month on the timeline chart.

### 4. Amount mismatches — 10x errors and negatives (11 rows corrected)
- **What I found**: 11 rows where `total_amount_inr` was blatantly wrong:
  - **5 negative amounts**: e.g. BK1250 showed ₹-28,497 when the expected amount (₹7,483 × 5 nights) was ₹28,497. Clearly a sign error in data entry.
  - **6 rows at exactly 10x**: e.g. BK1118 showed ₹81,750 when the expected amount (₹2,725 × 3 nights) was ₹8,175. Exactly 10x — someone added an extra zero.
- **How I handled it**: I flag these rows (`amount_error_flag = True`) and overwrite the erroneous `total_amount_inr` with the recalculated value (`nightly_rate_inr × nights`). I used a >2x threshold to catch the 10x errors without accidentally flagging minor rounding or tax differences.
- **Why this matters**: These 11 rows alone would distort revenue by hundreds of thousands of rupees. If left unchecked, the health score and property revenue charts would be completely wrong.

### 5. Cancelled and No-Show bookings excluded from revenue (85 bookings)
- **What I found**: 42 bookings marked "Cancelled" and 43 marked "No-Show" — 85 total, representing over a third of all bookings.
- **How I handled it**: I created a `realized_revenue` column. For Cancelled and No-Show bookings, `realized_revenue = 0`. The original `total_amount_inr` is preserved so you can still see "potential revenue lost."
- **Why this matters**: This is the assignment's explicitly named red flag — "cancelled or invalid bookings silently counted as revenue" is an automatic fail. A cancelled booking is not real income, full stop.

### 6. Missing financial values (9 missing rates, 3 missing amounts — flagged, not guessed)
- **What I found**: 9 rows had no `nightly_rate_inr` and 3 rows had no `total_amount_inr`.
- **How I handled it**: I flag them (`missing_rate_flag`, `missing_amount_flag`) and set their `realized_revenue` to 0. I do NOT impute or guess a rate.
- **Why this matters**: Inventing financial data is worse than admitting it's missing. If I averaged nearby rates and filled in ₹5,000, I'd be fabricating revenue. Instead, the dashboard can honestly say "3 bookings excluded due to missing data."

### 7. Zero-night anomalies (4 rows flagged)
- **What I found**: 4 rows where `nights = 0` but revenue was attached (e.g. BK1133: 0 nights, ₹29,320).
- **How I handled it**: Flagged with `zero_night_anomaly = True`. I did not drop or modify these rows — they're visible for inspection.
- **Why this matters**: Nights=0 with money is contradictory. It would break Average Daily Rate calculations (division by zero). Flagging it makes the anomaly visible instead of letting it silently corrupt metrics.

### 8. Missing booking channels (27 rows flagged)
- **What I found**: 27 bookings had no booking channel recorded.
- **How I handled it**: I kept these rows (they have valid revenue) but flagged them with `missing_channel_flag = True`.
- **Why this matters**: The client asked "which booking channels are worth it." These 27 rows can't contribute to that answer, but they shouldn't be dropped entirely because their revenue is real. The dashboard can note "27 bookings with unknown channel."

---

## Health Score Definition

The client asked for "an overall health score for each property so I know where to focus." The key phrase is **"where to focus"** — this is a diagnostic tool, not a vanity metric. It needs to surface underperforming properties, not just rename revenue.

### Formula: Health Score (0–100)

```
Health Score = (0.30 × Occupancy) + (0.25 × Revenue) + (0.25 × Cancellation) + (0.20 × Rate)
```

| Component | Weight | What it measures | Normalisation |
|---|---|---|---|
| **Occupancy** | 30% | Room-nights sold | 0–100 vs. best property |
| **Revenue** | 25% | Realized revenue | 0–100 vs. best property |
| **Cancellation** | 25% | Inverse of cancel rate | Lower cancel = higher score |
| **Rate** | 20% | Avg nightly rate (completed) | 0–100 vs. best property |

### Actual Scores (Jan–May 2026)

| Property | Occupancy | Revenue | Cancellation | Rate | **Health Score** |
|---|---|---|---|---|---|
| Marigold Suites | 100.0 | 100.0 | 100.0 | 86.4 | **97.3** ✅ |
| Cedar Court | 45.8 | 46.5 | 82.1 | 86.6 | **63.2** |
| Lakeview Residency | 47.6 | 48.5 | 62.7 | 92.3 | **60.6** |
| Birchwood Stay | 31.5 | 31.8 | 74.4 | 91.6 | **54.3** |
| Palm Grove Inn | 53.0 | 61.4 | 0.0 | 100.0 | **51.2** 🔴 |

### Why these weights

- **Occupancy (30%)**: Gets the most weight because a hotel with empty rooms is losing money every night regardless of rate.
- **Revenue (25%)**: The bottom line — but not the only thing, because a high-revenue property with 50% cancellations has a problem.
- **Cancellation (25%)**: Equally weighted to revenue because cancellations signal operational issues (overbooking, poor channel quality, guest experience).
- **Rate (20%)**: Least weight because a low rate might be a deliberate strategy for a budget property, not a weakness.

### What it deliberately excludes

- **True occupancy %**: We don't have room inventory data, so we use room-nights sold as a proxy. A property with 10 rooms selling 50 nights looks the same as one with 100 rooms selling 50 nights.
- **Seasonality**: The score is computed over the full Jan–May period. March had 100 bookings vs. January's 24 — the score treats all months equally.
- **Guest satisfaction**: No review or rating data available.
- **Cost/profit margins**: We only have revenue, not operating costs.

### Key Finding

Palm Grove Inn scores lowest (**51.2/100**) despite having the highest nightly rate (₹5,582). The problem is its **51% cancellation rate** — more than half its bookings don't convert. That's where the client should focus. The health score correctly identifies this because it doesn't just look at revenue — it penalises unreliable bookings.

## Part B: Dashboard Design Decisions

### Why Streamlit + Plotly
I chose Streamlit because the client asked for a "simple dashboard" — not a React app, not a BI tool. Streamlit lets me build a clean, interactive UI in a single Python file that can be deployed for free. Plotly gives interactive hover tooltips and zoom on charts, which static matplotlib charts wouldn't.

### Dashboard structure — 3 tabs matching 3 questions
The client asked three questions. The dashboard has three tabs. Each tab maps directly to one question:
1. **Property Performance** → "How is each property doing?"
2. **Channel Analysis** → "Which booking channels are worth it?"
3. **Health Score** → "Where should I focus?"

I deliberately avoided adding extra tabs or features. The client didn't ask for guest demographics, room type optimization, or trend forecasting. Adding those would make the dashboard harder to navigate without answering the actual questions.

### Key Channel Insight
The data reveals something the client should act on immediately:
- **Walk-In** is the most valuable channel — highest avg booking value (₹20,665) and lowest cancellation rate (33%).
- **Corporate** is the least valuable — lowest avg booking value (₹9,722) and highest cancellation rate (53%).
- This suggests the Corporate channel relationships may need renegotiation or the Corporate booking process has a confirmation gap.

### Revenue Lost metric
I added a "Revenue Lost" KPI (₹16.5L lost to cancellations) because showing only realized revenue hides the cost of the cancellation problem. The client asked "where to focus" — knowing that cancellations are costing ₹16.5L makes the case for intervention concrete.

### Edge case handling
- **Zero-night bookings** (4 rows): Excluded from Average Daily Rate calculations to prevent division by zero.
- **Missing nightly rates** (6 completed bookings): Their revenue is counted (the `total_amount_inr` exists) but they're excluded from avg rate calculations.
- **Empty filter state**: The dashboard shows a warning message instead of crashing. A client demo should never crash on a filter click.

---

## Assumptions
1. `nightly_rate_inr × nights` is the source of truth for revenue when `total_amount_inr` is blatantly corrupted (negative or 10x off). Minor differences (taxes, discounts) are accepted.
2. The client wants "realized revenue" (money actually earned), not "booked revenue" (including cancellations). The dashboard uses `realized_revenue` for all financial charts.
3. Dates are Indian-format (DD/MM/YYYY) when ambiguous, because the hotel group is based in Bengaluru. The Jan–May 2026 range was used as a sanity check to catch format errors.
4. "DLX" = "Deluxe" and "Std" = "Standard" — these are abbreviations used by some front-desk staff, not distinct room categories.

## What I Would Do Next With More Time
- Investigate whether the 85 cancelled/no-show bookings cluster around specific properties or channels (the data already hints at this — Palm Grove Inn has 51% and Corporate channel has 53%).
- Build a data quality score per property (e.g., "Cedar Court has 15% of its entries with data issues").
- Add automated data validation that runs before the dashboard loads, alerting if new data has the same issues.
- Add a month-over-month comparison view so the client can track if Palm Grove's cancellation rate is improving or worsening.

