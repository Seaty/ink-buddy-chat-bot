"""Embedding entry points shared by the AI layer.

Image RAG uses Qwen3-VL-Embedding (2048-d, image + text in one space).
Text RAG uses BGE-M3 (bge_embedding.py). The two vector spaces are not
comparable — never store or search them in the same table.

torch/transformers are imported lazily, so importing this module stays cheap.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .qwen3_vl_embedding import Qwen3VLEmbedding

# Query-side instruction for customer photos / descriptions. Catalog items are
# embedded without an instruction (model default).
IMAGE_QUERY_INSTRUCTION = "Retrieve the stationery product in the store catalog that matches this item."


@lru_cache(maxsize=1)
def get_image_embedder(
    model_name_or_path: str = "Qwen/Qwen3-VL-Embedding-2B",
    device: str | None = None,
    dim: int = 2048,
    max_pixels: int = 800 * 800,
) -> "Qwen3VLEmbedding":
    """Process-wide instance; the model loads on first call."""
    from .qwen3_vl_embedding import Qwen3VLEmbedding

    return Qwen3VLEmbedding(model_name_or_path, device=device, dim=dim, max_pixels=max_pixels)
