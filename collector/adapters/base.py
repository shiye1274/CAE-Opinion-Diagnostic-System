# -*- coding: utf-8 -*-
"""
collector.adapters.base
=======================
所有采集通道适配器的公共基础设施：

- HTTPSession：带重试/限速/统一 UA 的请求封装
- RawStore：原始数据落盘 corpus/raw/{source_id}/{yyyymmdd}/ + manifest.json + SHA256
- AuditLog：每次运行的查询级审计（run_id、查询式、命中数、失败原因全留痕）
  输出：collector/audit/run_{run_id}.jsonl
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "corpus" / "raw"
AUDIT_DIR = PROJECT_ROOT / "collector" / "audit"

UA = ("GreenSilk-MENA-Corpus/0.1 (academic research; contact: research-team)"
      " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def norm_text_for_hash(text: str) -> str:
    """规范化文本（去空白/大小写）用于精确去重。"""
    t = re.sub(r"\s+", " ", text or "").strip().lower()
    return t


class HTTPSession:
    """带限速与重试的 requests 封装。"""

    def __init__(self, source_id: str, rate: float = 2.0, timeout: int = 30,
                 max_retries: int = 4, audit: Optional["AuditLog"] = None,
                 proxy: Optional[str] = None):
        self.source_id = source_id
        self.rate = max(rate, 0.5)
        self.timeout = timeout
        self.max_retries = max_retries
        self.audit = audit
        self._last_ts = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "ar,en,zh;q=0.9",
        })
        if proxy:  # 例: http://127.0.0.1:8080（部分境外站点需经本地代理）
            self.session.proxies = {"http": proxy, "https": proxy}

    def _throttle(self) -> None:
        wait = self.rate - (time.time() - self._last_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_ts = time.time()

    def get(self, url: str, **kw) -> requests.Response:
        """GET with retry。429/503 走长退避（GDELT 等要求 ≥5s 间隔）。抛出最后一轮失败。"""
        last_err: Optional[Exception] = None
        timeout = kw.pop("timeout", self.timeout)   # 允许调用方覆盖，避免重复传参
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=timeout, **kw)
                if resp.status_code in (429, 503):
                    wait = min(30 * attempt, 90)
                    time.sleep(wait)
                    raise RuntimeError(f"throttled {resp.status_code}, backed off {wait}s")
                return resp
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(3 * attempt)
        raise RuntimeError(f"GET failed after {self.max_retries} retries: {url}: {last_err}")


@dataclass
class RawRecord:
    """一条原始语料的元信息（由适配器产出，pipeline 再加工）。"""
    source_id: str
    layer: str
    language: str          # 采集时预期语言（pipeline 会复核）
    country: str
    url: str
    title: str
    text: str
    published: Optional[str] = None
    author: Optional[str] = None
    engagement: Dict[str, Any] = field(default_factory=dict)
    content_type: str = "article"   # article / comment / subtitle / listing
    parent_url: Optional[str] = None  # 评论所属主帖
    raw_path: Optional[str] = None
    sha256: Optional[str] = None
    fetched_at: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class RawStore:
    """原始数据落盘 + manifest。"""

    def __init__(self, raw_dir: Path = RAW_DIR):
        self.raw_dir = Path(raw_dir)

    def save(self, source_id: str, record: RawRecord, raw_payload: Optional[str] = None) -> Path:
        day_dir = self.raw_dir / source_id / today_str()
        day_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", (record.url or record.title)[:80]) or uuid.uuid4().hex[:8]
        path = day_dir / f"{slug[:60]}_{uuid.uuid4().hex[:6]}.json"
        # 先赋值再序列化（修复：fetched_at/sha256 曾在 payload 构建后才设置 → meta 恒为 null）
        record.sha256 = text_sha256(record.text or "")
        record.fetched_at = utc_now()
        payload = {
            "meta": record.to_dict(),
            "raw_payload": raw_payload,   # 原始 HTML/JSON/字幕全文（保留快照）
        }
        blob = json.dumps(payload, ensure_ascii=False, indent=1)
        path.write_text(blob, encoding="utf-8")
        try:
            record.raw_path = str(path.relative_to(PROJECT_ROOT))
        except ValueError:      # raw_dir 在项目外（冒烟测试等场景），记绝对路径
            record.raw_path = str(path)
        return path


class AuditLog:
    """查询级审计日志：一条查询一行 JSONL，可复现任何一次采集。"""

    def __init__(self, run_id: str):
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.path = AUDIT_DIR / f"run_{run_id}.jsonl"
        self._fh = open(self.path, "a", encoding="utf-8")

    def log(self, source_id: str, adapter: str, query: str, url: str,
            status: str = "ok", n_hits: int = 0, saved: int = 0,
            error: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        rec = {
            "ts": utc_now(),
            "run_id": self.run_id,
            "source_id": source_id,
            "adapter": adapter,
            "query": query,
            "url": url,
            "status": status,      # ok / degraded / error / skipped
            "n_hits": n_hits,
            "saved": saved,
            "error": str(error)[:300],
            "extra": extra or {},
        }
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def load_yaml(path: Path) -> Any:
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(path: Path) -> List[Dict[str, Any]]:
    data = load_yaml(path)
    return data if isinstance(data, list) else data.get("sources", [])


def iter_enabled(sources: List[Dict[str, Any]],
                 only_ids: Optional[Iterable[str]] = None,
                 only_layers: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    out = []
    for s in sources:
        if only_ids and s["id"] not in set(only_ids):
            continue
        if only_layers and s["layer"] not in set(only_layers):
            continue
        out.append(s)
    return out
