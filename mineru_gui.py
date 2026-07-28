#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU 图形界面：选择 PDF 文件或文件夹，一键自动解析为 Markdown / JSON。

用法:
    conda activate mineru
    python mineru_gui.py

或双击 / 终端运行:
    ./start_gui.sh
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import (
    END,
    BooleanVar,
    StringVar,
    Tk,
    filedialog,
    messagebox,
    scrolledtext,
    ttk,
)

# 项目与输出默认路径
APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = APP_DIR / "output"
SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
                  ".docx", ".pptx", ".xlsx"}

BACKEND_OPTIONS = [
    ("pipeline", "pipeline（推荐 Mac：稳定、省内存，支持 CPU）"),
    ("hybrid-engine", "hybrid-engine（更高精度，占用更多内存）"),
    ("vlm-engine", "vlm-engine（纯 VLM 高精度）"),
]

METHOD_OPTIONS = ["auto", "txt", "ocr"]
LANG_OPTIONS = ["ch", "ch_server", "korean", "ta", "te", "ka", "th", "el",
                "arabic", "east_slavic", "cyrillic", "devanagari"]
EFFORT_OPTIONS = ["medium", "high"]
MODEL_SOURCE_OPTIONS = [
    ("modelscope", "ModelScope（国内推荐）"),
    ("huggingface", "HuggingFace"),
    ("local", "本地已下载模型"),
]


def find_python_bin() -> str:
    """定位 mineru conda 环境中的 python。"""
    if sys.executable and "mineru" in sys.executable:
        return sys.executable
    candidates = [
        Path("/opt/anaconda3/envs/mineru/bin/python"),
        Path.home() / "anaconda3/envs/mineru/bin/python",
        Path.home() / "miniconda3/envs/mineru/bin/python",
        APP_DIR / ".venv/bin/python",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    # 回退：当前 python 或 which python
    which = subprocess.run(["which", "python"], capture_output=True, text=True)
    if which.returncode == 0 and which.stdout.strip():
        return which.stdout.strip()
    return sys.executable or "python"


PROCESS_SCRIPT = APP_DIR / "process_pdf.py"


class MinerUGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("MinerU PDF / 文档解析工具")
        self.root.geometry("860x720")
        self.root.minsize(720, 600)

        self.input_path = StringVar()
        self.output_path = StringVar(value=str(DEFAULT_OUTPUT))
        self.backend = StringVar(value="pipeline")
        self.method = StringVar(value="auto")
        self.lang = StringVar(value="ch")
        self.effort = StringVar(value="medium")
        self.model_source = StringVar(value="modelscope")
        self.enable_formula = BooleanVar(value=True)
        self.enable_table = BooleanVar(value=True)
        self.running = False
        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_log()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="MinerU 文档解析", font=("", 16, "bold"))
        title.pack(anchor="w", pady=(0, 4))
        ttk.Label(
            main,
            text="选择 PDF 文件或文件夹，点击「开始处理」自动转为 Markdown / JSON",
            foreground="#555",
        ).pack(anchor="w", pady=(0, 10))

        # —— 输入 ——
        row_in = ttk.LabelFrame(main, text="输入（PDF 文件或文件夹）", padding=8)
        row_in.pack(fill="x", **pad)
        ttk.Entry(row_in, textvariable=self.input_path).pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        ttk.Button(row_in, text="选择文件…", command=self._pick_file).pack(side="left", padx=2)
        ttk.Button(row_in, text="选择文件夹…", command=self._pick_folder).pack(side="left", padx=2)

        # —— 输出 ——
        row_out = ttk.LabelFrame(main, text="输出目录", padding=8)
        row_out.pack(fill="x", **pad)
        ttk.Entry(row_out, textvariable=self.output_path).pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        ttk.Button(row_out, text="选择目录…", command=self._pick_output).pack(side="left")

        # —— 参数 ——
        opts = ttk.LabelFrame(main, text="解析参数", padding=8)
        opts.pack(fill="x", **pad)

        g = ttk.Frame(opts)
        g.pack(fill="x")

        ttk.Label(g, text="后端:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        backend_combo = ttk.Combobox(
            g,
            textvariable=self.backend,
            values=[b[0] for b in BACKEND_OPTIONS],
            state="readonly",
            width=18,
        )
        backend_combo.grid(row=0, column=1, sticky="w", padx=4, pady=4)
        self.backend_hint = ttk.Label(g, text=BACKEND_OPTIONS[0][1], foreground="#666")
        self.backend_hint.grid(row=0, column=2, sticky="w", padx=4, pady=4)
        backend_combo.bind("<<ComboboxSelected>>", self._on_backend_change)

        ttk.Label(g, text="方法:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            g, textvariable=self.method, values=METHOD_OPTIONS, state="readonly", width=18
        ).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(g, text="auto / txt / ocr（pipeline / hybrid 有效）", foreground="#666").grid(
            row=1, column=2, sticky="w", padx=4, pady=4
        )

        ttk.Label(g, text="语言:").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            g, textvariable=self.lang, values=LANG_OPTIONS, state="readonly", width=18
        ).grid(row=2, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(g, text="中文文档选 ch（pipeline OCR）", foreground="#666").grid(
            row=2, column=2, sticky="w", padx=4, pady=4
        )

        ttk.Label(g, text="Hybrid 强度:").grid(row=3, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            g, textvariable=self.effort, values=EFFORT_OPTIONS, state="readonly", width=18
        ).grid(row=3, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(g, text="仅 hybrid-engine 有效", foreground="#666").grid(
            row=3, column=2, sticky="w", padx=4, pady=4
        )

        ttk.Label(g, text="模型源:").grid(row=4, column=0, sticky="w", padx=4, pady=4)
        ttk.Combobox(
            g,
            textvariable=self.model_source,
            values=[m[0] for m in MODEL_SOURCE_OPTIONS],
            state="readonly",
            width=18,
        ).grid(row=4, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(g, text="国内网络建议 modelscope", foreground="#666").grid(
            row=4, column=2, sticky="w", padx=4, pady=4
        )

        flags = ttk.Frame(opts)
        flags.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(flags, text="启用公式解析", variable=self.enable_formula).pack(
            side="left", padx=8
        )
        ttk.Checkbutton(flags, text="启用表格解析", variable=self.enable_table).pack(
            side="left", padx=8
        )

        # —— 操作按钮 ——
        actions = ttk.Frame(main)
        actions.pack(fill="x", **pad)
        self.start_btn = ttk.Button(actions, text="▶  开始处理", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(
            actions, text="■  停止", command=self._stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(actions, text="打开输出目录", command=self._open_output).pack(
            side="left", padx=4
        )
        ttk.Button(actions, text="清空日志", command=self._clear_log).pack(side="left", padx=4)

        self.status_var = StringVar(value="就绪")
        ttk.Label(actions, textvariable=self.status_var, foreground="#0a7").pack(
            side="right", padx=8
        )

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 6))

        # —— 日志 ——
        log_frame = ttk.LabelFrame(main, text="运行日志", padding=6)
        log_frame.pack(fill="both", expand=True, **pad)
        self.log = scrolledtext.ScrolledText(
            log_frame, height=18, wrap="word", font=("Menlo", 11)
        )
        self.log.pack(fill="both", expand=True)
        self._log("MinerU GUI 已启动。")
        self._log(f"Python: {find_python_bin()}")
        self._log(f"处理脚本: {PROCESS_SCRIPT}")
        self._log("请选择 PDF 文件或包含 PDF 的文件夹，然后点击「开始处理」。")
        self._log("推荐参数：后端 pipeline · 方法 auto/txt · 模型源 modelscope\n")

    def _on_backend_change(self, _event=None) -> None:
        mapping = {b[0]: b[1] for b in BACKEND_OPTIONS}
        self.backend_hint.config(text=mapping.get(self.backend.get(), ""))

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要解析的文件",
            filetypes=[
                ("支持的文档", "*.pdf *.png *.jpg *.jpeg *.webp *.docx *.pptx *.xlsx"),
                ("PDF", "*.pdf"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.input_path.set(path)

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title="选择包含 PDF / 文档的文件夹")
        if path:
            self.input_path.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_path.set(path)

    def _open_output(self) -> None:
        out = Path(self.output_path.get().strip() or str(DEFAULT_OUTPUT))
        out.mkdir(parents=True, exist_ok=True)
        webbrowser.open(out.as_uri())

    def _clear_log(self) -> None:
        self.log.delete("1.0", END)

    def _log(self, msg: str) -> None:
        self.log.insert(END, msg + "\n")
        self.log.see(END)

    def _poll_log(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def _validate(self) -> tuple[Path, Path] | None:
        raw_in = self.input_path.get().strip()
        raw_out = self.output_path.get().strip()
        if not raw_in:
            messagebox.showwarning("提示", "请先选择 PDF 文件或文件夹。")
            return None
        in_path = Path(raw_in).expanduser().resolve()
        if not in_path.exists():
            messagebox.showerror("错误", f"输入路径不存在：\n{in_path}")
            return None
        if in_path.is_file():
            if in_path.suffix.lower() not in SUPPORTED_EXTS:
                messagebox.showerror(
                    "错误",
                    f"不支持的文件类型：{in_path.suffix}\n"
                    f"支持: {', '.join(sorted(SUPPORTED_EXTS))}",
                )
                return None
        elif in_path.is_dir():
            found = [
                p for p in in_path.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            ]
            if not found:
                # 也允许只扫一层（mineru 默认扫目录内文件）
                found = [
                    p for p in in_path.iterdir()
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
                ]
            if not found:
                messagebox.showwarning(
                    "提示",
                    f"文件夹中未找到可处理文件：\n{in_path}\n"
                    f"支持 PDF / 图片 / DOCX / PPTX / XLSX",
                )
                return None
        else:
            messagebox.showerror("错误", "输入路径无效。")
            return None

        out_path = Path(raw_out or str(DEFAULT_OUTPUT)).expanduser().resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        return in_path, out_path

    def _build_cmd(
        self,
        in_path: Path,
        out_path: Path,
        *,
        method: str | None = None,
        backend: str | None = None,
    ) -> list[str]:
        """使用 process_pdf.py 直接解析，避免 mineru CLI 临时 API 的空错误问题。"""
        py = find_python_bin()
        backend = backend or self.backend.get()
        method = method or self.method.get()
        if not PROCESS_SCRIPT.is_file():
            raise FileNotFoundError(f"缺少处理脚本: {PROCESS_SCRIPT}")
        cmd = [
            py,
            str(PROCESS_SCRIPT),
            "-p", str(in_path),
            "-o", str(out_path),
            "-b", backend,
            "-m", method,
            "-l", self.lang.get(),
            "-f", "true" if self.enable_formula.get() else "false",
            "-t", "true" if self.enable_table.get() else "false",
            "--effort", self.effort.get(),
        ]
        return cmd

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["MINERU_MODEL_SOURCE"] = self.model_source.get()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        py = Path(find_python_bin())
        if py.parent.name == "bin":
            env["PATH"] = f"{py.parent}:{env.get('PATH', '')}"
        return env

    def _run_mineru(self, cmd: list[str], env: dict[str, str], log_file: Path) -> int:
        """运行处理脚本：输出写文件，再 tail 到 GUI，避免管道死锁。"""
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # 每次运行覆盖/追加分隔
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write("\n" + "=" * 60 + "\n")
            lf.write(f"CMD: {' '.join(cmd)}\n")
            lf.write("=" * 60 + "\n")

        # 把 stdout/stderr 重定向到日志文件（比 PIPE 更稳）
        log_fh = open(log_file, "a", encoding="utf-8", errors="replace")
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(APP_DIR),
            )
            # 轮询日志文件，把新增内容刷到 GUI
            pos = log_fh.tell() if hasattr(log_fh, "tell") else 0
            # 更稳：用独立只读句柄 tail
            with open(log_file, "r", encoding="utf-8", errors="replace") as reader:
                reader.seek(0, os.SEEK_END)
                while True:
                    line = reader.readline()
                    if line:
                        self.log_queue.put(line.rstrip("\n"))
                        continue
                    if self.proc.poll() is not None:
                        # 读完剩余
                        rest = reader.read()
                        if rest:
                            for part in rest.splitlines():
                                self.log_queue.put(part)
                        break
                    threading.Event().wait(0.15)
            code = self.proc.wait()
            return code
        finally:
            try:
                log_fh.close()
            except Exception:
                pass

    def _start(self) -> None:
        if self.running:
            return
        validated = self._validate()
        if not validated:
            return
        in_path, out_path = validated
        env = self._build_env()
        log_file = APP_DIR / "logs" / "mineru_gui_last.log"

        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("处理中…")
        self.progress.start(12)

        self._log("=" * 60)
        self._log(f"输入: {in_path}")
        self._log(f"输出: {out_path}")
        self._log(f"模型源: {env['MINERU_MODEL_SOURCE']}")
        self._log(f"处理引擎: process_pdf.py（直连，绕过临时 API）")
        self._log(f"完整日志: {log_file}")
        self._log("开始解析…\n")

        def worker() -> None:
            try:
                cmd = self._build_cmd(in_path, out_path)
                self.log_queue.put(f"命令: {' '.join(cmd)}")
                code = self._run_mineru(cmd, env, log_file)

                # pipeline + auto 失败时自动 txt 重试
                if (
                    code != 0
                    and code is not None
                    and code > 0
                    and self.backend.get() == "pipeline"
                    and self.method.get() == "auto"
                    and in_path.is_file()
                    and in_path.suffix.lower() == ".pdf"
                ):
                    self.log_queue.put(
                        "\n⚠️ 首次处理失败。自动用 method=txt 重试…\n"
                    )
                    cmd2 = self._build_cmd(in_path, out_path, method="txt")
                    self.log_queue.put(f"重试命令: {' '.join(cmd2)}")
                    code = self._run_mineru(cmd2, env, log_file)

                if code == 0:
                    self.log_queue.put("\n✅ 处理完成！结果已写入输出目录。")
                    self.root.after(0, lambda: self.status_var.set("完成"))
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "完成",
                            f"处理完成！\n\n输出目录：\n{out_path}\n\n"
                            f"Markdown 一般在：\n"
                            f"{out_path}/<文件名>/auto/*.md 或 <文件名>/txt/*.md",
                        ),
                    )
                elif code is not None and code < 0:
                    self.log_queue.put(f"\n⏹ 已停止（信号 {-code}）。")
                    self.root.after(0, lambda: self.status_var.set("已停止"))
                else:
                    tip = (
                        "\n\n建议：\n"
                        "1) 后端保持 pipeline\n"
                        "2) 方法改为 txt 或 ocr\n"
                        "3) 关闭其他占内存软件后重试\n"
                        f"4) 查看日志: {log_file}"
                    )
                    self.log_queue.put(f"\n❌ 处理失败，退出码: {code}{tip}")
                    self.root.after(0, lambda: self.status_var.set("失败"))
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "失败",
                            f"处理失败，退出码 {code}。\n\n完整日志：\n{log_file}",
                        ),
                    )
            except FileNotFoundError as e:
                self.log_queue.put(f"\n❌ {e}\n请先: conda activate mineru")
                self.root.after(0, lambda: self.status_var.set("未安装"))
            except Exception as e:
                self.log_queue.put(f"\n❌ 异常: {e}")
                self.root.after(0, lambda: self.status_var.set("异常"))
            finally:
                self.proc = None
                self.running = False
                self.root.after(0, self._reset_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_ui(self) -> None:
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def _stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self._log("正在停止…")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.status_var.set("已停止")

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno("确认", "任务仍在运行，确定退出并停止？"):
                return
            self._stop()
        self.root.destroy()


def main() -> None:
    # 提升 macOS 上 Tk 界面清晰度
    try:
        from ctypes import cdll
        # 无操作：部分环境无高 DPI 设置
    except Exception:
        pass

    root = Tk()
    try:
        # 使用系统主题
        style = ttk.Style()
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    MinerUGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
