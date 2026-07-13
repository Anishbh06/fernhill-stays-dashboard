# AI Workflow Log

## Tools Used
- **AI assistants (Gemini Code Assist / Cursor)**: Drafted the data cleaning script, dashboard code, audit helpers for cross-checking numbers, and initial documentation. Every output was manually reviewed against the raw CSV and corrected (see mistakes below).
- **Python 3.11 + Pandas / Plotly / Streamlit**: Data pipeline and dashboard. Chosen because the client asked for a simple dashboard — Streamlit is the fastest reliable path from CSV to a deployed interactive app.
- **GitHub Desktop + Git CLI**: Branch-per-feature workflow (`feature/data-cleaning`, `feature/health-score-dashboard`). Changes were reviewed before merging to `main`.
- **VS Code / Cursor**: Code editing, comparing AI output to the raw data, and reading the CSV directly.
- **Streamlit Cloud**: Free deployment, connected to the GitHub repo for continuous updates.

## Prompts That Mattered

### Prompt 1: Setting the cleaning priority order
I gave the AI a strict order for cleaning — duplicates first, then amount mismatches, then cancellation exclusion, then cosmetic normalisation, then dates, then missing-value flagging, then edge cases. The AI does not know which issues silently corrupt money math versus which are cosmetic. The order was my decision; the AI executed it.

### Prompt 2: "Run a rigorous data validation against the raw source file"
After the first version of `clean_data.py`, I asked for a separate verification against the raw file to confirm no silent data loss. That audit script surfaced critical bugs in the AI's own cleaning code (see below).

### Prompt 3: Catching the generic DECISIONS.md
The first DECISIONS.md draft read like generic documentation — no booking IDs, no exact dataset counts, weak ownership. The assignment treats generic AI-sounding decision logs as a red flag. I required a rewrite with specific row counts, booking IDs, and dataset-specific rationale.

### Prompt 4: "Cross-reference the dashboard metrics against the business requirements"
Before locking the dashboard, I asked the AI to re-read the brief and recalculate every KPI from the cleaned data. Approximate health scores in the plan were off by 2–4 points — ranking was correct (Palm Grove worst), exact scores were not. Those numbers were recalculated before they entered DECISIONS.md.

### Prompt 5: "Perform a final end-to-end audit against all requirements"
After the first complete dashboard, I asked for a full CSV → cleaning → UI audit as if preparing client handover. That pass produced Mistakes 6–8 below.

### Prompt 6: "Make this client-ready — recommendations, not only charts"
A final readiness pass: charts alone answer "what happened"; the client also asked "where should I focus." I required a concise, filter-aware recommendation banner and accurate health-score callouts so advice stays true when filters change. Documentation (README, DECISIONS, TEST-REPORT) was updated to match the shipped behaviour.

## Concrete Examples of AI Mistakes I Caught

### Mistake 1: Date parser silently broke 76% of the data
First implementation used `pd.to_datetime(..., dayfirst=True, errors='coerce')` in one call. That silently failed on 175 of 230 rows because `dayfirst=True` conflicts with ISO dates like `2026-01-25`. The timeline would have been nearly empty with no error.

**How I caught it**: Triple-check audit showed `Unparseable dates: 175`. Fixed with two-pass parsing (ISO first, then `dayfirst` for the rest) plus a Jan–May 2026 range check that corrected 20 day/month swaps.

### Mistake 2: Room type abbreviations not unified
`.str.title()` turned "DLX" into "Dlx" and left "Std" separate from "Standard". The UI would have shown five room types instead of three.

**How I caught it**: Audit printed `Room types: ['Dlx', 'Deluxe', 'Standard', 'Std', 'Suite']`. Fixed with explicit mapping dictionaries.

### Mistake 3: 27 missing booking channels ignored
The first script neither flagged nor explained empty channels. The client specifically asked which channels are worth it — dropping attribution silently would bias that answer.

**How I caught it**: Audit showed 29 missing in raw data (27 after dedup). Added `missing_channel_flag` and UI note.

### Mistake 4: Missing nightly rates not tracked
Only missing `total_amount_inr` (3 rows) was tracked; 9 missing `nightly_rate_inr` values were ignored.

**How I caught it**: Audit showed `nightly_rate_inr: 9 missing`. Added `missing_rate_flag`.

### Mistake 5: Files created in the wrong directory
Project skeleton files were created outside the Git repository root and had to be moved before version control reflected them.

**How I caught it**: Files did not appear in the expected GitHub Desktop tree.

### Mistake 6: Dashboard crash when all filters deselected
Empty filter selections could divide by zero when computing cancellation rate (`len(cancelled) / len(fdf)` with `len(fdf) = 0`).

**How I caught it**: Edge-case UI audit. Added a warning and `st.stop()` guard.

### Mistake 7: No "Revenue Lost" metric
First dashboard showed only realized revenue. A 37% cancel rate is abstract without the rupee cost (₹13.7L).

**How I caught it**: Mapped each chart back to "where should I focus?" Added the Revenue Lost KPI.

### Mistake 8: No status or room-type breakdown
Property Performance was revenue-only. Operators also need status mix (checked-out vs cancelled vs no-show) and room-type revenue share.

**How I caught it**: Client-readiness review. Added stacked status bars and a room-type pie chart.

### Mistake 9: Health-score alert overstated "highest cancellation rate"
The callout always said the lowest-scoring property had the highest cancellation rate. That is true on the full dataset (Palm Grove) but can be false under filters.

**How I caught it**: Final audit with alternate filter slices. Rewrote the alert to name the weakest health-score component and report cancel rate without claiming a global maximum.

## Takeaway
The AI produced most of the code, but unreviewed output repeatedly introduced silent failures — bugs that do not crash and still make the dashboard wrong. Across cleaning, dashboard, and the final readiness pass I caught **9** distinct issues. My contribution was priority-setting, verification against the raw data, scoping (cleaning order, health-score weights), and pushing for a client-ready experience: accurate numbers, honest assumptions, and recommendations that stay correct when the view is filtered.
