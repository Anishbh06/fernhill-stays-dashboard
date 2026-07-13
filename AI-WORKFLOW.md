# AI Workflow Log

## Tools Used
- **Claude (AI assistant)**: Used for writing the data cleaning script (`clean_data.py`), generating initial DECISIONS.md drafts, and running data audits.
- **GitHub Desktop**: Version control and branch management.
- **VS Code**: Code editing and review.

## Prompts That Mattered

### Prompt 1: Setting the cleaning priority order
I gave the AI a strict ordering for the cleaning steps — duplicates first, then amount mismatches, then cancellation exclusion, then cosmetic normalisation, then dates, then missing-value flagging, then edge cases. The AI doesn't know which data issues hurt the most; I had to decide the priority based on what silently corrupts money math vs. what's cosmetic. The AI followed the order, but the ordering itself was my decision.

### Prompt 2: "Triple check if everything that was needed to be done in this branch is perfectly done"
After the AI wrote the first version of `clean_data.py`, I asked it to go back and verify everything against the raw data. This is when the AI's own audit script revealed that its code had critical bugs (see below).

### Prompt 3: Catching the generic DECISIONS.md
The AI's first draft of DECISIONS.md read like generic documentation — no specific booking IDs, no exact numbers from the dataset, no first-person ownership. I flagged that the assignment explicitly says "a DECISIONS.md that reads like generic AI output with no specific reference to this dataset" is an automatic red flag. The AI rewrote it with specific row counts, booking IDs, and data-specific rationale.

### Prompt 4: "Check the problem statement, check if cleaning is done properly, check if the dashboard is giving everything perfectly"
Before building the dashboard, I told the AI to re-read the assignment and cross-check every number in the plan against the actual data. This caught approximate health score numbers in the plan that were off by 2–4 points — the ranking was right (Palm Grove = worst) but the exact numbers were wrong. Sloppy presentation in a client deliverable looks bad, so I made the AI recalculate with the exact formula before putting the numbers in DECISIONS.md.

### Prompt 5: "Triple check — make me unrejectable"
After the dashboard was built, I made the AI go back and audit everything from the CSV to the cleaning to the dashboard output. This audit found 3 improvements the AI had missed in the dashboard (see Mistakes 6–8 below).

## Concrete Examples of AI Mistakes I Caught

### Mistake 1: Date parser silently broke 76% of the data
The AI's first implementation used `pd.to_datetime(df['check_in_date'], dayfirst=True, errors='coerce')` as a single call. This silently failed on 175 out of 230 rows because `dayfirst=True` conflicts with ISO-format dates like `2026-01-25`. The dashboard would have had an almost entirely empty timeline chart with no error message.

**How I caught it**: I asked the AI to triple-check everything. Its own audit script showed `Unparseable dates: 175`. I made it fix this with a two-pass approach (ISO first, then dayfirst for the rest) plus a range sanity check that caught 20 more day/month swaps.

### Mistake 2: Room type abbreviations not unified
The AI's text normalisation used `.str.title()` which turned "DLX" into "Dlx" and "Std" into "Std" — still separate from "Deluxe" and "Standard". The dashboard would have shown 5 room types instead of 3, with fragmented data in each.

**How I caught it**: The deep audit printed `Room types: ['Dlx', 'Deluxe', 'Standard', 'Std', 'Suite']` — immediately obvious that abbreviations weren't being unified. Fixed by adding explicit mapping dictionaries.

### Mistake 3: 27 missing booking channels completely ignored
The AI's first script didn't flag or acknowledge that 27 rows had no booking channel. Since the client specifically asked "which booking channels are worth it," silently losing 27 rows from that analysis would have been a problem.

**How I caught it**: The audit showed `booking_channel: 29 missing` (29 in the raw data, 27 after dedup). Added a `missing_channel_flag` column and logging.

### Mistake 4: Missing nightly rates not tracked
The AI only tracked missing `total_amount_inr` (3 rows) but ignored that 9 rows had missing `nightly_rate_inr`. Both are financial data gaps that should be visible.

**How I caught it**: The audit output showed `nightly_rate_inr: 9 missing`. Added a `missing_rate_flag` column.

### Mistake 5: Files created in wrong directory
When I asked the AI to set up the project skeleton, it created all files in the outer workspace folder instead of inside the actual Git repository. I had to point out "I am already inside fernhill, why was it created inside again?" and the files had to be moved.

**How I caught it**: I noticed the files weren't showing up in the right place in GitHub Desktop.

### Mistake 6: Dashboard crashed when all filters deselected
The AI's first dashboard version had no empty-state handling. If a user unchecked all properties in the sidebar, it would try to divide by zero when calculating cancellation rate (`len(cancelled) / len(fdf)` where `len(fdf) = 0`). A client demo crashing on a simple filter action is embarrassing.

**How I caught it**: During the final audit I asked the AI to check edge cases in the UI. It found the division-by-zero risk and added a `st.stop()` guard with a user-friendly warning message.

### Mistake 7: No "Revenue Lost" metric
The AI's first dashboard only showed "Realized Revenue" — what was earned. But the client also needs to know how much money was *lost* to cancellations and no-shows. Without that number, the 37% cancellation rate is abstract; with it (₹16.5L lost), the client can quantify the problem.

**How I caught it**: During the dashboard audit, I reviewed each chart against the client's actual questions. "Where to focus" implies the client needs to see the cost of inaction — not just what's working but what's failing and how much it's costing.

### Mistake 8: No booking status or room type breakdown
The AI's first Property Performance tab only had revenue charts. It was missing two views that a hotel operator would immediately want: (1) a status breakdown showing how many bookings per property are checked-out vs cancelled vs no-show, and (2) revenue by room type. These add context that revenue alone can't provide.

**How I caught it**: I asked "is this the most optimal thing to give a client?" and realized the tab was revenue-only. Added a stacked status bar chart and a room type pie chart.

## Takeaway
The AI wrote 90% of the code, but every time I let it run without checking, it introduced silent bugs — the kind that don't throw errors but make the dashboard lie. Across both phases (cleaning and dashboard), I caught 8 distinct mistakes. The value I added was knowing what to check, catching what the AI missed, making scoping decisions (like the cleaning priority order and health score weights) that the AI couldn't make on its own, and pushing back when the output wasn't client-ready.

