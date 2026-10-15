from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.product import ProductResponse

class TextSearchRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query: str = Field(min_length=1,max_length=4000)
    limit: int = Field(default=5,ge=1,le=10)
    category: str | None = Field(default=None,min_length=1,max_length=100)
    brand: str | None = Field(default=None,min_length=1,max_length=100)

    @field_validator('query','category','brand',mode='before')
    @classmethod
    def trim(cls,v): return v.strip() if isinstance(v,str) else v

class TextSearchHit(BaseModel):
    catalog_snapshot: dict = Field(default_factory=dict,exclude=True)
    product: ProductResponse
    score: float = Field(description='Reciprocal rank fusion score, not probability')
    semantic_similarity: float | None = None
    keyword_rank: int | None = None
    semantic_rank: int | None = None

class TextSearchResponse(BaseModel):
    guardrail_status: Literal['allowed','blocked','needs_clarification','no_match']='allowed'
    guardrail_reason: str | None = None
    policy_version: str = 'catalog-scope-v1'
    relevance_rejected: int = 0
    items: list[TextSearchHit]
    clarification: str | None = None
    embedding_model: str
    method: Literal['hybrid_rrf']='hybrid_rrf'
    index_status: Literal['ready','partial','missing','not_checked']
    stale_skipped: int = 0
    timings_ms: dict[str,float] = Field(default_factory=dict)
