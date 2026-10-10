"""Retrievers.

Image RAG part (docs/architecture/IMAGE_RAG_DESIGN.md §1.3):
- ``ImageRetriever``: hybrid image + caption similarity over a vector index.
- ``MockCatalogRetriever``: metadata-only stand-in used before the catalog is embedded.

The vector index is a Protocol so this layer does not depend on
repositories/ — the pgvector implementation lives in
repositories/product_repository.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from app.ai.embeddings.embedding_service import IMAGE_QUERY_INSTRUCTION
from app.ai.prompts.vision_prompt import ImageAnalysis
from app.ai.rag.indexing_service import build_brand_aliases, load_catalog


@dataclass
class RetrievalQuery:
    image: Image.Image  # cropped main item
    text: str  # description + readable brand/model, for the caption side
    analysis: ImageAnalysis


class ProductRetriever(Protocol):
    def search(self, query: RetrievalQuery, top_k: int) -> list[dict]:
        """Products as ``CatalogProduct.to_metadata()`` dicts plus ``score`` (0-1), best first."""


class ImageVectorIndex(Protocol):
    def best_by_sku(self, vector: np.ndarray, chunk_type: str, limit: int) -> dict[str, tuple[float, dict]]:
        """Best cosine similarity per SKU among chunks of ``chunk_type``: {sku: (similarity, metadata)}."""


class ImageEmbedder(Protocol):
    def embed_images(self, images, instruction: str | None = None) -> np.ndarray: ...
    def embed_texts(self, texts, instruction: str | None = None) -> np.ndarray: ...


def normalize_key(text: str) -> str:
    """Lower-case, keep only Latin/Thai letters and digits (for brand/model matching)."""
    return re.sub(r"[^0-9a-z฀-๿]", "", (text or "").lower())


class ImageRetriever:
    """score = w_image·sim(image) + w_caption·sim(caption) + category/brand boosts.

    Weights and boosts are starting values; tune them on the eval set
    (docs/architecture/IMAGE_RAG_DESIGN.md §4).
    """

    def __init__(
        self,
        embedder: ImageEmbedder,
        index: ImageVectorIndex,
        w_image: float = 0.6,
        w_caption: float = 0.4,
        category_boost: float = 0.05,
        brand_boost: float = 0.10,
        instruction: str = IMAGE_QUERY_INSTRUCTION,
    ):
        self.embedder = embedder
        self.index = index
        self.w_image, self.w_caption = w_image, w_caption
        self.category_boost, self.brand_boost = category_boost, brand_boost
        self.instruction = instruction

    def search(self, query: RetrievalQuery, top_k: int) -> list[dict]:
        pool = top_k * 4
        q_img = self.embedder.embed_images([query.image], instruction=self.instruction)[0]
        img_hits = self.index.best_by_sku(q_img, "image", pool)
        cap_hits: dict[str, tuple[float, dict]] = {}
        if query.text.strip():
            q_txt = self.embedder.embed_texts([query.text], instruction=self.instruction)[0]
            cap_hits = self.index.best_by_sku(q_txt, "caption", pool)

        a = query.analysis
        brand = normalize_key(a.brand_text)
        results = []
        for sku in img_hits.keys() | cap_hits.keys():
            meta = (img_hits.get(sku) or cap_hits[sku])[1]
            img_sim = img_hits[sku][0] if sku in img_hits else 0.0
            if cap_hits:
                cap_sim = cap_hits[sku][0] if sku in cap_hits else 0.0
                score = self.w_image * img_sim + self.w_caption * cap_sim
            else:
                score = img_sim
            if meta.get("category") == a.category_guess:
                score += self.category_boost
            if brand and brand == normalize_key(meta.get("brand", "")):
                score += self.brand_boost
            results.append({**meta, "score": round(min(score, 1.0), 4)})
        results.sort(key=lambda d: d["score"], reverse=True)
        return results[:top_k]


class MockCatalogRetriever:
    """TEMPORARY stand-in until the catalog is embedded.

    Scores by metadata only: category (0.55) + readable brand (0.25) +
    readable model text (0.10) + color word in the name (0.05 each, max 0.10).
    Enough to exercise every pipeline branch; says nothing about real accuracy.
    """

    def __init__(self, catalog_dir: Path):
        products, _ = load_catalog(catalog_dir, strict=False)
        self.products = [p for p in products if p.is_active]
        aliases = build_brand_aliases([p.brand for p in self.products])
        self._brand_keys = {normalize_key(v): normalize_key(c) for v, c in aliases.items()}

    def search(self, query: RetrievalQuery, top_k: int) -> list[dict]:
        a = query.analysis
        brand = self._brand_keys.get(normalize_key(a.brand_text), normalize_key(a.brand_text))
        model = normalize_key(a.model_text)
        scored = []
        for p in self.products:
            name = normalize_key(p.name)
            score = 0.55 if p.category == a.category_guess else 0.20
            if brand and (brand == normalize_key(p.brand_norm) or brand in name):
                score += 0.25
            if model and model in name:
                score += 0.10
            score += min(0.10, 0.05 * sum(1 for c in a.colors if normalize_key(c) and normalize_key(c) in name))
            scored.append({**p.to_metadata(), "score": round(min(score, 0.99), 3)})
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[:top_k]
