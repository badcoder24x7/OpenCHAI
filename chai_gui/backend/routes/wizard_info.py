"""
OpenCHAI GUI — Wizard Section Info Routes

GET /wizard-info/sections          → list of known section keys
GET /wizard-info/section/{key}     → {"section": key, "content": "<markdown>"}
GET /wizard-info/all               → {key: markdown, ...} for every section
"""

from __future__ import annotations

from fastapi import APIRouter

from services import wizard_info_service as svc

router = APIRouter()


@router.get("/sections", summary="List known wizard info section keys")
async def sections():
    return {"sections": svc.list_sections()}


@router.get("/section/{key}", summary="Get markdown info content for one wizard section")
async def section(key: str):
    return svc.get_section_info(key)


@router.get("/all", summary="Get markdown info content for every wizard section")
async def all_sections():
    return svc.get_all_sections()
