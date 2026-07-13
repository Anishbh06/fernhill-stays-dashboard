import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def clean_bookings(input_path, output_path):
    logging.info(f"Loading data from {input_path}")
    df = pd.read_csv(input_path)
    initial_rows = len(df)

    # ── STEP 1: Remove exact duplicate rows ──────────────────────────────
    # WHY FIRST: If a booking is counted twice, every downstream metric
    # (revenue, occupancy, health score) is silently inflated.
    df = df.drop_duplicates()
    dupes_removed = initial_rows - len(df)
    logging.info(f"Step 1 — Removed {dupes_removed} exact duplicate rows. ({initial_rows} → {len(df)})")

    # ── STEP 2: Normalise text columns ────────────────────────────────────
    # WHY: Without this, groupby("property") treats "Cedar Court" and
    # "cedar court" as two different hotels → silently wrong dashboard.
    #
    # Property names: strip whitespace + title-case
    # e.g. "Marigold Suites " → "Marigold Suites", "MARIGOLD SUITES" → "Marigold Suites"
    df['property'] = df['property'].astype(str).str.strip().str.title()

    # Status: normalise to a clean set (Checked-Out, Confirmed, Cancelled, No-Show)
    df['status'] = df['status'].astype(str).str.strip().str.lower()
    status_map = {
        'checked out': 'Checked-Out',
        'checked-out': 'Checked-Out',
        'confirmed': 'Confirmed',
        'cancelled': 'Cancelled',
        'no-show': 'No-Show',
    }
    df['status'] = df['status'].map(status_map).fillna(df['status'])
    logging.info(f"Step 2a — Normalised property names. Unique properties: {sorted(df['property'].unique())}")
    logging.info(f"Step 2b — Normalised status values. Unique statuses: {sorted(df['status'].unique())}")

    # Booking channel: strip + map to canonical names
    df['booking_channel'] = df['booking_channel'].astype(str).str.strip().str.lower()
    channel_map = {
        'direct': 'Direct',
        'corporate': 'Corporate',
        'walk-in': 'Walk-In',
        'ota-mmt': 'OTA-MMT',
        'ota-booking': 'OTA-Booking',
        'nan': None,  # preserve actual missing values
    }
    df['booking_channel'] = df['booking_channel'].map(channel_map).fillna(df['booking_channel'])
    logging.info(f"Step 2c — Normalised booking channels. Unique channels: {sorted(df['booking_channel'].dropna().unique())}")

    # Room type: unify abbreviations (DLX → Deluxe, Std → Standard)
    df['room_type'] = df['room_type'].astype(str).str.strip().str.lower()
    room_map = {
        'dlx': 'Deluxe',
        'deluxe': 'Deluxe',
        'std': 'Standard',
        'standard': 'Standard',
        'suite': 'Suite',
    }
    df['room_type'] = df['room_type'].map(room_map).fillna(df['room_type'])
    logging.info(f"Step 2d — Normalised room types. Unique types: {sorted(df['room_type'].unique())}")

    # ── STEP 3: Parse dates ───────────────────────────────────────────────
    # WHY: The CSV has dates in 4+ formats (YYYY-MM-DD, DD Mon YYYY,
    # MM-DD-YYYY, DD/MM/YYYY). A single pd.to_datetime call can't handle
    # all of them because dayfirst conflicts with ISO format. So we try
    # multiple format passes and combine results.
    #
    # The booking data is Jan–May 2026, so any parsed date outside that
    # range is a sign of day/month confusion (e.g. 05-07-2026 read as
    # Jul 5 instead of May 7). We use that as a sanity check.
    raw_dates = df['check_in_date'].copy()
    
    # Pass 1: Try YYYY-MM-DD (ISO) — these are unambiguous
    parsed = pd.to_datetime(raw_dates, format='%Y-%m-%d', errors='coerce')
    
    # Pass 2: Try "DD Mon YYYY" (e.g. "9 Mar 2026") for rows still unparsed
    mask_unparsed = parsed.isna()
    parsed[mask_unparsed] = pd.to_datetime(raw_dates[mask_unparsed], format='mixed', dayfirst=True, errors='coerce')
    
    df['check_in_date'] = parsed
    
    # Sanity check: dates should fall within Jan–May 2026
    out_of_range = (df['check_in_date'] < '2026-01-01') | (df['check_in_date'] > '2026-05-31')
    out_of_range = out_of_range & df['check_in_date'].notna()
    if out_of_range.sum() > 0:
        logging.warning(f"Step 3 — {out_of_range.sum()} dates fall outside Jan-May 2026 (day/month swap detected)")
        # Fix by swapping day and month for out-of-range dates
        bad_dates = df.loc[out_of_range, 'check_in_date']
        df.loc[out_of_range, 'check_in_date'] = bad_dates.apply(
            lambda d: d.replace(month=d.day, day=d.month) if d.day <= 12 else pd.NaT
        )
        still_bad = df.loc[out_of_range, 'check_in_date'].isna().sum()
        if still_bad > 0:
            logging.warning(f"Step 3 — {still_bad} dates could not be fixed (day > 12, swap impossible)")
    
    unparseable_dates = df['check_in_date'].isna().sum()
    logging.info(f"Step 3 — Parsed dates. Unparseable: {unparseable_dates}, Fixed day/month swaps: {out_of_range.sum()}")

    # ── STEP 4: Coerce numeric columns ────────────────────────────────────
    df['nights'] = pd.to_numeric(df['nights'], errors='coerce')
    df['nightly_rate_inr'] = pd.to_numeric(df['nightly_rate_inr'], errors='coerce')
    df['total_amount_inr'] = pd.to_numeric(df['total_amount_inr'], errors='coerce')
    df['guests'] = pd.to_numeric(df['guests'], errors='coerce')

    # ── STEP 5: Fix amount mismatches (10x errors & negatives) ────────────
    # WHY: 11 rows had total_amount values that were 10x the expected
    # (nightly_rate × nights), or were negative. These are data-entry typos
    # that would massively distort revenue. We recalculate from rate × nights.
    expected_amount = df['nightly_rate_inr'] * df['nights']
    df['amount_error_flag'] = False

    # 5a: Negative amounts (5 rows) — clearly wrong
    negative_mask = df['total_amount_inr'] < 0
    df.loc[negative_mask, 'amount_error_flag'] = True

    # 5b: 10x/30x entry errors (7 unique rows, but some are duplicates)
    # Using >2x as the threshold to catch 10x errors without flagging
    # minor rounding or tax differences.
    mismatch_mask = (
        (df['total_amount_inr'] > 0)
        & (expected_amount > 0)
        & (df['total_amount_inr'] > expected_amount * 2)
    )
    df.loc[mismatch_mask, 'amount_error_flag'] = True

    error_count = df['amount_error_flag'].sum()
    logging.info(f"Step 5 — Flagged {error_count} rows with amount errors (negative or >2x expected).")

    # Overwrite the bad total with the recalculated correct amount
    df.loc[df['amount_error_flag'], 'total_amount_inr'] = expected_amount[df['amount_error_flag']]

    # ── STEP 6: Flag missing financial values ─────────────────────────────
    # WHY: 9 rows have missing nightly_rate, 3 have missing total_amount.
    # We do NOT guess or impute — that would mean inventing financial data.
    # Instead we flag them and exclude from revenue.
    df['missing_rate_flag'] = df['nightly_rate_inr'].isna()
    df['missing_amount_flag'] = df['total_amount_inr'].isna()
    logging.info(f"Step 6 — Missing nightly rates: {df['missing_rate_flag'].sum()}, Missing total amounts: {df['missing_amount_flag'].sum()}")

    # ── STEP 7: Create realized_revenue (excludes cancellations) ──────────
    # WHY: Cancelled/No-show bookings are not real income. The assignment
    # explicitly lists this as an auto-fail if silently counted as revenue.
    df['realized_revenue'] = df['total_amount_inr']
    cancelled_mask = df['status'].isin(['Cancelled', 'No-Show'])
    df.loc[cancelled_mask, 'realized_revenue'] = 0
    # Also zero out revenue for rows with missing amounts
    df.loc[df['missing_amount_flag'], 'realized_revenue'] = 0
    logging.info(f"Step 7 — Excluded {cancelled_mask.sum()} cancelled/no-show bookings from realized revenue.")

    # ── STEP 8: Flag zero-night anomalies ─────────────────────────────────
    # WHY: nights=0 with money attached is contradictory. We flag it rather
    # than silently ignoring it or letting it break ADR calculations.
    df['zero_night_anomaly'] = (df['nights'] == 0) & (df['total_amount_inr'] > 0)
    logging.info(f"Step 8 — Flagged {df['zero_night_anomaly'].sum()} rows with zero nights but positive amount.")

    # ── STEP 9: Flag missing booking channel ──────────────────────────────
    # WHY: 27 rows (after dedup) have no booking channel. We keep these rows (they have
    # valid revenue data) but flag them so the "which channels are worth it"
    # chart can note incomplete channel attribution.
    df['missing_channel_flag'] = df['booking_channel'].isna()
    logging.info(f"Step 9 — Flagged {df['missing_channel_flag'].sum()} rows with missing booking channel.")

    # ── Summary ───────────────────────────────────────────────────────────
    logging.info(f"")
    logging.info(f"=== CLEANING SUMMARY ===")
    logging.info(f"Rows in raw file:        {initial_rows}")
    logging.info(f"Duplicates removed:      {dupes_removed}")
    logging.info(f"Rows in clean file:      {len(df)}")
    logging.info(f"Amount errors corrected: {error_count}")
    logging.info(f"Cancelled/No-show:       {cancelled_mask.sum()}")
    logging.info(f"Missing amounts:         {df['missing_amount_flag'].sum()}")
    logging.info(f"Missing rates:           {df['missing_rate_flag'].sum()}")
    logging.info(f"Missing channels:        {df['missing_channel_flag'].sum()}")
    logging.info(f"Zero-night anomalies:    {df['zero_night_anomaly'].sum()}")
    logging.info(f"========================")

    df.to_csv(output_path, index=False)
    logging.info(f"Cleaned data saved to {output_path}")

if __name__ == '__main__':
    clean_bookings('data/bookings_raw.csv', 'data/bookings_clean.csv')
