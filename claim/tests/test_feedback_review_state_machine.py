"""
WO-022: Feedback and review sub-workflow state machine tests.
"""

from django.test import TestCase

from claim.feedback_review_state_machine import (
    FeedbackReviewStatusTransitionError,
    apply_feedback_status,
    apply_review_status,
    can_transition_feedback,
    can_transition_review,
    validate_feedback_transition,
    validate_review_transition,
)
from claim.models import Claim
from claim.services import set_claims_status
from claim.test_helpers import (
    create_test_claim,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.test_helpers import create_test_officer
from insuree.test_helpers import create_test_insuree


class FeedbackReviewStateMachineUnitTest(TestCase):
    def test_feedback_valid_transitions(self):
        self.assertTrue(
            can_transition_feedback(Claim.FEEDBACK_IDLE, Claim.FEEDBACK_SELECTED)
        )
        self.assertTrue(
            can_transition_feedback(Claim.FEEDBACK_SELECTED, Claim.FEEDBACK_DELIVERED)
        )
        self.assertTrue(
            can_transition_feedback(Claim.FEEDBACK_SELECTED, Claim.FEEDBACK_BYPASSED)
        )

    def test_review_valid_transitions(self):
        self.assertTrue(can_transition_review(Claim.REVIEW_IDLE, Claim.REVIEW_SELECTED))
        self.assertTrue(
            can_transition_review(Claim.REVIEW_SELECTED, Claim.REVIEW_DELIVERED)
        )
        self.assertTrue(
            can_transition_review(Claim.REVIEW_SELECTED, Claim.REVIEW_BYPASSED)
        )

    def test_feedback_invalid_transition_raises_structured_error(self):
        with self.assertRaises(FeedbackReviewStatusTransitionError) as ctx:
            validate_feedback_transition(
                Claim.FEEDBACK_DELIVERED, Claim.FEEDBACK_SELECTED
            )
        self.assertIn("feedback_status", str(ctx.exception))
        self.assertIn("delivered", str(ctx.exception).lower())

    def test_review_invalid_transition_raises_structured_error(self):
        with self.assertRaises(FeedbackReviewStatusTransitionError) as ctx:
            validate_review_transition(Claim.REVIEW_BYPASSED, Claim.REVIEW_SELECTED)
        self.assertIn("review_status", str(ctx.exception))
        self.assertIn("bypassed", str(ctx.exception).lower())

    def test_terminal_feedback_states_have_no_outgoing_transitions(self):
        for status in (Claim.FEEDBACK_DELIVERED, Claim.FEEDBACK_BYPASSED):
            self.assertFalse(
                can_transition_feedback(status, Claim.FEEDBACK_SELECTED)
            )

    def test_apply_helpers_assign_after_validation(self):
        claim = Claim(feedback_status=Claim.FEEDBACK_IDLE, review_status=Claim.REVIEW_IDLE)
        apply_feedback_status(claim, Claim.FEEDBACK_SELECTED)
        apply_review_status(claim, Claim.REVIEW_SELECTED)
        self.assertEqual(claim.feedback_status, Claim.FEEDBACK_SELECTED)
        self.assertEqual(claim.review_status, Claim.REVIEW_SELECTED)


class FeedbackReviewStateMachineIntegrationTest(TestCase):
    class DummyUser:
        id_for_audit = -1
        id = 1

    def test_set_claims_status_enforces_feedback_transitions(self):
        insuree = create_test_insuree()
        create_test_officer(
            villages=[insuree.current_village or insuree.family.location]
        )
        claim = create_test_claim(
            custom_props={
                "status": Claim.STATUS_CHECKED,
                "insuree": insuree,
                "feedback_status": Claim.FEEDBACK_DELIVERED,
            }
        )
        errors = set_claims_status(
            [claim.uuid],
            "feedback_status",
            Claim.FEEDBACK_SELECTED,
            user=self.DummyUser(),
        )
        self.assertTrue(errors)
        claim.refresh_from_db()
        self.assertEqual(claim.feedback_status, Claim.FEEDBACK_DELIVERED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_set_claims_status_allows_review_delivery(self):
        claim = create_test_claim(
            custom_props={
                "status": Claim.STATUS_CHECKED,
                "review_status": Claim.REVIEW_SELECTED,
            }
        )
        errors = set_claims_status(
            [claim.uuid],
            "review_status",
            Claim.REVIEW_DELIVERED,
            {"audit_user_id_review": self.DummyUser().id_for_audit},
        )
        self.assertEqual(errors, [])
        claim.refresh_from_db()
        self.assertEqual(claim.review_status, Claim.REVIEW_DELIVERED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)
