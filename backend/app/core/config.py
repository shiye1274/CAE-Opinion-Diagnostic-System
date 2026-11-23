# -*- coding: utf-8 -*-
"""全局配置：路径与常量。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]   # backend/app/core/config.py → 项目根
DB_PATH = PROJECT_ROOT / "corpus" / "meta" / "corpus.sqlite"
PACKS_DIR = PROJECT_ROOT / "collector" / "packs"

API_V1 = "/api/v1"
