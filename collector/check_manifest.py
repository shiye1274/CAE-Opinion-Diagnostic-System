# -*- coding: utf-8 -*-
"""
数据包交接校验脚本（A 侧使用）
用法：
    python collector/check_manifest.py --zip corpus_raw_B_20261125.zip
校验项：
    - zip 文件名与 manifest.package_id 一致
    - owner == "B"
    - 每个 source_id 在 sources.yaml 中存在
    - 每个文件存在且记录数与 manifest 一致
    - total_records 等于各源记录数之和
    - SHA-256 校验（如 manifest 提供）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path


def load_source_ids(yaml_path: Path) -> set[str]:
    try:
        import yaml
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        return {s.get("id") for s in (data or []) if isinstance(s, dict) and s.get("id")}
    except Exception as e:
        print(f"[WARN] 无法解析 sources.yaml: {e}")
        return set()


def count_records(file_path: Path) -> int:
    """统计 jsonl/csv/txt 行数；JSON 数组文件统计元素数。"""
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return len(data) if isinstance(data, list) else 1
        except Exception:
            return 0
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".csv":
        lines = text.splitlines()
        return max(0, len(lines) - 1) if lines else 0
    # jsonl / txt
    return sum(1 for line in text.splitlines() if line.strip())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest(zip_path: Path, sources_yaml: Path) -> bool:
    if not zip_path.exists():
        print(f"[ERROR] zip 不存在: {zip_path}")
        return False

    source_ids = load_source_ids(sources_yaml)
    expected_zip_name = zip_path.stem
    ok = True

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)

        manifest_path = tmp / "manifest.json"
        if not manifest_path.exists():
            print("[ERROR] manifest.json 缺失")
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[ERROR] manifest.json 解析失败: {e}")
            return False

        print(f"[INFO] package_id: {manifest.get('package_id')}")
        print(f"[INFO] created_at: {manifest.get('created_at')}")
        print(f"[INFO] total_records (manifest): {manifest.get('total_records')}")

        if manifest.get("package_id") != expected_zip_name:
            print(f"[ERROR] package_id({manifest.get('package_id')}) != zip 名({expected_zip_name})")
            ok = False

        if manifest.get("owner") != "B":
            print(f"[WARN] owner 不是 B: {manifest.get('owner')}")

        # checksum
        cs = manifest.get("checksum") or {}
        if cs.get("algorithm", "").lower() == "sha256" and cs.get("value"):
            actual = sha256_file(zip_path)
            if actual.lower() != cs["value"].lower():
                print(f"[ERROR] SHA-256 不一致: 实际 {actual} != 期望 {cs['value']}")
                ok = False
            else:
                print("[OK] SHA-256 校验通过")

        sources = manifest.get("sources", [])
        total_counted = 0
        for src in sources:
            sid = src.get("source_id")
            print(f"\n[INFO] 检查源: {sid}")
            if sid not in source_ids:
                print(f"[ERROR] source_id {sid} 不在 {sources_yaml} 中")
                ok = False

            rec_count = 0
            for rel in src.get("files", []):
                fp = tmp / rel.replace("/", "\\")  # Windows 兼容
                if not fp.exists():
                    print(f"[ERROR] 文件缺失: {rel}")
                    ok = False
                    continue
                c = count_records(fp)
                print(f"  {rel}: {c} 条")
                rec_count += c

            declared = src.get("records")
            if declared is not None and rec_count != declared:
                print(f"[ERROR] {sid} 记录数不符: 实际 {rec_count} != manifest {declared}")
                ok = False
            total_counted += rec_count

        declared_total = manifest.get("total_records")
        if declared_total is not None and total_counted != declared_total:
            print(f"\n[ERROR] total_records 不符: 实际 {total_counted} != manifest {declared_total}")
            ok = False
        else:
            print(f"\n[INFO] 实际总记录数: {total_counted}")

    if ok:
        print("\n[OK] manifest 校验全部通过，可以进入 ingestion")
    else:
        print("\n[FAIL] manifest 校验存在错误，请 B 修正后重传")
    return ok


def main():
    parser = argparse.ArgumentParser(description="校验 B 的数据包")
    parser.add_argument("--zip", required=True, type=Path, help="数据包 zip 路径")
    parser.add_argument("--sources-yaml", type=Path,
                        default=Path(__file__).resolve().parent / "sources.yaml",
                        help="sources.yaml 路径")
    args = parser.parse_args()
    ok = check_manifest(args.zip, args.sources_yaml)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
