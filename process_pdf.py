#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU 稳定批处理入口（绕过临时 mineru-api，直接调用 do_parse）。

用法:
  python process_pdf.py -p /path/to/file.pdf -o /path/to/output
  python process_pdf.py -p /path/to/folder -o /path/to/output -b pipeline -m auto -l ch
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="MinerU direct parse (stable)")
    parser.add_argument("-p", "--path", required=True, help="PDF/image/office file or directory")
    parser.add_argument("-o", "--output", required=True, help="Output directory")
    parser.add_argument(
        "-b",
        "--backend",
        default="pipeline",
        choices=["pipeline", "hybrid-engine", "vlm-engine"],
        help="Parsing backend (default: pipeline)",
    )
    parser.add_argument(
        "-m",
        "--method",
        default="auto",
        choices=["auto", "txt", "ocr"],
        help="Parse method for pipeline/hybrid",
    )
    parser.add_argument("-l", "--lang", default="ch", help="OCR language (pipeline)")
    parser.add_argument(
        "-f",
        "--formula",
        default="true",
        choices=["true", "false"],
        help="Enable formula parsing",
    )
    parser.add_argument(
        "-t",
        "--table",
        default="true",
        choices=["true", "false"],
        help="Enable table parsing",
    )
    parser.add_argument(
        "--effort",
        default="medium",
        choices=["medium", "high"],
        help="Hybrid effort level",
    )
    args = parser.parse_args()

    # 国内默认 modelscope（可被外部环境覆盖）
    os.environ.setdefault("MINERU_MODEL_SOURCE", "modelscope")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    input_path = Path(args.path).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[ERROR] 输入路径不存在: {input_path}", file=sys.stderr)
        return 2

    try:
        from mineru.cli.common import do_parse, read_fn
        from mineru.utils.guess_suffix_or_lang import guess_suffix_by_path
        from mineru.cli.common import image_suffixes, office_suffixes, pdf_suffixes
    except Exception as e:
        print(f"[ERROR] 无法导入 mineru，请先 conda activate mineru\n{e}", file=sys.stderr)
        return 3

    supported = set(pdf_suffixes + image_suffixes + office_suffixes)

    def collect_files(path: Path) -> list[Path]:
        if path.is_file():
            suf = guess_suffix_by_path(path)
            if suf not in supported:
                raise ValueError(f"不支持的文件类型: {path.name} ({suf})")
            return [path]
        files = sorted(
            p.resolve()
            for p in path.iterdir()
            if p.is_file() and guess_suffix_by_path(p) in supported
        )
        if not files:
            raise ValueError(f"目录中没有可处理文件: {path}")
        return files

    try:
        files = collect_files(input_path)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    print(f"[INFO] 输入: {input_path}")
    print(f"[INFO] 输出: {output_dir}")
    print(f"[INFO] 文件数: {len(files)}")
    print(f"[INFO] 后端: {args.backend} | 方法: {args.method} | 语言: {args.lang}")
    print(f"[INFO] 模型源: {os.environ.get('MINERU_MODEL_SOURCE')}")
    for f in files:
        print(f"  - {f.name}")

    # 逐个处理，避免一次加载过多大文件导致内存峰值
    ok, failed = 0, []
    for idx, file_path in enumerate(files, 1):
        stem = file_path.stem
        print(f"\n[INFO] ({idx}/{len(files)}) 开始处理: {file_path.name}")
        try:
            pdf_bytes = read_fn(file_path)
            do_parse(
                output_dir=str(output_dir),
                pdf_file_names=[stem],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=[args.lang],
                backend=args.backend,
                parse_method=args.method,
                formula_enable=(args.formula == "true"),
                table_enable=(args.table == "true"),
                f_draw_layout_bbox=True,
                f_draw_span_bbox=True,
                f_dump_md=True,
                f_dump_middle_json=True,
                f_dump_model_output=True,
                f_dump_orig_pdf=True,
                f_dump_content_list=True,
                effort=args.effort,
            )
            # 粗略检查输出
            md_candidates = list(output_dir.glob(f"**/{stem}.md"))
            if md_candidates:
                print(f"[OK] 完成: {file_path.name}")
                print(f"     Markdown: {md_candidates[0]}")
            else:
                print(f"[OK] 完成: {file_path.name}（未找到 .md，请检查输出目录结构）")
            ok += 1
        except Exception as e:
            print(f"[FAIL] {file_path.name}: {e}", file=sys.stderr)
            traceback.print_exc()
            failed.append((file_path.name, str(e) or repr(e)))

    print("\n" + "=" * 50)
    print(f"成功: {ok}/{len(files)}")
    if failed:
        print("失败列表:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return 1
    print("全部完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
