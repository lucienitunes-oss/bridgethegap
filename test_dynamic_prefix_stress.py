import unittest

from run_dynamic_prefix_stress import (
    dependency,
    exhaustive_outcomes,
    initial_state,
    make_scenario,
    reduced_outcomes,
    step,
    terminal_outcome,
)


class DynamicPrefixStressTests(unittest.TestCase):
    def test_failed_delivery_remains_pending_until_unblock_and_retry(self):
        scenario = make_scenario(seed=7, audit_count=0, initially_blocked=True, retry_deadline=8)
        state = initial_state(scenario)

        state = step(scenario, state, "dispatch")
        state = step(scenario, state, "deliver_first")
        self.assertEqual(state.slots[3], 1, "failed delivery must keep the message pending")
        self.assertEqual(state.slots[4], 1, "failed delivery must record the failed attempt")
        self.assertNotIn("retry_delivery", scenario.enabled(state))

        state = step(scenario, state, "unblock")
        self.assertIn("retry_delivery", scenario.enabled(state))
        state = step(scenario, state, "retry_delivery")
        self.assertEqual(state.slots[1], 1)
        self.assertEqual(state.slots[3], 0)

    def test_missed_deadline_is_observable_as_expiration(self):
        scenario = make_scenario(seed=8, audit_count=3, initially_blocked=True, retry_deadline=2)
        state = initial_state(scenario)
        for event in ("dispatch", "deliver_first", "audit0", "audit1", "audit2", "unblock"):
            state = step(scenario, state, event)
        outcome = terminal_outcome(scenario, state, frozenset())
        self.assertEqual(outcome.retry_status, "expired")
        self.assertEqual(outcome.pending, 1)

    def test_property_visible_dependency_is_stronger_than_storage_dependency(self):
        scenario = make_scenario(seed=9, audit_count=0, initially_blocked=False, retry_deadline=8)
        self.assertFalse(dependency(scenario.event("deliver_first"), scenario.event("policy_update"), scenario, mode="storage"))
        self.assertTrue(dependency(scenario.event("deliver_first"), scenario.event("policy_update"), scenario, mode="route_property"))

    def test_deadline_makes_time_advancing_events_dependent(self):
        scenario = make_scenario(seed=20261107, audit_count=3, initially_blocked=True, retry_deadline=4)
        self.assertTrue(dependency(scenario.event("audit0"), scenario.event("retry_delivery"), scenario, mode="route_property"))

    def test_route_property_reduction_matches_exhaustive_outcomes(self):
        scenario = make_scenario(seed=10, audit_count=2, initially_blocked=True, retry_deadline=7)
        exhaustive = exhaustive_outcomes(scenario)
        reduced = reduced_outcomes(scenario, mode="route_property")
        self.assertEqual(reduced.outcomes, exhaustive.outcomes)
        self.assertEqual(reduced.mismatches, 0)


if __name__ == "__main__":
    unittest.main()
