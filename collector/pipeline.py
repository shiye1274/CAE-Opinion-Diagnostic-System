# -*- coding: utf-8 -*-
"""
collector.pipeline
==================
清洗 → 去重 → 语言/方言识别 → 脱敏 → 入库（JSONL + SQLite 四表）

表结构对齐规划文档表 3-4：
  corpus_documents        文档主表
  doc_entities            品牌-文档映射表
  ugc_threads             评论树表
  (corpus_spans_annotations 预留，标注阶段写入)
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "corpus" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "corpus" / "processed"
DB_PATH = PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"

CLEAN_VER = "v0.1"   # 清洗规则版本，写入每条记录以保障可复现

# ---------- 语言/方言 ----------
AR_CHARS = re.compile(r"[\u0600-\u06FF]")
ZH_CHARS = re.compile(r"[\u4E00-\u9FFF]")
GULF_WORDS = [
    "موتر", "وش", "شلون", "الحين", "وين", "عاد", "طيب", "ماشي",
    "بو هبة", "يالله", "الله يرحم", "ما شاء الله", "زي ما", "هجولة",
]
ARABIZI = re.compile(r"\b(3arab|ana|khaliji|wallah|ya5i|7ilwa|shu)\b", re.I)


def detect_language(text: str, fallback: str = "en") -> str:
    if not text:
        return "en"
    if fallback not in ("ar", "en", "zh"):   # 防污染：适配器误传正文等非法兜底值
        fallback = "en"
    ar = len(AR_CHARS.findall(text))
    zh = len(ZH_CHARS.findall(text))
    total = len(text)
    if zh / max(total, 1) > 0.05:
        return "zh"
    if ar / max(total, 1) > 0.15:
        return "ar"
    return fallback


def detect_lang_variant(text: str) -> str:
    """MSA / Khaliji / Arabizi / EN / ZH 粗判（方言精判由模型层完成）。"""
    if ZH_CHARS.search(text or ""):
        return "ZH"
    ar_ratio = len(AR_CHARS.findall(text or "")) / max(len(text or ""), 1)
    if ar_ratio < 0.1:
        return "EN" if not ARABIZI.search(text or "") else "Arabizi"
    hits = sum(1 for w in GULF_WORDS if w in (text or ""))
    if hits >= 2:
        return "Khaliji"
    if ARABIZI.search(text or ""):
        return "Arabizi"
    return "MSA"


# ---------- 清洗 ----------
NOISE_PATTERNS = [
    re.compile(r"(?i)subscribe|sign in|read more|advertisement|cookie|privacy policy"),
    re.compile(r"^\s*[\|\-–—•]\s*$"),
]
SPAM_MAX_EMOJI_RATIO = 0.5
URL_RE = re.compile(r"https?://\S+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"\+?\d[\d \-()]{7,}\d")
USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{3,}")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or any(p.search(ln) for p in NOISE_PATTERNS):
            continue
        lines.append(ln)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return out.strip()


def is_spam(text: str) -> bool:
    if not text or len(text) < 15:
        return True
    emoji = sum(1 for c in text if ord(c) > 0x1F000)
    if emoji / max(len(text), 1) > SPAM_MAX_EMOJI_RATIO:
        return True
    if len(URL_RE.findall(text)) > 5:
        return True
    return False


def scrub_pii(text: str, author: Optional[str]) -> tuple[str, str]:
    """PII 脱敏：邮箱/手机/用户名清除，author 一律哈希。"""
    t = EMAIL_RE.sub("[EMAIL]", text or "")
    t = PHONE_RE.sub("[PHONE]", t)
    t = USERNAME_RE.sub("[USER]", t)
    t = URL_RE.sub("[URL]", t)
    a_hash = hashlib.sha256((author or "").encode("utf-8")).hexdigest()[:16] if author else ""
    return t, a_hash


# ---------- 去重 ----------
class Dedup:
    """SHA256 精确 + 8-gram SimHash 近似。"""

    def __init__(self, simhash_hamming: int = 4):
        self.exact: set[str] = set()
        self.fuzzy: List[int] = []
        self.hamming = simhash_hamming

    @staticmethod
    def _simhash(text: str, bits: int = 64) -> int:
        import mmh3  # 延迟导入
        grams = re.findall(r"\w+", text.lower())
        v = [0] * bits
        for i in range(max(len(grams) - 7, 1)):
            h = mmh3.hash(" ".join(grams[i:i + 8]), signed=False)
            for b in range(bits):
                if h & (1 << b):
                    v[b] += 1
                else:
                    v[b] -= 1
        return sum(1 << b for b in range(bits) if v[b] > 0)

    def check(self, text_norm: str) -> bool:
        h = hashlib.sha256(text_norm.encode("utf-8")).hexdigest()
        if h in self.exact:
            return False
        self.exact.add(h)
        try:
            sh = self._simhash(text_norm)
            if any(bin(sh ^ f).count("1") <= self.hamming for f in self.fuzzy):
                return False
            self.fuzzy.append(sh)
        except ImportError:
            pass
        return True


# ---------- SQLite ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS corpus_documents (
    doc_id TEXT PRIMARY KEY, source_id TEXT, source_layer TEXT, country TEXT,
    language TEXT, lang_variant TEXT, url TEXT, title TEXT,
    published TEXT, fetched_at TEXT, word_count INTEGER,
    text_clean TEXT, raw_path TEXT, sha256 TEXT, clean_ver TEXT,
    content_type TEXT, modality TEXT, engagement TEXT, extra TEXT
);
CREATE TABLE IF NOT EXISTS doc_entities (
    map_id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, brand_id TEXT,
    role_in_doc TEXT, mention_count INTEGER,
    FOREIGN KEY(doc_id) REFERENCES corpus_documents(doc_id)
);
CREATE TABLE IF NOT EXISTS ugc_threads (
    comment_id TEXT PRIMARY KEY, parent_doc_id TEXT, reply_to_id TEXT,
    author_hash TEXT, comment_text TEXT, language TEXT, dialect_tag TEXT,
    stance_towards_cn_brand TEXT, engagement TEXT
);
CREATE INDEX IF NOT EXISTS idx_doc_lang ON corpus_documents(language);
CREATE INDEX IF NOT EXISTS idx_doc_layer ON corpus_documents(source_layer);
"""


class CorpusDB:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def insert(self, rec: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO corpus_documents "
            "(doc_id, source_id, source_layer, country, language, lang_variant, url, title,"
            " published, fetched_at, word_count, text_clean, raw_path, sha256, clean_ver,"
            " content_type, modality, engagement, extra) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["doc_id"], rec["source_id"], rec["layer"], rec["country"], rec["language"],
             rec["lang_variant"], rec["url"], rec["title"], rec["published"],
             rec["fetched_at"], rec["word_count"], rec["text_clean"], rec["raw_path"],
             rec["sha256"], rec["clean_ver"], rec["content_type"], rec["modality"],
             json.dumps(rec.get("engagement", {}), ensure_ascii=False),
             json.dumps(rec.get("extra", {}), ensure_ascii=False)),
        )

    def commit(self) -> None:
        self.conn.commit()

    def stats(self) -> dict:
        cur = self.conn.execute(
            "SELECT language, source_layer, COUNT(*) FROM corpus_documents GROUP BY 1,2")
        out: Dict[str, dict] = {}
        for lang, layer, n in cur.fetchall():
            out.setdefault(lang, {})[layer] = n
        return out


# ---------- 主流水线 ----------
def run_pipeline(raw_dir: Path = RAW_DIR, dedup: Optional[Dedup] = None) -> dict:
    """处理 corpus/raw 全量原始记录 → corpus/processed/records.jsonl + SQLite。"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dedup = dedup or Dedup()
    db = CorpusDB()
    out_path = PROCESSED_DIR / "records.jsonl"
    n_in = n_out = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for manifest in raw_dir.glob("*/*/ *.json"):
            pass  # 占位防误匹配
        for manifest in sorted(raw_dir.glob("*/*/*.json")):
            n_in += 1
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            meta: dict = payload.get("meta", {})
            text = clean_text(meta.get("text", ""))
            if is_spam(text):
                continue
            norm = re.sub(r"\s+", " ", text).strip().lower()
            if not dedup.check(norm):
                continue
            language = detect_language(text, meta.get("language", "en"))
            lang_variant = detect_lang_variant(text)
            text, author_hash = scrub_pii(text, meta.get("author"))
            if meta.get("content_type") == "comment":
                doc_id = "ugc_" + (meta.get("sha256") or hashlib.sha256(norm.encode()).hexdigest()[:16])
                db.conn.execute(
                    "INSERT OR REPLACE INTO ugc_threads (comment_id, parent_doc_id, author_hash,"
                    " comment_text, language, dialect_tag, engagement) VALUES (?,?,?,?,?,?,?)",
                    (doc_id, meta.get("parent_url"), author_hash, text, language,
                     lang_variant, json.dumps(meta.get("engagement", {}), ensure_ascii=False)),
                )
            else:
                doc_id = "doc_" + (meta.get("sha256") or hashlib.sha256(norm.encode()).hexdigest()[:16])
            rec = {
                "doc_id": doc_id,
                "source_id": meta.get("source_id"),
                "layer": meta.get("layer"),
                "country": meta.get("country"),
                "language": language,
                "lang_variant": lang_variant,
                "url": meta.get("url"),
                "title": clean_text(meta.get("title", ""))[:300],
                "published": meta.get("published"),
                "fetched_at": meta.get("fetched_at"),
                "word_count": len(text.split()),
                "text_clean": text,
                "raw_path": meta.get("raw_path"),
                "sha256": meta.get("sha256"),
                "clean_ver": CLEAN_VER,
                "content_type": meta.get("content_type", "article"),
                "modality": meta.get("layer"),
                "engagement": meta.get("engagement", {}),
                "extra": meta.get("extra", {}),
                "author_hash": author_hash,
            }
            db.insert(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_out += 1
    db.commit()
    return {"raw_in": n_in, "kept": n_out, "stats": db.stats()}


if __name__ == "__main__":
    r = run_pipeline()
    print(json.dumps(r, ensure_ascii=False, indent=2))
