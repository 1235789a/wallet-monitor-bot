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
    if track == "local":
        row["location_count"] = 1
        row["location_count_verified"] = evidence(
            "Full source pool and official identity resolve to one location.")
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

    def test_local_pool_rejects_three_or_more_locations(self):
        row = valid_row("local")
        row["location_count"] = 69
        result = qualify(row, date(2026, 9, 10))
        self.assertEqual(result["qualification"], "QUARANTINED")
        self.assertIn("local_business_has_more_than_two_locations", result["hard_failures"])

    def test_local_pool_requires_location_count_evidence(self):
        row = valid_row("local")
        row.pop("location_count_verified")
        result = qualify(row, date(2026, 9, 10))
        self.assertEqual(result["qualification"], "REVIEW_REQUIRED")
        self.assertIn("verified_location_count", result["missing"])

    def test_dry_run_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "rows.json"
            source.write_text(json.dumps([valid_row()]))
            db = root / "prospects.db"
            summary = execute(source, "2026-09-10", db, root / "out", commit=False)
            self.assertFalse(db.exists())
            self.assertEqual(summary["selected_mix"], {"b2b": 1, "local": 0})

    def test_dedup_keeps_reviewed_record_when_placeholder_comes_first(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reviewed = valid_row()
            placeholder = {
                "company_name": "Sample directory placeholder",
                "website_url": reviewed["website_url"],
                "directory_id": "older-source-row",
                "discovery_channel": "industry_directory",
                "discovery_source_url": "https://directory.example/older-source-row",
                "icp": "blockchain_agency",
            }
            source = root / "rows.json"
            source.write_text(json.dumps([placeholder, reviewed]))
            out = root / "out"
            summary = execute(source, "2026-09-10", root / "prospects.db", out, commit=False)
            decisions = json.loads((out / "decisions.json").read_text())
            self.assertEqual(summary["selected"], 1)
            self.assertEqual(decisions[0]["qualification"], "DUPLICATE")
            self.assertEqual(decisions[1]["qualification"], "P0")

    def test_commit_records_internal_audit_but_not_audit_sent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "rows.json"
            source.write_text(json.dumps([valid_row()]))
            db = root / "prospects.db"
            execute(source, "2026-09-10", db, root / "out", commit=True)
            conn = sqlite3.connect(db)
            stages = {r[0] for r in conn.execute("SELECT stage FROM buyer_events")}
            touches = list(conn.execute("SELECT event_kind FROM buyer_touchpoints"))
            self.assertEqual(stages, {"RAW", "QUALIFIED", "P0", "AUDITED"})
            self.assertEqual(touches, [])
            conn.close()

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
