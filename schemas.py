"""Pydantic input schemas for all agent tools.

Each schema validates and normalises the arguments the LLM passes before they
reach the tool handler.  Validation happens in Orchestrator._execute(), which
catches ValidationError and returns a plain error string so the LLM can
self-correct without crashing.
"""

from pydantic import BaseModel, field_validator


class WebSearchInput(BaseModel):
    query: str


class FetchUrlInput(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must begin with http:// or https://. Got: {v!r}")
        return v


class SaveFindingInput(BaseModel):
    key: str
    value: str

    @field_validator("key")
    @classmethod
    def key_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("key must not be empty")
        return stripped

    @field_validator("value", mode="before")
    @classmethod
    def coerce_to_string(cls, v: object) -> str:
        if isinstance(v, list):
            return ", ".join(str(i) for i in v)
        return str(v)
