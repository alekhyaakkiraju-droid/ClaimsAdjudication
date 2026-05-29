"""
WO-021: Claim lifecycle state machine tests.
"""

from django.test import TestCase

from claim.models import Claim
from claim.services import set_claim_processed_or_valuated, set_claim_submitted
from claim.state_machine import (
    ClaimStatusTransitionError,
    apply_claim_status,
    can_transition,
    validate_transition,
)
from claim.test_helpers import (
    DummyUser,
    create_test_claim,
    delete_claim_with_itemsvc_dedrem_and_history,
    mark_test_claim_as_processed,
)


class ClaimStateMachineUnitTest(TestCase):
    def test_valid_transitions(self):
        self.assertTrue(can_transition(Claim.STATUS_ENTERED, Claim.STATUS_CHECKED))
        self.assertTrue(can_transition(Claim.STATUS_CHECKED, Claim.STATUS_VALUATED))
        self.assertTrue(can_transition(Claim.STATUS_CHECKED, Claim.STATUS_PROCESSED))
        self.assertTrue(can_transition(Claim.STATUS_ENTERED, Claim.STATUS_REJECTED))

    def test_invalid_transition_raises_structured_error(self):
        with self.assertRaises(ClaimStatusTransitionError) as ctx:
            validate_transition(Claim.STATUS_VALUATED, Claim.STATUS_CHECKED)
        self.assertIn("valuated", str(ctx.exception).lower())
        self.assertIn("checked", str(ctx.exception).lower())

    def test_terminal_states_have_no_outgoing_transitions(self):
        for status in (
            Claim.STATUS_REJECTED,
            Claim.STATUS_PROCESSED,
            Claim.STATUS_VALUATED,
        ):
            self.assertFalse(can_transition(status, Claim.STATUS_ENTERED))


class ClaimStateMachineIntegrationTest(TestCase):
    def test_set_claim_submitted_uses_state_machine(self):
        claim = create_test_claim()
        mark_test_claim_as_processed(claim, status=Claim.STATUS_ENTERED)
        claim.status = Claim.STATUS_ENTERED
        claim.save()

        set_claim_submitted(claim, [], DummyUser())
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.STATUS_CHECKED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_invalid_direct_status_assignment_blocked_by_helper(self):
        claim = create_test_claim()
        mark_test_claim_as_processed(claim, status=Claim.STATUS_VALUATED)
        claim.status = Claim.STATUS_VALUATED
        claim.save()

        with self.assertRaises(ClaimStatusTransitionError):
            apply_claim_status(claim, Claim.STATUS_CHECKED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_processing_rejection_routes_through_state_machine(self):
        claim = create_test_claim()
        mark_test_claim_as_processed(claim, status=Claim.STATUS_CHECKED)

        set_claim_processed_or_valuated(
            claim, [{"message": "forced failure"}], DummyUser()
        )
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.STATUS_REJECTED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)
