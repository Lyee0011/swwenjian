#!/usr/bin/env python3
"""
DaVinci Resolve 字幕搜索定位插件
在导入的 SRT 字幕中搜索关键词，点击结果即可跳转到对应时间线位置。

使用方法:
  方式一 (推荐): 在 DaVinci Resolve 菜单 → 工作区 → 脚本 中运行
  方式二: 直接运行 python3 davinci_subtitle_search.py

前置条件:
  1. DaVinci Resolve 已打开并加载了项目
  2. 将 SRT 字幕文件拖入/导入到时间线
  3. 脚本需要能访问 DaVinci Resolve 的脚本 API

安装到 DaVinci Resolve 脚本菜单:
  将此文件复制到以下目录之一:
  - macOS: ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
  - Windows: %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Fusion\\Scripts\\Utility\\
  - Linux: ~/.local/share/DaVinci Resolve/Fusion/Scripts/Utility/
  然后在 DaVinci Resolve 中: 工作区 → 脚本 → davinci_subtitle_search
"""

import re
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path


# ==================== SRT 解析 ====================


def parse_time(time_str: str) -> float:
    """将 SRT 时间格式 (HH:MM:SS,mmm) 转为秒数。"""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def format_time(seconds: float) -> str:
    """将秒数转为 HH:MM:SS.mmm 格式。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def parse_srt(filepath: str) -> list[dict]:
    """
    解析 SRT 文件，返回字幕条目列表。
    每个条目: {"index": int, "start": float, "end": float, "text": str}
    """
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()

    # SRT 格式: 序号 → 时间行 → 文本 → 空行
    pattern = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"
        r"((?:.+\n?)+)",
        re.MULTILINE,
    )

    entries = []
    for match in pattern.finditer(content):
        idx = int(match.group(1))
        start = parse_time(match.group(2))
        end = parse_time(match.group(3))
        text = match.group(4).strip().replace("\n", " ")
        # 去除 HTML 标签 (部分 SRT 包含 <i>, <b> 等)
        text = re.sub(r"<[^>]+>", "", text)
        entries.append({
            "index": idx,
            "start": start,
            "end": end,
            "text": text,
        })

    return entries


def search_subtitles(entries: list[dict], keyword: str) -> list[dict]:
    """在字幕条目中搜索关键词，返回匹配的条目。"""
    keyword = keyword.strip().lower()
    if not keyword:
        return entries
    results = []
    for entry in entries:
        if keyword in entry["text"].lower():
            results.append(entry)
    return results


# ==================== DaVinci Resolve API ====================


def get_resolve():
    """获取 DaVinci Resolve 脚本 API 对象。"""
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except ImportError:
        pass

    # 尝试通过 fusionscript 模块
    try:
        import fusionscript as dvr
        return dvr.scriptapp("Resolve")
    except ImportError:
        pass

    # 尝试添加常见路径
    resolve_paths = [
        # macOS
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        # Linux
        "/opt/resolve/Developer/Scripting/Modules",
        "/opt/resolve/libs/Fusion/Modules",
        # Windows (常见路径)
        "C:/ProgramData/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules",
    ]
    for p in resolve_paths:
        if Path(p).exists() and p not in sys.path:
            sys.path.append(p)

    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except (ImportError, AttributeError):
        return None


def jump_to_time(resolve, seconds: float) -> bool:
    """在 DaVinci Resolve 时间线上跳转到指定时间（秒）。"""
    if not resolve:
        return False

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        if not project:
            return False

        timeline = project.GetCurrentTimeline()
        if not timeline:
            return False

        fps = float(timeline.GetSetting("timelineFrameRate"))
        # 将秒数转为帧号（从时间线起始帧开始）
        start_frame = int(timeline.GetStartFrame())
        target_frame = start_frame + int(seconds * fps)
        timeline.SetCurrentTimecode(
            frame_to_timecode(target_frame, fps)
        )
        return True
    except Exception as e:
        print(f"跳转失败: {e}")
        return False


def frame_to_timecode(frame: int, fps: float) -> str:
    """将帧号转为时间码字符串 HH:MM:SS:FF。"""
    fps_int = round(fps)
    total_seconds = frame // fps_int
    ff = frame % fps_int
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


# ==================== GUI ====================


class SubtitleSearchApp:
    """字幕搜索主界面。"""

    def __init__(self):
        self.entries = []
        self.results = []
        self.resolve = None
        self.srt_path = None

        # 尝试连接 DaVinci Resolve
        self.resolve = get_resolve()

        self._build_ui()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("DaVinci Resolve 字幕搜索定位")
        self.root.geometry("700x550")
        self.root.configure(bg="#1a1a2e")
        self.root.minsize(600, 400)

        style = ttk.Style()
        style.theme_use("clam")

        # 深色主题样式
        style.configure("Dark.TFrame", background="#1a1a2e")
        style.configure("Dark.TLabel", background="#1a1a2e", foreground="#e0e0e0",
                         font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background="#1a1a2e", foreground="#00d4ff",
                         font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Status.TLabel", background="#16213e", foreground="#888",
                         font=("Microsoft YaHei UI", 9))
        style.configure("Dark.TButton", font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))

        main_frame = ttk.Frame(self.root, style="Dark.TFrame", padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        title_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(title_frame, text="字幕搜索定位", style="Title.TLabel").pack(side=tk.LEFT)

        # 连接状态
        status_text = "已连接 DaVinci Resolve" if self.resolve else "未连接 (仅搜索模式)"
        status_color = "#00ff88" if self.resolve else "#ff6b6b"
        self.status_dot = tk.Label(title_frame, text="●", fg=status_color,
                                    bg="#1a1a2e", font=("", 10))
        self.status_dot.pack(side=tk.RIGHT, padx=(0, 5))
        self.status_label = tk.Label(title_frame, text=status_text, fg=status_color,
                                      bg="#1a1a2e", font=("Microsoft YaHei UI", 9))
        self.status_label.pack(side=tk.RIGHT)

        # 文件选择
        file_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        file_frame.pack(fill=tk.X, pady=(0, 8))

        self.file_var = tk.StringVar(value="请选择 SRT 字幕文件...")
        file_entry = tk.Entry(file_frame, textvariable=self.file_var, state="readonly",
                               bg="#16213e", fg="#aaa", relief=tk.FLAT,
                               font=("Microsoft YaHei UI", 9), readonlybackground="#16213e")
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        open_btn = ttk.Button(file_frame, text="打开 SRT", command=self._open_file,
                               style="Dark.TButton")
        open_btn.pack(side=tk.RIGHT, padx=(8, 0))

        # 搜索栏
        search_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        search_frame.pack(fill=tk.X, pady=(0, 8))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._on_search())

        search_entry = tk.Entry(search_frame, textvariable=self.search_var,
                                 bg="#16213e", fg="#e0e0e0", insertbackground="#00d4ff",
                                 relief=tk.FLAT, font=("Microsoft YaHei UI", 12))
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        search_entry.bind("<Return>", lambda e: self._on_search())

        self.count_label = tk.Label(search_frame, text="", bg="#1a1a2e", fg="#888",
                                     font=("Microsoft YaHei UI", 9))
        self.count_label.pack(side=tk.RIGHT, padx=(8, 0))

        # 搜索提示
        hint_label = tk.Label(main_frame, text="输入关键词实时搜索，双击结果跳转到时间线位置",
                               bg="#1a1a2e", fg="#666", font=("Microsoft YaHei UI", 9))
        hint_label.pack(anchor=tk.W, pady=(0, 5))

        # 结果列表
        list_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview (表格样式)
        columns = ("time", "text")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                  selectmode="browse", height=15)
        self.tree.heading("time", text="时间", anchor=tk.W)
        self.tree.heading("text", text="字幕内容", anchor=tk.W)
        self.tree.column("time", width=120, minwidth=100, stretch=False)
        self.tree.column("text", width=500, minwidth=200)

        # Treeview 样式
        style.configure("Treeview",
                         background="#0f3460",
                         foreground="#e0e0e0",
                         fieldbackground="#0f3460",
                         font=("Microsoft YaHei UI", 10),
                         rowheight=28)
        style.configure("Treeview.Heading",
                         background="#16213e",
                         foreground="#00d4ff",
                         font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#e94560")],
                   foreground=[("selected", "#ffffff")])

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击跳转
        self.tree.bind("<Double-1>", self._on_double_click)
        # 回车跳转
        self.tree.bind("<Return>", self._on_double_click)

        # 底部状态栏
        bottom_frame = tk.Frame(main_frame, bg="#16213e", height=28)
        bottom_frame.pack(fill=tk.X, pady=(8, 0))
        self.bottom_label = tk.Label(bottom_frame, text="就绪", bg="#16213e", fg="#888",
                                      font=("Microsoft YaHei UI", 9), padx=8)
        self.bottom_label.pack(side=tk.LEFT, fill=tk.X)

        # 快捷键
        self.root.bind("<Control-o>", lambda e: self._open_file())
        self.root.bind("<Control-f>", lambda e: search_entry.focus_set())
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def _open_file(self):
        """打开 SRT 文件。"""
        filepath = filedialog.askopenfilename(
            title="选择 SRT 字幕文件",
            filetypes=[("SRT 字幕文件", "*.srt"), ("所有文件", "*.*")],
        )
        if not filepath:
            return

        try:
            self.entries = parse_srt(filepath)
            self.srt_path = filepath
            self.file_var.set(Path(filepath).name)
            self.bottom_label.config(text=f"已加载 {len(self.entries)} 条字幕")
            self._on_search()  # 刷新列表
        except Exception as e:
            messagebox.showerror("解析错误", f"无法解析 SRT 文件:\n{e}")

    def _on_search(self):
        """搜索并刷新结果列表。"""
        keyword = self.search_var.get()
        self.results = search_subtitles(self.entries, keyword)

        # 清空列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 填充结果
        for entry in self.results:
            time_str = format_time(entry["start"])
            self.tree.insert("", tk.END, values=(time_str, entry["text"]),
                              tags=(str(entry["start"]),))

        # 更新计数
        total = len(self.entries)
        found = len(self.results)
        if keyword.strip():
            self.count_label.config(text=f"{found}/{total} 条匹配")
        else:
            self.count_label.config(text=f"共 {total} 条")

    def _on_double_click(self, event):
        """双击结果行，跳转到对应时间点。"""
        selection = self.tree.selection()
        if not selection:
            return

        item = self.tree.item(selection[0])
        time_str = item["values"][0]
        text = item["values"][1]

        # 从 tags 获取精确秒数
        tags = self.tree.item(selection[0], "tags")
        seconds = float(tags[0]) if tags else 0

        if self.resolve:
            success = jump_to_time(self.resolve, seconds)
            if success:
                self.bottom_label.config(
                    text=f"已跳转到 {time_str} → {text[:30]}...",
                    fg="#00ff88",
                )
            else:
                self.bottom_label.config(
                    text="跳转失败，请确认 DaVinci Resolve 已打开时间线",
                    fg="#ff6b6b",
                )
        else:
            self.bottom_label.config(
                text=f"[未连接] {time_str} → {text[:40]}",
                fg="#ffaa00",
            )

    def run(self):
        self.root.mainloop()


# ==================== 入口 ====================

if __name__ == "__main__":
    app = SubtitleSearchApp()
    app.run()
