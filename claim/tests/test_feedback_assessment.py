"""WO-032: Feedback assessment field alias tests."""

from django.test import SimpleTestCase

from claim.feedback_input import normalize_feedback_input


class FeedbackAssessmentAliasTest(SimpleTestCase):
    def test_normalize_maps_legacy_asessment_key(self):
        data = normalize_feedback_input({"asessment": 3, "care_rendered": True})
        self.assertEqual(data["assessment"], 3)
        self.assertNotIn("asessment", data)

    def test_assessment_takes_precedence_over_legacy_key(self):
        data = normalize_feedback_input({"asessment": 1, "assessment": 5})
        self.assertEqual(data["assessment"], 5)
        self.assertNotIn("asessment", data)

    def test_feedback_model_exposes_assessment_field_name(self):
        from claim.models import Feedback

        field = Feedback._meta.get_field("assessment")
        self.assertEqual(field.db_column, "Asessment")
