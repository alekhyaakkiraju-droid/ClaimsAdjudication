"""
WO-023: Referral fields and multi-diagnosis support tests.
"""

import json
from datetime import date, timedelta
from unittest import mock
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from claim.apps import ClaimConfig
from claim.models import Claim
from claim.referral_diagnosis import (
    ADDITIONAL_ICD_FIELD_NAMES,
    build_same_diagnosis_filter,
    count_additional_diagnoses_in_data,
)
from claim.services import (
    ClaimReportService,
    claim_update,
    update_or_create_claim,
    validate_claim_data,
    validate_number_of_additional_diagnoses,
)
from claim.test_helpers import (
    DummyUser,
    create_test_claim,
    create_test_claim_admin,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.models.openimis_graphql_test_case import BaseTestContext, openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token
from insuree.test_helpers import create_test_insuree
from location.test_helpers import create_test_health_facility
from medical.test_helpers import create_test_diagnosis
from policy.test_helpers import create_test_policy2
from product.test_helpers import create_test_product


class ReferralDiagnosisHelperTest(TestCase):
    def test_count_additional_diagnoses_in_data(self):
        data = {"icd_id": 1, "icd_1_id": 2, "icd_2_id": 3, "code": "X"}
        self.assertEqual(count_additional_diagnoses_in_data(data), 2)

    def test_validate_number_of_additional_diagnoses_uses_config(self):
        allowed = ClaimConfig.additional_diagnosis_number_allowed
        within = {f"icd_{i}_id": i for i in range(1, allowed + 1)}
        over = {f"icd_{i}_id": i for i in range(1, allowed + 2)}
        self.assertTrue(validate_number_of_additional_diagnoses(within))
        self.assertFalse(validate_number_of_additional_diagnoses(over))

    def test_build_same_diagnosis_filter_matches_additional_icd_field(self):
        insuree = create_test_insuree()
        primary_icd = create_test_diagnosis(custom_props={"code": f"WO023P-{uuid4().hex[:6]}"})
        secondary_icd = create_test_diagnosis(custom_props={"code": f"WO023S-{uuid4().hex[:6]}"})
        claim = create_test_claim(
            custom_props={
                "insuree": insuree,
                "icd": primary_icd,
                "icd_1": secondary_icd,
            }
        )
        matched = Claim.objects.filter(
            build_same_diagnosis_filter(
                icd_code=secondary_icd.code,
                chf_id=insuree.chf_id,
            )
        )
        self.assertIn(claim, matched)
        delete_claim_with_itemsvc_dedrem_and_history(claim)


class ReferralDiagnosisServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="wo023-service")
        cls.product = create_test_product("WO023")
        cls.insuree = create_test_insuree()
        create_test_policy2(cls.product, cls.insuree, link=True)
        cls.primary_icd = create_test_diagnosis(custom_props={"code": f"WO023I-{uuid4().hex[:6]}"})
        cls.extra_icd = create_test_diagnosis(custom_props={"code": f"WO023E-{uuid4().hex[:6]}"})
        cls.refer_from = create_test_health_facility(f"RF{uuid4().hex[:4]}")
        cls.refer_to = create_test_health_facility(f"RT{uuid4().hex[:4]}")
        cls.claim_admin = create_test_claim_admin()

    def test_create_claim_persists_referral_and_additional_diagnoses(self):
        code = f"WO023-{uuid4().hex[:8]}"
        claim = update_or_create_claim(
            {
                "code": code,
                "status": Claim.STATUS_ENTERED,
                "insuree_id": self.insuree.id,
                "date_from": date.today() - timedelta(days=2),
                "date_claimed": date.today() - timedelta(days=1),
                "icd_id": self.primary_icd.id,
                "icd_1_id": self.extra_icd.id,
                "health_facility_id": self.claim_admin.health_facility_id,
                "admin_id": self.claim_admin.id,
                "refer_from_id": self.refer_from.id,
                "refer_to_id": self.refer_to.id,
                "referral_code": "REF-WO023",
                "visit_type": "O",
                "services": [],
                "items": [],
            },
            self.user,
        )
        claim.refresh_from_db()
        self.assertEqual(claim.refer_from_id, self.refer_from.id)
        self.assertEqual(claim.refer_to_id, self.refer_to.id)
        self.assertEqual(claim.referral_code, "REF-WO023")
        self.assertEqual(claim.icd_1_id, self.extra_icd.id)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_update_claim_resets_referral_fields_when_omitted(self):
        claim = create_test_claim(
            custom_props={
                "insuree": self.insuree,
                "refer_from": self.refer_from,
                "refer_to": self.refer_to,
                "referral_code": "OLD-REF",
            }
        )
        claim_update(
            claim,
            {
                "code": claim.code,
                "insuree_id": claim.insuree_id,
                "date_from": claim.date_from,
                "date_claimed": claim.date_claimed,
                "icd_id": claim.icd_id,
                "health_facility_id": claim.health_facility_id,
                "admin_id": claim.admin_id,
                "visit_type": claim.visit_type,
                "services": [],
                "items": [],
            },
            DummyUser(),
        )
        claim.refresh_from_db()
        self.assertIsNone(claim.refer_from_id)
        self.assertIsNone(claim.refer_to_id)
        self.assertIsNone(claim.referral_code)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_validate_claim_data_rejects_excess_additional_diagnoses(self):
        claim = create_test_claim(custom_props={"insuree": self.insuree})
        allowed = ClaimConfig.additional_diagnosis_number_allowed
        extra_icds = [
            create_test_diagnosis(custom_props={"code": f"WO023X{i}-{uuid4().hex[:4]}"})
            for i in range(allowed + 1)
        ]
        data = {
            "code": claim.code,
            "uuid": str(claim.uuid),
            "services": [],
            "icd_id": claim.icd_id,
        }
        for idx, icd in enumerate(extra_icds, start=1):
            data[f"icd_{idx}_id"] = icd.id

        with self.assertRaises(ValidationError):
            validate_claim_data(data, self.user)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_report_service_includes_referral_and_additional_diagnosis_fields(self):
        claim = create_test_claim(
            custom_props={
                "insuree": self.insuree,
                "icd_1": self.extra_icd,
                "refer_from": self.refer_from,
                "refer_to": self.refer_to,
                "referral_code": "REF-REPORT",
            }
        )
        report = ClaimReportService(self.user).fetch(str(claim.uuid))
        self.assertEqual(report["referralCode"], "REF-REPORT")
        self.assertIn(str(self.refer_from), report["referFrom"])
        self.assertIn(str(self.refer_to), report["referTo"])
        self.assertIn(str(self.extra_icd), report["icd1"])
        delete_claim_with_itemsvc_dedrem_and_history(claim)


class ReferralDiagnosisGraphQLTest(openIMISGraphQLTestCase):
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo023-gql")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.product = create_test_product("WO023GQL")
        cls.insuree = create_test_insuree()
        create_test_policy2(cls.product, cls.insuree, link=True)
        cls.primary_icd = create_test_diagnosis(custom_props={"code": f"WO023GP-{uuid4().hex[:6]}"})
        cls.match_icd = create_test_diagnosis(custom_props={"code": f"WO023GM-{uuid4().hex[:6]}"})
        cls.refer_from = create_test_health_facility(f"GF{uuid4().hex[:4]}")
        cls.refer_to = create_test_health_facility(f"GT{uuid4().hex[:4]}")
        cls.claim_admin = create_test_claim_admin()
        cls.claims = []

    @classmethod
    def tearDownClass(cls):
        for claim in cls.claims:
            delete_claim_with_itemsvc_dedrem_and_history(claim)
        super().tearDownClass()

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    @mock.patch("claim.services.submit.processing_claim", return_value=[])
    def test_graphql_create_and_query_referral_fields(self, _mock_processing):
        code = f"WO023G-{uuid4().hex[:8]}"
        mutation_id = str(uuid4())
        create_resp = self.query(
            f"""
            mutation {{
                createClaim(input: {{
                    clientMutationId: "{mutation_id}"
                    clientMutationLabel: "WO023 referral create"
                    code: "{code}"
                    autogenerate: false
                    insureeId: {self.insuree.id}
                    adminId: {self.claim_admin.id}
                    dateFrom: "{(date.today() - timedelta(days=3)).isoformat()}"
                    dateClaimed: "{(date.today() - timedelta(days=1)).isoformat()}"
                    icdId: {self.primary_icd.id}
                    icd1Id: {self.match_icd.id}
                    healthFacilityId: {self.claim_admin.health_facility_id}
                    referFromId: {self.refer_from.id}
                    referToId: {self.refer_to.id}
                    referralCode: "REF-GQL"
                    visitType: "O"
                    feedbackStatus: 1
                    reviewStatus: 1
                    jsonExt: "{{}}"
                    services: []
                    items: []
                }}) {{
                    clientMutationId
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(create_resp)
        claim = Claim.objects.get(code=code)
        self.claims.append(claim)

        query_resp = self.query(
            f"""
            query {{
                claim(uuid: "{claim.uuid}") {{
                    referralCode
                    referFrom {{ id code }}
                    referTo {{ id code }}
                    icd1 {{ code }}
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(query_resp)
        data = json.loads(query_resp.content)["data"]["claim"]
        self.assertEqual(data["referralCode"], "REF-GQL")
        self.assertEqual(data["referFrom"]["code"], self.refer_from.code)
        self.assertEqual(data["referTo"]["code"], self.refer_to.code)
        self.assertEqual(data["icd1"]["code"], self.match_icd.code)

    def test_claim_with_same_diagnosis_matches_additional_icd_field(self):
        claim = create_test_claim(
            custom_props={
                "insuree": self.insuree,
                "icd": self.primary_icd,
                "icd_1": self.match_icd,
            }
        )
        self.claims.append(claim)

        response = self.query(
            f"""
            query {{
                claimWithSameDiagnosis(
                    icd: "{self.match_icd.code}",
                    chfid: "{self.insuree.chf_id}"
                ) {{
                    totalCount
                    edges {{ node {{ code icd1 {{ code }} }} }}
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(response)
        payload = json.loads(response.content)["data"]["claimWithSameDiagnosis"]
        codes = {edge["node"]["code"] for edge in payload["edges"]}
        self.assertIn(claim.code, codes)
        self.assertGreaterEqual(payload["totalCount"], 1)

    def test_claims_filter_by_referral_code(self):
        claim = create_test_claim(
            custom_props={
                "insuree": self.insuree,
                "referral_code": f"UNIQUE-REF-{uuid4().hex[:8]}",
            }
        )
        self.claims.append(claim)

        response = self.query(
            f"""
            query {{
                claims(referralCode_Icontains: "{claim.referral_code[:12]}") {{
                    edges {{ node {{ code referralCode }} }}
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(response)
        codes = {
            edge["node"]["code"]
            for edge in json.loads(response.content)["data"]["claims"]["edges"]
        }
        self.assertIn(claim.code, codes)


class ReferralDiagnosisConstantsTest(TestCase):
    def test_additional_icd_field_names_match_model(self):
        for field in ADDITIONAL_ICD_FIELD_NAMES:
            self.assertTrue(hasattr(Claim, field))
