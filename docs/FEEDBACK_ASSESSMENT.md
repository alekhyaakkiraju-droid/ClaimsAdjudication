# Feedback assessment field (WO-032)

Corrects the misspelled `asessment` Python field to `assessment` while preserving the legacy SQL Server column `Asessment`.

## Model

- Field: `Feedback.assessment` → `db_column="Asessment"`
- Deprecated Python alias: `feedback.asessment` property (getter/setter)

## GraphQL

- Input: `assessment` (preferred) and deprecated `asessment`
- Output: `FeedbackGQLType.assessment` plus deprecated `asessment` resolver alias
- `normalize_feedback_input()` maps legacy mutation payloads

## Migration

- `0038_rename_feedback_asessment_to_assessment` — Django state rename only; no DB column change

## Tests

- `claim/tests/test_feedback_assessment.py`
