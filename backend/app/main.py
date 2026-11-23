# -*- coding: utf-8 -*-
"""
GreenSilk-Monitor 后端 v0.5（FastAPI）
启动：uvicorn app.main:app --reload --port 8000  （在 backend/ 目录下）
文档：http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import API_V1
from .routers import brands, compliance, documents, stats

app = FastAPI(
    title="GreenSilk-Monitor API",
    description="中阿英跨语言舆情语料库检索与品牌出海舆情诊断",
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats.router, prefix=API_V1, tags=["dashboard"])
app.include_router(documents.router, prefix=API_V1, tags=["corpus"])
app.include_router(brands.router, prefix=API_V1, tags=["brands"])
app.include_router(compliance.router, prefix=API_V1, tags=["compliance"])


@app.get("/")
def root():
    return {"service": "GreenSilk-Monitor", "version": "0.5.0", "docs": "/docs"}


@app.get("/health")
def health():
    """健康检查（供探测探针使用，避免 404 刷屏）。"""
    return {"status": "ok"}
