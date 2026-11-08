import unittest

from finops_copilot.plan import QueryPlan, ValidationError


VALID_PLAN = {
    "metric": "amortized_cost",
    "start_date": "2026-09-01",
    "end_date": "2026-10-01",
    "group_by": ["service", "environment"],
    "filters": [{"field": "team", "operator": "eq", "value": "data-platform"}],
    "limit": 10,
}


class QueryPlanTests(unittest.TestCase):
    def test_valid_plan_is_normalized(self) -> None:
        plan = QueryPlan.from_mapping(VALID_PLAN)
        self.assertEqual(plan.metric, "amortized_cost")
        self.assertEqual(plan.group_by, ("service", "environment"))
        self.assertEqual(plan.filters[0].values, ("data-platform",))

    def test_unknown_root_key_is_rejected(self) -> None:
        value = {**VALID_PLAN, "sql": "DROP TABLE anything"}
        with self.assertRaisesRegex(ValidationError, "Unknown query-plan keys"):
            QueryPlan.from_mapping(value)

    def test_unknown_metric_is_rejected(self) -> None:
        value = {**VALID_PLAN, "metric": "credits_after_tax"}
        with self.assertRaisesRegex(ValidationError, "Unsupported metric"):
            QueryPlan.from_mapping(value)

    def test_reverse_date_range_is_rejected(self) -> None:
        value = {
            **VALID_PLAN,
            "start_date": "2026-10-01",
            "end_date": "2026-09-01",
        }
        with self.assertRaisesRegex(ValidationError, "end_date"):
            QueryPlan.from_mapping(value)

    def test_empty_exclusive_date_range_is_rejected(self) -> None:
        value = {
            **VALID_PLAN,
            "start_date": "2026-09-01",
            "end_date": "2026-09-01",
        }
        with self.assertRaisesRegex(ValidationError, "exclusive"):
            QueryPlan.from_mapping(value)

    def test_too_large_limit_is_rejected(self) -> None:
        value = {**VALID_PLAN, "limit": 1000}
        with self.assertRaisesRegex(ValidationError, "limit"):
            QueryPlan.from_mapping(value)

    def test_arbitrary_filter_field_is_rejected(self) -> None:
        value = {
            **VALID_PLAN,
            "filters": [
                {"field": "resource_id", "operator": "eq", "value": "secret"}
            ],
        }
        with self.assertRaisesRegex(ValidationError, "Unsupported filter field"):
            QueryPlan.from_mapping(value)


if __name__ == "__main__":
    unittest.main()
