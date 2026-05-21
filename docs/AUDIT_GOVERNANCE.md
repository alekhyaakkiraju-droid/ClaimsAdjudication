# Audit governance (WO-015)

## Module: `claim/audit_governance.py`

Central helpers for significant claim operations:

| Function | Purpose |
|----------|---------|
| `mask_payload` / `mask_sensitive_value` | Redact PII and large payloads in logs |
| `record_claim_audit_event` | Structured `claim.audit` log (actor, timestamp, claim ref, operation) |
| `record_mutation_audit` | Map GraphQL mutation class → operation |
| `operation_for_status_change` | Feedback/review status transitions |
| `MUTATION_OPERATION_MAP` | Documented mutation → operation coverage |

## Covered operations

- **Create / update / restore** — `CreateClaimMutation`, `UpdateClaimMutation` (`save_history`, `audit_user_id`, `ClaimMutation` link via signals)
- **Submit** — `set_claim_submitted` + `SubmitClaimsMutation`
- **Process** — `ProcessClaimsMutation` (`save_history`, `audit_user_id_process`)
- **Feedback / review** — `set_claims_status` + deliver/save mutations
- **Delete** — `DeleteClaimsMutation`
- **Attachments** — create / update / delete mutations

## Logging policy

- Logger name: `claim.audit` (INFO for significant actions)
- Context fields matching PII markers (`chf_id`, `document`, `phone`, etc.) are masked
- Unexpected exception details are not written to client responses (see `api_errors.mutation_error_list`)

## Retention

Audit DB fields (`audit_user_id*`, `save_history`, `ClaimMutation`) follow openIMIS core retention; configure log retention at the deployment layer (out of scope for this module).

## Verification

```bash
python -m flake8 claim/audit_governance.py claim/tests/test_audit_governance.py
python manage.py test claim.tests.test_audit_governance --settings=core.test_settings
```
