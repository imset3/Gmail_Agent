import unittest

from agent import AgentResult, RuleEngine, ScheduleAgent, count_results, extract_schedule_window


class AgentRuleTests(unittest.TestCase):
    def test_dummy_category_counts(self):
        results = [
            AgentResult(category="spam", confidence=0.9, reason=""),
            AgentResult(category="spam", confidence=0.9, reason=""),
            AgentResult(category="no_response", confidence=0.9, reason=""),
            AgentResult(category="no_response", confidence=0.9, reason=""),
            AgentResult(category="auto_reply", confidence=0.9, reason=""),
            AgentResult(category="decision_required", confidence=0.9, reason=""),
            AgentResult(category="decision_required", confidence=0.9, reason=""),
        ]
        counts = count_results(results)

        self.assertEqual(counts["spam"], 2)
        self.assertEqual(counts["no_response"], 2)
        self.assertEqual(counts["auto_reply"], 1)
        self.assertEqual(counts["decision_required"], 2)
        self.assertEqual(counts["schedule_update"], 0)

    def test_rule_engine_detects_auto_reply(self):
        hint = RuleEngine().classify_hint(
            {
                "sender_name": "박영희",
                "sender_email": "younghee@gmail.com",
                "subject": "오랜만이에요!",
                "body": "서울 올라오는데 시간 괜찮으면 밥 먹자.",
            }
        )

        self.assertEqual(hint["category"], "auto_reply")
        self.assertIn("밥 먹자", hint["proposed_reply"])

    def test_schedule_conflict_extraction(self):
        email = {
            "subject": "[긴급] 3차 회의 안건 상정",
            "body": "2026-05-29 15:00 ~ 2026-05-29 16:30 회의 가능 여부를 검토해 주세요.",
        }
        window = extract_schedule_window(email)

        self.assertEqual(window["from"], "2026-05-29 15:00")
        self.assertEqual(window["to"], "2026-05-29 16:30")

    def test_schedule_agent_detects_existing_conflict(self):
        result = AgentResult(
            category="decision_required",
            confidence=0.86,
            reason="",
            requires_user_decision=True,
            email={
                "subject": "[긴급] 3차 회의 안건 상정",
                "body": "2026-05-29 15:00 ~ 2026-05-29 16:30 회의 가능 여부를 검토해 주세요.",
            },
        )
        enriched = ScheduleAgent().enrich(result)

        self.assertEqual(enriched.schedule_action, "conflict")
        self.assertEqual(enriched.schedule_conflict["conflict"]["event_name"], "팀 스프린트 리뷰")


if __name__ == "__main__":
    unittest.main()
