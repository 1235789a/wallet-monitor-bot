from __future__ import annotations

import unittest

from prospect_os.outreach_copy import (
    EVIDENCE_PASS,
    PRELOCK_REVIEW,
    build_generation_prompt,
    language_for,
    review_candidate,
    review_and_select,
    validate_legacy_first_message,
)


def sample_record(*, status="PRELOCK_REVIEW", channel="whatsapp", country="Brazil"):
    route = "https://wa.me/5511999999999" if channel == "whatsapp" else "https://t.me/acme_owner"
    return {
        "company_name": "Acme AI",
        "country": country,
        "track": "track_a",
        "prelock_status": status,
        "channel": channel,
        "contact_url": route,
        "route_kind": "business_account" if channel == "telegram" else "",
        "evidence": [
            {"id": "service", "category": "service", "claim": "Acme builds AI agents for WhatsApp support",
             "status": "observed", "source_url": "https://acme.example/services", "checked_at": "2026-09-30"}
        ],
    }


def sem_review(**overrides):
    result = {key: True for key in (
        "grounded", "specific", "natural", "compressed", "single_cta",
        "low_friction", "not_salesy", "plain_language", "claim_safe",
    )}
    result.update(overrides)
    return result


def candidate(message=None, **overrides):
    result = {
        "language": "pt-BR",
        "message_mode": PRELOCK_REVIEW,
        "message": message or "Oi, aqui é [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Quer que eu teste uma busca real por esse serviço e te mande o que aparece?",
        "cta": "Quer que eu teste uma busca real por esse serviço e te mande o que aparece?",
        "personalization_fact": "Acme builds AI agents for WhatsApp support",
        "personalization_evidence_ids": ["service"],
        "factual_claims": [{"claim_type": "service", "claim": "Builds WhatsApp AI agents", "evidence_ids": ["service"]}],
        "buyer_query_used": None,
        "visibility_evidence_used": False,
        "semantic_review": sem_review(),
    }
    result.update(overrides)
    return result


class OutreachCopyTests(unittest.TestCase):
    def test_review_mode_rejects_competitor_gap_claim(self):
        row = sample_record()
        draft = candidate("Oi, aqui é [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Dois concorrentes aparecem antes de vocês nessa busca. Quer que eu envie a comparação?")
        checked = review_candidate(row, draft)
        self.assertEqual(checked["status"], "MESSAGE_REVIEW_REQUIRED")
        self.assertIn("review_mode_contains_visibility_or_competitor_claim", checked["issues"])

    def test_pass_mode_can_use_verified_buyer_query_and_comparison(self):
        row = sample_record(status="PRELOCK_PASS")
        row["buyer_queries"] = [{"query": "agente de IA para WhatsApp Brasil", "tested": True, "status": "observed"}]
        row["evidence"].extend([
            {"id": "query", "category": "buyer_query", "claim": "agente de IA para WhatsApp Brasil", "status": "observed", "source_url": "https://search.example/query", "checked_at": "2026-09-29"},
            {"id": "gap", "category": "visibility", "claim": "Two named providers were shown above Acme for the tested query", "status": "observed", "source_url": "https://search.example/result", "checked_at": "2026-09-29"},
        ])
        draft = candidate(
            "Oi, aqui é [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Testei agente de IA para WhatsApp Brasil e duas consultorias apareceram antes. Quer que eu envie a comparação?",
            message_mode=EVIDENCE_PASS,
            buyer_query_used="agente de IA para WhatsApp Brasil",
            visibility_evidence_used=True,
            cta="Quer que eu envie a comparação?",
            factual_claims=[
                {"claim_type": "service", "claim": "Builds WhatsApp AI agents", "evidence_ids": ["service"]},
                {"claim_type": "buyer_query", "claim": "Tested query", "evidence_ids": ["query"]},
                {"claim_type": "visibility_gap", "claim": "Two providers appeared above", "evidence_ids": ["gap"]},
            ],
        )
        checked = review_candidate(row, draft)
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual(checked["buyer_query_used"], "agente de IA para WhatsApp Brasil")

    def test_untested_query_cannot_be_used(self):
        row = sample_record(status="PRELOCK_PASS")
        row["buyer_queries"] = [{"query": "AI WhatsApp agent Brazil", "tested": False}]
        row["evidence"].append({"id": "gap", "category": "visibility", "status": "observed", "source_url": "https://search.example/result", "checked_at": "2026-09-29"})
        draft = candidate(
            "Oi, aqui é [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Quer que eu confira AI WhatsApp agent Brazil e te mande o resultado?",
            message_mode=EVIDENCE_PASS, buyer_query_used="AI WhatsApp agent Brazil",
            visibility_evidence_used=True,
            factual_claims=[{"claim_type": "service", "evidence_ids": ["service"]}],
        )
        self.assertIn("buyer_query_not_tested_or_not_allowed", review_candidate(row, draft)["issues"])

    def test_brazilian_prospect_uses_portuguese(self):
        row = sample_record()
        draft = candidate()
        checked = review_candidate(row, draft)
        self.assertEqual(language_for(row), "pt-BR")
        self.assertNotIn("message_language_does_not_match_market", checked["issues"])

    def test_whatsapp_copy_stays_in_normal_length_range(self):
        checked = review_candidate(sample_record(), candidate())
        self.assertGreaterEqual(checked["word_count"], 20)
        self.assertLessEqual(checked["word_count"], 60)
        self.assertEqual(checked["status"], "PASS")

    def test_multiple_ctas_are_rejected(self):
        draft = candidate("Oi, aqui é [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Quer que eu teste uma busca? Também posso marcar uma reunião?")
        checked = review_candidate(sample_record(), draft)
        self.assertEqual(checked["status"], "MESSAGE_REVIEW_REQUIRED")
        self.assertIn("expected_exactly_one_question_cta", checked["issues"])

    def test_generic_message_is_flagged(self):
        draft = candidate("Oi, aqui é [Your Name]. Vi que vocês oferecem soluções inovadoras. Quer que eu teste uma busca real e te mande o que aparece?",
                          cta="Quer que eu teste uma busca real e te mande o que aparece?",
                          personalization_fact="custom software services",
                          semantic_review=sem_review(specific=False))
        checked = review_candidate(sample_record(), draft)
        self.assertIn("semantic_review:specific", checked["issues"])
        self.assertIn("generic_personalization", checked["issues"])
        self.assertEqual(checked["status"], "REWRITE_ONCE")

    def test_plain_phone_is_not_whatsapp(self):
        row = sample_record()
        row["contact_url"] = "tel:+5511999999999"
        self.assertIn("WhatsApp needs an explicit WhatsApp direct URL", review_candidate(row, candidate())["issues"][0])

    def test_telegram_group_channel_or_bot_is_not_direct_message(self):
        row = sample_record(channel="telegram")
        row["contact_url"] = "https://t.me/s/acme_updates"
        self.assertIn("Telegram group, channel, invite, or share URL", review_candidate(row, candidate())["issues"][0])
        row["contact_url"] = "https://t.me/m/temporary-deep-link"
        self.assertIn("Telegram group, channel, invite, or share URL", review_candidate(row, candidate())["issues"][0])
        row["contact_url"] = "https://t.me/acme_bot"
        row["is_bot"] = True
        self.assertIn("Telegram bots", review_candidate(row, candidate())["issues"][0])

    def test_sender_name_stays_placeholder(self):
        draft = candidate("Oi, aqui é Daniel. Vi que a Acme AI cria agentes de IA para WhatsApp. Quer que eu teste uma busca real e te mande o resultado?")
        self.assertIn("transparent_sender_placeholder_missing", review_candidate(sample_record(), draft)["issues"])

    def test_placeholder_does_not_allow_a_fabricated_sender_name(self):
        msg = "Oi, aqui é Daniel [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Quer que eu teste uma busca real e te mande o resultado?"
        draft = candidate(msg, cta="Quer que eu teste uma busca real e te mande o resultado?")
        self.assertIn("sender_name_must_remain_a_placeholder", review_candidate(sample_record(), draft)["issues"])

    def test_message_cannot_pretend_to_be_a_customer(self):
        draft = candidate("Oi, aqui é [Your Name]. Como cliente, quero comprar da Acme AI. Quer que eu teste uma busca real e te mande o resultado?")
        self.assertIn("message_pretends_to_be_a_customer", review_candidate(sample_record(), draft)["issues"])

    def test_legacy_validator_treats_missing_prelock_as_review_mode(self):
        row = {"company_name": "Acme AI", "personalization_hook": "AI agents for WhatsApp"}
        text = "Hi, I'm [Your Name]. Saw your AI agents for WhatsApp. Your competitors are more visible for this service. Want me to send a comparison?"
        errors, _ = validate_legacy_first_message(row, text)
        self.assertTrue(any("PRELOCK_REVIEW" in error for error in errors))

    def test_review_generation_prompt_does_not_inject_suggested_query_as_tested(self):
        prompt = build_generation_prompt(sample_record())
        self.assertEqual(prompt["message_mode"], PRELOCK_REVIEW)
        self.assertEqual(prompt["context"]["tested_buyer_queries"], [])
        self.assertIn("Do not research", prompt["prompt"])

    def test_selector_returns_one_message_and_preserves_debug_variants(self):
        row = sample_record()
        picked = review_and_select(row, [candidate(), candidate("Oi, aqui é [Your Name]. Vi que a Acme AI cria agentes de IA para WhatsApp. Quer que eu teste uma busca real por esse serviço e te mande o que aparece?", personalization_fact="Acme builds AI agents for WhatsApp support")])
        self.assertIsNotNone(picked["outreach"]["recommended_first_message"])
        self.assertEqual(len(picked["outreach"]["message_candidates"]), 2)
        self.assertEqual(picked["outreach"]["message_quality"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
