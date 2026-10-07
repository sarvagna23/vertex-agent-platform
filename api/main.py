"""FastAPI layer in front of the agent workflow. Deployed on Cloud Run.

Request path: question -> PII redaction -> ADK workflow -> JSON answer.
Run locally:  uvicorn api.main:app --reload --port 8080
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents.runner import run_pipeline
from pii.redactor import redact_pii

app = FastAPI(title="Vertex Agent Platform", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskResponse(BaseModel):
    answer: str
    redacted_question: str  # exactly what the model saw
    pii_found: dict         # counts per type, never the raw values
    latency_ms: int


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """Mask PII first, then hand only the redacted text to the agents."""
    redaction = redact_pii(request.question)

    try:
        result = await run_pipeline(redaction.text)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"agent workflow failed: {error}")

    return AskResponse(
        answer=result["answer"],
        redacted_question=redaction.text,
        pii_found=redaction.counts,
        latency_ms=result["latency_ms"],
    )
