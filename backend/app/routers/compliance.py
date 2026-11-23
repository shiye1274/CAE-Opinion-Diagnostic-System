# -*- coding: utf-8 -*-
"""文化合规审查接口。"""
from pydantic import BaseModel, Field
from fastapi import APIRouter

from ..services import compliance_rules

router = APIRouter()


class ComplianceRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="待审查的阿/英/中营销文案")
    scene: str = Field("ad", description="ad / pr / social")


@router.post("/compliance/check")
def compliance_check(req: ComplianceRequest):
    result = compliance_rules.scan(req.text)
    return {"scene": req.scene, **result}
