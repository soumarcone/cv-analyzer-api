"""Pydantic schemas for CV analysis responses."""

from typing import Literal
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """A single "proof" item used to reduce hallucinations.
    
    The model should only make claims it can back up with a short quote 
    from the CV text.
    """

    claim: str = Field(
        ...,
        description="A concise statement about the candidate (e.g., 'Has FastAPI experience').",
    )
    cv_quote: str = Field(
        ...,
        description="A short, verbatim quote from the CV that supports the claim.",
    )


class CVAnalysisResponse(BaseModel):
    """Comprehensive CV analysis response with structured feedback.
    
    Provides quantified fit scoring, evidence-backed claims, actionable 
    recommendations, and ATS optimization guidance.
    """

    summary: str = Field(
        ...,
        description="Short narrative summary of the candidate's alignment with the job.",
    )

    fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall fit score from 0 to 100.",
    )

    fit_score_rationale: str = Field(
        ...,
        description="Explanation for why the fit_score was assigned, referencing key strengths/gaps.",
    )

    strengths: list[str] = Field(
        ...,
        description="Key strengths of the candidate for this role (bullet list).",
    )

    gaps: list[str] = Field(
        ...,
        description="Key gaps or missing experience compared to the job requirements (bullet list).",
    )

    missing_keywords: list[str] = Field(
        ...,
        description="Important keywords from the job description missing or weakly represented in the CV.",
    )

    rewrite_suggestions: list[str] = Field(
        ...,
        description="Specific rewrite suggestions to improve CV content and alignment with the job.",
    )

    ats_notes: list[str] = Field(
        ...,
        description="ATS-focused recommendations (formatting, sections, keyword density, file structure).",
    )

    red_flags: list[str] = Field(
        ...,
        description="Potential concerns or risk signals (e.g., inconsistent dates, vague claims, missing evidence).",
    )

    next_steps: list[str] = Field(
        ...,
        description="Immediate actionable next steps (prioritized checklist).",
    )

    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items linking claims to direct CV quotes.",
    )

    confidence: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Confidence in the analysis given input quality and evidence strength.",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about input quality or processing constraints (e.g., truncation, possible OCR-needed PDF).",
    )

    cached: bool = Field(
        default=False,
        description="True if the response was returned from cache (same inputs previously analyzed).",
    )
