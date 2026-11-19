import unittest
from prospect_os.outreach_humanizer import (
    build_conversation_prompt, humanizer_issues, review_conversation_copy,
)


class HumanizerTest(unittest.TestCase):
    def test_old_copy_is_blocked(self):
        self.assertTrue(humanizer_issues(
            "I'm researching how teams find providers. I prepared a short GEO study card."
        ))
        self.assertTrue(humanizer_issues("Would one example buyer-search check be useful?"))

    def test_warm_reply_without_question(self):
        self.assertEqual(review_conversation_copy(
            "Here's the screenshot. I searched for contract audits. The results are in the image.",
            stage="permission_received", evidence_ready=True, attachment_attached=True
        ), [])

    def test_dont_ask_again(self):
        self.assertIn("conversation:permission_already_granted", review_conversation_copy(
            "Would you like me to share the results?", stage="permission_received"
        ))

    def test_unverified_results_and_attachment(self):
        self.assertIn("conversation:unverified_result", review_conversation_copy(
            "I found a gap.", stage="sample_delivery"
        ))
        self.assertIn("conversation:attachment_not_attached", review_conversation_copy(
            "Here's the screenshot.", stage="sample_delivery"
        ))

    def test_opt_out_and_question_limits(self):
        self.assertIn("conversation:stop_outreach", review_conversation_copy(
            "One more thing.", stage="opt_out"
        ))
        self.assertIn("conversation:question_count", review_conversation_copy(
            "Interested? Can we talk?", stage="followup"
        ))

    def test_prompt_uses_humanizer_and_stage(self):
        prompt = build_conversation_prompt(channel="telegram", stage="permission_received",
                                           last_customer_message="Please share", facts=[])
        self.assertIn("Humanizer v4.0", prompt["prompt"])
        self.assertIn("chinese_translation", prompt["prompt"])
        self.assertEqual(prompt["context"]["stage"], "permission_received")


if __name__ == "__main__":
    unittest.main()
