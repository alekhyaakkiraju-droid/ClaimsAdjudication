"""XML claim submission serialization (WO-030)."""

import xml.etree.ElementTree as ET

import core
from medical.models import Item, Service

from claim.models import ClaimItem, ClaimService


@core.comparable
class ClaimElementSubmit(object):
    def __init__(self, type, code, quantity, price=None):
        self.type = type
        self.code = code
        self.price = price
        self.quantity = quantity

    def add_to_xmlelt(self, xmlelt):
        item = ET.SubElement(xmlelt, self.type)
        ET.SubElement(item, "%sCode" % self.type).text = "%s" % self.code
        if self.price:
            ET.SubElement(item, "%sPrice" % self.type).text = "%s" % self.price
        ET.SubElement(item, "%sQuantity" % self.type).text = "%s" % self.quantity

    def to_claim_provision(self):
        raise NotImplementedError()


@core.comparable
class ClaimItemSubmit(ClaimElementSubmit):
    def __init__(self, code, quantity, price=None):
        super().__init__(type="Item", code=code, price=price, quantity=quantity)

    def to_claim_provision(self):
        item = Item.objects.filter(validity_to__isnull=True, code=self.code).get()
        return ClaimItem(qty_provided=self.quantity, price_asked=self.price, item=item)


@core.comparable
class ClaimServiceSubmit(ClaimElementSubmit):
    def __init__(self, code, quantity, price=None):
        super().__init__(type="Service", code=code, price=price, quantity=quantity)

    def to_claim_provision(self):
        service = Service.objects.filter(validity_to__isnull=True, code=self.code).get()
        return ClaimService(
            qty_provided=self.quantity, price_asked=self.price, service=service
        )


# FIXME only used in test, should be moved to test_helpers
@core.comparable
class ClaimSubmit(object):
    def __init__(
        self,
        date,
        code,
        icd_code,
        total,
        start_date,
        insuree_chf_id,
        health_facility_code,
        claim_admin_code,
        item_submits=None,
        service_submits=None,
        end_date=None,
        icd_code_1=None,
        icd_code_2=None,
        icd_code_3=None,
        icd_code_4=None,
        visit_type=None,
        guarantee_no=None,
        comment=None,
    ):
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

    def _details_to_xmlelt(self, xmlelt):
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

    def add_elt_list_to_xmlelt(self, xmlelt, elts_name, elts):
        if elts and len(elts) > 0:
            elts_xml = ET.SubElement(xmlelt, elts_name)
            for item in elts:
                item.add_to_xmlelt(elts_xml)

    def add_to_xmlelt(self, xmlelt):
        details = ET.SubElement(xmlelt, "Details")
        self._details_to_xmlelt(details)
        self.add_elt_list_to_xmlelt(xmlelt, "Items", self.items)
        self.add_elt_list_to_xmlelt(xmlelt, "Services", self.services)

    def to_xml(self):
        claim_xml = ET.Element("Claim")
        self.add_to_xmlelt(claim_xml)
        return ET.tostring(claim_xml, encoding="utf-8", method="xml").decode()
