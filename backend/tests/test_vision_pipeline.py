"""Pipeline tests with a fake Qwen3-VL (no Ollama) and the mock retriever."""
import io
from pathlib import Path

import pytest
from PIL import Image

from app.ai.llm.qwen_vision import QwenVision, VisionModelError, _extract_json, encode_image
from app.ai.prompts.vision_prompt import ImageAnalysis, Intent, MatchLevel
from app.ai.vision.image_analyzer import ImageAnalyzer, crop_to_bbox
from app.ai.vision.vision_pipeline import (
    InvalidImageError,
    MockCatalogRetriever,
    PipelineSettings,
    VisionPipeline,
    load_upload,
)

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "catalog"
needs_catalog = pytest.mark.skipif(not CATALOG.exists(), reason="dataset not present")


class FakeVision:
    def __init__(self, **analysis):
        base = {"is_stationery": True, "intent": "find_similar", "category_guess": "scissors",
                "description": "กรรไกรด้ามแดง"}
        self._analysis = ImageAnalysis.model_validate({**base, **analysis})
        self.answer_calls = []

    def analyze(self, image, message=None):
        return self._analysis

    def answer(self, system_prompt, user_prompt, images=()):
        self.answer_calls.append((user_prompt, list(images)))
        return "LLM ANSWER"


def jpeg_bytes(size=(200, 100), fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, fmt)
    return buf.getvalue()


def pipeline(**analysis):
    vision = FakeVision(**analysis)
    settings = PipelineSettings(catalog_dir=CATALOG)
    return VisionPipeline(ImageAnalyzer(vision), MockCatalogRetriever(CATALOG), settings), vision


# --- upload validation -------------------------------------------------------
def test_upload_ok():
    assert load_upload(jpeg_bytes(), 1 << 20).size == (200, 100)


@pytest.mark.parametrize("data, max_bytes, msg", [
    (b"", 1 << 20, "empty"),
    (b"not an image", 1 << 20, "not a readable image"),
    (jpeg_bytes(), 10, "larger than"),
    (jpeg_bytes((20, 20)), 1 << 20, "too small"),
    (jpeg_bytes(fmt="BMP"), 1 << 20, "unsupported format"),
], ids=["empty", "garbage", "too-big", "too-small", "bmp"])
def test_upload_rejected(data, max_bytes, msg):
    with pytest.raises(InvalidImageError, match=msg):
        load_upload(data, max_bytes)


# --- crop / encode / json ----------------------------------------------------
def test_crop_to_bbox():
    img = Image.new("RGB", (1000, 500))
    cropped, ok = crop_to_bbox(img, [500, 200, 900, 800])
    # box 400x300 px + 5% of box size on each side → 440x330
    assert ok and cropped.size == (440, 330)


def test_crop_rejects_tiny_or_missing_box():
    img = Image.new("RGB", (1000, 500))
    assert crop_to_bbox(img, [0, 0, 100, 100]) == (img, False)
    assert crop_to_bbox(img, None) == (img, False)


def test_encode_image_keeps_aspect_and_flattens_alpha():
    img = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
    decoded = Image.open(io.BytesIO(__import__("base64").b64decode(encode_image(img))))
    assert decoded.size == (1024, 512) and decoded.mode == "RGB"
    assert decoded.getpixel((10, 10)) == (255, 255, 255)


def test_extract_json_tolerates_fences():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, model, messages, **kw):
        return self.responses.pop(0)


def test_qwen_vision_empty_answer_explains_thinking_budget():
    qv = QwenVision(client=FakeClient([{"message": {"content": "", "thinking": "..."}, "done_reason": "length"}]))
    with pytest.raises(VisionModelError, match="num_predict"):
        qv.analyze(Image.new("RGB", (64, 64)))


def test_qwen_vision_retries_bad_json():
    good = '{"is_stationery": true, "intent": "find_similar", "category_guess": "ruler", "description": "x"}'
    qv = QwenVision(client=FakeClient([{"message": {"content": "oops"}}, {"message": {"content": good}}]))
    assert qv.analyze(Image.new("RGB", (64, 64))).category_guess == "ruler"


# --- pipeline branches -------------------------------------------------------
@needs_catalog
def test_out_of_scope_skips_retrieval_and_llm():
    p, vision = pipeline(is_stationery=False, category_guess="other")
    r = p.run(jpeg_bytes(), "ราคาเท่าไหร่")
    assert r.intent == Intent.OUT_OF_SCOPE and r.products == [] and vision.answer_calls == []


@needs_catalog
def test_find_similar_category_only_is_similar():
    p, vision = pipeline()
    r = p.run(jpeg_bytes())
    assert r.intent == Intent.FIND_SIMILAR and r.match_level == MatchLevel.SIMILAR
    assert r.products and all(x["category"] == "scissors" for x in r.products)
    assert r.answer == "LLM ANSWER" and vision.answer_calls[0][1] == []


@needs_catalog
def test_price_stock_exact_is_deterministic():
    # "1448" appears in exactly one catalog name → verified EXACT, price answered from data
    p, vision = pipeline(category_guess="scissors", brand_text="Scotch", model_text="1448")
    r = p.run(jpeg_bytes(), "อันนี้ราคาเท่าไหร่")
    assert r.intent == Intent.PRICE_STOCK and r.match_level == MatchLevel.EXACT
    assert r.products[0]["sku"] == "b2s_2071790"
    assert "บาท" in r.answer and not r.needs_confirmation and vision.answer_calls == []


@needs_catalog
def test_shared_series_name_is_not_exact():
    # "Precision" names two Scotch scissors → not verified → SIMILAR, ask which one
    p, _ = pipeline(category_guess="scissors", brand_text="Scotch", model_text="Precision")
    r = p.run(jpeg_bytes(), "อันนี้ราคาเท่าไหร่")
    assert r.match_level == MatchLevel.SIMILAR and r.needs_confirmation and "บาท" not in r.answer


@needs_catalog
def test_price_stock_similar_asks_confirmation():
    p, _ = pipeline()
    r = p.run(jpeg_bytes(), "ราคาเท่าไหร่")
    assert r.needs_confirmation and "บาท" not in r.answer


@needs_catalog
def test_compare_sends_customer_then_catalog_images():
    p, vision = pipeline()
    r = p.run(jpeg_bytes(), "เทียบกับของในร้านหน่อย")
    assert r.intent == Intent.COMPARE and len(r.products) == 2
    assert len(vision.answer_calls[0][1]) == 3


@needs_catalog
def test_recommend_cheaper_excludes_reference_and_pricier():
    p, _ = pipeline(category_guess="scissors", brand_text="Scotch", model_text="Precision")
    r = p.run(jpeg_bytes(), "มีแบบที่ถูกกว่านี้ไหม")
    assert r.intent == Intent.RECOMMEND
    ref = MockCatalogRetriever(CATALOG).search(p._query(p.analyzer.analyze(Image.new("RGB", (64, 64)))), 1)[0]
    assert all(x["sku"] != ref["sku"] and x["price_thb"] < ref["price_thb"] for x in r.products)


@needs_catalog
def test_recommend_max_price_constraint():
    p, _ = pipeline(intent="recommend", constraints={"max_price": 50})
    r = p.run(jpeg_bytes(), "แนะนำหน่อย")
    assert all(x["price_thb"] <= 50 for x in r.products)


@needs_catalog
def test_result_serializes():
    p, _ = pipeline()
    d = p.run(jpeg_bytes()).to_dict()
    assert d["intent"] == "find_similar" and d["analysis"]["category_guess"] == "scissors"


# --- fast path (no VLM) --------------------------------------------------------
class CountingVision(FakeVision):
    def __init__(self, **analysis):
        super().__init__(**analysis)
        self.analyze_calls = 0

    def analyze(self, image, message=None):
        self.analyze_calls += 1
        return super().analyze(image, message)


class ScoredRetriever:
    """Returns fixed products with the given scores, best first."""

    def __init__(self, *scores):
        self.scores = scores

    def search(self, query, top_k):
        return [{
            "sku": f"s{i}", "name": f"สินค้า {i}", "category": "scissors", "category_th": "กรรไกร",
            "brand": "Scotch", "price_thb": 50.0 + i, "unit": None, "pack_qty": None, "unit_price": None,
            "price_date": "2026-09-28", "stock_qty": None, "image_url": "https://x", "source_url": "https://x",
            "image_path": "scissors/scotch_precision_1448_8in.jpg", "score": s,
        } for i, s in enumerate(self.scores)][:top_k]


def fast_pipeline(*scores, fast_path=True, **analysis):
    vision = CountingVision(**analysis)
    settings = PipelineSettings(catalog_dir=CATALOG, fast_path=fast_path)
    return VisionPipeline(ImageAnalyzer(vision), ScoredRetriever(*scores), settings), vision


def test_fast_path_high_score_is_similar_not_exact():
    # a high score alone never verifies the model (spec) → SIMILAR even at 0.92
    p, vision = fast_pipeline(0.92, 0.70, 0.60, 0.50, 0.40)
    r = p.run(jpeg_bytes())
    assert r.path == "fast" and r.match_level == MatchLevel.SIMILAR and r.intent == Intent.FIND_SIMILAR
    assert vision.analyze_calls == 0 and vision.answer_calls == []
    assert [x["sku"] for x in r.products] == ["s0", "s1", "s2"]  # ≥ tau_similar, max 3
    assert r.answer.startswith("สินค้าในร้านที่ใกล้เคียง") and "ยังยืนยันรุ่น" in r.answer
    assert r.analysis is None and "retrieve_fast" in r.timings_s


def test_fast_path_similar_wording():
    p, _ = fast_pipeline(0.70, 0.60)
    r = p.run(jpeg_bytes(), "มีแบบนี้ไหม")
    assert r.path == "fast" and r.match_level == MatchLevel.SIMILAR
    assert r.answer.startswith("สินค้าในร้านที่ใกล้เคียง")


def test_fast_path_price_asks_which_product():
    # unverified on the fast path → no direct price; list the options instead
    p, vision = fast_pipeline(0.95, 0.50)
    r = p.run(jpeg_bytes(), "อันนี้ราคาเท่าไหร่")
    assert r.path == "fast" and r.intent == Intent.PRICE_STOCK
    assert r.needs_confirmation and "บาท" not in r.answer and "s0" in r.answer
    assert vision.analyze_calls == 0


def test_fast_path_price_similar_asks_confirmation():
    p, _ = fast_pipeline(0.70, 0.65)
    r = p.run(jpeg_bytes(), "ราคาเท่าไหร่")
    assert r.path == "fast" and r.needs_confirmation and "บาท" not in r.answer


def test_fast_path_no_match_escalates_to_vlm():
    p, vision = fast_pipeline(0.30, 0.20)
    r = p.run(jpeg_bytes())
    assert r.path == "full" and vision.analyze_calls == 1
    assert "retrieve_fast" in r.timings_s and "analyze" in r.timings_s


def test_fast_path_not_used_for_compare():
    p, vision = fast_pipeline(0.95, 0.90)
    r = p.run(jpeg_bytes(), "เทียบกับของในร้านหน่อย")
    assert r.path == "full" and vision.analyze_calls == 1 and r.intent == Intent.COMPARE


def test_fast_path_can_be_disabled():
    p, vision = fast_pipeline(0.95, fast_path=False)
    r = p.run(jpeg_bytes())
    assert r.path == "full" and vision.analyze_calls == 1


def test_upload_codes_and_pixel_limit():
    with pytest.raises(InvalidImageError) as e:
        load_upload(jpeg_bytes((200, 100)), 1 << 20, max_pixels=10_000)
    assert e.value.code == "IMAGE_TOO_LARGE"
    with pytest.raises(InvalidImageError) as e:
        load_upload(b"nope", 1 << 20)
    assert e.value.code == "UNSUPPORTED_MEDIA_TYPE"


# --- exact = model verified from the photo ---------------------------------------
from app.ai.vision.vision_pipeline import verify_exact  # noqa: E402


def cand(sku, name, score, brand="Pentel"):
    return {"sku": sku, "name": name, "brand": brand, "score": score}


def reading(model="", brand=""):
    return ImageAnalysis(is_stationery=True, intent="find_similar", category_guess="gel_pen",
                         description="x", model_text=model, brand_text=brand)


@pytest.mark.parametrize("cands, model, brand, expected", [
    ([cand("a", "ปากกาเจล Energel BL667", 0.8), cand("b", "ปากกา Feel-it", 0.7)], "BL-667", "PENTEL", "a"),
    ([cand("a", "ปากกา Feel-it", 0.8), cand("b", "ปากกาเจล Energel BL667", 0.6)], "bl667", "", "b"),  # promoted
    ([cand("a", "เทป 500 1/2 นิ้ว", 0.9), cand("b", "เทป 500 3/4 นิ้ว", 0.8)], "500", "", None),     # ambiguous
    ([cand("a", "ปากกาเจล Energel BL667", 0.4)], "BL667", "", None),                                  # score too low
    ([cand("a", "ปากกาเจล Energel BL667", 0.9)], "BL667", "Uni", None),                               # brand contradicts
    ([cand("a", "ปากกา A5", 0.9)], "A5", "", None),                                                   # too short to identify
    ([cand("a", "ปากกาเจล Energel BL667", 0.9)], "", "Pentel", None),                                 # brand alone is not enough
])
def test_verify_exact(cands, model, brand, expected):
    hit = verify_exact(cands, reading(model, brand), PipelineSettings(catalog_dir=CATALOG))
    assert (hit["sku"] if hit else None) == expected


class NamedRetriever:
    def __init__(self, items):
        self.items = items

    def search(self, query, top_k):
        return [{**ScoredRetriever(s).search(query, 1)[0], "sku": sku, "name": name, "brand": "Pentel"}
                for sku, name, s in self.items][:top_k]


def test_full_path_promotes_verified_product_to_top():
    vision = CountingVision(model_text="BL667", brand_text="Pentel", category_guess="gel_pen")
    retriever = NamedRetriever([("x", "ปากกา Feel-it", 0.80), ("y", "ปากกาเจล Energel BL667", 0.62)])
    p = VisionPipeline(ImageAnalyzer(vision), retriever, PipelineSettings(catalog_dir=CATALOG, fast_path=False))
    r = p.run(jpeg_bytes(), with_answer=False)
    assert r.path == "full" and r.match_level == MatchLevel.EXACT
    assert [x["sku"] for x in r.products][:2] == ["y", "x"]


def test_qwen_vision_ocr_parses_segments():
    content = '{"segments": [{"text": " Pentel "}, {"text": ""}, {"text": "BL667"}]}'
    qv = QwenVision(client=FakeClient([{"message": {"content": "oops"}}, {"message": {"content": content}}]))
    assert qv.ocr(Image.new("RGB", (64, 64))) == ["Pentel", "BL667"]  # retried once, blanks dropped


def test_qwen_vision_ocr_gives_up_after_retries():
    qv = QwenVision(client=FakeClient([{"message": {"content": "x"}}] * 2))
    with pytest.raises(VisionModelError, match="OCR"):
        qv.ocr(Image.new("RGB", (64, 64)))


class RecordingClient(FakeClient):
    def __init__(self, responses):
        super().__init__(responses)
        self.options = []

    def chat(self, model, messages, **kw):
        self.options.append(kw.get("options"))
        return super().chat(model, messages, **kw)


def test_qwen_vision_passes_num_ctx_only_when_set():
    ok = {"message": {"content": '{"segments": []}'}}
    default, wide = RecordingClient([ok]), RecordingClient([ok])
    QwenVision(client=default).ocr(Image.new("RGB", (64, 64)))
    QwenVision(client=wide, num_ctx=16384).ocr(Image.new("RGB", (64, 64)))
    assert "num_ctx" not in default.options[0] and wide.options[0]["num_ctx"] == 16384


# --- no match → "did you mean?" ---------------------------------------------------
def none_pipeline(*scores, **analysis):
    vision = CountingVision(**analysis)
    settings = PipelineSettings(catalog_dir=CATALOG)  # tau_similar 0.55, tau_suggest 0.47, 3 suggestions
    return VisionPipeline(ImageAnalyzer(vision), ScoredRetriever(*scores), settings), vision


def test_no_match_offers_top3_did_you_mean():
    p, vision = none_pipeline(0.53, 0.52, 0.50, 0.48, 0.20)
    r = p.run(jpeg_bytes())
    assert r.match_level == MatchLevel.NONE and r.products == []
    assert [x["sku"] for x in r.suggestions] == ["s0", "s1", "s2"]
    assert r.answer.startswith("ไม่พบสินค้าที่ตรงกับในรูปค่ะ หมายถึงสินค้าเหล่านี้หรือเปล่าคะ?")
    assert "s0" in r.answer and "50 บาท" in r.answer
    assert r.needs_confirmation and vision.answer_calls == []  # template, no second LLM call


def test_no_match_skips_products_below_suggest_floor():
    p, _ = none_pipeline(0.46, 0.10)  # e.g. a random-noise photo scored 0.46
    r = p.run(jpeg_bytes())
    assert r.suggestions == [] and r.answer == "ขออภัยค่ะ ไม่พบสินค้าที่คล้ายกับในรูปในร้าน"
    assert not r.needs_confirmation


def test_no_match_price_question_asks_which_suggestion():
    p, _ = none_pipeline(0.52, 0.50, 0.30)
    r = p.run(jpeg_bytes(), "ราคาเท่าไหร่")
    assert r.intent == Intent.PRICE_STOCK and r.needs_confirmation
    assert r.answer.startswith("ไม่พบสินค้าที่ตรงกับในรูป") and [x["sku"] for x in r.suggestions] == ["s0", "s1"]


def test_not_stationery_gets_no_suggestions():
    p, _ = none_pipeline(0.53, 0.50, is_stationery=False, category_guess="other")
    r = p.run(jpeg_bytes())
    assert r.intent == Intent.OUT_OF_SCOPE and r.suggestions == [] and r.products == []


def test_no_escalation_gives_did_you_mean_on_fast_path():
    vision = CountingVision()
    settings = PipelineSettings(catalog_dir=CATALOG, escalate_no_match=False)
    p = VisionPipeline(ImageAnalyzer(vision), ScoredRetriever(0.53, 0.52, 0.50, 0.48), settings)
    r = p.run(jpeg_bytes())
    assert r.path == "fast" and r.match_level == MatchLevel.NONE and vision.analyze_calls == 0
    assert [x["sku"] for x in r.suggestions] == ["s0", "s1", "s2"] and r.products == []
    assert r.answer.startswith("ไม่พบสินค้าที่ตรงกับในรูปค่ะ") and r.needs_confirmation
