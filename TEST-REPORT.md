# Test Report

## Overview

This document covers testing performed on the Fernhill Stays dashboard before client delivery. I tested data integrity, edge cases in the cleaning pipeline, UI behaviour under different filter states, and cross-checked the dashboard numbers against manual calculations.

---

## 1. Data Cleaning Pipeline Tests

### Test 1.1: Duplicate removal
- **What I tested**: Ran `clean_data.py` and verified the row count dropped from 238 to 230.
- **How**: Compared `len(df)` before and after `drop_duplicates()`.
- **Result**: ✅ 8 duplicates removed. Verified the duplicate booking IDs (BK1028, BK1044, BK1068, BK1096, BK1126, BK1138, BK1207, BK1285) were fully identical rows, not different bookings that happened to share an ID.

### Test 1.2: Amount error correction
- **What I tested**: All 11 flagged rows should have `total_amount_inr` equal to `nightly_rate_inr × nights` after correction.
- **How**: Ran a script that recalculated expected amounts and compared.
- **Result**: ✅ All 11 rows match. No negatives remain in the cleaned data.

### Test 1.3: Cancelled bookings excluded from revenue
- **What I tested**: Every row with status "Cancelled" or "No-Show" should have `realized_revenue = 0`.
- **How**: Filtered the clean CSV for cancelled/no-show rows and checked if any had `realized_revenue > 0`.
- **Result**: ✅ 85 out of 85 cancelled/no-show bookings have `realized_revenue = 0`. Zero leakage.

### Test 1.4: Date parsing completeness
- **What I tested**: All 230 rows should have a valid parsed date within Jan–May 2026.
- **How**: Checked `df['check_in_date'].isna().sum()` and filtered for dates outside 2026-01-01 to 2026-05-31.
- **Result**: ✅ 0 unparseable dates, 0 out-of-range dates. The two-pass parser + day/month swap fixed all 20 ambiguous dates.

### Test 1.5: Text normalisation
- **What I tested**: Properties should be exactly 5, statuses exactly 4, channels exactly 5, room types exactly 3.
- **How**: Printed `df['property'].unique()` etc. on the clean CSV.
- **Result**: ✅ All match expected counts. No fragmented groupings.

---

## 2. Edge Cases in the Data

### Test 2.1: Zero-night bookings
- **What I tested**: 4 rows have `nights = 0` with revenue attached. Do they break the dashboard?
- **How**: Checked if any division-by-zero errors occur in ADR (Average Daily Rate) calculations.
- **Result**: ✅ The dashboard excludes zero-night rows from ADR calculations (`completed[(completed['nights'] > 0)]`). The bookings are still counted in totals and visible in the property table.

### Test 2.2: Missing nightly rate with valid revenue
- **What I tested**: 6 completed bookings have `nightly_rate_inr = NaN` but valid `total_amount_inr`. Does the dashboard handle them?
- **How**: Checked that these rows are excluded from Average Nightly Rate calculations but their revenue is still counted in totals.
- **Result**: ✅ Revenue is correctly included. Avg Rate calculations use `.mean()` which ignores NaN by default.

### Test 2.3: Missing booking channel
- **What I tested**: 27 bookings have no channel. Does the channel analysis chart account for this?
- **How**: Checked the Channel Analysis tab for data completeness.
- **Result**: ✅ The dashboard shows an info banner: "27 bookings have no channel recorded and are excluded from channel analysis. Their revenue is still counted in property totals."

### Test 2.4: All filters deselected
- **What I tested**: What happens if a user deselects all properties or all months in the sidebar?
- **How**: Unchecked all property filters in the sidebar.
- **Result**: ✅ The dashboard shows a clear warning ("No data matches the selected filters. Please adjust your selections.") and stops rendering charts. No crash, no empty/misleading charts.

---

## 3. Dashboard UI Tests

### Test 3.1: KPI cards accuracy
- **What I tested**: Do the top-level KPI numbers match manual calculations?
- **How**: Manually summed `realized_revenue` for completed bookings and compared to the dashboard's "Total Revenue" card.
- **Result**: ✅ Dashboard shows ₹23,26,854 which matches `completed['realized_revenue'].sum()`.

### Test 3.2: Health Score consistency
- **What I tested**: Do the health scores on the dashboard match the scores documented in DECISIONS.md?
- **How**: Compared dashboard scores with the scores calculated in the cross-check script.
- **Result**: ✅ Marigold Suites = 97, Palm Grove Inn = 51. Rankings match.

### Test 3.3: Filter interaction
- **What I tested**: Do the charts update correctly when filters are applied?
- **How**: Selected only "Palm Grove Inn" in the property filter and verified all charts, tables, and health scores reflect only that property's data.
- **Result**: ✅ All charts and KPIs update correctly.

### Test 3.4: Charts use cleaned data
- **What I tested**: Confirmed the dashboard reads `data/bookings_clean.csv`, not the raw file.
- **How**: Checked line 16 of `app.py`: `df = pd.read_csv("data/bookings_clean.csv")`.
- **Result**: ✅ Dashboard runs on cleaned data only. This is the assignment's #1 red flag and we avoid it.

---

## 4. What I Found and Fixed

| Issue | Found During | Fix |
|---|---|---|
| Date parser broke 175/230 dates | Pipeline testing | Rewrote with two-pass parsing + range sanity check |
| Room types DLX/Std not unified | Audit script | Added explicit mapping dictionaries |
| 27 missing channels not flagged | Audit script | Added `missing_channel_flag` column + info banner in UI |
| 9 missing rates not tracked | Audit script | Added `missing_rate_flag` column |
| Health score numbers slightly off in plan | Cross-check script | Recalculated with exact normalisation formula |

---

## 5. What I Chose NOT to Fix (and Why)

### No loading state indicator
When the page first loads or when the cache is cleared, there is a brief flash before charts render. Streamlit does not natively support custom loading spinners inside tabs without additional JavaScript. I chose not to fix this because:
- The load time is under 1 second with 230 rows — it's barely noticeable.
- Adding a custom spinner would require injecting JavaScript, which adds complexity without meaningful user benefit for this dataset size.
- The assignment says "clean and usable beats beautiful."

### Zero-night bookings not corrected
The 4 rows with `nights = 0` are flagged but not corrected (e.g., I don't guess what the nights should be). I chose to leave them as anomalies because:
- Without external confirmation, any correction would be inventing data.
- They're excluded from per-night calculations, so they don't corrupt metrics.
- Flagging them makes the issue visible rather than hiding it.

### BK1194: Suspicious high amount with missing rate
BK1194 (Palm Grove Inn) has `total_amount_inr = ₹47,705` with `nightly_rate_inr = NaN`. At 7 nights, that's ~₹6,815/night — higher than Palm Grove's average (₹5,582) but not impossibly so. Without the rate to cross-check, I can't confirm if this is a 10x error or a legitimately expensive booking. I chose to keep the revenue as-is because flagging it as an error without evidence would be equally wrong.
