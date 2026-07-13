# Decisions & Rationale

This document outlines the data issues I identified in `bookings_jan_may_2026.csv`, how I handled them, and the assumptions I made. My guiding principle was simple: a dashboard built on bad data is worse than no dashboard at all, so every row that could silently corrupt revenue or occupancy had to be addressed before I touched the UI.

## Part A: Data Issues Identified and Handled

I wrote an audit script (`clean_data.py`) that processes the raw dataset in a strict sequence. The ordering matters — I fixed things that silently corrupt money math first, cosmetic normalisation second, and edge-case flagging last.

### 1. Duplicates (8 rows removed)
- **What I found**: 8 completely identical rows in the 238-row dataset. Some booking IDs appeared twice with the exact same data across every column (e.g. BK1028, BK1044, BK1068, BK1096, BK1126, BK1138, BK1207, BK1285).
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
*(To be defined in the next phase — this will be a composite metric with explicit weights and acknowledged trade-offs.)*

## Assumptions
1. `nightly_rate_inr × nights` is the source of truth for revenue when `total_amount_inr` is blatantly corrupted (negative or 10x off). Minor differences (taxes, discounts) are accepted.
2. The client wants "realized revenue" (money actually earned), not "booked revenue" (including cancellations). The dashboard uses `realized_revenue` for all financial charts.
3. Dates are Indian-format (DD/MM/YYYY) when ambiguous, because the hotel group is based in Bengaluru. The Jan–May 2026 range was used as a sanity check to catch format errors.
4. "DLX" = "Deluxe" and "Std" = "Standard" — these are abbreviations used by some front-desk staff, not distinct room categories.

## What I Would Do Next With More Time
- Investigate whether the 85 cancelled/no-show bookings cluster around specific properties or channels (potential operational issue).
- Build a data quality score per property (e.g., "Cedar Court has 15% of its entries with data issues").
- Add automated data validation that runs before the dashboard loads, alerting if new data has the same issues.
