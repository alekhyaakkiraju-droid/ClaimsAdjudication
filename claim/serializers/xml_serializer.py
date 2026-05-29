"""XML claim submission serialization (WO-030)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date as date_type
from typing import Any, List, Optional, Union

import core
from medical.models import Item, Service

from claim.models import ClaimItem, ClaimService

ElementTree = ET.Element


@core.comparable
class ClaimElementSubmit(object):
    def __init__(
        self,
        type: str,
        code: str,
        quantity: Union[int, float],
        price: Optional[Union[int, float]] = None,
    ) -> None:
        self.type = type
        self.code = code
        self.price = price
        self.quantity = quantity

    def add_to_xmlelt(self, xmlelt: ElementTree) -> None:
        item = ET.SubElement(xmlelt, self.type)
        ET.SubElement(item, "%sCode" % self.type).text = "%s" % self.code
        if self.price:
            ET.SubElement(item, "%sPrice" % self.type).text = "%s" % self.price
        ET.SubElement(item, "%sQuantity" % self.type).text = "%s" % self.quantity

    def to_claim_provision(self) -> Union[ClaimItem, ClaimService]:
        raise NotImplementedError()


@core.comparable
class ClaimItemSubmit(ClaimElementSubmit):
    def __init__(
        self,
        code: str,
        quantity: Union[int, float],
        price: Optional[Union[int, float]] = None,
    ) -> None:
        super().__init__(type="Item", code=code, price=price, quantity=quantity)

    def to_claim_provision(self) -> ClaimItem:
        item = Item.objects.filter(validity_to__isnull=True, code=self.code).get()
        return ClaimItem(qty_provided=self.quantity, price_asked=self.price, item=item)


@core.comparable
class ClaimServiceSubmit(ClaimElementSubmit):
    def __init__(
        self,
        code: str,
        quantity: Union[int, float],
        price: Optional[Union[int, float]] = None,
    ) -> None:
        super().__init__(type="Service", code=code, price=price, quantity=quantity)

    def to_claim_provision(self) -> ClaimService:
        service = Service.objects.filter(validity_to__isnull=True, code=self.code).get()
        return ClaimService(
            qty_provided=self.quantity, price_asked=self.price, service=service
        )


# FIXME only used in test, should be moved to test_helpers
@core.comparable
class ClaimSubmit(object):
    def __init__(
        self,
        date: date_type,
        code: str,
        icd_code: str,
        total: Union[int, float],
        start_date: date_type,
        insuree_chf_id: str,
        health_facility_code: str,
        claim_admin_code: Optional[str],
        item_submits: Optional[List[ClaimItemSubmit]] = None,
        service_submits: Optional[List[ClaimServiceSubmit]] = None,
        end_date: Optional[date_type] = None,
        icd_code_1: Optional[str] = None,
        icd_code_2: Optional[str] = None,
        icd_code_3: Optional[str] = None,
        icd_code_4: Optional[str] = None,
        visit_type: Optional[str] = None,
        guarantee_no: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> None:
        self.date = date
        self.code = code
        self.icd_code = icd_code
        self.total = total
        self.start_date = start_date
        self.insuree_chf_id = insuree_chf_id
        self.health_facility_code = health_facility_code
        self.end_date = end_date
        self.icd_code_1 = icd_code_1
        self.icd_code_2 = icd_code_2
        self.icd_code_3 = icd_code_3
        self.icd_code_4 = icd_code_4
        self.claim_admin_code = claim_admin_code
        self.visit_type = visit_type
        self.guarantee_no = guarantee_no
        self.comment = comment
        self.items = item_submits
        self.services = service_submits

    def _details_to_xmlelt(self, xmlelt: ElementTree) -> None:
        ET.SubElement(xmlelt, "ClaimDate").text = self.date.strftime("%d/%m/%Y")
        ET.SubElement(xmlelt, "HFCode").text = "%s" % self.health_facility_code
        if self.claim_admin_code:
            ET.SubElement(xmlelt, "ClaimAdmin").text = "%s" % self.claim_admin_code
        ET.SubElement(xmlelt, "ClaimCode").text = "%s" % self.code
        ET.SubElement(xmlelt, "CHFID").text = "%s" % self.insuree_chf_id
        ET.SubElement(xmlelt, "StartDate").text = self.start_date.strftime("%d/%m/%Y")
        if self.end_date:
            ET.SubElement(xmlelt, "EndDate").text = self.end_date.strftime("%d/%m/%Y")
        ET.SubElement(xmlelt, "ICDCode").text = "%s" % self.icd_code
        if self.comment:
            ET.SubElement(xmlelt, "Comment").text = "%s" % self.comment
        ET.SubElement(xmlelt, "Total").text = "%s" % self.total
        if self.icd_code_1:
            ET.SubElement(xmlelt, "ICDCode1").text = "%s" % self.icd_code_1
        if self.icd_code_2:
            ET.SubElement(xmlelt, "ICDCode2").text = "%s" % self.icd_code_2
        if self.icd_code_3:
            ET.SubElement(xmlelt, "ICDCode3").text = "%s" % self.icd_code_3
        if self.icd_code_4:
            ET.SubElement(xmlelt, "ICDCode4").text = "%s" % self.icd_code_4
        if self.visit_type:
            ET.SubElement(xmlelt, "VisitType").text = "%s" % self.visit_type
        if self.guarantee_no:
            ET.SubElement(xmlelt, "GuaranteeNo").text = "%s" % self.guarantee_no

    def add_elt_list_to_xmlelt(
        self,
        xmlelt: ElementTree,
        elts_name: str,
        elts: Optional[List[ClaimElementSubmit]],
    ) -> None:
        if elts and len(elts) > 0:
            elts_xml = ET.SubElement(xmlelt, elts_name)
            for item in elts:
                item.add_to_xmlelt(elts_xml)

    def add_to_xmlelt(self, xmlelt: ElementTree) -> None:
        details = ET.SubElement(xmlelt, "Details")
        self._details_to_xmlelt(details)
        self.add_elt_list_to_xmlelt(xmlelt, "Items", self.items)
        self.add_elt_list_to_xmlelt(xmlelt, "Services", self.services)

    def to_xml(self) -> str:
        claim_xml = ET.Element("Claim")
        self.add_to_xmlelt(claim_xml)
        return ET.tostring(claim_xml, encoding="utf-8", method="xml").decode()
