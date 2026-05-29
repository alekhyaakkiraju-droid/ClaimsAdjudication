# flake8: noqa

from django.db import connection
from tools.utils import dictfetchall

import logging

from claim.reports.template_loader import load_report_template

logger = logging.getLogger(__name__)

template = load_report_template("claim_percentage_referrals")

# TODO transform the SQL query into a Django ORM query
percentage_referrals_sql = """
SELECT CONCAT(HF."HFCode", ' - ', HF."HFName") HF, TotalClaim.TotalClaims, RefOP.TotalOP, RefIP.TotalIP
FROM (SELECT HF."HfID", HF."HFCode", HF."HFName"
      FROM "tblHF" HF
               INNER JOIN "uvwLocations" L ON L."LocationId" = HF."LocationId"
      WHERE HF."ValidityTo" Is NULL
        AND HF."HFLevel" IN ('D', 'C')
        AND (L."RegionId" = %(region_id)s OR %(region_id)s = 0 OR L."LocationId" IS NULL)
        AND (L."DistrictId" = %(district_id)s OR %(district_id)s = 0 OR L."DistrictId" IS NULL)
      ) HF
         LEFT OUTER JOIN (SELECT COUNT(1) TotalClaims, "HFID"
                          FROM "tblClaim"
                          WHERE "ValidityTo" Is NULL
                          AND "DateClaimed" BETWEEN %(date_start)s AND %(date_end)s
                          GROUP BY "HFID") TotalClaim ON HF."HfID" = TotalClaim."HFID"
         LEFT OUTER JOIN (SELECT I."HFID", COUNT(C."ClaimID") TotalOP
                          FROM "tblClaim" C
                                   INNER JOIN "tblInsuree" I ON C."InsureeID" = I."InsureeID"
                                   INNER JOIN "tblHF" HF ON C."HFID" = HF."HfID"
                                   INNER JOIN "uvwLocations" L ON L."LocationId" = HF."LocationId"
                          WHERE C."ValidityTo" Is NULL
                            AND I."ValidityTo" IS NULL
                            AND HF."ValidityTo" IS NULL
                            AND (C."DateTo" is null OR C."DateFrom" = C."DateTo")
                            AND HF."HfID" <> I."HFID"
                            AND C."VisitType" = N'R'
                            AND (L."RegionId" = %(region_id)s OR %(region_id)s = 0 OR L."LocationId" IS NULL)
                            AND (L."DistrictId" = %(district_id)s OR %(district_id)s = 0 OR L."DistrictId" IS NULL)
                            AND C."DateClaimed" BETWEEN %(date_start)s AND %(date_end)s
                          GROUP BY I."HFID") RefOP ON HF."HfID" = RefOP."HFID"
         LEFT OUTER JOIN (SELECT I."HFID", COUNT(C."ClaimID") TotalIP
                          FROM "tblClaim" C
                                   INNER JOIN "tblInsuree" I ON C."InsureeID" = I."InsureeID"
                                   INNER JOIN "tblHF" HF ON C."HFID" = HF."HfID"
                                   INNER JOIN "uvwLocations" L ON L."LocationId" = HF."LocationId"
                          WHERE C."ValidityTo" Is NULL
                            AND I."ValidityTo" IS NULL
                            AND HF."ValidityTo" IS NULL
                            AND C."DateTo" is not null and C."DateFrom" <> C."DateTo"
                            AND HF."HfID" <> I."HFID"
                            AND C."VisitType" = N'R'
                            AND (L."RegionId" = %(region_id)s OR %(region_id)s = 0 OR L."LocationId" IS NULL)
                            AND (L."DistrictId" = %(district_id)s OR %(district_id)s = 0 OR L."DistrictId" IS NULL)
                            AND C."DateClaimed" BETWEEN %(date_start)s AND %(date_end)s
                          GROUP BY I."HFID") RefIP ON HF."HfID" = RefIP."HFID"
"""


def claim_percentage_referrals_query(
    user,
    region_id=0,
    district_id=0,
    date_start="2019-01-01",
    date_end="2022-12-31",
    **kwargs
):
    with connection.cursor() as cur:
        try:
            cur.execute(
                percentage_referrals_sql,
                {
                    "region_id": region_id,
                    "district_id": district_id,
                    "date_start": date_start,
                    "date_end": date_end,
                },
            )
            data = dictfetchall(cur)
            return {"data": data}
        except Exception as e:
            logger.exception("Error fetching claim percentage referrals query")
            raise e

    logger.error("Claim percentage referrals query arrived at end of function")
    return {"data": None}
