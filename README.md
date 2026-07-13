# Fernhill Stays — Performance Dashboard

A data-driven dashboard for Fernhill Stays, a boutique hotel group with 5 properties in Bengaluru. It answers three questions: how each property is doing, which booking channels are worth it, and where to focus (health score).

## Live Dashboard

**[Open live dashboard](https://fernhill-stays-dashboard-yrnwtdbmxdykhk5wlthrkm.streamlit.app/)**

## Key Findings (Jan–May 2026)

| Finding | Detail |
|---|---|
| Focus property | **Palm Grove Inn** — lowest health score (**51.2/100**); **51%** cancellation rate despite the highest average nightly rate |
| Strongest property | **Marigold Suites** — health score **97.1/100** |
| Best channel | **Walk-In** — highest average booking value (₹20,665); lowest cancel rate (33%) |
| Weakest channel | **Corporate** — lowest average value (₹9,722); highest cancel rate (53%) |
| Cost of cancellations | **₹13.7L** booked value in Cancelled / No-Show (37% of bookings) |

All revenue charts use **realized revenue only**. Cancelled and no-show bookings are never counted as income.

## Quick Start (Local)

```bash
git clone https://github.com/Anishbh06/fernhill-stays-dashboard.git
cd fernhill-stays-dashboard
pip install -r requirements.txt
python clean_data.py
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Project Structure

```
├── data/
│   ├── bookings_raw.csv        # Raw bookings (Jan–May 2026)
│   └── bookings_clean.csv      # Output of clean_data.py
├── clean_data.py               # 9-step cleaning pipeline (logged)
├── app.py                      # Streamlit dashboard
├── requirements.txt
├── DECISIONS.md                # Issues, health-score formula, assumptions
├── AI-WORKFLOW.md              # Tools, prompts, mistakes caught
├── TEST-REPORT.md              # QA methodology and results
└── README.md
```

## What the Dashboard Shows

1. **Property Performance** — Revenue, bookings, cancellation rates, monthly trends
2. **Channel Analysis** — Revenue, cancel rate, and average booking value by channel
3. **Health Score** — 0–100 composite (30% occupancy, 25% revenue, 25% cancellation, 20% rate)

A filter-aware **Where to focus** banner summarises the highest-risk property, best/weakest channels, and revenue at risk for the current filter selection.

## Data Cleaning Summary

Raw file: 238 rows, 14 distinct issue types. `clean_data.py` handles:

- 8 duplicate rows removed
- 11 amount errors corrected (negatives, 10× typos)
- 85 cancelled/no-show bookings excluded from revenue
- Text normalisation (9 property variants → 5, etc.)
- 4 date formats parsed; 20 day/month swaps corrected
- Missing values flagged (not imputed)

Details: [DECISIONS.md](DECISIONS.md) · AI use: [AI-WORKFLOW.md](AI-WORKFLOW.md) · QA: [TEST-REPORT.md](TEST-REPORT.md)

## Tech Stack

- Python 3.11
- Streamlit
- Plotly
- Pandas
