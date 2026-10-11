import unittest

from prospect_os.intent_signals import (
    IntentEvent,
    events_from_payloads,
    normalize_external_event,
    score_events,
)


class IntentSignalTests(unittest.TestCase):
    def test_public_activity_cannot_become_direct_reply(self) -> None:
        result = score_events([
            IntentEvent("public_activity_recent", "agent_reach"),
            IntentEvent("public_reply", "agent_reach"),
        ])
        self.assertEqual(result["reply_ground_truth"], "not_observed")
        self.assertEqual(result["reply_state"], "publicly_active_only")
        self.assertLessEqual(result["reply_willingness_score"], 45)
        self.assertIn("没有真实直接回复", " ".join(result["warnings"]))

    def test_chatwoot_incoming_message_is_direct_reply(self) -> None:
        events = normalize_external_event("chatwoot", {
            "event": "message_created",
            "message_type": "incoming",
            "company_key": "shop-1",
        })
        self.assertEqual([event.event_type for event in events], ["direct_reply"])
        result = score_events(events)
        self.assertEqual(result["reply_ground_truth"], "observed_direct_reply")
        self.assertEqual(result["reply_state"], "direct_replied")

    def test_price_question_is_reply_and_purchase_signal(self) -> None:
        result = score_events([
            IntentEvent("asked_price", "chatwoot"),
        ])
        self.assertEqual(result["reply_state"], "commercial_reply")
        self.assertEqual(result["purchase_state"], "commercial_interest")
        self.assertGreater(result["purchase_intent_score"], 0)

    def test_payment_is_the_only_positive_ground_truth_for_purchase(self) -> None:
        weak = score_events([IntentEvent("pricing_page_view", "posthog")])
        paid = score_events([IntentEvent("paid", "wallet_monitor")])
        self.assertEqual(weak["purchase_ground_truth"], "not_observed")
        self.assertEqual(paid["purchase_ground_truth"], "observed_payment")
        self.assertEqual(paid["purchase_intent_score"], 100)

    def test_unknown_external_events_are_dropped(self) -> None:
        events = events_from_payloads([{"event": "unknown_magic"}], "posthog")
        self.assertEqual(events, [])

    def test_crypto_signal_is_not_usdt_proof(self) -> None:
        result = score_events([IntentEvent("public_crypto_signal", "agent_reach")])
        self.assertIn("不是 USDT 接受证明", " ".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
