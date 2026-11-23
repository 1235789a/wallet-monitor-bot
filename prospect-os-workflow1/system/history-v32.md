# V3.2 history provenance and contact-state audit

This is a **read-only** QA stage for the private MultiHub history index. It
does not connect to Google Sheets/Docs by itself, discover additional companies,
send messages, certify opt-in, or promote HISTORY_CLEAR/SEND_READY.

## Why it exists

- An inherited VERIFIED_COMPLETE flag is *not* proof that the original Google
  Sheets/Docs, later daily batches and conversation logs were independently
  re-read. The audit compares declared counts, source scope and inventory
  read-status/digest **metadata** and reports missing provenance per category.
- A later research READY cannot erase SENT/CONTACTED history. A central
  REPLIED claim and an explicit no-reply note are a conflict, not proof of
  an inbound reply. Inbound replies/payments require independently examined
  message/transaction evidence.
- Some Drive export tools reserialize JSON and change retrieved_at on each
  fetch. The semantic checksum removes only downloader timestamps for
  *comparison*; original-source file SHA256 still matters for forensics.

## Usage

Obtain the **private** index via the user's authorized Drive access. Save it
outside this public repository. Do not commit actual client names, domains,
phone numbers, source URLs, or the generated audit reports.

    python scripts/audit_history_v32.py \
      --history-index /private/history_index.json \
      --output /private/history_audit.json

Optionally review conflicting historical contact statuses from private
Sheets/Docs exports using this JSON shape:

    {
      "subjects": [
        {
          "key": "synthetic-fixture",
          "claims": [
            {"status": "REPLIED", "detail": "old central ledger"},
            {"status": "READY", "detail": "later research batch"},
            {"status": "已联系", "detail": "暂无回复"}
          ]
        }
      ]
    }

    python scripts/audit_history_v32.py \
      --history-index /private/history_index.json \
      --claims /private/contact_claims.json \
      --output /private/history_audit.json

Outputs for the example: stage CONTACTED, issue REPLY_CONFLICT,
eligible_for_new_first_contact false, send_ready false.

### Provenance definitions

For each of 103_MASTER, 112_MASTER, CENTRAL_HISTORY, FB_PRESENTED and
DAILY_PRESENTED, compare actual indexed row count with recorded count.
Verify there is a nonempty source scope and that each scoped URL has a
matching source_inventory record with READ_VERIFIED, record_count, and a
syntactically valid SHA256 digest. The tool reports whether those **metadata
statements** are consistent. It cannot prove the downloaded bytes match the
digest unless an independent source-byte verifier actually reads them, nor
whether an unlisted archive exists. It therefore never sets HISTORY_CLEAR.

If Sheets/Docs are unavailable in the executing environment, use an already
authorized environment to export and read the originals, or keep
HOLD_HISTORY_INCOMPLETE. Do not disable the history gate to accommodate
missing permissions.

The existing merge tool remains the append-only import path:

    python scripts/merge_private_history_archives.py \
      /private/old_index.json /private/source_manifest.json \
      /private/new_index.json /private/merge_report.json

Run the V3.2 audit **after** import. No client is automatically send-ready;
recipient identity and marketing consent require their own evidence and human
authorization.

### Testing

    python scripts/test_history_v32.py

CI runs these synthetic regression tests with the existing Daily27 QA suite.
