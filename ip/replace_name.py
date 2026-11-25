# -*- coding: utf-8 -*-
"""
ip/replace_name.py — 替换软著申请人姓名占位符并重新生成材料
===========================================================

用法：
    python ip/replace_name.py --name 张三

功能：
  1. 把 ip/ipmeta.py 中的 COPYRIGHT_HOLDER 占位符替换为真实姓名；
  2. 依次调用现有生成脚本，重新输出 outputs/ip/ 下的鉴别材料：
     - 源程序文档（make_source_code_doc.py）
     - 申请表信息单（make_apply_form.py）
     - 使用说明书（make_manual_greensilk.py）
  3. 若生成脚本因依赖/数据缺失失败，会给出对应的手动运行命令。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 保证中文在 Windows 默认终端上尽量正常输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
IPMETA = ROOT / "ip" / "ipmeta.py"
OUTPUTS_IP = ROOT / "outputs" / "ip"

# 按依赖顺序排列：源程序 → 申请表（依赖源程序校验报告）→ 使用说明书
GENERATORS = [
    (ROOT / "ip" / "make_source_code_doc.py", []),
    (ROOT / "ip" / "make_apply_form.py", []),
    (ROOT / "ip" / "make_manual_greensilk.py", []),
]


def replace_holder(name: str) -> bool:
    """替换 ipmeta.py 中的 COPYRIGHT_HOLDER 占位符。"""
    if not IPMETA.exists():
        print(f"[错误] 未找到 {IPMETA}")
        return False

    text = IPMETA.read_text(encoding="utf-8")
    # 匹配：COPYRIGHT_HOLDER = "..."（支持中文/全角引号也被兼容）
    pattern = re.compile(r'^(COPYRIGHT_HOLDER\s*=\s*["\u201c\u201d])([^"\u201c\u201d]+)(["\u201c\u201d])',
                         re.MULTILINE)
    if not pattern.search(text):
        print(f"[错误] 在 {IPMETA} 中未找到 COPYRIGHT_HOLDER 占位符，请人工检查。")
        return False

    new_text = pattern.sub(lambda m: f'{m.group(1)}{name}{m.group(3)}', text)
    if new_text == text:
        print(f"[提示] COPYRIGHT_HOLDER 已经是「{name}」，无需替换。")
    else:
        IPMETA.write_text(new_text, encoding="utf-8")
        print(f"[OK] 已将著作权人替换为：{name}")
    return True


def run_generator(script: Path, args: list[str]) -> bool:
    """调用单个生成脚本，失败返回 False 但不中断主流程。"""
    if not script.exists():
        print(f"[跳过] 未找到 {script.name}")
        return False
    print(f"\n[生成] 正在运行 {script.name} ...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=env,
        )
        if proc.stdout:
            print(proc.stdout)
        if proc.returncode != 0:
            print(f"[失败] {script.name} 返回非零退出码 {proc.returncode}")
            if proc.stderr:
                print(proc.stderr)
            return False
        print(f"[OK] {script.name} 执行完毕")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] {script.name} 调用异常：{exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="替换软著申请人姓名并重新生成登记材料")
    ap.add_argument("--name", required=True, help="真实申请人姓名（著作权人）")
    args = ap.parse_args()

    name = args.name.strip()
    if not name:
        print("[错误] --name 不能为空")
        return 1

    if not replace_holder(name):
        return 1

    print("\n" + "=" * 60)
    print("开始重新生成 outputs/ip/ 下的软著鉴别材料")
    print("=" * 60)

    OUTPUTS_IP.mkdir(parents=True, exist_ok=True)
    failed: list[tuple[Path, list[str]]] = []
    for script, script_args in GENERATORS:
        if not run_generator(script, script_args):
            failed.append((script, script_args))

    print("\n" + "=" * 60)
    if not failed:
        print("[OK] 全部材料已重新生成，请检查 outputs/ip/ 目录。")
        print("   建议随后运行：python ip/render_check.py outputs/ip/*.docx")
    else:
        print("[注意] 以下脚本未能自动成功，已把 ipmeta.py 替换好，请按提示手动补跑：")
        for script, script_args in failed:
            rel = script.relative_to(ROOT)
            arg_s = " ".join(script_args)
            print(f"   python {rel} {arg_s}")
        print("\n常见原因：")
        print("  - make_source_code_doc.py：缺少 python-docx 或源文件路径变更")
        print("  - make_apply_form.py：依赖上一步生成的 源程序_校验报告.json")
        print("  - make_manual_greensilk.py：依赖 corpus/meta/corpus.sqlite 等真实运行结果")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
