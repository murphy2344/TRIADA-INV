import unittest

try:
    from modules import critic
except ModuleNotFoundError as exc:
    if exc.name in {"requests", "groq"}:
        raise unittest.SkipTest(f"Critic dependencies are not installed: {exc.name}")
    raise


class CriticJsonContractTests(unittest.TestCase):
    def test_valid_json_is_normalized(self):
        result = critic._parse_critic_result(
            '{"agree": true, "critic_recommendation": "LONG", "critic_note": "Risk remains."}'
        )
        self.assertEqual(result, {
            "agree": True,
            "critic_recommendation": "long",
            "critic_note": "Risk remains.",
        })

    def test_fenced_json_with_leading_text_is_parsed(self):
        result = critic._parse_critic_result(
            'Result:\n```json\n{"agree": false, "critic_recommendation": "neutral", "critic_note": "Wait for data."}\n```'
        )
        self.assertFalse(result["agree"])
        self.assertEqual(result["critic_recommendation"], "neutral")

    def test_non_object_json_is_rejected(self):
        with self.assertRaises(ValueError):
            critic._parse_critic_result('[{"agree": true}]')

    def test_invalid_recommendation_is_rejected(self):
        with self.assertRaises(ValueError):
            critic._parse_critic_result(
                '{"agree": true, "critic_recommendation": "buy", "critic_note": "Good."}'
            )

    def test_missing_note_is_rejected(self):
        with self.assertRaises(ValueError):
            critic._parse_critic_result(
                '{"agree": true, "critic_recommendation": "long"}'
            )


if __name__ == "__main__":
    unittest.main()
