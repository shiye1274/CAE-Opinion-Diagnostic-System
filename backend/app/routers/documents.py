# -*- coding: utf-8 -*-
"""语料检索：列表 / 详情 / KWIC 索引行。"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..core.db import query, query_one

router = APIRouter()


@router.get("/documents")
def search_documents(
    lang: Optional[str] = None,
    layer: Optional[str] = None,
    country: Optional[str] = None,
    variant: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    where, params = ["1=1"], []
    if lang:
        where.append("language = ?"); params.append(lang)
    if layer:
        where.append("source_layer = ?"); params.append(layer)
    if country:
        where.append("country = ?"); params.append(country)
    if variant:
        where.append("lang_variant = ?"); params.append(variant)
    if keyword:
        where.append("(title LIKE ? OR text_clean LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    cond = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) n FROM corpus_documents WHERE {cond}", tuple(params))["n"]
    rows = query(
        f"""SELECT doc_id, source_id, source_layer, language, lang_variant, country,
                   title, published, word_count, url, content_type
            FROM corpus_documents WHERE {cond}
            ORDER BY fetched_at DESC LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, (page - 1) * page_size),
    )
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/documents/{doc_id}")
def document_detail(doc_id: str):
    doc = query_one("SELECT * FROM corpus_documents WHERE doc_id = ?", (doc_id,))
    if not doc:
        raise HTTPException(404, "doc not found")
    return doc


@router.get("/kwic")
def kwic(term: str, lang: Optional[str] = None, width: int = 40, limit: int = 50):
    """KWIC 索引行：term 左右各 width 字符窗口（语料库语言学核心功能）。"""
    if not term.strip():
        return {"hits": [], "total": 0}
    where, params = ["(title LIKE ? OR text_clean LIKE ?)"], [f"%{term}%", f"%{term}%"]
    if lang:
        where.append("language = ?"); params.append(lang)
    rows = query(
        f"""SELECT doc_id, title, language, country, published, text_clean
            FROM corpus_documents WHERE {' AND '.join(where)} LIMIT 500""",
        tuple(params),
    )
    hits, w = [], max(width, 10)
    for r in rows:
        text = (r["text_clean"] or "") + " " + (r["title"] or "")
        pos = text.find(term)
        if pos < 0:
            continue
        hits.append({
            "doc_id": r["doc_id"],
            "language": r["language"],
            "country": r["country"],
            "published": r["published"],
            "left": text[max(pos - w, 0):pos],
            "keyword": term,
            "right": text[pos + len(term):pos + w + len(term)],
        })
        if len(hits) >= limit:
            break
    return {"hits": hits, "total": len(hits)}
