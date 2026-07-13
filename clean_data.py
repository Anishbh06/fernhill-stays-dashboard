import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def clean_bookings(input_path, output_path):
    logging.info(f"Loading data from {input_path}")
    df = pd.read_csv(input_path)
    initial_rows = len(df)

    # Step 1 — exact duplicates first (prevents inflated metrics)
    df = df.drop_duplicates()
    dupes_removed = initial_rows - len(df)
    logging.info(f"Step 1 — Removed {dupes_removed} exact duplicate rows. ({initial_rows} → {len(df)})")

    # Step 2 — normalise categoricals
    df['property'] = df['property'].astype(str).str.strip().str.title()

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

    df['booking_channel'] = df['booking_channel'].astype(str).str.strip().str.lower()
    channel_map = {
        'direct': 'Direct',
        'corporate': 'Corporate',
        'walk-in': 'Walk-In',
        'ota-mmt': 'OTA-MMT',
        'ota-booking': 'OTA-Booking',
        'nan': None,
    }
    df['booking_channel'] = df['booking_channel'].map(channel_map).fillna(df['booking_channel'])
    logging.info(f"Step 2c — Normalised booking channels. Unique channels: {sorted(df['booking_channel'].dropna().unique())}")

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

    # Step 3 — parse dates (ISO first, then dayfirst; swap day/month if outside Jan–May 2026)
    raw_dates = df['check_in_date'].copy()
    parsed = pd.to_datetime(raw_dates, format='%Y-%m-%d', errors='coerce')
    mask_unparsed = parsed.isna()
    parsed[mask_unparsed] = pd.to_datetime(raw_dates[mask_unparsed], format='mixed', dayfirst=True, errors='coerce')
    df['check_in_date'] = parsed

    out_of_range = (df['check_in_date'] < '2026-01-01') | (df['check_in_date'] > '2026-05-31')
    out_of_range = out_of_range & df['check_in_date'].notna()
    if out_of_range.sum() > 0:
        logging.warning(f"Step 3 — {out_of_range.sum()} dates fall outside Jan-May 2026 (day/month swap detected)")
        bad_dates = df.loc[out_of_range, 'check_in_date']
        df.loc[out_of_range, 'check_in_date'] = bad_dates.apply(
            lambda d: d.replace(month=d.day, day=d.month) if d.day <= 12 else pd.NaT
        )
        still_bad = df.loc[out_of_range, 'check_in_date'].isna().sum()
        if still_bad > 0:
            logging.warning(f"Step 3 — {still_bad} dates could not be fixed (day > 12, swap impossible)")

    unparseable_dates = df['check_in_date'].isna().sum()
    logging.info(f"Step 3 — Parsed dates. Unparseable: {unparseable_dates}, Fixed day/month swaps: {out_of_range.sum()}")

    # Step 4 — numeric coercion
    df['nights'] = pd.to_numeric(df['nights'], errors='coerce')
    df['nightly_rate_inr'] = pd.to_numeric(df['nightly_rate_inr'], errors='coerce')
    df['total_amount_inr'] = pd.to_numeric(df['total_amount_inr'], errors='coerce')
    df['guests'] = pd.to_numeric(df['guests'], errors='coerce')

    # Step 5 — fix negatives / >2x amount errors from rate × nights
    expected_amount = df['nightly_rate_inr'] * df['nights']
    df['amount_error_flag'] = False
    negative_mask = df['total_amount_inr'] < 0
    df.loc[negative_mask, 'amount_error_flag'] = True
    mismatch_mask = (
        (df['total_amount_inr'] > 0)
        & (expected_amount > 0)
        & (df['total_amount_inr'] > expected_amount * 2)
    )
    df.loc[mismatch_mask, 'amount_error_flag'] = True
    error_count = df['amount_error_flag'].sum()
    logging.info(f"Step 5 — Flagged {error_count} rows with amount errors (negative or >2x expected).")
    df.loc[df['amount_error_flag'], 'total_amount_inr'] = expected_amount[df['amount_error_flag']]

    # Step 6 — flag missing financials (do not impute)
    df['missing_rate_flag'] = df['nightly_rate_inr'].isna()
    df['missing_amount_flag'] = df['total_amount_inr'].isna()
    logging.info(f"Step 6 — Missing nightly rates: {df['missing_rate_flag'].sum()}, Missing total amounts: {df['missing_amount_flag'].sum()}")

    # Step 7 — realized_revenue excludes Cancelled / No-Show / missing amount
    df['realized_revenue'] = df['total_amount_inr']
    cancelled_mask = df['status'].isin(['Cancelled', 'No-Show'])
    df.loc[cancelled_mask, 'realized_revenue'] = 0
    df.loc[df['missing_amount_flag'], 'realized_revenue'] = 0
    logging.info(f"Step 7 — Excluded {cancelled_mask.sum()} cancelled/no-show bookings from realized revenue.")

    # Step 8 — flag zero-night anomalies
    df['zero_night_anomaly'] = (df['nights'] == 0) & (df['total_amount_inr'] > 0)
    logging.info(f"Step 8 — Flagged {df['zero_night_anomaly'].sum()} rows with zero nights but positive amount.")

    # Step 9 — flag missing channels (keep rows; exclude from channel analysis)
    df['missing_channel_flag'] = df['booking_channel'].isna()
    logging.info(f"Step 9 — Flagged {df['missing_channel_flag'].sum()} rows with missing booking channel.")

    logging.info("")
    logging.info("=== CLEANING SUMMARY ===")
    logging.info(f"Rows in raw file:        {initial_rows}")
    logging.info(f"Duplicates removed:      {dupes_removed}")
    logging.info(f"Rows in clean file:      {len(df)}")
    logging.info(f"Amount errors corrected: {error_count}")
    logging.info(f"Cancelled/No-show:       {cancelled_mask.sum()}")
    logging.info(f"Missing amounts:         {df['missing_amount_flag'].sum()}")
    logging.info(f"Missing rates:           {df['missing_rate_flag'].sum()}")
    logging.info(f"Missing channels:        {df['missing_channel_flag'].sum()}")
    logging.info(f"Zero-night anomalies:    {df['zero_night_anomaly'].sum()}")
    logging.info("========================")

    df.to_csv(output_path, index=False)
    logging.info(f"Cleaned data saved to {output_path}")

if __name__ == '__main__':
    clean_bookings('data/bookings_raw.csv', 'data/bookings_clean.csv')
