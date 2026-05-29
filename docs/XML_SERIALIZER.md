# XML serializer (WO-030)

Dedicated XML serialization for claim phone submission, extracted from the service layer.

## Module layout

| Concern | Module |
|---------|--------|
| XML helper classes | `claim/serializers/xml_serializer.py` |
| Package re-exports | `claim/serializers/__init__.py` |
| Backward-compatible shim | `claim/services/xml_submit.py` |

## Backward compatibility

- `from claim.services import ClaimSubmit, ClaimItemSubmit, ...` — unchanged
- `claim.services.xml_submit` — re-exports from `claim.serializers.xml_serializer`

## Tests

- `claim/tests/test_xml_serializer.py` — import boundary checks
- `claim/tests/tests_services.py` — XML output regression tests (`to_xml()`)
