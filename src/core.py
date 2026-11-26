# -*- coding: utf-8 -*-
"""Logic thuần (không dùng Qt): tạo prompt theo loại ghi chú, đọc kết quả AI,
gọi Gemini, tìm ảnh, và thêm ghi chú vào bộ sưu tập Anki."""
from __future__ import annotations

import hashlib
import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .i18n import tr

VERSION = "1.8.10"
UA = "AICardFiller/1.1 (personal flashcard helper)"
ROLE_AI, ROLE_IMG, ROLE_SKIP, ROLE_AUDIO = "ai", "img", "skip", "audio"
ROLE_NAMES = {ROLE_AI: tr('AI điền chữ'), ROLE_IMG: tr('Ảnh'), ROLE_AUDIO: tr('Âm thanh (đọc từ ô khác)'), ROLE_SKIP: tr('Bỏ qua')}

IMG_RE = re.compile(r"(^|[_\W])(pic|img|image|photo|picture)([_\W]|$)|ảnh|hình", re.I)
SKIP_RE = re.compile(r"audio|sound|tts|mp3|voice|stroke|vector|svg|^mc_|^match", re.I)

DEFAULT_INTRO = (
    tr('Bạn là trợ lý chuyên tạo nội dung thẻ ghi nhớ (flashcard) Anki. Độ chính xác quan trọng hơn sự sáng tạo; điều gì không chắc thì để chuỗi rỗng.')
)

# ---------------------------------------------------------------- cấu hình sẵn cho bộ "Hán tự - Hub v5"
HUB_INTRO = (
    "Bạn là gia sư tiếng Trung giàu kinh nghiệm, dạy người học Việt Nam. Bạn tạo nội dung cho thẻ "
    "ghi nhớ (flashcard) Anki. Độ chính xác quan trọng hơn sự sáng tạo."
)
HUB_HINTS = {
    "Vocab": "giữ NGUYÊN VĂN từ gốc (chữ Hán giản thể) như trong danh sách.",
    "Pinyin": "pinyin có dấu thanh (kùcún), viết liền theo từ, không viết hoa trừ tên riêng.",
    "POS": "loại từ bằng tiếng Việt ngắn gọn (danh từ, động từ, tính từ, trạng từ, lượng từ, liên từ, giới từ, thán từ, thành ngữ).",
    "Vietnamese": "nghĩa tiếng Việt ngắn gọn, tự nhiên, 1-6 từ, chọn nghĩa phổ biến nhất; nếu có gợi ý nghĩa thì dùng đúng nghĩa đó.",
    "HanViet": "âm Hán Việt viết thường, cách nhau bằng dấu cách (vd. khố tồn). Không có âm Hán Việt tự nhiên thì để chuỗi rỗng.",
    "English": "nghĩa tiếng Anh ngắn gọn (1-4 từ), các nghĩa cách nhau bằng dấu chấm phẩy.",
    "French": "nghĩa tiếng Pháp ngắn gọn (1-4 từ).",
    "Radical": "đúng 1 ký tự bộ thủ chính của chữ Hán đầu tiên trong từ.",
    "Explain": "1-2 câu tiếng Việt giải thích cấu tạo chữ hoặc nghĩa gốc của từng chữ trong từ.",
    "Tip": "1 mẹo nhớ ngắn bằng tiếng Việt (gợi hình, liên tưởng); không bịa từ nguyên.",
    "Ex1_Chin": "câu ví dụ 1: tự nhiên, thực tế, dài 6-14 chữ Hán, PHẢI chứa nguyên văn từ Vocab, ngữ pháp đúng, từ khác trong câu dễ hơn hoặc bằng trình độ người học.",
    "Ex1_Pinyin": "pinyin có dấu thanh của đúng câu Ex1_Chin, có dấu câu.",
    "Ex1_Eng": "dịch tiếng Anh tự nhiên của Ex1_Chin.",
    "Ex1_Fr": "dịch tiếng Pháp tự nhiên của Ex1_Chin.",
    "Ex2_Chin": "câu ví dụ 2: KHÁC câu 1 và thuộc ngữ cảnh khác, cùng yêu cầu như Ex1_Chin, PHẢI chứa nguyên văn từ Vocab.",
    "Ex2_Pinyin": "pinyin có dấu thanh của đúng câu Ex2_Chin, có dấu câu.",
    "Ex2_Eng": "dịch tiếng Anh tự nhiên của Ex2_Chin.",
    "Ex2_Fr": "dịch tiếng Pháp tự nhiên của Ex2_Chin.",
    "Audio": "Vocab", "Ex1_Audio": "Ex1_Chin", "Ex2_Audio": "Ex2_Chin",
    "Pic": "ảnh minh họa cho NGHĨA của từ.",
    "Ex1_Pic": "ảnh minh họa cho nội dung câu ví dụ 1 (Ex1_Chin), khác hẳn ảnh của từ.",
    "Ex2_Pic": "ảnh minh họa cho nội dung câu ví dụ 2 (Ex2_Chin), khác hẳn ảnh câu 1.",
}
HUB_EXAMPLE = {
    "Vocab": "库存", "Pinyin": "kùcún", "POS": "danh từ", "Vietnamese": "hàng tồn kho", "HanViet": "khố tồn",
    "English": "inventory; stock", "French": "stock", "Radical": "广",
    "Explain": "库 (kho, có bộ 广 mái nhà) + 存 (cất giữ): hàng được cất giữ trong kho.",
    "Tip": "Kho (库) + cất (存) = hàng nằm im trong kho.",
    "Ex1_Chin": "我们的库存不多了。", "Ex1_Pinyin": "Wǒmen de kùcún bù duō le.",
    "Ex1_Eng": "Our stock is running low.", "Ex1_Fr": "Notre stock est presque épuisé.",
    "Ex2_Chin": "请每月检查一次库存。", "Ex2_Pinyin": "Qǐng měi yuè jiǎnchá yí cì kùcún.",
    "Ex2_Eng": "Please check the inventory once a month.", "Ex2_Fr": "Veuillez vérifier l'inventaire une fois par mois.",
    "Pic_Query": "warehouse shelves boxes", "Pic_Alt": "warehouse",
    "Ex1_Pic_Query": "nearly empty warehouse shelf", "Ex1_Pic_Alt": "empty shelf",
    "Ex2_Pic_Query": "worker counting stock clipboard", "Ex2_Pic_Alt": "inventory count",
}


def is_hub_type(field_names):
    s = set(field_names)
    return {"Vocab", "Pinyin", "Ex1_Chin", "Pic"} <= s


def guess_role(name):
    if IMG_RE.search(name):
        return ROLE_IMG
    if SKIP_RE.search(name):
        return ROLE_SKIP
    return ROLE_AI


def default_type_config(field_names):
    hub = is_hub_type(field_names)
    roles, hints = {}, {}
    for i, n in enumerate(field_names):
        roles[n] = ROLE_AI if i == 0 else guess_role(n)
        if hub and n in HUB_HINTS:
            hints[n] = HUB_HINTS[n]
    return {"intro": HUB_INTRO if hub else DEFAULT_INTRO, "roles": roles, "hints": hints}


def type_config(cfg_all, model_name, field_names):
    """Gộp cấu hình đã lưu với mặc định (ô mới/ô bị xóa tự khớp lại)."""
    base = default_type_config(field_names)
    saved = (cfg_all.get("types") or {}).get(model_name) or {}
    roles = dict(base["roles"])
    for k, v in (saved.get("roles") or {}).items():
        if k in roles and v in ROLE_NAMES:
            roles[k] = v
    roles[field_names[0]] = ROLE_AI  # ô đầu luôn là "từ" người dùng nhập
    hints = dict(base["hints"])
    hints.update({k: v for k, v in (saved.get("hints") or {}).items() if k in roles})
    return {"intro": saved.get("intro") or base["intro"], "roles": roles, "hints": hints}


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", s or "")).strip()


def build_example(field_names, tcfg, values):
    """Biến một thẻ có sẵn thành ví dụ mẫu cho prompt (bỏ âm thanh/SVG/ô bị bỏ qua)."""
    ex = {}
    roles = tcfg["roles"]
    for i, n in enumerate(field_names):
        r = roles.get(n)
        v = (values.get(n) or "").strip()
        if r == ROLE_AI:
            bad = "[sound:" in v or "<svg" in v.lower() or len(v) > 1500
            ex[n] = "" if (bad and i > 0) else v
        elif r == ROLE_IMG:
            q, a = img_keys(n)
            has = "<img" in v.lower()
            ex[q] = tr('[2-4 từ khóa tiếng Anh]') if has else ""
            ex[a] = tr('[1-2 từ đơn giản hơn]') if has else ""
    if not any(ex.get(n) for n in field_names if roles.get(n) == ROLE_AI):
        return None
    return ex


def img_keys(field):
    return field + "_Query", field + "_Alt"


# ---------------------------------------------------------------- prompt
IMG_RULES = (
    tr('Ảnh sẽ được tìm tự động trên kho ảnh miễn phí (Flickr/Wikimedia) theo từ khóa tiếng Anh rồi lấy ảnh đầu tiên, nên từ khóa phải giống cách người ta gắn nhãn một bức ảnh.\n1. Tự hỏi: "Một bức ảnh chụp thật có nhãn đúng cụm này không?" Nếu không thì đổi cụm khác.\n2. Query dài 2-4 từ, theo mẫu [chủ thể cụ thể] + [bối cảnh/vật đi kèm], ví dụ "bank teller counter", "delivery truck loading boxes".\n3. Chỉ dùng DANH TỪ và vật/cảnh nhìn thấy được. TRÁNH: động từ trừu tượng, cảm xúc đơn thuần, thì quá khứ, đại từ, tên riêng, thương hiệu, năm, sự kiện lịch sử (vd. "receiving a birthday gift" dễ ra ảnh lịch sử, hãy dùng "birthday gift box").\n4. Với ảnh minh họa cho một câu: bỏ ngữ pháp, chỉ lấy HÌNH CHÍNH của câu (ai/cái gì ở đâu). Các ảnh của cùng một thẻ phải có query khác hẳn nhau.\n5. Alt (dự phòng) phải ĐƠN GIẢN HƠN Query: 1-2 từ, một vật hoặc địa điểm phổ biến nhất.\n6. Khái niệm trừu tượng: dùng hình ẩn dụ dễ chụp (vd. growth -> plant seedling, strategy -> chess pieces).\n7. Từ khóa viết thường, chỉ chữ Latin, KHÔNG chứa chữ Hán, KHÔNG dấu câu, KHÔNG nhắc tới photo/image/picture.\n')
)


def parse_lines(text):
    """Mỗi dòng: 'từ | gợi ý nghĩa' (hoặc tab/dấu hai chấm). Trả [(từ, gợi ý)]."""
    out = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*•0123456789.) \t") if re.match(r"^\s*(\d+[.)]|[-*•])\s+", raw) else raw.strip()
        if not line:
            continue
        parts = re.split(r"\s*[|\t]\s*|\s+[-–—:]\s+|\s*[:：]\s*", line, maxsplit=1)
        w = parts[0].strip()
        h = parts[1].strip() if len(parts) > 1 else ""
        if w:
            out.append((w, h))
    return out


def looks_like_list(text):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    if len(lines) == 1:
        one = lines[0].strip()
        if "|" in one or "\t" in one:   # một mục có gợi ý: "từ | nghĩa"
            return len(re.split(r"[|\t]", one)[0].strip()) <= 24
        return len(one) <= 24 and " " not in one
    avg = sum(len(l.split("|")[0].strip()) for l in lines) / len(lines)
    return avg <= 24 and len(lines) >= 2


def build_prompt(field_names, tcfg, text, extra="", max_words=30, example=None):
    text = (text or "").strip()
    if not text:
        return ""
    first = field_names[0]
    roles, hints = tcfg["roles"], tcfg["hints"]
    ai_fields = [n for n in field_names if roles.get(n) == ROLE_AI]
    img_fields = [n for n in field_names if roles.get(n) == ROLE_IMG]
    keys = list(ai_fields)
    for f in img_fields:
        keys += list(img_keys(f))
    if looks_like_list(text):
        items = parse_lines(text)
        head = tr('## DANH SÁCH MỤC (%d mục)\nTạo ĐÚNG %d phần tử, theo đúng thứ tự dưới đây, không thêm, không bớt, không gộp:\n') % (len(items), len(items))
        head += "\n".join("%d. %s%s" % (i + 1, w, (tr('   <- gợi ý của người học: ') + h) if h else "") for i, (w, h) in enumerate(items))
        head += tr('\n\nNếu một mục có "gợi ý", hãy dùng đúng ý đó và viết nội dung theo gợi ý.')
    else:
        head = (tr('## VĂN BẢN NGUỒN\n"""\n%s\n"""\n\nHãy chọn tối đa %d mục đáng học nhất trong văn bản (bỏ tên riêng, số, và nội dung quá cơ bản), mỗi mục tạo một phần tử; ô "%s" giữ đúng dạng xuất hiện trong văn bản và nội dung phải đúng nghĩa trong ngữ cảnh đó.')) % (text, max_words, first)
    p = tr('# VAI TRÒ\n%s\n') % tcfg["intro"].strip()
    if extra.strip():
        p += tr('Bối cảnh/yêu cầu thêm của người học: %s\n') % extra.strip()
    p += "\n" + head + "\n\n"
    p += (tr('# ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC)\n- Chỉ trả về MỘT khối mã ```json duy nhất chứa MỘT JSON array hợp lệ. Không viết lời chào, giải thích hay chữ nào ngoài khối mã.\n- Mỗi phần tử là một object có ĐÚNG các khóa sau, giá trị đều là chuỗi (không có thì dùng ""): %s.\n- Dùng dấu nháy kép chuẩn, không xuống dòng bên trong giá trị, không dấu phẩy thừa ở cuối.\n\n')) % ", ".join(keys)
    p += tr('# QUY ĐỊNH TỪNG KHÓA\n')
    for n in ai_fields:
        h = hints.get(n, "").strip()
        if n == first and not h:
            h = tr('giữ NGUYÊN VĂN mục gốc như trong danh sách.')
        p += "- %s: %s\n" % (n, h or tr('nội dung phù hợp với tên ô "%s" và với các ô còn lại của thẻ.') % n)
    if img_fields:
        p += tr('\n# QUY TẮC TỪ KHÓA ẢNH (rất quan trọng)\n')
        for f in img_fields:
            q, a = img_keys(f)
            p += tr('- %s / %s: từ khóa tìm ảnh cho ô "%s" (%s)\n') % (q, a, f, hints.get(f, tr('ảnh minh họa phù hợp với thẻ')).strip().rstrip("."))
        p += "\n" + IMG_RULES
    p += tr('\n# NGUYÊN TẮC CHẤT LƯỢNG\n- Không bịa: không chắc thì để "".\n- Mọi nội dung tiếng Việt phải có dấu đầy đủ.\n')
    p += tr('- Kiểm tra lại trước khi trả lời: số phần tử trong array = số mục yêu cầu; JSON hợp lệ.\n')
    if example:
        p += tr('\n# VÍ DỤ MỘT PHẦN TỬ (lấy từ một thẻ thật của người học: hãy viết CÙNG phong cách, độ dài và định dạng; KHÔNG đưa chính ví dụ này vào kết quả)\n```json\n%s\n```\n') % json.dumps([example], ensure_ascii=False, indent=2)
    return p


# ---------------------------------------------------------------- đọc kết quả AI
def parse_ai_json(raw):
    s = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S | re.I)
    if m:
        s = m.group(1).strip()
    a, b = s.find("["), s.rfind("]")
    if a < 0 or b <= a:
        a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError(tr('Không thấy khối JSON trong nội dung đã dán.'))
    s = s[a:b + 1]
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r",\s*([\]}])", r"\1", s)
    data = json.loads(s)
    if isinstance(data, dict):
        data = data.get("cards") or data.get("items") or [data]
    if not isinstance(data, list):
        raise ValueError(tr('Kết quả không phải danh sách.'))
    return [d for d in data if isinstance(d, dict)]


def norm_rows(items, field_names, tcfg, hints_by_word=None):
    """Trả danh sách hàng: {'f': {field: text}, 'q': {imgfield: [query, alt]}}"""
    low = {n.lower(): n for n in field_names}
    first = field_names[0]
    img_fields = [n for n in field_names if tcfg["roles"].get(n) == ROLE_IMG]
    rows = []
    for d in items:
        d2 = {str(k).strip().lower(): v for k, v in d.items()}
        f = {}
        for n in field_names:
            if tcfg["roles"].get(n) == ROLE_AI:
                v = d2.get(n.lower(), "")
                f[n] = "" if v is None else str(v).strip()
        if not f.get(first):
            continue
        q = {}
        for fld in img_fields:
            ka, kb = img_keys(fld)
            q[fld] = [str(d2.get(ka.lower(), "") or "").strip(), str(d2.get(kb.lower(), "") or "").strip()]
        rows.append({"f": f, "q": q})
    return rows


def hub_helpers(rows, seed=7):
    """Điền MC_*/Match* (đáp án nhiễu) cho bộ Hub v5 từ các thẻ trong cùng lượt."""
    r = random.Random(seed)

    def sample(arr, n):
        arr = list(arr)
        r.shuffle(arr)
        return arr[:n]
    for i, w in enumerate(rows):
        others = [o for j, o in enumerate(rows) if j != i]
        f = w["f"]
        f.setdefault("MC_Meaning", "")
        if not f["MC_Meaning"]:
            f["MC_Meaning"] = "||".join(sample([o["f"].get("Vietnamese", "") for o in others if o["f"].get("Vietnamese") and o["f"].get("Vietnamese") != f.get("Vietnamese")], 3))
        if not f.get("MC_Hanzi"):
            same = sample([o["f"]["Vocab"] for o in others if len(o["f"]["Vocab"]) == len(f["Vocab"])], 99)
            rest = sample([o["f"]["Vocab"] for o in others if len(o["f"]["Vocab"]) != len(f["Vocab"])], 99)
            f["MC_Hanzi"] = "||".join((same + rest)[:3])
        if not f.get("MatchW"):
            pick = sample([o for o in others if o["f"].get("Vietnamese") and o["f"].get("Pinyin")], 4)
            f["MatchW"] = "||".join(o["f"]["Vocab"] for o in pick)
            f["MatchM"] = "||".join(o["f"]["Vietnamese"] for o in pick)
            f["MatchP"] = "||".join(o["f"]["Pinyin"] for o in pick)


# ---------------------------------------------------------------- mạng
def _ctx():
    try:
        return ssl.create_default_context()
    except Exception:  # pragma: no cover
        return None


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read()


class AIError(RuntimeError):
    """Lỗi khi gọi dịch vụ AI."""


class QuotaError(AIError):
    """Hết hạn mức hoặc bị giới hạn tốc độ (HTTP 429)."""


def _b64(data):
    import base64
    return base64.b64encode(data).decode("ascii")


def _post_json(url, body, headers, timeout, what):
    """POST JSON, thử lại một lần khi bị giới hạn tốc độ. Trả dict JSON."""
    hdrs = {"Content-Type": "application/json", "User-Agent": UA}
    hdrs.update(headers)
    raw = json.dumps(body).encode("utf-8")
    for attempt in range(2):
        req = urllib.request.Request(url, data=raw, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                err = json.loads(e.read().decode("utf-8")).get("error", {})
                msg = err.get("message", "") if isinstance(err, dict) else str(err)
            except Exception:  # noqa: BLE001
                pass
            if e.code == 429:
                if attempt == 0:
                    time.sleep(3)
                    continue
                raise QuotaError(tr('%s đã hết hạn mức hoặc đang bị giới hạn tốc độ (429). %s') % (what, msg[:160]))
            if e.code in (401, 403) or (e.code == 400 and "key" in msg.lower()):
                raise AIError(tr('Khóa API của %s không hợp lệ hoặc chưa được cấp quyền (%s).') % (what, e.code))
            raise AIError(tr('%s lỗi %s: %s') % (what, e.code, msg[:200]))
        except urllib.error.URLError as e:
            raise AIError(tr('Không kết nối được tới %s: %s') % (what, e.reason))
    raise AIError(tr('%s không phản hồi.') % what)


def gemini_text(key, prompt, model, json_mode=True, timeout=120, images=None):
    """Gọi Gemini. images: [(mime, bytes)] để đọc ảnh. Dùng đúng model được chọn."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
    parts = [{"inline_data": {"mime_type": m, "data": _b64(d)}} for m, d in (images or [])]
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.4, **({"responseMimeType": "application/json"} if json_mode else {})}}
    j = _post_json(url, body, {"x-goog-api-key": key}, timeout, "Gemini")
    cand = (j.get("candidates") or [{}])[0]
    t = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    if not t:
        raise AIError(tr('Gemini không trả về nội dung (%s).') % cand.get("finishReason", ""))
    return t


def openai_text(base_url, key, model, prompt, images=None, timeout=120):
    """Gọi API kiểu OpenAI (OpenAI, OpenRouter, Ollama chạy trên máy, LM Studio…)."""
    base = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    content = [{"type": "text", "text": prompt}]
    for m, d in (images or []):
        content.append({"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (m, _b64(d))}})
    body = {"model": model, "temperature": 0.4,
            "messages": [{"role": "user", "content": content if images else prompt}]}
    headers = {"Authorization": "Bearer " + key} if key else {}
    j = _post_json(base + "/chat/completions", body, headers, timeout, "API " + base.split("//")[-1].split("/")[0])
    msg = ((j.get("choices") or [{}])[0].get("message") or {}).get("content")
    if isinstance(msg, list):
        msg = "".join(p.get("text", "") for p in msg if isinstance(p, dict))
    if not msg:
        raise AIError(tr('Dịch vụ AI không trả về nội dung.'))
    return msg


def anthropic_text(key, model, prompt, images=None, timeout=120):
    """Gọi Claude (Anthropic Messages API)."""
    content = [{"type": "image", "source": {"type": "base64", "media_type": m, "data": _b64(d)}} for m, d in (images or [])]
    content.append({"type": "text", "text": prompt})
    body = {"model": model, "max_tokens": 8192, "messages": [{"role": "user", "content": content}]}
    j = _post_json("https://api.anthropic.com/v1/messages", body,
                   {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout, "Claude")
    t = "".join(p.get("text", "") for p in j.get("content", []) if isinstance(p, dict) and p.get("type") == "text")
    if not t:
        raise AIError(tr('Claude không trả về nội dung.'))
    return t


PROVIDER_LABELS = {"gemini": "Gemini", "openai": "OpenAI / OpenRouter / Ollama", "anthropic": "Claude"}
OPENAI_PRESETS = [
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash"),
    ("Ollama (trên máy bạn)", "http://localhost:11434/v1", "qwen2.5:7b"),
    ("LM Studio (trên máy bạn)", "http://localhost:1234/v1", "local-model"),
]


def provider_ready(cfg, name):
    """Dịch vụ này đã đủ thông tin để gọi chưa?"""
    if name == "gemini":
        return bool((cfg.get("gemini_key") or "").strip() and (cfg.get("gemini_model") or "").strip())
    if name == "openai":
        o = cfg.get("openai") or {}
        local = "localhost" in (o.get("base_url") or "") or "127.0.0.1" in (o.get("base_url") or "")
        return bool((o.get("model") or "").strip() and (o.get("base_url") or "").strip() and ((o.get("key") or "").strip() or local))
    if name == "anthropic":
        a = cfg.get("anthropic") or {}
        return bool((a.get("key") or "").strip() and (a.get("model") or "").strip())
    return False


def _call_provider(cfg, name, prompt, images, json_mode=True):
    if name == "gemini":
        return gemini_text((cfg.get("gemini_key") or "").strip(), prompt,
                           (cfg.get("gemini_model") or "").strip().removeprefix("models/"), images=images, json_mode=json_mode)
    if name == "openai":
        o = cfg.get("openai") or {}
        return openai_text(o.get("base_url"), (o.get("key") or "").strip(), (o.get("model") or "").strip(), prompt, images=images)
    if name == "anthropic":
        a = cfg.get("anthropic") or {}
        return anthropic_text((a.get("key") or "").strip(), (a.get("model") or "").strip(), prompt, images=images)
    raise AIError("provider?")


def ai_text(cfg, prompt, images=None, json_mode=True):
    """Gọi dịch vụ AI đang chọn. Nếu bị hết hạn mức (429) và bật 'tự đổi', thử dịch vụ khác đã cấu hình."""
    name = cfg.get("provider") or "gemini"
    try:
        return _call_provider(cfg, name, prompt, images, json_mode)
    except QuotaError as first:
        if cfg.get("auto_fallback", True):
            for other in PROVIDER_LABELS:
                if other != name and provider_ready(cfg, other):
                    try:
                        return _call_provider(cfg, other, prompt, images, json_mode)
                    except AIError:
                        continue
        raise first


def wav_from_pcm(pcm, rate=24000):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def gemini_tts(key, text, model="gemini-2.5-flash-preview-tts", voice="Kore", timeout=120):
    """Đọc text bằng giọng của Gemini (thử nghiệm). Trả bytes WAV."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    j = _post_json(url, body, {"x-goog-api-key": key}, timeout, "Gemini")
    import base64
    for p in ((j.get("candidates") or [{}])[0].get("content") or {}).get("parts", []):
        blob = p.get("inlineData") or p.get("inline_data")
        if blob and blob.get("data"):
            pcm = base64.b64decode(blob["data"])
            mime = blob.get("mimeType") or blob.get("mime_type") or ""
            m = re.search(r"rate=(\d+)", mime)
            return wav_from_pcm(pcm, int(m.group(1)) if m else 24000)
    raise AIError(tr('Gemini không trả về âm thanh. Thử đổi model đọc trong cấu hình.'))


def gemini_models(key):
    """Return generateContent-capable models from Google's live API."""
    out, token = set(), ''
    for _ in range(10):
        query = urllib.parse.urlencode({'pageSize': 100, **({'pageToken': token} if token else {})})
        request = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models?' + query,
                                         headers={'x-goog-api-key': key, 'User-Agent': UA})
        with urllib.request.urlopen(request, timeout=25, context=_ctx()) as response:
            data = json.loads(response.read().decode('utf-8'))
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                out.add(model['name'].removeprefix('models/'))
        token = data.get('nextPageToken', '')
        if not token:
            break
    return sorted(out)


_SEARCH_CACHE = {}


def _openverse(q, limit):
    u = "https://api.openverse.org/v1/images/?page_size=%d&category=photograph&mature=false&q=%s" % (limit, urllib.parse.quote(q))
    return [(r.get("thumbnail"), "Openverse") for r in json.loads(http_get(u, 10).decode("utf-8")).get("results", [])]


def _wikimedia(q):
    u = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit=15&gsrsearch=%s"
         "&prop=imageinfo&iiprop=url|mime&iiurlwidth=400") % urllib.parse.quote(q + " filetype:bitmap")
    out = []
    pages = (json.loads(http_get(u, 10).decode("utf-8")).get("query") or {}).get("pages", {})
    for p in sorted(pages.values(), key=lambda x: x.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        if str(ii.get("mime", "")).startswith(("image/jpeg", "image/png")):
            out.append((ii.get("thumburl"), "Wikimedia"))
    return out


def search_images(q, limit=18):
    """Openverse và Wikimedia tìm song song; đủ ảnh từ Openverse thì không chờ Wikimedia. Trả [{'thumb','src'}]."""
    if q in _SEARCH_CACHE:
        return _SEARCH_CACHE[q]
    from concurrent.futures import ThreadPoolExecutor
    ex = ThreadPoolExecutor(max_workers=2)
    fo, fw = ex.submit(_openverse, q, limit), ex.submit(_wikimedia, q)
    out, seen = [], set()

    def add(pairs):
        for u, s in pairs:
            if u and u not in seen:
                seen.add(u)
                out.append({"thumb": u, "src": s})
    try:
        add(fo.result())
    except Exception:  # noqa: BLE001
        pass
    if len(out) < 6:
        try:
            add(fw.result())
        except Exception:  # noqa: BLE001
            pass
    ex.shutdown(wait=False)
    if out:
        _SEARCH_CACHE[q] = out
    return out


def _first_download(cands):
    """Tải song song vài ứng viên đầu, lấy cái xong trước."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ex = ThreadPoolExecutor(max_workers=len(cands))
    futs = [ex.submit(http_get, r["thumb"], 10) for r in cands]
    try:
        for f in as_completed(futs):
            try:
                d = f.result()
                if d and len(d) > 100:
                    return d
            except Exception:  # noqa: BLE001
                continue
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return None


def find_image_bytes(queries, tries=3):
    """Thử lần lượt các query, trả (bytes, query, danh sách ứng viên)."""
    cands, used = [], ""
    for q in [x for x in queries if x]:
        c = search_images(q)
        if not c:
            continue
        cands, used = c, q
        data = _first_download(c[:tries])
        if data:
            return data, used, c
    return None, used, cands


# ---------------------------------------------------------------- mẫu cấu hình dùng sẵn
_VI = "viết bằng tiếng Việt, ngắn gọn, tự nhiên."
CFG_PRESETS = {
    "zh": {
        "label": "Từ vựng tiếng Trung (Hán)",
        "intro": "Bạn là gia sư tiếng Trung giàu kinh nghiệm, dạy người học Việt Nam. Bạn tạo nội dung cho thẻ ghi nhớ (flashcard) Anki. Độ chính xác quan trọng hơn sự sáng tạo.",
        "hints": [
            (r"pinyin|pin.?yin|phiên âm", "pinyin có dấu thanh, viết liền theo từ, không viết hoa trừ tên riêng."),
            (r"han.?viet|hán.?việt", "âm Hán Việt viết thường; không có âm tự nhiên thì để chuỗi rỗng."),
            (r"viet|nghĩa|meaning|vn", "nghĩa tiếng Việt ngắn gọn 1-6 từ, chọn nghĩa phổ biến nhất."),
            (r"eng", "nghĩa tiếng Anh ngắn gọn (1-4 từ)."),
            (r"pos|loại.?từ|từ.?loại", "loại từ bằng tiếng Việt (danh từ, động từ, tính từ, trạng từ…)."),
            (r"radical|bộ.?thủ", "đúng 1 ký tự bộ thủ chính của chữ Hán đầu tiên."),
            (r"tip|mẹo|mnemonic|nhớ", "1 mẹo nhớ ngắn bằng tiếng Việt; không bịa từ nguyên."),
            (r"ex.*(chin|zh|han|hán)|ví.?dụ|example|câu|sentence", "câu ví dụ tự nhiên, dài 6-14 chữ Hán, PHẢI chứa nguyên văn từ đang học, từ khác trong câu dễ hơn hoặc bằng trình độ người học."),
            (r"ex.*pin", "pinyin có dấu thanh của đúng câu ví dụ."),
            (r"ex.*(eng|en)\b|ex.*(vi|nghĩa)", "bản dịch tự nhiên của câu ví dụ."),
        ],
    },
    "ko": {
        "label": "Từ vựng tiếng Hàn",
        "intro": "Bạn là gia sư tiếng Hàn giàu kinh nghiệm, dạy người học Việt Nam. Bạn tạo nội dung cho thẻ ghi nhớ (flashcard) Anki. Độ chính xác quan trọng hơn sự sáng tạo.",
        "hints": [
            (r"roman|phiên âm|pronun", "phiên âm La-tinh (romaja) theo chuẩn Revised Romanization, viết thường."),
            (r"hanja|hán", "chữ Hán (Hanja) nếu từ có gốc Hán; không có thì để chuỗi rỗng."),
            (r"viet|nghĩa|meaning|vn", "nghĩa tiếng Việt ngắn gọn 1-6 từ, chọn nghĩa phổ biến nhất."),
            (r"eng", "nghĩa tiếng Anh ngắn gọn (1-4 từ)."),
            (r"pos|loại.?từ|từ.?loại", "loại từ bằng tiếng Việt (danh từ, động từ, tính từ…)."),
            (r"ex|ví.?dụ|example|câu|sentence", "câu ví dụ tự nhiên bằng tiếng Hàn, 5-12 từ, PHẢI chứa nguyên văn từ đang học, mức lịch sự 해요체."),
        ],
    },
    "en": {
        "label": "Từ vựng tiếng Anh",
        "intro": "Bạn là gia sư tiếng Anh giàu kinh nghiệm, dạy người học Việt Nam. Bạn tạo nội dung cho thẻ ghi nhớ (flashcard) Anki. Độ chính xác quan trọng hơn sự sáng tạo.",
        "hints": [
            (r"ipa|phiên âm|pronun", "phiên âm IPA giọng Mỹ, đặt trong dấu gạch chéo /…/."),
            (r"pos|loại.?từ|từ.?loại", "loại từ viết tắt (n., v., adj., adv.…)."),
            (r"viet|nghĩa|meaning|vn|định nghĩa|definition", "nghĩa tiếng Việt ngắn gọn 1-6 từ, chọn nghĩa phổ biến nhất."),
            (r"synonym|đồng nghĩa", "1-3 từ đồng nghĩa phổ biến, cách nhau dấu phẩy."),
            (r"ex|ví.?dụ|example|câu|sentence", "câu ví dụ tự nhiên, 8-16 từ, PHẢI chứa nguyên văn từ đang học, từ khác dễ hơn hoặc bằng trình độ người học."),
        ],
    },
    "cloze": {
        "label": "Cloze (câu có chỗ trống)",
        "intro": "Bạn là trợ lý tạo thẻ cloze cho Anki. Ô đầu là câu hoặc cụm do người học nhập (có thể đã có {{c1::…}}). Bạn chỉ bổ sung phần giải thích. Độ chính xác quan trọng hơn sự sáng tạo.",
        "hints": [
            (r"extra|back|giải|note|ghi.?chú|explain", "giải thích ngắn (1-2 câu) bằng tiếng Việt về nghĩa và cách dùng của phần được che."),
            (r"viet|nghĩa|meaning|dịch|translation", "bản dịch tiếng Việt tự nhiên của cả câu."),
        ],
    },
}


def apply_preset(field_names, key):
    """Trả (intro, hints{ô: gợi ý}) cho các ô của loại ghi chú, khớp theo tên ô. Ô đầu bỏ qua."""
    pr = CFG_PRESETS.get(key)
    if not pr:
        return None
    hints = {}
    for n in field_names[1:]:
        for rx, h in pr["hints"]:
            if re.search(rx, n, re.I):
                hints[n] = h
                break
    return pr["intro"], hints


def sanitize_type_config(data, field_names):
    """Kiểm tra dữ liệu cấu hình nhập từ file. Trả {'intro','roles','hints'} chỉ gồm ô có thật, hoặc ném ValueError."""
    if not isinstance(data, dict) or data.get("acf_type_config") != 1:
        raise ValueError(tr('Đây không phải file cấu hình của AI Card Filler.'))
    roles, hints = {}, {}
    for k, v in (data.get("roles") or {}).items():
        if k in field_names and v in ROLE_NAMES:
            roles[k] = v
    for k, v in (data.get("hints") or {}).items():
        if k in field_names and isinstance(v, str):
            hints[k] = v.strip()[:600]
    intro = data.get("intro") if isinstance(data.get("intro"), str) else ""
    if not roles and not hints and not intro.strip():
        raise ValueError(tr('File không có cấu hình nào khớp với các ô của loại ghi chú này.'))
    return {"intro": intro.strip()[:2000], "roles": roles, "hints": hints}


# ---------------------------------------------------------------- kiểm tra hàng
MAX_FIRST, MAX_OTHER = 80, 400


def validate_row(row, field_names, tcfg, all_rows=()):
    """Trả {ô: lý do} cho các ô nghi sai (trống, quá dài, trùng, câu ví dụ thiếu từ)."""
    out = {}
    first = field_names[0]
    f = row.get("f", {})
    for i, n in enumerate(field_names):
        if tcfg["roles"].get(n) != ROLE_AI:
            continue
        v = (f.get(n) or "").strip()
        if i > 0 and not v:
            out[n] = tr('Ô trống')
        elif len(v) > (MAX_FIRST if i == 0 else MAX_OTHER):
            out[n] = tr('Quá dài (%d ký tự)') % len(v)
    fv = (f.get(first) or "").strip()
    if fv and any(o is not row and (o.get("f", {}).get(first) or "").strip() == fv for o in all_rows):
        out[first] = tr('Trùng với một dòng khác trong bản xem trước')
    if is_hub_type(field_names):
        w = (f.get("Vocab") or "").strip()
        for k in ("Ex1_Chin", "Ex2_Chin"):
            v = (f.get(k) or "").strip()
            if w and v and w not in v and k not in out:
                out[k] = tr('Câu ví dụ không chứa từ “%s”') % w
        a, b = (f.get("Ex1_Chin") or "").strip(), (f.get("Ex2_Chin") or "").strip()
        if a and a == b:
            out["Ex2_Chin"] = tr('Giống hệt câu ví dụ 1')
    return out


# ---------------------------------------------------------------- chia lượt
def chunk_items(text, size):
    """Chia danh sách (mỗi dòng một mục) thành các khối văn bản nhỏ. Đoạn văn hoặc ít mục thì giữ nguyên một khối."""
    if not looks_like_list(text):
        return [text]
    items = parse_lines(text)
    size = max(2, int(size or 20))
    if len(items) <= size:
        return [text]
    chunks = [items[i:i + size] for i in range(0, len(items), size)]
    if len(chunks) > 1 and len(chunks[-1]) < 2:
        last = chunks.pop()
        chunks[-1] += last
    return ["\n".join(("%s | %s" % (w, h)) if h else w for w, h in c) for c in chunks]


def without_known(text, known):
    """Bỏ các dòng đã có trong 'known' (tập ô đầu) để chạy tiếp phần còn thiếu."""
    if not looks_like_list(text):
        return text
    keep = [(w, h) for w, h in parse_lines(text) if w not in known]
    return "\n".join(("%s | %s" % (w, h)) if h else w for w, h in keep)


# ---------------------------------------------------------------- tạo lại một dòng / điền thẻ có sẵn
def _ai_rules(field_names, tcfg, fields):
    first = field_names[0]
    out = ""
    for n in fields:
        h = (tcfg["hints"].get(n) or "").strip()
        if n == first and not h:
            h = tr('giữ NGUYÊN VĂN.')
        out += "- %s: %s\n" % (n, h or tr('nội dung phù hợp với tên ô "%s" và với các ô còn lại của thẻ.') % n)
    return out


def build_regen_prompt(field_names, tcfg, values, redo, instruction="", extra="", example=None):
    """Prompt tạo lại MỘT thẻ: giữ ô đầu, viết lại các ô trong 'redo' (ô chữ hoặc ô ảnh) theo yêu cầu ngắn."""
    roles = tcfg["roles"]
    first = field_names[0]
    text_redo = [n for n in redo if roles.get(n) == ROLE_AI and n != first]
    img_redo = [n for n in redo if roles.get(n) == ROLE_IMG]
    keys = [first] + text_redo
    for f in img_redo:
        keys += list(img_keys(f))
    have = {n: (values.get(n) or "").strip() for n in field_names if roles.get(n) == ROLE_AI and (values.get(n) or "").strip()}
    p = tr('# VAI TRÒ\n%s\n') % tcfg["intro"].strip()
    if extra.strip():
        p += tr('Bối cảnh/yêu cầu thêm của người học: %s\n') % extra.strip()
    p += tr('\n# THẺ HIỆN TẠI\n```json\n%s\n```\n') % json.dumps(have, ensure_ascii=False, indent=2)
    p += tr('\n# VIỆC CẦN LÀM\nViết lại CHỈ các khóa: %s. Giữ nguyên nghĩa của từ "%s" và nhất quán với các ô còn lại của thẻ.\n') % (", ".join(text_redo + img_redo), have.get(first, ""))
    if instruction.strip():
        p += tr('Yêu cầu của người học cho lần viết lại này: %s\n') % instruction.strip()
    p += tr('\n# ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC)\n- Chỉ trả về MỘT khối mã ```json duy nhất chứa MỘT JSON array có ĐÚNG 1 object với các khóa: %s. Giá trị đều là chuỗi.\n- Khóa "%s" giữ nguyên như thẻ hiện tại. Không viết chữ nào ngoài khối mã.\n\n') % (", ".join(keys), first)
    p += tr('# QUY ĐỊNH TỪNG KHÓA\n') + _ai_rules(field_names, tcfg, text_redo)
    if img_redo:
        p += tr('\n# QUY TẮC TỪ KHÓA ẢNH\n')
        for f in img_redo:
            q, a = img_keys(f)
            p += tr('- %s / %s: từ khóa tìm ảnh cho ô "%s" (%s)\n') % (q, a, f, tcfg["hints"].get(f, tr('ảnh minh họa phù hợp với thẻ')).strip().rstrip("."))
        p += "\n" + IMG_RULES
    p += tr('\n# NGUYÊN TẮC CHẤT LƯỢNG\n- Không bịa: không chắc thì để "".\n- Mọi nội dung tiếng Việt phải có dấu đầy đủ.\n')
    if example:
        p += tr('\n# VÍ DỤ MỘT PHẦN TỬ (một thẻ thật của người học: viết CÙNG phong cách; KHÔNG đưa chính ví dụ này vào kết quả)\n```json\n%s\n```\n') % json.dumps([example], ensure_ascii=False, indent=2)
    return p


def apply_regen(row, item, redo, field_names, tcfg):
    """Ghi kết quả AI vào hàng. Trả danh sách ô ảnh đã đổi từ khóa (cần tìm lại ảnh)."""
    d = {str(k).strip().lower(): v for k, v in (item or {}).items()}
    changed_img = []
    for n in redo:
        role = tcfg["roles"].get(n)
        if role == ROLE_AI and n != field_names[0] and n.lower() in d and d[n.lower()] is not None:
            row["f"][n] = str(d[n.lower()]).strip()
        elif role == ROLE_IMG:
            ka, kb = img_keys(n)
            q, a = str(d.get(ka.lower(), "") or "").strip(), str(d.get(kb.lower(), "") or "").strip()
            if q or a:
                row.setdefault("q", {})[n] = [q, a]
                row.get("img", {}).pop(n, None)
                changed_img.append(n)
    return changed_img


def build_fill_prompt(field_names, tcfg, items, extra="", example=None):
    """Prompt điền ô còn trống cho các thẻ có sẵn. items: [{'key','have':{ô:giá trị},'need':[ô]}]."""
    roles = tcfg["roles"]
    first = field_names[0]
    need_all = []
    for it in items:
        for n in it["need"]:
            if n not in need_all:
                need_all.append(n)
    text_need = [n for n in need_all if roles.get(n) == ROLE_AI]
    img_need = [n for n in need_all if roles.get(n) == ROLE_IMG]
    keys = [first] + text_need
    for f in img_need:
        keys += list(img_keys(f))
    p = tr('# VAI TRÒ\n%s\n') % tcfg["intro"].strip()
    if extra.strip():
        p += tr('Bối cảnh/yêu cầu thêm của người học: %s\n') % extra.strip()
    p += tr('\n# CÁC THẺ CẦN ĐIỀN (%d thẻ)\nMỗi phần tử có "key" (giá trị ô "%s"), "have" (các ô đã có, đừng viết lại) và "need" (các ô còn trống cần bạn điền).\n```json\n%s\n```\n') % (
        len(items), first, json.dumps([{"key": i["key"], "have": i["have"], "need": i["need"]} for i in items], ensure_ascii=False, indent=1))
    p += tr('\n# ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC)\n- Chỉ trả về MỘT khối mã ```json duy nhất chứa MỘT JSON array, ĐÚNG %d phần tử theo đúng thứ tự trên.\n- Mỗi phần tử là object có khóa "%s" (chép lại đúng "key") và CHỈ các khóa trong "need" của thẻ đó; khóa có thể dùng: %s. Giá trị đều là chuỗi.\n- Nhất quán với các ô trong "have". Không viết chữ nào ngoài khối mã.\n\n') % (len(items), first, ", ".join(keys))
    p += tr('# QUY ĐỊNH TỪNG KHÓA\n') + _ai_rules(field_names, tcfg, text_need)
    if img_need:
        p += tr('\n# QUY TẮC TỪ KHÓA ẢNH\n')
        for f in img_need:
            q, a = img_keys(f)
            p += tr('- %s / %s: từ khóa tìm ảnh cho ô "%s" (%s)\n') % (q, a, f, tcfg["hints"].get(f, tr('ảnh minh họa phù hợp với thẻ')).strip().rstrip("."))
        p += "\n" + IMG_RULES
    p += tr('\n# NGUYÊN TẮC CHẤT LƯỢNG\n- Không bịa: không chắc thì để "".\n- Mọi nội dung tiếng Việt phải có dấu đầy đủ.\n')
    if example:
        p += tr('\n# VÍ DỤ MỘT PHẦN TỬ (một thẻ thật của người học: viết CÙNG phong cách; KHÔNG đưa chính ví dụ này vào kết quả)\n```json\n%s\n```\n') % json.dumps([example], ensure_ascii=False, indent=2)
    return p


def fill_targets(col, note_ids, field_names, tcfg, want):
    """Chọn các ghi chú có ô trống cần điền. want: tập tên ô được phép điền. Trả [{'nid','key','have','need'}]."""
    roles = tcfg["roles"]
    out = []
    for nid in note_ids:
        note = col.get_note(nid)
        key = strip_html(note[field_names[0]])
        if not key:
            continue
        need, have = [], {}
        for n in field_names:
            v = note[n] if n in note else ""
            if roles.get(n) == ROLE_AI:
                if strip_html(v):
                    have[n] = strip_html(v)[:300]
                elif n != field_names[0] and n in want:
                    need.append(n)
            elif roles.get(n) == ROLE_IMG and n in want and "<img" not in v.lower():
                need.append(n)
        if need:
            out.append({"nid": nid, "key": key, "have": have, "need": need})
    return out


def match_fill(results, targets, first_field):
    """Ghép kết quả AI với thẻ theo giá trị ô đầu (rồi theo thứ tự nếu số lượng bằng nhau). Trả [(target, item hoặc None)]."""
    def norm(r):
        return {str(k).strip().lower(): v for k, v in r.items()}
    res = [norm(r) for r in results]
    by_key = {}
    for r in res:
        k = strip_html(str(r.get(first_field.lower(), "") or ""))
        if k and k not in by_key:
            by_key[k] = r
    out = []
    for i, t in enumerate(targets):
        item = by_key.get(t["key"])
        if item is None and len(res) == len(targets):
            item = res[i]
        out.append((t, item))
    return out


# ---------------------------------------------------------------- Anki
def create_note_type(col, name, fields, reverse=False):
    """Tạo loại ghi chú mới kiểu Basic: ô đầu ở mặt trước, các ô còn lại ở mặt sau. Trả id."""
    name = (name or "").strip()
    fields = [f.strip() for f in fields if f and f.strip()]
    if not name or not fields:
        raise ValueError("empty")
    if col.models.by_name(name):
        raise KeyError(name)
    mm = col.models
    m = mm.new(name)
    for f in fields:
        mm.add_field(m, mm.new_field(f))
    back = "".join("<div>{{%s}}</div>" % f for f in fields[1:])
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{%s}}" % fields[0]
    t["afmt"] = "{{FrontSide}}\n\n<hr id=answer>\n\n" + (back or "")
    mm.add_template(m, t)
    if reverse and len(fields) > 1:
        t2 = mm.new_template("Card 2")
        t2["qfmt"] = "{{%s}}" % fields[1]
        t2["afmt"] = "{{FrontSide}}\n\n<hr id=answer>\n\n{{%s}}" % fields[0]
        mm.add_template(m, t2)
    out = mm.add_dict(m) if hasattr(mm, "add_dict") else mm.add(m)
    return getattr(out, "id", None) or mm.id_for_name(name)


def clone_note_type(col, src_id, name):
    """Sao chép một loại ghi chú có sẵn (ô, mẫu thẻ, CSS) thành loại mới. Trả id."""
    name = (name or "").strip()
    if not name:
        raise ValueError("empty")
    if col.models.by_name(name):
        raise KeyError(name)
    import copy
    m = copy.deepcopy(col.models.get(src_id))
    m["name"] = name
    m["id"] = 0
    m["originalId"] = None
    out = col.models.add_dict(m) if hasattr(col.models, "add_dict") else col.models.add(m)
    return getattr(out, "id", None) or col.models.id_for_name(name)


def img_html(fname):
    return '<img src="%s">' % fname


def media_name(data):
    extension = 'gif' if data.startswith((b'GIF87a', b'GIF89a')) else 'jpg'
    return "hub_%s.%s" % (hashlib.sha1(data).hexdigest()[:12], extension)


def existing_firsts(col, model_id):
    out = set()
    for flds in col.db.list("select flds from notes where mid = ?", model_id):
        out.add(flds.split("\x1f")[0].strip())
    return out


def sound_tag(fname):
    return "[sound:%s]" % fname


def audio_name(data):
    return "acf_%s.wav" % hashlib.sha1(data).hexdigest()[:12]


def add_rows(col, model, deck_id, tags, rows, fields, images, audios=None):
    """rows: [{'f':..}], images/audios: [{field: bytes}] cùng chỉ số. Trả OpChangesWithCount."""
    reqs = []
    from anki.collection import AddNoteRequest
    audios = audios or [{} for _ in rows]
    for row, imgs, auds in zip(rows, images, audios):
        note = col.new_note(model)
        for n in fields:
            if n in row["f"]:
                note[n] = row["f"][n]
        for fld, data in (imgs or {}).items():
            if data and fld in note:
                note[fld] = img_html(col.media.write_data(media_name(data), data))
        for fld, data in (auds or {}).items():
            if data and fld in note:
                note[fld] = sound_tag(col.media.write_data(audio_name(data), data))
        note.tags = list(tags)
        reqs.append(AddNoteRequest(note=note, deck_id=deck_id))
    return col.add_notes(reqs)


def update_notes_fill(col, updates, tags=()):
    """updates: [{'nid', 'f': {ô: chữ}, 'img': {ô: bytes}}]. Chỉ ghi vào ô đang TRỐNG. Trả OpChanges (hoàn tác được)."""
    notes = []
    for u in updates:
        note = col.get_note(u["nid"])
        changed = False
        for n, v in (u.get("f") or {}).items():
            if n in note and not strip_html(note[n]) and (v or "").strip():
                note[n] = v.strip()
                changed = True
        for n, data in (u.get("img") or {}).items():
            if data and n in note and "<img" not in note[n].lower():
                note[n] = img_html(col.media.write_data(media_name(data), data))
                changed = True
        if changed:
            for t in tags:
                if t and t not in note.tags:
                    note.tags.append(t)
            notes.append(note)
    return col.update_notes(notes), len(notes)


PHOTO_PROMPT = tr('Đây là ảnh một trang tài liệu học ngoại ngữ (giáo trình, bài đọc, bảng từ vựng). Hãy liệt kê các từ hoặc cụm từ đáng học xuất hiện trong ảnh, mỗi dòng một mục theo dạng "từ | nghĩa hoặc gợi ý ngắn" (chỉ ghi phần nghĩa nếu trang có sẵn, nếu không thì chỉ ghi từ). Chép lại ĐÚNG như trong ảnh, không thêm từ không có trong ảnh, không đánh số, không giải thích, không viết thêm chữ nào khác. Nếu ảnh không có chữ đọc được thì trả về một dòng trống.')


def clean_vocab_lines(text):
    """Làm sạch kết quả đọc ảnh: bỏ rào mã, số thứ tự/gạch đầu dòng, dòng trống; tối đa 200 dòng."""
    s = (text or "").strip()
    m = re.search(r"```(?:\w+)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1)
    out = []
    for raw in s.splitlines():
        line = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s+", "", raw).strip()
        if line and line not in out:
            out.append(line)
    return "\n".join(out[:200])
