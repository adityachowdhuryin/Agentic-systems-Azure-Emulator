# A02 End-to-end audit (21 Sep 2026)

## Verdict
**Pass with one defect found and fixed.** Invoice review works end-to-end; Sales Lead regression passes.

## Scores
- Live checks: **27/27**
- Acceptance T1–T10: **10/10**
- Unit tests: **6/6**
- Journal purity after fix: **verified on CASE-04**

## Defect fixed during audit
**Journal pollution:** SQLite ran without `foreign_keys=ON`, so deleted runs left orphan `journal_turns`/`findings`. Recycled `run_id`s mixed CASE-01 + CASE-03 turns in one journal.

**Fix:** enable FK pragma, orphan cleanup on migrate, clear journal+finding at agent start. Re-test: CASE-04 journal only contains `CASE-04_INV-04766`.

## Notes
- Model: `gpt-5-mini` (gpt-4o-mini deprecated on account)
- Extract field `po_reference` (agent maps to `po_number`)
- Azure Phase 5 still deferred

## Artifacts
- `docs/a02_audit_live.json`
- `docs/a02_audit_partial.json`
- Canvas: `a02-system-audit.canvas.tsx`
