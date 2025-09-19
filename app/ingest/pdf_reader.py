import fitz  # PyMuPDF
import re
from dataclasses import dataclass
from typing import List, Tuple, Dict

FILTER_KEYS = [
    "images", "captions", "tables", "formulas",
    "headers", "footers", "footnotes"
]
DEFAULT_FILTERS = {k: (k == "images") for k in FILTER_KEYS}  # default: skip images

@dataclass
class Sentence:
    page_index: int
    text: str
    word_boxes: List[Tuple[float,float,float,float]]  # list of (x0,y0,x1,y1) per word

@dataclass
class Chunk:
    page_index: int
    order_idx: int
    section: str  # body | footnote | page_number | caption
    text: str
    boxes: List[Tuple[float,float,float,float]]

_DEF_SENT_SPLIT = re.compile(r"(?<=[.?!])\s+")
_CAPTION_PREFIX = re.compile(r"^(fig\.|figure|table|chart)\b", re.IGNORECASE)
_SUPERSCRIPT_MARK = re.compile(r"[¹²³⁴-⁹*†]")


def _is_header_footer(y0, y1, page_h):
    top = page_h * 0.10
    bot = page_h * 0.90
    return (y0 < top) or (y1 > bot)


def _is_formula(text):
    return bool(re.search(r"[=+\-*/^∑∫≈≤≥∞√∀∃→←↔ΔΩλμσπ{}\[\]()]", text)) and len(text) < 200


def _sentences_from_words(words: List[Tuple[str, Tuple[float,float,float,float], str]]):
    # words: (word, bbox, section)
    text = " ".join(w for (w, _b, _s) in words)
    if not text.strip():
        return []
    raw_sents = [s.strip() for s in re.split(_DEF_SENT_SPLIT, text) if s.strip()]
    boxes_only = [_b for (_w,_b,_s) in words]
    sections_only = [_s for (_w,_b,_s) in words]
    # approximate mapping by word counts
    wi = 0
    out = []
    for s in raw_sents:
        n = len(s.split())
        if n == 0:
            continue
        s_boxes = boxes_only[wi : wi + n]
        sec_slice = sections_only[wi : wi + n]
        # dominant section in the sentence
        section = max(set(sec_slice), key=sec_slice.count) if sec_slice else "body"
        out.append((s, s_boxes, section))
        wi += n
    return out


def _group_into_chunks(sent_triplets, max_chars=400, max_sents=3):
    # sent_triplets: list of (text, boxes, section)
    chunks = []
    cur_text = []
    cur_boxes = []
    cur_section = None
    for (txt, boxes, section) in sent_triplets:
        # start new chunk when section changes
        if cur_section is None:
            cur_section = section
        if section != cur_section or len(cur_text) >= max_sents or (sum(len(t) for t in cur_text) + len(txt) > max_chars):
            if cur_text:
                chunks.append((" ".join(cur_text), cur_boxes, cur_section))
            cur_text = []
            cur_boxes = []
            cur_section = section
        cur_text.append(txt)
        cur_boxes.extend(boxes)
    if cur_text:
        chunks.append((" ".join(cur_text), cur_boxes, cur_section))
    return chunks


def extract_sentences(pdf_path: str, user_filters: dict) -> List[Sentence]:
    doc = fitz.open(pdf_path)
    sentences: List[Sentence] = []

    for pno in range(doc.page_count):
        page = doc[pno]
        page_dict = page.get_text("dict")
        page_words = page.get_text("words")  # (x0,y0,x1,y1,"word", block_no, line_no, word_no)
        page_h = page.rect.height

        # table + image regions
        try:
            table_boxes = [t["bbox"] for t in page.find_tables().tables]
        except Exception:
            table_boxes = []
        image_boxes = []
        try:
            for img in page.get_image_info():
                if "bbox" in img:
                    image_boxes.append(img["bbox"])
        except Exception:
            pass

        def in_any_box(x0,y0,x1,y1, boxes):
            for bx0,by0,bx1,by1 in boxes:
                if x0>=bx0 and y0>=by0 and x1<=bx1 and y1<=by1:
                    return True
            return False

        buffer_words = []  # list of (text, bbox)
        for block in page_dict.get("blocks", []):
            if block.get("type", 0) == 1:  # image block
                if user_filters.get("images", False):
                    continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = span.get("text", "").strip()
                    if not t:
                        continue
                    (x0,y0,x1,y1) = span["bbox"]

                    if (user_filters.get("headers", False) or user_filters.get("footers", False)) and _is_header_footer(y0, y1, page_h):
                        continue
                    if user_filters.get("formulas", False) and _is_formula(t):
                        continue
                    if user_filters.get("tables", False) and in_any_box(x0,y0,x1,y1, table_boxes):
                        continue
                    if user_filters.get("images", False) and in_any_box(x0,y0,x1,y1, image_boxes):
                        continue

                    # collect words inside this span bbox
                    for w in page_words:
                        if w[0]>=x0 and w[1]>=y0 and w[2]<=x1 and w[3]<=y1:
                            buffer_words.append((w[4], (w[0],w[1],w[2],w[3])))

        # build text and sentence boundaries
        text = " ".join(w for (w, _b) in buffer_words)
        if not text.strip():
            continue
        raw_sents = [s.strip() for s in re.split(r"(?<=[.?!])\\s+", text) if s.strip()]

        # map words to sentences approximately (by word counts)
        words_only = [w for (w,_b) in buffer_words]
        boxes_only = [_b for (_w,_b) in buffer_words]
        wi = 0
        for s in raw_sents:
            n = len(s.split())
            if n == 0: continue
            s_boxes = boxes_only[wi : wi + n]
            wi += n
            sentences.append(Sentence(page_index=pno, text=s, word_boxes=s_boxes))

    return sentences


def extract_chunks(pdf_path: str) -> List[Chunk]:
    doc = fitz.open(pdf_path)
    chunks: List[Chunk] = []
    order = 0

    # first pass to gather per-page info and font sizes
    page_font_sizes: List[float] = []
    page_span_info: List[List[Dict]] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        d = page.get_text("dict")
        spans = []
        for b in d.get("blocks", []):
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    size = sp.get("size", 12.0)
                    text = sp.get("text", "").strip()
                    (x0,y0,x1,y1) = sp.get("bbox", (0,0,0,0))
                    spans.append({"text": text, "bbox": (x0,y0,x1,y1), "size": size})
        page_span_info.append(spans)
        if spans:
            sizes = [s["size"] for s in spans if s.get("size")]
            sizes.sort()
            mid = sizes[len(sizes)//2]
        else:
            mid = 12.0
        page_font_sizes.append(mid)

    # second pass: build words with section tags, then sentences, then chunks
    for pno in range(doc.page_count):
        page = doc[pno]
        page_h = page.rect.height
        d = page.get_text("dict")
        words_data = page.get_text("words")
        # image boxes for figure detection
        image_boxes = []
        try:
            for img in page.get_image_info():
                if "bbox" in img:
                    image_boxes.append(img["bbox"])
        except Exception:
            pass
        image_boxes = image_boxes or []

        # Build list of words with section tag
        words_tagged: List[Tuple[str, Tuple[float,float,float,float], str]] = []
        spans = page_span_info[pno]
        median_size = page_font_sizes[pno]

        # derive caption regions: text spans near images and with caption prefix
        caption_spans_boxes = []
        for sp in spans:
            txt = sp["text"]
            (x0,y0,x1,y1) = sp["bbox"]
            near_image = any(abs(y0 - ib[3]) < 100 or (y0 >= ib[1] and y0 <= ib[3] + 120) for ib in image_boxes)
            if near_image and _CAPTION_PREFIX.match(txt):
                caption_spans_boxes.append(sp["bbox"])

        def in_any_box(bx, boxes):
            x0,y0,x1,y1 = bx
            for bx0,by0,bx1,by1 in boxes:
                if x0>=bx0 and y0>=by0 and x1<=bx1 and y1<=by1:
                    return True
            return False

        # Iterate dict blocks to preserve order
        for b in d.get("blocks", []):
            if b.get("type", 0) == 1:  # image
                continue
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    txt = sp.get("text", "").strip()
                    if not txt:
                        continue
                    (sx0,sy0,sx1,sy1) = sp.get("bbox", (0,0,0,0))
                    size = sp.get("size", median_size)
                    # determine section
                    section = "body"
                    # page number heuristic
                    if (sy0 < page_h*0.10 or sy1 > page_h*0.90) and len(txt) <= 5 and re.fullmatch(r"[0-9ivxIVX]+", txt):
                        section = "page_number"
                    # footnote heuristic
                    elif sy1 > page_h*0.85 and size < (median_size * 0.9) and ( _SUPERSCRIPT_MARK.search(txt) or len(txt) < 120):
                        section = "footnote"
                    # caption near image
                    elif in_any_box((sx0,sy0,sx1,sy1), caption_spans_boxes) or (_CAPTION_PREFIX.match(txt) and any(abs(sy0 - ib[3]) < 100 for ib in image_boxes)):
                        section = "caption"
                    # else body

                    # collect words in this span
                    for w in words_data:
                        if w[0]>=sx0 and w[1]>=sy0 and w[2]<=sx1 and w[3]<=sy1:
                            words_tagged.append((w[4], (w[0],w[1],w[2],w[3]), section))

        # sentences per page
        sent_triplets = _sentences_from_words(words_tagged)  # (text, boxes, section)
        # chunking preserving section groups
        page_chunks = _group_into_chunks(sent_triplets)
        for (txt, boxes, section) in page_chunks:
            chunks.append(Chunk(page_index=pno, order_idx=order, section=section, text=txt, boxes=boxes))
            order += 1

    return chunks
