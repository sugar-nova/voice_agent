# KB Scope — Wise "Where is my money"

This bot is scoped to one Wise help section: transfer tracking and payout status for
"Where is my money". The runtime pattern is Q->A semantic routing:

- Embed user query.
- KNN match against pre-authored question variants (`embedded_questions`) for each intent.
- If similarity >= threshold, return stored voice answer directly to TTS.
- If no high-confidence in-scope match, deflect to a human.

## In-Scope intents

- Track transfer status in Activity
- Transfer ETA and timing updates
- Processing delays and common reasons
- Sent status but recipient not credited yet
- Recipient has not received transfer yet
- Proof of payment / transfer receipt
- Transfer reference number
- Cancelled transfer refund path
- Failed transfer refund path
- Email / app notifications for status changes

## Explicit Out-of-Scope examples

- Fees, exchange rates, and pricing
- Account setup, login, password, verification profile issues
- Card issues, chargebacks, disputes
- New transfer creation flow
- Business account onboarding
- Product support unrelated to "where is my money"

## Content engineering rules

- Keep answers voice-first: concise, plain language, no UI-heavy phrasing.
- Each intent includes 5+ conversational question variants.
- Embed only question variants for L1 routing.
- Store one canonical answer payload per intent (TTS output text).
- Keep wording deterministic to reduce latency and avoid unnecessary LLM calls.

Run `python scripts/eval_l1_threshold.py` after KB edits to tune `BRAIN_L1_THRESHOLD`
with precision/recall on in-scope vs out-of-scope fixtures.

Use the hard-negative set for stricter gating checks:
`python scripts/eval_l1_threshold.py --eval-file server/app/kb/eval_queries_hard_negatives.yaml`