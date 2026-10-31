import unittest
from datetime import date
from validate_daily_evidence import validate

TODAY = date(2026, 10, 31)
SOURCES = ["103_MASTER", "112_MASTER", "CENTRAL_HISTORY", "FB_PRESENTED", "DAILY_PRESENTED"]

def lead(ch="WA", seg="CORE_B2B", domain="example.com", vertical=None):
    url = {"WA": "https://wa.me/12125550123", "TG": "https://t.me/FounderTest1",
           "FB": "https://www.facebook.com/people/BusinessOwner/100000000000000"}[ch]
    return dict(id="ID", company="Test", canonical_domain=domain, website="https://" + domain,
                channel=ch, segment=seg, retail_vertical=vertical, independent_store=True,
                identity_status="VERIFIED", non_chain=True, team_size=8,
                discovery_source="https://example-directory.org/companies",
                buyer_job="compare suppliers", buyer_problem="find reliable qualified providers",
                external_purchase_fit="EVIDENCED", recent_activity_source="https://" + domain + "/news",
                recent_activity_at="2026-10-29", history_status="NO_MATCH_IN_CHECKED_SOURCES",
                checked_sources=SOURCES, presented_before=False, opted_out=False,
                evidence_type="onsite_observation", evidence_url="https://" + domain + "/about",
                raw_capture_url="https://drive.google.com/raw", image_url="https://drive.google.com/image",
                source_manifest_url="https://drive.google.com/manifest", image_sha256="a"*64,
                image_status="VERIFIED_PNG_RAW", pairing_status="PASS", message="Hi from MultiHub, here's a note.",
                message_status="PASS", ai_gap_claimed=False, contact_url=url,
                contact_route_source="https://" + domain + "/contact",
                route_status="FB_DIRECT_BUSINESS_VERIFIED" if ch=="FB" else "BUSINESS_ROUTE_VERIFIED",
                fb_route_type="VERIFIED_PERSON_BUSINESS_DM" if ch=="FB" else None,
                recipient_status="FOUNDER_VERIFIED", human_review_status="PASS",
                contact_policy_status="PASS", regulatory_compliance_status="UNKNOWN",
                send_status="NOT_SENT")

class StageGates(unittest.TestCase):
    def test_wa_three_stages(self):
        r=validate([lead()],as_of=TODAY)
        self.assertEqual(r["counts"]["WA"]["send_ready"],1)
        self.assertEqual(r["shortfall_send_ready"]["WA"],14)
    def test_tg_and_fb_accepted(self):
        for ch in ("TG","FB"):
            self.assertEqual(validate([lead(ch=ch)],as_of=TODAY)["counts"][ch]["send_ready"],1)
    def test_fb_page_only_fails(self):
        x=lead("FB"); x["fb_route_type"]="FB_PAGE_ONLY"
        self.assertEqual(validate([x],as_of=TODAY)["counts"]["FB"]["send_ready"],0)
    def test_png_failure_does_not_reset_icp(self):
        x=lead(); x["image_url"]=""; x["image_status"]="PENDING"
        d=validate([x],as_of=TODAY)["counts"]["WA"]
        self.assertEqual((d["icp_pass"],d["asset_ready"],d["send_ready"]),(1,0,0))
    def test_three_retail_research_only(self):
        for v in ("wine","vape","adult"):
            x=lead(seg="REGULATED_RETAIL_TEST",vertical=v)
            r=validate([x],as_of=TODAY)
            self.assertEqual(r["retail"][v]["icp_pass"],1)
            self.assertEqual(r["retail"][v]["send_ready"],0)
            x["regulatory_compliance_status"]="PASS"
            self.assertEqual(validate([x],as_of=TODAY)["retail"][v]["send_ready"],1)
    def test_duplicate_across_channels(self):
        r=validate([lead(),lead("TG")],as_of=TODAY)
        self.assertEqual(r["counts"]["TG"]["icp_pass"],0)
    def test_unverified_ai_claim(self):
        x=lead();x["ai_gap_claimed"]=True
        self.assertEqual(validate([x],as_of=TODAY)["counts"]["WA"]["asset_ready"],0)
    def test_partial_history(self):
        x=lead();x["checked_sources"]=["103_MASTER"]
        self.assertEqual(validate([x],as_of=TODAY)["counts"]["WA"]["icp_pass"],0)
    def test_backup_excluded_from_primary(self):
        x=lead("FB");x["slot"]="BACKUP"
        r=validate([x],as_of=TODAY)
        self.assertEqual(r["fb_backup_count"],1)
        self.assertEqual(r["counts"]["FB"]["send_ready"],0)

if __name__=="__main__":
    unittest.main()
