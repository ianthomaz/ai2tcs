"""API models for NF extraction endpoint."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NFExtractResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    source_type: Literal["upload", "server_file_path", "document_url"] | None = None
    document_type: Literal["xml", "pdf", "img", "unknown"] = "unknown"
    file_name: str | None = None

    supplier_name: str | None = None
    supplier_code: str | None = Field(None, description="CNPJ only digits")
    nf_number: str | None = None
    issue_date: str | None = Field(None, description="YYYY-MM-DD when available")

    amount: float | None = None
    amount_type: Literal["total", "imposto_retido", "unknown"] = "unknown"
    amount_deposit: float | None = None
    amount_tax: float | None = None

    description: str | None = None
    payment_pix_code: str | None = Field(default=None, alias="payment_pixCode")
    payment_bank: str | None = None
    payment_bank_agency: str | None = None
    payment_bank_account: str | None = None
    payment_bank_account_type: Literal["corrente", "poupanca", "unknown"] = "unknown"
    payment_receiver_name: str | None = None
    payment_receiver_document: str | None = None

    confidence: float = 0.0
    confidence_by_field: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    raw_text_excerpt: str | None = None

    model_config = {"populate_by_name": True}
