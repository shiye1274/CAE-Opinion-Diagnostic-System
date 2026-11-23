# -*- coding: utf-8 -*-
"""
GDELT 2.0 DOC API 适配器：全量新闻索引查全（主力通道）。
支持 sourcelang / sourcecountry 过滤与时间窗分页。
"""
from __future__ import annotations

from typing import Iterator, List
from urllib.parse import quote_plus

from .base import AuditLog, HTTPSession, RawRecord, RawStore

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTAdapter:
    adapter_name = "gdelt"

    def __init__(self, http: HTTPSession, store: RawStore, audit: AuditLog,
                 source_id: str = "gdelt", layer: str = "L2"):
        self.http = http
        self.store = store
        self.audit = audit
        self.source_id = source_id
        self.layer = layer

    def build_query(self, brand_queries: List[str], lang_filter: str = "",
                    country_filter: str = "") -> str:
        """brand_queries: ["BYD", "بي واي دي"] → OR 组合 + 语言/国别过滤"""
        core = " OR ".join(f'"{q}"' for q in brand_queries)
        return " ".join(x for x in [f"({core})", lang_filter, country_filter] if x)

    def _parse_or_fix(self, query: str) -> str:
        """实测规则：
        1) OR 查询必须用括号包裹；
        2) 引号短语 ≥4 字符，短词（BYD/نيو 等）去掉引号用裸词；
        3) 国别代码被拒时去掉 sourcecountry 过滤重试。
        """
        import re
        terms = re.findall(r'"([^"]{1,3})"', query)
        for t in terms:
            query = query.replace(f'"{t}"', t)
        return query

    def collect(self, queries: List[tuple], max_per_query: int = 50,
                timespan: str = "1y") -> Iterator[RawRecord]:
        """queries: [(query_string, lang, country_code), ...]"""
        for query, lang, country in queries:
            query = self._parse_or_fix(query)
            params = {
                "query": query,
                "mode": "artlist",
                "maxrecords": str(min(max_per_query, 250)),
                "format": "json",
                "timespan": timespan,
                "sort": "datedesc",
            }
            url = GDELT_DOC + "?" + "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
            try:
                resp = self.http.get(url)
                # GDELT 错误以 200 + 纯文本返回，必须检查内容
                body = resp.text.strip()
                if not body.startswith("{"):
                    if "Invalid/Unsupported Country" in body:
                        # 去掉国别过滤降级重试一次（仍可按 language 查全）
                        import re
                        q2 = re.sub(r"\(?sourcecountry:[A-Z]{2}( OR sourcecountry:[A-Z]{2})*\)?", "", query).strip()
                        params["query"] = q2
                        url2 = GDELT_DOC + "?" + "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())
                        resp = self.http.get(url2)
                        body = resp.text.strip()
                        self.audit.log(self.source_id, self.adapter_name, query, url,
                                       status="degraded",
                                       error=f"country filter rejected, retried w/o filter: {body[:80]}")
                    elif "phrase is too short" in body or "OR'd terms" in body:
                        self.audit.log(self.source_id, self.adapter_name, query, url,
                                       status="error", error=body[:200])
                        continue
                if not body.startswith("{"):
                    continue
                data = resp.json()
                articles = data.get("articles", [])
                self.audit.log(self.source_id, self.adapter_name, query, url,
                               status="ok", n_hits=len(articles))
                saved = 0
                for art in articles[:max_per_query]:
                    rec = RawRecord(
                        source_id=self.source_id,
                        layer=self.layer,
                        language=lang,
                        country=art.get("sourcecountry", country)[:2] or country,
                        url=art.get("url", ""),
                        title=art.get("title", ""),
                        text=art.get("title", ""),   # GDELT 仅元数据；全文走 follow-link/site 通道
                        published=art.get("seendate"),
                        content_type="article",
                        extra={
                            "origin_query": query,
                            "domain": art.get("domain"),
                            "socialimage": art.get("socialimage", ""),
                        },
                    )
                    self.store.save(self.source_id, rec, raw_payload=resp.text[:200000])
                    saved += 1
                    yield rec
            except Exception as e:  # noqa: BLE001
                self.audit.log(self.source_id, self.adapter_name, query, url,
                               status="error", error=str(e))
                continue
