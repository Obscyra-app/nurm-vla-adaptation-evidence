#!/usr/bin/env python3
"""Dependency-free checks for a NURM VLA public result card."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
from pathlib import Path
from typing import Any


ROOT_FIELDS = {
    "schema",
    "status",
    "title",
    "model",
    "data",
    "comparison",
    "adapter_audit",
    "metrics",
    "claims",
    "disclosure",
}

MODEL_FIELDS = {"repo_id", "revision", "license", "parameter_class"}
DATA_FIELDS = {
    "source",
    "license",
    "public_disclosure_allowed",
    "permission_basis",
    "permission_reference",
    "heldout_unit",
    "train_units",
    "evaluation_units",
}
COMPARISON_FIELDS = {
    "base_arm",
    "candidate_arm",
    "same_base",
    "same_inputs",
    "same_seeds",
    "same_sampling",
    "only_intended_difference",
}
AUDIT_FIELDS = {
    "trainable_fraction",
    "trainables_outside_adapter",
    "visual_encoder_frozen",
    "action_expert_frozen",
    "save_reload_verified",
}
METRIC_FIELDS = {
    "name",
    "direction",
    "base",
    "candidate",
    "delta",
    "ci95",
    "ci_method",
    "paired",
    "cluster_unit",
    "unit",
    "scale_owner",
}
CLAIM_FIELDS = {"official_benchmark", "road_safety", "closed_loop_driving", "state_of_the_art"}
DISCLOSURE_FIELDS = {
    "contains_dataset_bytes",
    "contains_raw_outputs",
    "contains_event_identifiers",
    "contains_prompts_or_gold",
    "contains_adapter_weights",
}

FORBIDDEN_KEYS = {
    "clip_id",
    "event_id",
    "task_id",
    "prompt",
    "gold",
    "raw_output",
    "prediction",
    "adapter_sha256",
    "r2_url",
    "training_rows",
}

PRIVATE_VALUE_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])(?:clip_id|event_id|task_id|raw_output|prompt|gold)(?:$|[^a-z0-9])", re.I),
    re.compile(r"r2://|/workspace/|/users/|x-amz-", re.I),
    re.compile(r"(?:api[_-]?key|password|secret|token)\s*[:=]", re.I),
)

EXCLUDED_CLAIM_PATTERNS = (
    re.compile(r"\bofficial[ -]?benchmark\b", re.I),
    re.compile(r"\b(?:state[ -]?of[ -]?the[ -]?art|sota)\b", re.I),
    re.compile(r"\broad[ -]?(?:ready|safe)\b", re.I),
    re.compile(r"\bsafer driving\b", re.I),
    re.compile(r"\bimproved autonomous driving\b", re.I),
    re.compile(r"\bclosed[ -]?loop driving\b", re.I),
)

PUBLIC_PERMISSION_RE = re.compile(r"^(https://[^\s]+|urn:[A-Za-z0-9][A-Za-z0-9:._/-]+)$")

MAX_RESULT_CARD_BYTES = 1_000_000
MAX_METRIC_ABS = Decimal("1e12")
MIN_NONZERO_METRIC_ABS = Decimal("1e-12")
MAX_SIGNIFICANT_DIGITS = 64
MAX_ABS_DECIMAL_EXPONENT = 64
MAX_NESTING_DEPTH = 128


def _walk(value: Any, errors: list[str], path: str = "$") -> None:
    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    while stack:
        current, current_path, depth = stack.pop()
        if depth > MAX_NESTING_DEPTH:
            errors.append(f"nesting depth exceeds {MAX_NESTING_DEPTH} at {current_path}")
            continue
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f"{current_path}.{key}"
                if key.lower() in FORBIDDEN_KEYS:
                    errors.append(f"forbidden key at {child_path}")
                stack.append((child, child_path, depth + 1))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                stack.append((child, f"{current_path}[{index}]", depth + 1))
        elif isinstance(current, str):
            normalized = unicodedata.normalize("NFKC", current)
            if normalized != current:
                errors.append(f"string is not NFKC-normalized at {current_path}")
            if current != current.strip():
                errors.append(f"leading or trailing whitespace at {current_path}")
            if any(unicodedata.category(character) in {"Cc", "Cf"} for character in normalized):
                errors.append(f"control or invisible formatting character at {current_path}")
            for pattern in PRIVATE_VALUE_PATTERNS:
                if pattern.search(normalized):
                    errors.append(f"private-content pattern in string at {current_path}")
                    break
            for pattern in EXCLUDED_CLAIM_PATTERNS:
                if pattern.search(normalized):
                    errors.append(f"excluded claim language in string at {current_path}")
                    break
        elif (
            _finite_decimal(current) is None
            and isinstance(current, (int, float, Decimal))
            and not isinstance(current, bool)
        ):
            errors.append(f"invalid numeric value at {current_path}")


def _exact_fields(value: Any, expected: set[str], path: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return False
    if set(value) != expected:
        errors.append(f"{path} fields differ from the v1 allowlist")
        return False
    return True


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, InvalidOperation, OverflowError, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def _number_to_decimal(value: Any) -> Decimal | None:
    number = _finite_decimal(value)
    if number is None:
        return None
    number_tuple = number.as_tuple()
    if len(number_tuple.digits) > MAX_SIGNIFICANT_DIGITS:
        return None
    if abs(number_tuple.exponent) > MAX_ABS_DECIMAL_EXPONENT:
        return None
    magnitude = number.copy_abs()
    if magnitude > MAX_METRIC_ABS:
        return None
    if magnitude != 0 and magnitude < MIN_NONZERO_METRIC_ABS:
        return None
    return number


def _exact_difference(candidate: Decimal, base: Decimal) -> Decimal | None:
    """Subtract bounded Decimal inputs without the process-global precision."""

    with localcontext() as context:
        context.prec = MAX_SIGNIFICANT_DIGITS + (2 * MAX_ABS_DECIMAL_EXPONENT) + 8
        context.Emax = (2 * MAX_ABS_DECIMAL_EXPONENT) + 8
        context.Emin = -context.Emax
        try:
            return candidate - base
        except DecimalException:
            return None


def _finite_number(value: Any) -> bool:
    return _number_to_decimal(value) is not None


def validate(card: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(card, dict):
        return ["root must be an object"]
    if set(card) != ROOT_FIELDS:
        errors.append("root fields differ from the v1 allowlist")
    if card.get("schema") != "nurm.vla-public-result-card.v1":
        errors.append("unexpected schema")
    status = card.get("status")
    if not isinstance(status, str) or status not in {"SYNTHETIC_DEMO", "PUBLIC_RESULT"}:
        errors.append("unexpected status")

    if not _nonempty_string(card.get("title")) or len(card["title"]) > 160:
        errors.append("title must contain 1 to 160 characters")

    model = card.get("model")
    if _exact_fields(model, MODEL_FIELDS, "model", errors):
        for field in MODEL_FIELDS:
            if not _nonempty_string(model[field]):
                errors.append(f"model.{field} must be non-empty")

    data = card.get("data")
    if _exact_fields(data, DATA_FIELDS, "data", errors):
        if data.get("public_disclosure_allowed") is not True:
            errors.append("public_disclosure_allowed must be true")
        for field in ("source", "license", "heldout_unit"):
            if not _nonempty_string(data.get(field)):
                errors.append(f"data.{field} must be non-empty")
        for field in ("permission_basis", "permission_reference"):
            if not _nonempty_string(data.get(field)):
                errors.append(f"data.{field} must be non-empty")
        if isinstance(data.get("permission_basis"), str) and len(data["permission_basis"]) < 8:
            errors.append("data.permission_basis must contain at least 8 characters")
        for field in ("train_units", "evaluation_units"):
            value = data.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(f"data.{field} must be a positive integer")
        permission_reference = data.get("permission_reference")
        if card.get("status") == "PUBLIC_RESULT" and (
            not isinstance(permission_reference, str)
            or PUBLIC_PERMISSION_RE.fullmatch(permission_reference) is None
        ):
            errors.append("PUBLIC_RESULT permission_reference must be an https URL or URN")
        if card.get("status") == "SYNTHETIC_DEMO" and data.get("permission_reference") != "SYNTHETIC_FIXTURE":
            errors.append("SYNTHETIC_DEMO must use the synthetic permission reference")

    comparison = card.get("comparison")
    if _exact_fields(comparison, COMPARISON_FIELDS, "comparison", errors):
        for field in ("base_arm", "candidate_arm"):
            if not _nonempty_string(comparison.get(field)):
                errors.append(f"comparison.{field} must be non-empty")
        for field in ("same_base", "same_inputs", "same_seeds", "same_sampling"):
            if comparison.get(field) is not True:
                errors.append(f"comparison.{field} must be true")
        if comparison.get("only_intended_difference") != "adapter":
            errors.append("only_intended_difference must be adapter")

    audit = card.get("adapter_audit")
    if _exact_fields(audit, AUDIT_FIELDS, "adapter_audit", errors):
        outside = audit.get("trainables_outside_adapter")
        if not isinstance(outside, int) or isinstance(outside, bool) or outside != 0:
            errors.append("trainables_outside_adapter must be zero")
        if audit.get("save_reload_verified") is not True:
            errors.append("save_reload_verified must be true")
        for field in ("visual_encoder_frozen", "action_expert_frozen"):
            if not isinstance(audit.get(field), bool):
                errors.append(f"adapter_audit.{field} must be boolean")
        fraction = audit.get("trainable_fraction")
        fraction_number = _finite_decimal(fraction)
        if fraction_number is None or not Decimal(0) <= fraction_number <= Decimal(1):
            errors.append("trainable_fraction must be between zero and one")

    metrics = card.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("metrics must be a non-empty list")
    else:
        names: set[str] = set()
        for index, metric in enumerate(metrics):
            if not _exact_fields(metric, METRIC_FIELDS, f"metrics[{index}]", errors):
                continue
            name = metric.get("name")
            if not _nonempty_string(name):
                errors.append(f"metrics[{index}].name must be non-empty")
            else:
                canonical_name = unicodedata.normalize("NFKC", name).strip().casefold()
                if canonical_name in names:
                    errors.append(f"duplicate metric name after normalization: {name}")
                else:
                    names.add(canonical_name)
            values = [metric.get(key) for key in ("base", "candidate", "delta")]
            if any(not _finite_number(v) for v in values):
                errors.append(f"metrics[{index}] contains invalid numeric values")
                continue
            direction = metric.get("direction")
            if not isinstance(direction, str) or direction not in {"higher_is_better", "lower_is_better"}:
                errors.append(f"metrics[{index}].direction is invalid")
            for field in ("ci_method", "cluster_unit", "unit", "scale_owner"):
                if not _nonempty_string(metric.get(field)):
                    errors.append(f"metrics[{index}].{field} must be non-empty")
            if metric.get("paired") is not True:
                errors.append(f"metrics[{index}].paired must be true")
            base = _number_to_decimal(metric["base"])
            candidate = _number_to_decimal(metric["candidate"])
            delta = _number_to_decimal(metric["delta"])
            assert base is not None and candidate is not None and delta is not None
            expected_delta = _exact_difference(candidate, base)
            if expected_delta is None or delta != expected_delta:
                errors.append(f"metrics[{index}].delta does not equal candidate - base")
            ci = metric.get("ci95")
            ci_values = [_number_to_decimal(value) for value in ci] if isinstance(ci, list) and len(ci) == 2 else []
            if len(ci_values) != 2 or any(value is None for value in ci_values):
                errors.append(f"metrics[{index}].ci95 must contain two finite numbers")
            elif not ci_values[0] <= delta <= ci_values[1]:
                errors.append(f"metrics[{index}].ci95 must contain the delta")

    claims = card.get("claims")
    if _exact_fields(claims, CLAIM_FIELDS, "claims", errors):
        if any(value is not False for value in claims.values()):
            errors.append("all excluded claim flags must be false")
    disclosure = card.get("disclosure")
    if _exact_fields(disclosure, DISCLOSURE_FIELDS, "disclosure", errors):
        if any(value is not False for value in disclosure.values()):
            errors.append("all prohibited-content flags must be false")

    _walk(card, errors)
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify.py RESULT_CARD.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if path.is_symlink() or not path.is_file():
        print("RED: result card must be a regular file", file=sys.stderr)
        return 1
    try:
        if path.stat().st_size > MAX_RESULT_CARD_BYTES:
            print("RED: result card exceeds the 1 MB size limit", file=sys.stderr)
            return 1
    except OSError as exc:
        print(f"RED: cannot inspect result card: {exc}", file=sys.stderr)
        return 1
    try:
        def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate key: {key}")
                result[key] = value
            return result

        card = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicates,
            parse_float=Decimal,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, RecursionError, ValueError, json.JSONDecodeError) as exc:
        print(f"RED: invalid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        errors = validate(card)
    except RecursionError as exc:
        print(f"RED: result card exceeds structural limits: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"RED: {error}", file=sys.stderr)
        return 1
    if card["status"] == "PUBLIC_RESULT":
        print("GREEN: structurally valid public result card (PUBLIC_RESULT); permission is publisher-attested, not independently verified")
    else:
        print("GREEN: valid public result card (SYNTHETIC_DEMO)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
