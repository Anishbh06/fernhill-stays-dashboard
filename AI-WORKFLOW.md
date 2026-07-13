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

## Takeaway
The AI wrote 90% of the code, but every time I let it run without checking, it introduced silent bugs — the kind that don't throw errors but make the dashboard lie. The value I added was knowing what to check, catching what the AI missed, and making scoping decisions (like the cleaning priority order) that the AI couldn't make on its own.
