from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import verify


FIXTURE = Path(__file__).parents[1] / "examples" / "SYNTHETIC_RESULT_CARD.json"


class ResultCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_green(self) -> None:
        self.assertEqual(verify.validate(self.card), [])

    def test_mismatched_inputs_are_red(self) -> None:
        card = copy.deepcopy(self.card)
        card["comparison"]["same_inputs"] = False
        self.assertIn("comparison.same_inputs must be true", verify.validate(card))

    def test_metric_arithmetic_is_recomputed(self) -> None:
        card = copy.deepcopy(self.card)
        card["metrics"][0]["delta"] = 0.08
        self.assertTrue(any("candidate - base" in error for error in verify.validate(card)))

    def test_permission_is_required(self) -> None:
        card = copy.deepcopy(self.card)
        card["data"]["public_disclosure_allowed"] = False
        self.assertIn("public_disclosure_allowed must be true", verify.validate(card))

    def test_private_row_key_is_rejected(self) -> None:
        card = copy.deepcopy(self.card)
        card["metrics"][0]["event_id"] = "private"
        errors = verify.validate(card)
        self.assertTrue(any("forbidden key" in error for error in errors))
        self.assertTrue(any("allowlist" in error for error in errors))

    def test_empty_claim_object_is_rejected(self) -> None:
        card = copy.deepcopy(self.card)
        card["claims"] = {}
        self.assertTrue(any("claims fields" in error for error in verify.validate(card)))

    def test_public_result_cannot_reuse_synthetic_permission(self) -> None:
        card = copy.deepcopy(self.card)
        card["status"] = "PUBLIC_RESULT"
        self.assertTrue(any("https URL or URN" in error for error in verify.validate(card)))

    def test_boolean_is_not_zero_trainables(self) -> None:
        card = copy.deepcopy(self.card)
        card["adapter_audit"]["trainables_outside_adapter"] = False
        self.assertIn("trainables_outside_adapter must be zero", verify.validate(card))

    def test_large_integer_arithmetic_keeps_precision(self) -> None:
        card = copy.deepcopy(self.card)
        card["metrics"][0].update(
            base=9007199254740992,
            candidate=9007199254740993,
            delta=0,
            ci95=[0, 0],
        )
        self.assertTrue(verify.validate(card))

    def test_huge_integer_does_not_crash(self) -> None:
        card = copy.deepcopy(self.card)
        card["metrics"][0].update(base=10**10000, candidate=10**10000 + 1, delta=0, ci95=[0, 0])
        self.assertTrue(verify.validate(card))

    def test_decimal_context_rounding_is_red(self) -> None:
        card = copy.deepcopy(self.card)
        card["metrics"][0].update(
            base=0,
            candidate=123456789012345678901234567890,
            delta=123456789012345678901234567900,
            ci95=[123456789012345678901234567900] * 2,
        )
        self.assertTrue(verify.validate(card))

    def test_extreme_decimal_exponents_are_red_without_crashing(self) -> None:
        for value in (Decimal("1e1000000"), Decimal("1e-10000000")):
            with self.subTest(value=value):
                card = copy.deepcopy(self.card)
                card["metrics"][0].update(base=0, candidate=value, delta=0, ci95=[0, 0])
                self.assertTrue(verify.validate(card))

    def test_non_metric_numbers_follow_the_schema_range(self) -> None:
        card = copy.deepcopy(self.card)
        card["adapter_audit"]["trainable_fraction"] = 1e-13
        card["data"]["train_units"] = 10**13
        self.assertEqual(verify.validate(card), [])

    def test_non_string_status_is_red_without_crashing(self) -> None:
        card = copy.deepcopy(self.card)
        card["status"] = []
        self.assertIn("unexpected status", verify.validate(card))

    def test_non_string_direction_is_red_without_crashing(self) -> None:
        card = copy.deepcopy(self.card)
        card["metrics"][0]["direction"] = []
        self.assertTrue(any("direction is invalid" in error for error in verify.validate(card)))

    def test_cli_reports_red_for_extreme_exponent(self) -> None:
        payload = FIXTURE.read_text(encoding="utf-8").replace('"base": 0.42', '"base": 1e1000000')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "card.json"
            path.write_text(payload, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(verify.__file__)), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("RED:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_reports_red_for_deep_nesting(self) -> None:
        payload = '{"a":' * 1200 + '0' + '}' * 1200
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep.json"
            path.write_text(payload, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(verify.__file__)), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("RED:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_private_identifier_hidden_in_string_is_rejected(self) -> None:
        card = copy.deepcopy(self.card)
        card["title"] = "Public report for event_id private-123"
        self.assertTrue(any("private-content pattern" in error for error in verify.validate(card)))

    def test_excluded_claim_hidden_in_title_is_rejected(self) -> None:
        card = copy.deepcopy(self.card)
        card["title"] = "Official benchmark and road-ready result"
        self.assertTrue(any("excluded claim language" in error for error in verify.validate(card)))

    def test_public_result_requires_reference_shape(self) -> None:
        card = copy.deepcopy(self.card)
        card["status"] = "PUBLIC_RESULT"
        card["data"]["permission_reference"] = "looks-valid-but-is-not"
        self.assertTrue(any("https URL or URN" in error for error in verify.validate(card)))

    def test_metric_names_are_unique_after_normalization(self) -> None:
        card = copy.deepcopy(self.card)
        duplicate = copy.deepcopy(card["metrics"][0])
        duplicate["name"] = " SYNTHETIC_SEMANTIC_SCORE "
        card["metrics"].append(duplicate)
        errors = verify.validate(card)
        self.assertTrue(any("duplicate metric name after normalization" in error for error in errors))

    def test_invisible_permission_reference_is_rejected(self) -> None:
        card = copy.deepcopy(self.card)
        card["status"] = "PUBLIC_RESULT"
        card["data"]["permission_reference"] = "\u200b"
        errors = verify.validate(card)
        self.assertTrue(any("https URL or URN" in error for error in errors))
        self.assertTrue(any("invisible formatting" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
