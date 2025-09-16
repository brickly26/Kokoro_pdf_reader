import fitz  # PyMuPDF
import re
from dataclasses import dataclass
from typing import List, Tuple

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

def _is_header_footer(y0, y1, page_h):
    top = page_h * 0.10
    bot = page_h * 0.90
    return (y0 < top) or (y1 > bot)

def _is_formula(text):
    return bool(re.search(r"[=+\\-*/^∑∫≈≤≥∞√∀∃→←↔ΔΩλμσπ{}\\[\\]()]", text)) and len(text) < 200

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
