import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from prospect_os.buyer_intent import (
    ensure_buyer_schema, qualify, record_event, record_touchpoint, execute,
)


CHECKED = "2026-09-10T08:00:00+00:00"


def evidence(claim, url="https://sample.example/evidence"):
    return {"label": "observed", "claim": claim, "source_url": url,
            "checked_at": CHECKED}


def valid_row(track="b2b"):
    queries = [
        "best blockchain development companies for startups",
        "companies that can build a crypto exchange",
        "token development company for a startup",
        "DeFi development agency for an MVP",
        "Web3 development company for fintech",
    ]
    row = {
        "company_name": "Sample Studio",
        "website_url": "https://sample.example/",
        "directory_id": "sample-1",
        "discovery_channel": "industry_directory",
        "discovery_source_url": "https://directory.example/sample-studio",
        "icp": "blockchain_agency" if track == "b2b" else "independent_tobacco",
        "company_verified": evidence("Official site identifies the operating business."),
        "small_team_verified": evidence("Directory and team page support a small team."),
        "non_chain_verified": evidence("One independent business identity was observed."),
        "chain": False,
        "contacts": [{"channel": "email", "value": "sales@sample.example",
                      "evidence": evidence("Official business email is published.")}],
        "buyer_queries": [{"query": q, "reviewed": True, "buyer_intent": True,
                           "service_relevance": "core service"} for q in queries],
        "visibility": [{"query": q, "tested_at": CHECKED, "artifact": "audit/q.json",
                        "platform": "web_search_tool", "status": "tested",
                        "returned_urls": ["https://competitor.example/service"],
                        "prospect_presence": "not_in_returned_results",
                        "competitors": ["Competitor"], "scope": "returned result sample"}
                       for q in queries],
        "gaps": [evidence("Gap one"), evidence("Gap two"), evidence("Gap three")],
        "recent_activity": {**evidence("Published a current service update."),
                            "occurred_at": "2026-09-08"},
        "signals": {
            "acquisition_investment": {"level": 2, **evidence("Multiple service pages and current commercial content.")},
            "buyer_value": {"level": 2, **evidence("Public project minimum indicates high-value work.")},
            "visibility_gap": {"level": 2, **evidence("Five tested queries returned competitors but not the prospect.")},
            "decision_access": {"level": 2, **evidence("Direct business contact is public.")},
            "delivery_fit": {"level": 2, **evidence("Official site is editable and has service pages.")},
            "recent_activity": {"level": 2, **evidence("Recent commercial content was observed.")},
            "usdt": {"level": 0},
        },
        "outreach": "Evidence-based opener",
        "recommended_first_fix": "Build one buyer-query service answer page.",
    }
    return row


class BuyerIntentTests(unittest.TestCase):
    def test_p0_requires_five_tested_queries(self):
        row = valid_row()
        self.assertEqual(qualify(row, date(2026, 9, 10))["qualification"], "P0")
        row["visibility"] = row["visibility"][:4]
        result = qualify(row, date(2026, 9, 10))
        self.assertEqual(result["qualification"], "REVIEW_REQUIRED")
        self.assertIn("tested_buyer_query_competitor_gap", result["missing"])
        self.assertEqual(result["score_breakdown"]["visibility_gap"], 0)

    def test_plain_phone_and_broadcast_channel_do_not_pass_contact_gate(self):
        row = valid_row()
        row["contacts"] = [
            {"channel": "whatsapp", "value": "+1 555 0100", "evidence": evidence("Phone")},
            {"channel": "telegram", "value": "https://t.me/sample_news", "route_type": "channel",
             "evidence": evidence("Broadcast channel")},
        ]
        self.assertIn("official_contact_source", qualify(row, date(2026, 9, 10))["missing"])

    def test_dry_run_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "rows.json"
            source.write_text(json.dumps([valid_row()]))
            db = root / "prospects.db"
            summary = execute(source, "2026-09-10", db, root / "out", commit=False)
            self.assertFalse(db.exists())
            self.assertEqual(summary["selected_mix"], {"b2b": 1, "local": 0})

    def test_payment_needs_unique_attributed_invoice(self):
        conn = sqlite3.connect(":memory:")
        ensure_buyer_schema(conn)
        row = qualify(valid_row(), date(2026, 9, 10))
        conn.execute("INSERT INTO buyer_assessments VALUES(?,?,?)",
                     ("sample.example", json.dumps(row), CHECKED))
        stages = ["RAW", "QUALIFIED", "P0", "CONTACTED", "REPLIED", "INTERESTED", "OFFERED"]
        for stage in stages:
            record_event(conn, {"event_id": stage, "website_url": "https://sample.example",
                                "stage": stage, "occurred_at": CHECKED, "evidence_ref": "fixture"})
        payment = {"event_id": "paid-1", "website_url": "https://sample.example", "stage": "PAID",
                   "occurred_at": CHECKED, "evidence_ref": "invoice.pdf", "payment_verified": True,
                   "invoice_id": "INV-1", "amount": 149, "currency": "USD"}
        record_event(conn, payment)
        record_event(conn, payment)  # exact replay is idempotent
        with self.assertRaises(sqlite3.IntegrityError):
            record_event(conn, {**payment, "event_id": "paid-2"})
        record_touchpoint(conn, {"event_id": "audit-sent-1", "website_url": "https://sample.example",
                                 "event_kind": "AUDIT_SENT", "occurred_at": CHECKED,
                                 "evidence_ref": "message-export"})


if __name__ == "__main__":
    unittest.main()
