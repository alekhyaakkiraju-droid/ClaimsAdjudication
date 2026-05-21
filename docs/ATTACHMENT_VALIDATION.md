# Attachment validation (WO-013)

Upload paths validate attachments in **`claim/attachment_validation.py`** before base64 decode or filesystem writes.

## Configuration (`ModuleConfiguration` / `ClaimConfig`)

| Key | Default | Purpose |
|-----|---------|---------|
| `attachment_validation_enabled` | `true` | Master switch (respects `default_validations_disabled`) |
| `attachment_max_size_bytes` | `10485760` (10 MiB) | Max decoded payload size |
| `attachment_allowed_mime_types` | pdf, jpeg, png, gif, plain text | MIME allowlist |
| `allowed_domains_attachments` | `[]` | URL host allowlist (netloc); empty = no restriction |

## Validation rules

| Check | Error code |
|-------|------------|
| MIME not in allowlist | `attachment_mime_not_allowed` |
| Filename extension vs MIME mismatch | `attachment_extension_mismatch` |
| Decoded size over limit (pre-decode estimate) | `attachment_size_exceeded` |
| Invalid base64 | `attachment_invalid_base64` |
| URL host not allowed | `attachment_url_domain_not_allowed` |
| Non http(s) URL | `attachment_url_scheme_not_allowed` |

## Integration points

- `create_attachment` / `create_attachments` (GraphQL create claim & attachment mutations)
- `UpdateAttachmentMutation.async_mutate`
- URL domain checks use **hostname** (`urlparse().netloc`), not path fragments

## Local check

```bash
python -m pytest claim/tests/test_attachment_validation.py  # if pytest available
python -m unittest claim.tests.test_attachment_validation
```
