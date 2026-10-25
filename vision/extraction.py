"""給決策 AI 用的影像提取：使用者附上的影像（螢幕框選、上傳）＋使用者的說明 → 結構化的文字。

決策 AI（main session）看不到原圖，只看得到這裡產生的文字，要拿它回答使用者、或當成觸發技能的線索
（影像裡的錯誤訊息、機器人編號、容器、topic 可以直接當技能的參數）。所以提取的順序與格式由程式保證
（format=extraction_schema(張數)），不是靠模型自己遵守範本——跟工具回傳的任務導向擷取同一個想法：
  每張影像：文字（逐字）→ 畫面的系統性描述（沒有文字時要完整）→ 明確的個體 → 個體以外的背景
  全部影像：影像之間的關係 → 可以拿去查系統的線索 → 看不清楚的地方 → 針對使用者說明的重點 → 檢索清單的描述
JSON 的欄位順序就是模型生成的順序：重點（focus）放最後，讓它根據已經提取出來的內容回答，而不是先下結論
再找證據；排版（render_extraction）時才把重點移到最上面，決策 AI 第一眼就知道這些資訊跟使用者要的事有什麼關係。

使用者的說明不是「回答完就好」的問題，它有三個用途：決定關注方向（相關的文字與細節優先、完整地提取）、
告訴視覺模型畫面裡某個東西是什麼（例如「左邊那台是 amr_03」）、補充屬性。使用者給的名稱標〔使用者說明〕，
決策 AI 才分得出哪些是影像裡讀到的、哪些是使用者告訴系統的。
"""
import json
import re

from agent_core import prompt_files

from .inference import DEFAULT_OPTIONS, analyze


def _v(key, /, **fields):
    """prompts/vision/extraction.md 的一則：給視覺模型的 system 與 user 訊息。"""
    return prompt_files.load("vision/extraction.md", key, **fields)


NAME_SOURCES = ["影像中的文字", "使用者說明", "外觀判斷"]

# 長度上限由 schema 硬性規定（Ollama 的結構化輸出會照 minItems／maxItems／maxLength 生成）：實測 e4b 遇到沒有文字的
# 影像時，texts 會一直輸出空字串直到 num_predict 用完，JSON 斷掉、七千字的殘骸差點交給決策 AI；背景欄也寫過四百字的
# 重複推論。陣列與字串都有上限，就一定是合法的 JSON。字串上限刻意放寬（正常內容碰不到），只防失控；真的碰到時
# 排版會退回最後一個完整的句子（_prose）。images 的張數固定等於附上的張數，模型不會少描述一張，也不會把一張拆成兩筆。
TEXTS_MAX, ENTITIES_MAX, CLUES_MAX, UNCLEAR_MAX = 40, 20, 12, 8
LIMITS = {"kind": 30, "text": 300, "overview": 600, "name": 60, "details": 250, "background": 200,
          "relations": 300, "clue_kind": 20, "clue_value": 300, "unclear": 200, "focus": 400, "index_hint": 200}


def extraction_schema(n_images):
    """這次呼叫的 JSON schema（format=）：欄位順序＝生成順序；images 剛好 n_images 筆，每個陣列都有上限。"""
    def text(key):
        return {"type": "string", "maxLength": LIMITS[key]}

    def texts(key, max_items):
        return {"type": "array", "items": text(key), "maxItems": max_items}
    entity = {
        "type": "object",
        "properties": {"name": text("name"), "name_from": {"type": "string", "enum": NAME_SOURCES}, "details": text("details")},
        "required": ["name", "name_from", "details"],
    }
    image = {
        "type": "object",
        "properties": {
            "kind": text("kind"),
            "texts": texts("text", TEXTS_MAX),
            "overview": text("overview"),
            "entities": {"type": "array", "items": entity, "maxItems": ENTITIES_MAX},
            "background": text("background"),
        },
        "required": ["kind", "texts", "overview", "entities", "background"],
    }
    clue = {"type": "object", "properties": {"kind": text("clue_kind"), "value": text("clue_value")}, "required": ["kind", "value"]}
    return {
        "type": "object",
        "properties": {
            "images": {"type": "array", "items": image, "minItems": n_images, "maxItems": n_images},
            "relations": text("relations"),
            "clues": {"type": "array", "items": clue, "maxItems": CLUES_MAX},
            "unclear": texts("unclear", UNCLEAR_MAX),
            "focus": text("focus"),
            "index_hint": text("index_hint"),
        },
        "required": ["images", "relations", "clues", "unclear", "focus", "index_hint"],
    }


EXTRACTION_SYSTEM_PROMPT = _v("system")   # 匯入時讀的內容（給沿用這個名稱的程式）；extract() 每次呼叫都重讀 prompts/vision/

# 結構化輸出失敗（JSON 解析不了）時的退路：同樣的提取順序，改成純文字格式再問一次，
# 決策 AI 拿到的仍是看得懂的一段文字，而不是一段斷掉的 JSON。
FALLBACK_SYSTEM_PROMPT = _v("fallback_system")

# 結構化輸出比較長；num_predict 是最後一道防線（陣列與字串都有上限，一般碰不到）
EXTRACTION_OPTIONS = {**DEFAULT_OPTIONS, "num_predict": 3072}


def describe_sources(items):
    """VisionSession 的影像項目（{"img", "source"}）→ 給視覺模型的來源說明，例如「螢幕框選的區域（1280×720）」。
    框選的是螢幕的一部分，模型才不會把它當成完整畫面去猜外面的內容；上傳的檔名常帶資訊（amr03_error.png）。"""
    out = []
    for it in items:
        img, source = it.get("img"), str(it.get("source") or "")
        size = _v("size", w=img.width, h=img.height) if hasattr(img, "width") else ""
        if source == "screen":
            out.append(_v("source_screen", size=size))
        elif source.startswith("file:"):
            out.append(_v("source_file", name=source[len("file:"):], size=size))
        else:
            out.append(_v("source_image", size=size))
    return out


def build_extraction_prompt(user_text, sources):
    """交給視覺模型的 user 訊息：附上了哪些影像、使用者的說明（沒有說明時明講，模型就照順序完整提取）。"""
    lines = [_v("images_header", count=len(sources))]
    lines += [_v("image_item", n=i, desc=desc) for i, desc in enumerate(sources, 1)]
    user_text = (user_text or "").strip()
    if user_text:
        lines += ["", _v("user_text_header"), user_text]
    else:
        lines += ["", _v("no_user_text")]
    return "\n".join(lines)


_SENTENCE_END_RE = re.compile(r"(?<=[。！？])")
# 模型偶爾在欄位裡寫自我檢查的註記，例如「(總字數：59/60字，符合要求。)」：整段括號拿掉
_META_NOTE_RE = re.compile(r"[（(【{][^（()）【】{}]*?(?:字數|字以內|符合要求|限制字數|已控制|自我檢查)[^（()）【】{}]*?[）)】}]")


def _text(value):
    return " ".join(str(value or "").split())


def _prose(value, limit_key=None):
    """描述性欄位（畫面、個體、背景、重點…）：收空白、拿掉自我檢查的註記、去掉重複的句子——實測小模型偶爾在一個
    欄位裡把同一段推論重複寫兩三次，去重之後內容不變、長度回到正常。寫到 schema 的字串上限（被硬切在半句）時，
    退回最後一個完整的句子；整段沒有句號就原樣保留。逐字照抄的 texts 不經過這裡。"""
    value = _text(value)
    if limit_key and len(value) >= LIMITS[limit_key]:
        cut = max(value.rfind(p) for p in "。！？")
        value = value[:cut + 1] if cut > 0 else value
    sentences = [x.strip() for x in _SENTENCE_END_RE.split(_META_NOTE_RE.sub("", value)) if x.strip()]
    return "".join(dict.fromkeys(sentences))


def _items(value):
    return [v for v in (value if isinstance(value, list) else []) if v not in (None, "", {})]


def render_extraction(data, n_images):
    """extraction_schema 的 JSON → 給決策 AI 與畫面卡片的固定文字區塊。重點放最上面；每張影像依「文字 → 畫面 →
    個體 → 背景」；線索與無法判斷放最後。模型描述的張數跟附上的不一樣時照實註明，不自己補。"""
    out = []
    focus = _prose(data.get("focus"), "focus")
    if focus:
        out.append(f"重點：{focus}")
    images = [x for x in _items(data.get("images")) if isinstance(x, dict)]
    for i, img in enumerate(images, 1):
        kind = _text(img.get("kind"))
        out.append(f"影像 {i}" + (f"（{kind}）" if kind else ""))
        texts = [_text(t) for t in _items(img.get("texts")) if _text(t)]
        if texts:
            out.append("- 文字（照抄）：")
            # 單行寫到 schema 上限時是被硬切的：標明後面沒抄到，決策 AI 才不會把半行當成完整的一行
            out += [f"  「{t}」" + ("（這一行後面未抄錄）" if len(t) >= LIMITS["text"] else "") for t in texts]
        else:
            out.append("- 文字：沒有看到文字")
        overview = _prose(img.get("overview"), "overview")
        if overview:
            out.append(f"- 畫面：{overview}")
        entities = [e for e in _items(img.get("entities")) if isinstance(e, dict) and _text(e.get("name"))]
        if entities:
            out.append("- 個體：")
            for e in entities:
                source = _text(e.get("name_from"))
                details = _prose(e.get("details"), "details")
                out.append(f"  - {_text(e.get('name'))}" + (f"〔{source}〕" if source else "") + (f"：{details}" if details else ""))
        background = _prose(img.get("background"), "background")
        if background:
            out.append(f"- 背景：{background}")
    if len(images) != n_images:
        out.append(f"（附上 {n_images} 張影像，視覺模型描述了 {len(images)} 張）")
    relations = _prose(data.get("relations"), "relations")
    if relations and n_images > 1:
        out.append(f"影像之間：{relations}")
    clues = [c for c in _items(data.get("clues")) if isinstance(c, dict) and _text(c.get("value"))]
    if clues:
        out.append("可以拿去查的線索（照抄）：")
        out += [f"- {_text(c.get('kind')) or '線索'}：{_text(c.get('value'))}" for c in clues]
    unclear = [x for x in (_prose(u, "unclear") for u in _items(data.get("unclear"))) if x]
    if unclear:
        out.append("無法判斷：")
        out += [f"- {u}" for u in unclear]
    return "\n".join(out)


def index_hint(data, user_text, text):
    """這次附圖分析在工具使用檢索清單上的描述：視覺模型寫的 index_hint；沒有（純文字退路）就用使用者的說明＋提取結果的
    第一行（通常是「重點：…」）組一句。整句照存、不截斷（跟工具回傳的描述同一個原則）。"""
    hint = _text((data or {}).get("index_hint"))
    if hint:
        return hint
    first = next((ln.strip() for ln in str(text or "").splitlines() if ln.strip()), "")
    first = first[len("重點："):] if first.startswith("重點：") else first
    return f"{_text(user_text) or '附圖（沒有說明）'}：{_text(first)}"


def extract(images, user_text="", sources=None, model=None, timeout=None):
    """對 images（PIL.Image 或 bytes 的列表）做給決策 AI 用的結構化提取。回傳 (text, data)：text 是排好的文字區塊，
    data 是模型的 JSON。JSON 解析不了時用純文字格式再問一次（FALLBACK_SYSTEM_PROMPT），回傳 (那段文字, None)。
    連線、逾時等失敗照樣拋 VisionError。"""
    images = list(images or [])
    sources = list(sources or []) or [_v("source_image", size="")] * len(images)
    prompt = build_extraction_prompt(user_text, sources)
    raw = analyze(images, prompt, model=model, timeout=timeout, system_prompt=_v("system"),
                  options=EXTRACTION_OPTIONS, format=extraction_schema(len(images)))
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if isinstance(data, dict):
        text = render_extraction(data, len(images))
        if text:
            return text, data
    return analyze(images, prompt, model=model, timeout=timeout, system_prompt=_v("fallback_system")), None
