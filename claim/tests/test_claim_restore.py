"""
WO-024: Claim restore validation and permission tests.
"""

from unittest import mock
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from claim.apps import ClaimConfig
from claim.claim_restore import (
    count_restores_for_source,
    validate_restore_request,
)
from claim.gql_authorization import require_restore_permission
from claim.models import Claim
from claim.services import claim_create, validate_claim_data
from claim.test_helpers import (
    DummyUser,
    create_test_claim,
    delete_claim_with_itemsvc_dedrem_and_history,
    mark_test_claim_as_processed,
)
from core.test_helpers import create_test_interactive_user, create_test_role


class ClaimRestorePermissionTest(TestCase):
    def test_require_restore_permission_denies_without_rights(self):
        user = create_test_interactive_user(username=f"wo024-no-restore-{uuid4().hex[:8]}")
        with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
            with self.assertRaises(ValidationError) as ctx:
                require_restore_permission(user)
        self.assertIn("no_restore_rights", str(ctx.exception))

    def test_require_restore_permission_allows_authorized_user(self):
        role = create_test_role(
            perm_names=["111012"],
            name=f"WO024Restore-{uuid4().hex[:8]}",
        )
        user = create_test_interactive_user(
            username=f"wo024-restore-{uuid4().hex[:8]}",
            roles=[role.id],
        )
        with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
            require_restore_permission(user)


class ClaimRestoreValidationTest(TestCase):
    def setUp(self):
        self.authorized_user = create_test_interactive_user(
            username=f"wo024-auth-{uuid4().hex[:8]}",
            roles=[
                create_test_role(
                    perm_names=["111012"],
                    name=f"WO024RestoreRole-{uuid4().hex[:8]}",
                ).id
            ],
        )
        with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
            self.source = create_test_claim(
                custom_props={"code": f"WO024-SRC-{uuid4().hex[:8]}"},
                user=self.authorized_user,
            )
        mark_test_claim_as_processed(self.source, status=Claim.STATUS_REJECTED)

    def tearDown(self):
        for claim in Claim.objects.filter(restore=self.source):
            delete_claim_with_itemsvc_dedrem_and_history(claim)
        delete_claim_with_itemsvc_dedrem_and_history(self.source)

    def _validate(self, restore_uuid, user=None):
        with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
            return validate_restore_request(restore_uuid, user or self.authorized_user)

    def test_validate_restore_returns_rejected_source(self):
        source = self._validate(self.source.uuid)
        self.assertEqual(source.id, self.source.id)
        self.assertEqual(source.status, Claim.STATUS_REJECTED)

    def test_validate_restore_accepts_claim_instance(self):
        source = self._validate(self.source)
        self.assertEqual(source.id, self.source.id)

    def test_validate_restore_rejects_missing_source(self):
        with self.assertRaises(ValidationError) as ctx:
            self._validate(uuid4())
        self.assertIn("restored_from_does_not_exist", str(ctx.exception))

    def test_validate_restore_rejects_empty_uuid(self):
        with self.assertRaises(ValidationError) as ctx:
            self._validate(None)
        self.assertIn("restored_from_does_not_exist", str(ctx.exception))

    def test_validate_restore_rejects_non_rejected_source(self):
        checked = create_test_claim(
            custom_props={"code": f"WO024-CHK-{uuid4().hex[:8]}"},
            user=self.authorized_user,
        )
        mark_test_claim_as_processed(checked, status=Claim.STATUS_CHECKED)
        try:
            with self.assertRaises(ValidationError) as ctx:
                self._validate(checked.uuid)
            self.assertIn("cannot_restore_not_rejected_claim", str(ctx.exception))
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(checked)

    def test_validate_restore_enforces_max_when_configured(self):
        with mock.patch.object(ClaimConfig, "claim_max_restore", 1):
            with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
                restored = create_test_claim(
                    custom_props={
                        "code": f"WO024-R1-{uuid4().hex[:8]}",
                        "restore": self.source,
                    },
                    user=self.authorized_user,
                )
                self.assertEqual(count_restores_for_source(self.source), 1)
                with self.assertRaises(ValidationError) as ctx:
                    validate_restore_request(self.source.uuid, self.authorized_user)
                self.assertIn("max_restored_claim", str(ctx.exception))
                delete_claim_with_itemsvc_dedrem_and_history(restored)

    def test_validate_restore_allows_unlimited_when_max_unset(self):
        with mock.patch.object(ClaimConfig, "claim_max_restore", None):
            with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
                for idx in range(2):
                    restored = create_test_claim(
                        custom_props={
                            "code": f"WO024-R{idx}-{uuid4().hex[:8]}",
                            "restore": self.source,
                        },
                        user=self.authorized_user,
                    )
                    delete_claim_with_itemsvc_dedrem_and_history(restored)
                self.assertEqual(count_restores_for_source(self.source), 0)

    def test_count_restores_ignores_invalidated_claims(self):
        with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
            restored = create_test_claim(
                custom_props={
                    "code": f"WO024-INV-{uuid4().hex[:8]}",
                    "restore": self.source,
                },
                user=self.authorized_user,
            )
            from core.utils import TimeUtils

            restored.validity_to = TimeUtils.now()
            restored.save()
            self.assertEqual(count_restores_for_source(self.source), 0)
            delete_claim_with_itemsvc_dedrem_and_history(restored)


class ClaimRestoreIntegrationTest(TestCase):
    def test_claim_create_links_restore_fk(self):
        role = create_test_role(
            perm_names=["111012"],
            name=f"WO024Create-{uuid4().hex[:8]}",
        )
        user = create_test_interactive_user(
            username=f"wo024-create-{uuid4().hex[:8]}",
            roles=[role.id],
        )
        source = create_test_claim(
            custom_props={"code": f"WO024-LNK-{uuid4().hex[:8]}"},
            user=user,
        )
        mark_test_claim_as_processed(source, status=Claim.STATUS_REJECTED)
        try:
            with mock.patch.object(ClaimConfig, "gql_mutation_restore_claims_perms", ["111012"]):
                restored = claim_create(
                    {
                        "code": f"WO024-NEW-{uuid4().hex[:8]}",
                        "date_from": source.date_from,
                        "date_claimed": source.date_claimed,
                        "insuree": source.insuree,
                        "icd": source.icd,
                        "health_facility": source.health_facility,
                        "admin": source.admin,
                        "status": Claim.STATUS_ENTERED,
                        "restore": source.uuid,
                        "items": [],
                        "services": [],
                    },
                    user,
                )
            self.assertEqual(restored.restore_id, source.id)
            delete_claim_with_itemsvc_dedrem_and_history(restored)
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(source)

    def test_validate_claim_data_delegates_to_restore_validator(self):
        user = DummyUser()
        with mock.patch("claim.claim_restore.validate_restore_request") as mock_validate:
            validate_claim_data(
                {"code": "RESTORE-TEST", "restore": uuid4(), "services": []},
                user,
            )
            mock_validate.assert_called_once()
