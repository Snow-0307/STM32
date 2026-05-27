#!/usr/bin/env python3
"""
Pen Plotter Host Software
用于 STM32G070 笔式绘图仪的上位机软件
功能: 绘图 → 解析为 自定义指令 → 串口发送
"""

import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import math
import os
import struct
import sys
import os
import json

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# ── 文字书写模块 ──
_HERSHEY_AVAILABLE = False

# 强制 PyInstaller 打包时包含 HersheyFonts
try:
    import HersheyFonts
except ImportError:
    pass
try:
    # PyInstaller 打包后模块在同级目录
    _base = os.path.dirname(sys.argv[0]) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
    sys.path.insert(0, _base)
    import hershey_reader as hr
    _HERSHEY_AVAILABLE = True
except ImportError:
    try:
        import hershey_reader as hr
        _HERSHEY_AVAILABLE = True
    except ImportError:
        pass


# ════════════════════════════════════════════════════════════════
#  Constants
# ════════════════════════════════════════════════════════════════

APP_TITLE     = "笔式绘图仪 上位机"
CANVAS_W      = 860
CANVAS_H      = 680
MARGIN        = 48
RULER_SIZE    = 28           # 外部 XY 轴标尺宽度
GRID_MINOR_MM = 10
GRID_MAJOR_MM = 50

WORK_AREA_MM_W = 210          # X 方向 210mm
WORK_AREA_MM_H = 297          # Y 方向 297mm (A4)

ZOOM_MIN  = 0.1
ZOOM_MAX  = 20.0
ZOOM_STEP = 1.15

WORK_AREA_BG = "#fff8dc"      # 淡黄色（护眼色）

BAUD_RATES = [
    9600, 19200, 38400, 57600,
    115200, 230400, 256000
]

STROKE_COLORS = ["#2c3e50", "#e74c3c", "#2980b9", "#27ae60",
                 "#8e44ad", "#d35400", "#16a085", "#c0392b"]

# ── Binary protocol constants (must match firmware) ──────────
PKT_SOF       = 0xAA
PKT_MOVE_TO   = 0x01
PKT_PEN_UP    = 0x02
PKT_PEN_DOWN  = 0x03
PKT_SYNC      = 0x04
PKT_ESTOP     = 0x05

SPEED_F500    = 0
SPEED_F800    = 1
SPEED_F1200   = 2
SPEED_F3000   = 3
BATCH_SIZE    = 15    # packets between SYNC checkpoints
MM_TO_STEPS   = 80

STATE_IDLE  = "idle"
STATE_SELECT = "select"
STATE_LINE  = "line"
STATE_CURVE  = "curve"


# ════════════════════════════════════════════════════════════════
#  Main Application
# ════════════════════════════════════════════════════════════════

class PenPlotterHost:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1400x800")
        self.root.minsize(1000, 650)

        # ---- state ----
        self.strokes       = []       # list of Stroke dicts
        self.current_color = STROKE_COLORS[0]
        self.draw_mode     = STATE_SELECT
        self.current_stroke = None
        self.zoom          = 1.0
        self.pan_x         = 0.0
        self.pan_y         = 0.0
        self.rotation      = 0        # 0/90/180/270

        # line mode state
        self.line_start = None

        # select mode drag state
        self._drag_start = None
        self._drag_pan_start = None

        # capture mode
        self._capture_idx = 0

        # serial
        self.ser           = None
        self.serial_lock   = threading.Lock()
        self._sending      = False
        self.binary_packets = None
        self.text_stroke_speeds = []

        self._text_drag_data = None  # {start_mm: (x,y), original_strokes: [...]}
        self.__path_of_host = os.path.dirname(os.path.abspath(__file__))
        self._text_position_confirmed = False  # 文字笔画速度列表
        self._font_mode = False
        self._font_chars = list("。，、；：？！（）【】《》——…·0123456789")
        self._font_char_idx = 0
        self._font_grid_x = 15.0
        self._font_grid_y = 220.0
        self._font_grid_size = 30.0

        # 模板目录（放在上位机目录下的 templates/）
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self._templates_dir = os.path.join(os.path.dirname(script_dir), 'templates')
        self._templates_file = os.path.join(self._templates_dir, 'templates.json')
        self._current_template = None  # str: template name, None = 空白
        self._template_images = {}     # name -> True 表示已加载
        self._template_image_paths = {} # name -> 原始图片路径
        self._template_scaled = None   # 当前缩放版本的 PhotoImage（保持引用防GC）
        self._template_pil_images = {}  # name -> PIL Image 对象
        # 弹窗设置持久化
        self._saved_dialog_settings = {
            'fs': '7', 'csp': '0.8', 'lsp': '0.9', 'al': 'left',
            'mgx': '25', 'mgy': '43',
            'hw_level': '自然', 'layout_level': '中等', 'spacing_level': '中等',
        }

        # ---- build UI ----
        self._build_ui()

        # ---- bindings ----
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── UI Build ──────────────────────────────────────────────

    def _build_ui(self):
        # top toolbar
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(top, text="端口:").pack(side=tk.LEFT)
        self.port_cb = ttk.Combobox(top, width=18, state="readonly")
        self.port_cb.pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="刷", width=3, command=self.refresh_ports).pack(side=tk.LEFT)

        ttk.Label(top, text="  波特率").pack(side=tk.LEFT, padx=(10, 0))
        self.baud_cb = ttk.Combobox(top, values=BAUD_RATES, width=8, state="readonly")
        self.baud_cb.current(4)
        self.baud_cb.pack(side=tk.LEFT, padx=2)

        ttk.Button(top, text="连接", command=self.connect_serial).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="断开", command=self.disconnect_serial).pack(side=tk.LEFT)

        self.status_lbl = ttk.Label(top, text="🔌 未连接", foreground="gray")
        self.status_lbl.pack(side=tk.LEFT, padx=15)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(top, text="二进制").pack(side=tk.LEFT)
        self.send_btn = ttk.Button(top, text="全部发送", command=self.send_gcode,
                    state=tk.DISABLED)
        self.send_btn.pack(side=tk.LEFT, padx=2)
        self.cancel_btn = ttk.Button(top, text="取消发送", command=self.cancel_send,
                    state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(top, text="模板:").pack(side=tk.LEFT)
        self.template_var = tk.StringVar(value="空白")
        self.template_menu = ttk.Combobox(top, values=self._get_template_names(),
                    textvariable=self.template_var, width=12, state="readonly")
        self.template_menu.pack(side=tk.LEFT, padx=2)
        self.template_menu.bind('<<ComboboxSelected>>', lambda e: self._select_template(self.template_var.get()))
        ttk.Button(top, text="📥 导入", command=self._import_template).pack(side=tk.LEFT, padx=2)

        # ---- mode toolbar ----
        mode_frame = ttk.Frame(self.root)
        mode_frame.pack(fill=tk.X, padx=6, pady=(0, 2))

        ttk.Label(mode_frame, text="模式:", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))

        self.mode_var = tk.StringVar(value="select")
        for mode_id, text in [("select", "选择"), ("line", "直线"), ("curve", "曲线")]:
            rb = ttk.Radiobutton(mode_frame, text=text, value=mode_id,
                    variable=self.mode_var, command=self._on_mode_change)
            rb.pack(side=tk.LEFT, padx=2)

        ttk.Separator(mode_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(mode_frame, text="🔄 左旋90°",
                   command=lambda: self.rotate_canvas(-90)).pack(side=tk.LEFT, padx=2)
        ttk.Button(mode_frame, text="🔄 右旋90°",
                   command=lambda: self.rotate_canvas(90)).pack(side=tk.LEFT, padx=2)

        ttk.Separator(mode_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(mode_frame, text="↩ 撤销",
                   command=self.undo_last).pack(side=tk.LEFT, padx=2)
        ttk.Button(mode_frame, text="🗑 清空",
                   command=self.clear_all).pack(side=tk.LEFT, padx=2)

        ttk.Separator(mode_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.parse_btn = ttk.Button(mode_frame, text="⚙ 解析为二进制",
                    command=self.parse_to_binary)
        self.parse_btn.pack(side=tk.LEFT, padx=2)

        # ── 文字书写 ──
        ttk.Separator(mode_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(mode_frame, text="写字:").pack(side=tk.LEFT)
        ttk.Button(mode_frame, text="✏ 写字",
                   command=self._open_text_dialog).pack(side=tk.LEFT, padx=2)
        # 字体选择下拉
        ttk.Label(mode_frame, text="字体:").pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value="乐米栀夏浅风体")
        font_menu = ttk.OptionMenu(mode_frame, self.font_var,
                    "乐米栀夏浅风体",
                    *hr.FONT_OPTIONS.keys(),
                    command=self._on_font_change)
        font_menu.pack(side=tk.LEFT, padx=2)

        # 英文字体下拉（放在中文下拉右侧）
        ttk.Label(mode_frame, text="英文:").pack(side=tk.LEFT, padx=(8,0))
        self.en_font_var = tk.StringVar(value="Hershey Script")
        en_font_menu = ttk.Combobox(mode_frame, values=[k for k in hr.FONT_OPTIONS.keys() if k.startswith("English")],
                    textvariable=self.en_font_var, width=14, state="readonly")
        en_font_menu.pack(side=tk.LEFT, padx=2)

        self.confirm_pos_btn = ttk.Button(mode_frame, text="✅ 确认位置",
                    command=self._confirm_text_position)
        self.confirm_pos_btn.pack(side=tk.LEFT, padx=2)
        self.confirm_pos_btn.pack_forget()


        self.stroke_lbl = ttk.Label(mode_frame, text="笔画数: 0")
        self.stroke_lbl.pack(side=tk.RIGHT, padx=10)

        # ---- main content ----
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)

        # left frame: canvas
        left_frame = ttk.Frame(main)
        main.add(left_frame, weight=3)

        self.canvas = tk.Canvas(left_frame, width=CANVAS_W, height=CANVAS_H,
                    bg="white", highlightthickness=0,
                    cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self._redraw_canvas()

        # coord label + zoom
        info_frame = ttk.Frame(left_frame)
        info_frame.pack(fill=tk.X, padx=8)
        self.coord_lbl = ttk.Label(info_frame, text="X: 0.0  Y: 0.0  mm",
                    font=("Consolas", 10))
        self.coord_lbl.pack(side=tk.LEFT)
        self.mode_lbl = ttk.Label(info_frame, text="曲线模式",
                    font=("Consolas", 10), foreground="#2980b9")
        self.mode_lbl.pack(side=tk.LEFT, padx=15)
        self.zoom_lbl = ttk.Label(info_frame, text="  缩放: 100%",
                    font=("Consolas", 10), foreground="#888")
        self.zoom_lbl.pack(side=tk.RIGHT)

        # right frame: gcode preview + echo debug
        right_frame = ttk.Frame(main)
        main.add(right_frame, weight=2)

        right_pane = ttk.PanedWindow(right_frame, orient=tk.VERTICAL)
        right_pane.pack(fill=tk.BOTH, expand=True)

        # ---- Top: Binary preview ----
        bin_frame = ttk.Frame(right_pane)
        right_pane.add(bin_frame, weight=1)

        bin_header = ttk.Frame(bin_frame)
        bin_header.pack(fill=tk.X)
        ttk.Label(bin_header, text="二进制指令预览",
                  font=("", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(bin_header, text="复制",
                   command=self.copy_gcode).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bin_header, text="清空",
                   command=self.clear_gcode_preview).pack(side=tk.RIGHT, padx=2)

        self.gcode_text = scrolledtext.ScrolledText(
            bin_frame, font=("Consolas", 10), height=8, width=40,
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
            wrap=tk.NONE, state=tk.DISABLED)
        self.gcode_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ---- Bottom: Serial echo / debug ----
        echo_frame = ttk.Frame(right_pane)
        right_pane.add(echo_frame, weight=1)

        echo_header = ttk.Frame(echo_frame)
        echo_header.pack(fill=tk.X)
        ttk.Label(echo_header, text="调试回显",
                  font=("", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(echo_header, text="清空",
                   command=self.clear_echo).pack(side=tk.RIGHT, padx=2)

        self.echo_text = scrolledtext.ScrolledText(
            echo_frame, font=("Consolas", 9), height=6, width=40,
            bg="#1a1a1a", fg="#b0b0b0", state=tk.DISABLED)
        self.echo_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ---- canvas bindings ----
        self.canvas.bind("<Button-1>", self._on_canvas_down)
        self.canvas.bind("<B1-Motion>", self._on_canvas_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_up)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<Motion>", self._on_canvas_hover)

        # 初始用after确保窗口布局完成后再重绘
        self.root.after(50, self._fix_initial_view)

        # populate ports
        self.refresh_ports()

    def _on_mode_change(self):
        mode = self.mode_var.get()
        self.draw_mode = mode
        self.line_start = None
        if mode == "select":
            self.mode_lbl.config(text="选择模式")
            self.canvas.config(cursor="fleur")
        elif mode == "line":
            self.mode_lbl.config(text="直线模式")
            self.canvas.config(cursor="crosshair")
        elif mode == "curve":
            self.mode_lbl.config(text="曲线模式")
            self.canvas.config(cursor="crosshair")
        self._redraw_canvas()

    # ── Port / Serial ─────────────────────────────────────────

    def refresh_ports(self):
        if not HAS_SERIAL:
            self.port_cb["values"] = ["(未安装pyserial)"]
            self.port_cb.set("(未安装pyserial)")
            return
        try:
            ports = list(serial.tools.list_ports.comports())
            items = [f"{p.device} - {p.description}" for p in ports]
            if not items:
                items = ["(无可用串口)"]
            self.port_cb["values"] = items
            if items:
                self.port_cb.current(0)
        except Exception:
            self.port_cb["values"] = ["(检测失败)"]

    def connect_serial(self):
        if not HAS_SERIAL:
            messagebox.showwarning("库缺失",
                    "未安装 pyserial 库。\n请在终端执行: pip install pyserial")
            return
        port_raw = self.port_cb.get()
        if not port_raw or port_raw.startswith("(未"):
            messagebox.showwarning("端口错误", "没有可用的串口端口。")
            return
        port = port_raw.split(" - ")[0]
        try:
            baud = int(self.baud_cb.get())
        except (ValueError, tk.TclError):
            baud = 115200

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(port, baud, timeout=0.5)
            self.status_lbl.config(text=f"🔌 已连接 {port} @ {baud}",
                    foreground="#27ae60")
            self._echo(f"已连接到 {port} @ {baud}\n")
        except Exception as e:
            self.status_lbl.config(text="🔌 连接失败", foreground="#e74c3c")
            self._echo(f"连接失败: {e}\n")

    def disconnect_serial(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.status_lbl.config(text="🔌 未连接", foreground="gray")

    # ── Echo / Debug ──────────────────────────────────────────

    def _echo(self, msg):
        self.echo_text.config(state=tk.NORMAL)
        self.echo_text.insert(tk.END, msg)
        self.echo_text.see(tk.END)
        self.echo_text.config(state=tk.DISABLED)

    def clear_echo(self):
        self.echo_text.config(state=tk.NORMAL)
        self.echo_text.delete("1.0", tk.END)
        self.echo_text.config(state=tk.DISABLED)

    # ── Canvas helpers ────────────────────────────────────────

    @property
    def _scale(self):
        """Current effective scale (px/mm)."""
        cw = max(self.canvas.winfo_width() or 0, CANVAS_W)
        ch = max(self.canvas.winfo_height() or 0, CANVAS_H)
        scale_x = (cw - 2 * MARGIN) / 700.0
        scale_y = (ch - 2 * MARGIN) / 700.0
        return min(scale_x, scale_y) * self.zoom

    def _rotate_display(self, x_mm, y_mm):
        """Rotate mm coords for display only (around A4 center). Reverse for mouse."""
        if self.rotation == 0:
            return x_mm, y_mm
        cx, cy = WORK_AREA_MM_W / 2, WORK_AREA_MM_H / 2
        dx, dy = x_mm - cx, y_mm - cy
        r = self.rotation % 360
        if r == 90:
            return cx - dy, cy + dx
        elif r == 180:
            return cx - dx, cy - dy
        elif r == 270:
            return cx + dy, cy - dx
        return x_mm, y_mm

    def _mm_to_canvas(self, x_mm, y_mm):
        """Convert mm coords to canvas pixels (applies rotation for display)."""
        xr, yr = self._rotate_display(x_mm, y_mm)
        s = self._scale
        cw = max(self.canvas.winfo_width() or 0, CANVAS_W)
        ch = max(self.canvas.winfo_height() or 0, CANVAS_H)
        ox = MARGIN + self.pan_x
        oy = (ch - MARGIN) + self.pan_y
        return ox + xr * s, oy - yr * s

    def _canvas_to_mm(self, px, py):
        """Convert canvas pixels to mm coords (reverse rotation for mouse)."""
        s = self._scale
        cw = self.canvas.winfo_width() or CANVAS_W
        ch = self.canvas.winfo_height() or CANVAS_H
        ox = MARGIN + self.pan_x
        oy = (ch - MARGIN) + self.pan_y
        xr = (px - ox) / s
        yr = (oy - py) / s
        # Reverse rotation to get fixed mm coords
        if self.rotation == 0:
            return xr, yr
        cx, cy = WORK_AREA_MM_W / 2, WORK_AREA_MM_H / 2
        dx, dy = xr - cx, yr - cy
        r = self.rotation % 360
        if r == 90:
            return cx + dy, cy - dx
        elif r == 180:
            return cx - dx, cy - dy
        elif r == 270:
            return cx - dy, cy + dx
        return xr, yr

    def _redraw_canvas(self):
        """Redraw: grid, axes, A4, strokes — rotation applied via _mm_to_canvas."""
        self.canvas.delete("all")

        VMIN, VMAX = -200, 500
        rf = ("Consolas", 8)

        def mm_line(x1, y1, x2, y2, **kw):
            px1, py1 = self._mm_to_canvas(x1, y1)
            px2, py2 = self._mm_to_canvas(x2, y2)
            self.canvas.create_line(px1, py1, px2, py2, **kw)

        def mm_rect(x1, y1, x2, y2, **kw):
            px1, py1 = self._mm_to_canvas(x1, y1)
            px2, py2 = self._mm_to_canvas(x2, y2)
            self.canvas.create_rectangle(px1, py1, px2, py2, **kw)

        def mm_text(x, y, text, **kw):
            px, py = self._mm_to_canvas(x, y)
            self.canvas.create_text(px, py, text=text, **kw)

        # ── White background ──
        mm_rect(VMIN, VMIN, VMAX, VMAX, fill="#fafafa", outline="")

        # ── A4 area (模板或黄色底色) ──
        A4_Y0 = -6
        A4_Y1 = 290
        if self._current_template and hasattr(self, '_template_pil_images') and self._current_template in self._template_pil_images:
            # 获取 A4 区域像素坐标
            x0, y0 = self._mm_to_canvas(1, A4_Y1)    # 左上
            x1, y1 = self._mm_to_canvas(WORK_AREA_MM_W + 1, A4_Y0)  # 右下
            a4_w = abs(x1 - x0)
            a4_h = abs(y1 - y0)
            if a4_w > 5 and a4_h > 5:
                try:
                    from PIL import ImageTk
                    pil_img = self._template_pil_images[self._current_template]
                    img_resized = pil_img.resize((int(a4_w), int(a4_h)))
                    tk_img = ImageTk.PhotoImage(img_resized)
                    self._template_scaled = tk_img
                    self.canvas.create_image(x0, y0, image=tk_img,
                    anchor=tk.NW, tags="bg_template")
                except:
                    mm_rect(1, A4_Y0, WORK_AREA_MM_W + 1, A4_Y1,
                    fill=WORK_AREA_BG, outline="", width=0)
        else:
            # 黄色底色
            mm_rect(1, A4_Y0, WORK_AREA_MM_W + 1, A4_Y1,
                    fill=WORK_AREA_BG, outline="", width=0)

        # ── Full grid ──
        for gx in range(VMIN, VMAX + 1, GRID_MINOR_MM):
            color = "#ddd" if gx % GRID_MAJOR_MM != 0 else "#bbb"
            mm_line(gx, VMIN, gx, VMAX, fill=color, width=1)
        for gy in range(VMIN, VMAX + 1, GRID_MINOR_MM):
            color = "#ddd" if gy % GRID_MAJOR_MM != 0 else "#bbb"
            mm_line(VMIN, gy, VMAX, gy, fill=color, width=1)

        # ── A4 border (独立画在网格上面) ──
        mm_rect(1, A4_Y0, WORK_AREA_MM_W + 1, A4_Y1,
                fill="", outline="#999", width=2)

        # ── XY axes ──
        mm_line(VMIN, 0, VMAX, 0, fill="#333", width=2)   # X-axis
        mm_line(0, VMIN, 0, VMAX, fill="#333", width=2)   # Y-axis

        # ── Axis labels ──
        for gx in range(VMIN, VMAX + 1, GRID_MAJOR_MM):
            if gx == 0: continue
            mm_line(gx, 2, gx, -2, fill="#555", width=1)
            mm_text(gx, -8, str(gx), font=rf, fill="#555", anchor=tk.N)
        for gy in range(VMIN, VMAX + 1, GRID_MAJOR_MM):
            if gy == 0: continue
            mm_line(-2, gy, 2, gy, fill="#555", width=1)
            mm_text(-8, gy, str(gy), font=rf, fill="#555", anchor=tk.E)
        mm_text(-8, -8, "0", font=rf, fill="#333", anchor=tk.NE)



        # ── Strokes ──
        for stroke in self.strokes:
            pts = stroke["points_mm"]
            color = stroke["color"]
            if len(pts) >= 2:
                coords = []
                for p in pts:
                    cx_px, cy_px = self._mm_to_canvas(p[0], p[1])
                    coords.extend([cx_px, cy_px])
                self.canvas.create_line(*coords, fill=color, width=2, tags="stroke")

        # ── Line mode preview ──
        if self.draw_mode == STATE_LINE and self.line_start is not None:
            mx, my = self.line_start
            sx, sy = self._mm_to_canvas(mx, my)
            # Draw a small circle at start point
            r = 4 / (self._scale / 3)  # constant visual size
            self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r,
                    outline=self.current_color, width=2, tags="preview")

        # ── Current drawing preview ──
        if self.current_stroke and len(self.current_stroke["points_mm"]) >= 2:
            pts = self.current_stroke["points_mm"]
            coords = []
            for p in pts:
                cx_px, cy_px = self._mm_to_canvas(p[0], p[1])
                coords.extend([cx_px, cy_px])
            self.canvas.create_line(*coords, fill=self.current_color,
                    width=2, dash=(4, 4), tags="preview")

    # ── Canvas mouse events ───────────────────────────────────

    def _on_canvas_down(self, event):
        mm_x, mm_y = self._canvas_to_mm(event.x, event.y)

        if self.draw_mode == STATE_SELECT:
            # 如果文字位置已确认，不可拖动
            if self._text_position_confirmed:
                self._drag_start = (event.x, event.y)
                self._drag_pan_start = (self.pan_x, self.pan_y)
                return

            # 检查是否点中了某个文字笔画（进入文字拖动模式）
            hit = None
            for si, stroke in enumerate(self.strokes):
                pts = stroke["points_mm"]
                for px, py in pts:
                    if abs(px - mm_x) < 3 and abs(py - mm_y) < 3:
                        hit = si
                        break
                if hit is not None:
                    break
            if hit is not None:
                self._text_drag_data = {
                    "start_mm": (mm_x, mm_y),
                    "original_strokes": [
                        [list(p) for p in s["points_mm"]] for s in self.strokes
                    ]
                }
                self.canvas.config(cursor="fleur")
            else:
                if self._text_drag_data is not None:
                    # 空白处点击 = 取消本次拖动（不确认位置）
                    self._text_drag_data = None
                    self.canvas.config(cursor="crosshair")
                    self._redraw_canvas()
                    return
                self._drag_start = (event.x, event.y)
                self._drag_pan_start = (self.pan_x, self.pan_y)
            return

        if self.draw_mode == STATE_LINE:
            if self.line_start is None:
                # First click — set start point
                self.line_start = (mm_x, mm_y)
                self._redraw_canvas()
            else:
                # Second click — draw line
                start = self.line_start
                # Add two strokes: pen-up move to start, pen-down line to end
                line_stroke = {
                    "points_mm": [start, (mm_x, mm_y)],
                    "color": self.current_color
                }
                if len(line_stroke["points_mm"]) >= 2:
                    self.strokes.append(line_stroke)
                    self.current_color = STROKE_COLORS[len(self.strokes) % len(STROKE_COLORS)]
                    self._update_stroke_count()
                self.line_start = None
                self._redraw_canvas()
            return

        # Curve mode
        self.current_stroke = {
            "points_mm": [(mm_x, mm_y)],
            "color": self.current_color
        }

    def _on_canvas_move(self, event):
        if self.draw_mode == STATE_SELECT:
            if self._text_drag_data is not None:
                mm_x, mm_y = self._canvas_to_mm(event.x, event.y)
                sx, sy = self._text_drag_data["start_mm"]
                dx_mm = mm_x - sx
                dy_mm = mm_y - sy
                orig = self._text_drag_data["original_strokes"]
                for si, stroke in enumerate(self.strokes):
                    pts = stroke["points_mm"]
                    for pi in range(len(pts)):
                        pts[pi] = (orig[si][pi][0] + dx_mm,
                    orig[si][pi][1] + dy_mm)
                self._redraw_canvas()
            elif self._drag_start is not None:
                dx = event.x - self._drag_start[0]
                dy = event.y - self._drag_start[1]
                self.pan_x = self._drag_pan_start[0] + dx
                self.pan_y = self._drag_pan_start[1] + dy
                self._redraw_canvas()
            return

        if self.draw_mode == STATE_LINE:
            # Just update coord display; preview is drawn on hover
            mm_x, mm_y = self._canvas_to_mm(event.x, event.y)
            if self.line_start is not None:
                # Show line preview by redrawing with hover line
                self._redraw_canvas()
                sx, sy = self._mm_to_canvas(self.line_start[0], self.line_start[1])
                ex, ey = self._mm_to_canvas(mm_x, mm_y)
                self.canvas.create_line(sx, sy, ex, ey,
                    fill=self.current_color, width=2,
                    dash=(4, 4), tags="preview")
            self.coord_lbl.config(text=f"X: {mm_x:.1f}  Y: {mm_y:.1f}  mm")
            return

        # Curve mode
        if self.current_stroke is None:
            return
        mm_x, mm_y = self._canvas_to_mm(event.x, event.y)
        self.current_stroke["points_mm"].append((mm_x, mm_y))
        self._redraw_canvas()
        self.coord_lbl.config(text=f"X: {mm_x:.1f}  Y: {mm_y:.1f}  mm")

    def _on_canvas_up(self, event):
        if self.draw_mode == STATE_SELECT:
            if self._text_drag_data is not None:
                # 拖动结束，保存当前笔画位置
                self._text_drag_data = None
                self.canvas.config(cursor="crosshair")
            self._drag_start = None
            self._drag_pan_start = None
            return

        if self.draw_mode == STATE_LINE:
            return  # Line is finalized on second click down, not up

        # Curve mode
        if self.current_stroke is None:
            return
        pts = self.current_stroke["points_mm"]
        if len(pts) >= 2:
            self.strokes.append(self.current_stroke)
            self.current_color = STROKE_COLORS[len(self.strokes) % len(STROKE_COLORS)]
            self._update_stroke_count()
        self.current_stroke = None
        self._redraw_canvas()

    def _fix_initial_view(self):
        """窗口布局完成后修正初始视图"""
        cw = max(self.canvas.winfo_width() or 0, CANVAS_W)
        ch = max(self.canvas.winfo_height() or 0, CANVAS_H)
        s = self._scale
        # A4中心对齐到画布中心
        a4_cx = WORK_AREA_MM_W / 2
        a4_cy = WORK_AREA_MM_H / 2
        self.pan_x = cw / 2 - MARGIN - a4_cx * s
        self.pan_y = -ch / 2 + MARGIN + a4_cy * s
        self._on_mode_change()
        self._redraw_canvas()

    def _on_canvas_hover(self, event):
        """Update coordinate display on mouse move (all modes)."""
        mm_x, mm_y = self._canvas_to_mm(event.x, event.y)
        self.coord_lbl.config(text=f"X: {mm_x:.1f}  Y: {mm_y:.1f}  mm")

    def _on_mousewheel(self, event):
        """Zoom keeping the point under cursor fixed."""
        delta = 0
        if event.num == 4 or event.delta > 0:
            delta = 1
        elif event.num == 5 or event.delta < 0:
            delta = -1
        if delta == 0:
            return

        # Get mm position under mouse BEFORE zoom
        mm_x, mm_y = self._canvas_to_mm(event.x, event.y)
        old_zoom = self.zoom

        if delta > 0:
            self.zoom = min(self.zoom * ZOOM_STEP, ZOOM_MAX)
        else:
            self.zoom = max(self.zoom / ZOOM_STEP, ZOOM_MIN)

        zf = self.zoom / old_zoom

        # Adjust pan so the mm point stays under the same canvas pixel
        cw = self.canvas.winfo_width() or CANVAS_W
        ch = self.canvas.winfo_height() or CANVAS_H
        cx, cy = event.x, event.y
        self.pan_x = cx - MARGIN - (cx - MARGIN - self.pan_x) * zf
        self.pan_y = cy - ch + MARGIN + (ch - MARGIN + self.pan_y - cy) * zf

        self._redraw_canvas()
        self.zoom_lbl.config(text=f"  缩放: {int(self.zoom * 100)}%")

    # ── Canvas commands ───────────────────────────────────────

    def rotate_canvas(self, deg):
        self.rotation = (self.rotation + deg) % 360
        self._redraw_canvas()

    def undo_last(self):
        if self.strokes:
            self.strokes.pop()
            self._redraw_canvas()
            self._update_stroke_count()

    def clear_all(self):
        if messagebox.askyesno("清空确认", "确定要清空所有笔画吗？"):
            self.strokes.clear()
            self.current_stroke = None
            self.line_start = None
            self._redraw_canvas()
            self._update_stroke_count()
            self.binary_packets = None
            self.gcode_text.config(state=tk.NORMAL)
            self.gcode_text.delete("1.0", tk.END)
            self.gcode_text.config(state=tk.DISABLED)

    def _update_stroke_count(self):
        self.stroke_lbl.config(text=f"笔画数: {len(self.strokes)}")

    # ── 文字书写 ──────────────────────────────────────────────

    def _open_text_dialog(self):
        """打开文字输入对话框（内嵌A4纸实时预览）"""
        dlg = tk.Toplevel(self.root)
        dlg.title("文字输入")
        dlg.geometry("1200x900")
        # 居中显示
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dlg.geometry(f"+{sw//2-600}+{sh//2-450}")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.minsize(1000, 800)

        A4_W_PX, A4_H_PX = 420, 594  # A4 比例

        # ── 可拖动标题栏 ──
        title_bar = ttk.Frame(dlg, relief=tk.RAISED, borderwidth=2)
        title_bar.pack(fill=tk.X)
        ttk.Label(title_bar, text="✏ 文字输入（拖动此栏移动窗口，调参实时看效果）",
                  font=("", 10, "bold")).pack(pady=4)

        def start_move(event):
            dlg._drag_data = (event.x_root - dlg.winfo_x(),
                    event.y_root - dlg.winfo_y())
        def do_move(event):
            x, y = dlg._drag_data
            dlg.geometry(f"+{event.x_root - x}+{event.y_root - y}")

        title_bar.bind("<Button-1>", start_move)
        title_bar.bind("<B1-Motion>", do_move)

        # ── 参数行 ──
        pf = ttk.Frame(dlg)
        pf.pack(fill=tk.X, padx=10, pady=4)

        ttk.Label(pf, text="字号:").pack(side=tk.LEFT)
        fs = tk.StringVar(value=self._saved_dialog_settings.get('fs', '7'))
        ttk.Spinbox(pf, from_=3, to=50, width=3, textvariable=fs).pack(side=tk.LEFT, padx=2)

        ttk.Label(pf, text="手写强度:").pack(side=tk.LEFT, padx=(8,0))
        self.hw_level_var = tk.StringVar(value=self._saved_dialog_settings.get('hw_level', '自然'))
        hw_menu = ttk.Combobox(pf, values=["关闭","轻微","自然","明显","狂草"],
                    textvariable=self.hw_level_var, width=5, state="readonly")
        hw_menu.pack(side=tk.LEFT, padx=2)

        ttk.Label(pf, text="字间距:").pack(side=tk.LEFT, padx=(8,0))
        csp = tk.StringVar(value=self._saved_dialog_settings.get('csp', '0.8'))
        ttk.Spinbox(pf, from_=0.5, to=5.0, increment=0.1, width=3, textvariable=csp).pack(side=tk.LEFT, padx=2)

        ttk.Label(pf, text="行距:").pack(side=tk.LEFT, padx=(8,0))
        lsp = tk.StringVar(value=self._saved_dialog_settings.get('lsp', '0.9'))
        ttk.Spinbox(pf, from_=0.5, to=5.0, increment=0.1, width=3, textvariable=lsp).pack(side=tk.LEFT, padx=2)

        ttk.Label(pf, text="对齐:").pack(side=tk.LEFT, padx=(8,0))
        al = tk.StringVar(value=self._saved_dialog_settings.get('al', 'left'))
        ttk.Combobox(pf, values=["left","center","right"],
                      textvariable=al, width=6, state="readonly").pack(side=tk.LEFT, padx=2)



        # 第二行参数
        pf2 = ttk.Frame(dlg)
        pf2.pack(fill=tk.X, padx=10, pady=(0, 4))

        ttk.Label(pf2, text="左边距:").pack(side=tk.LEFT)
        mgx = tk.StringVar(value=self._saved_dialog_settings.get('mgx', '10'))
        ttk.Spinbox(pf2, from_=0, to=50, width=3, textvariable=mgx).pack(side=tk.LEFT, padx=2)

        ttk.Label(pf2, text="上下边距:").pack(side=tk.LEFT, padx=(8,0))
        mgy = tk.StringVar(value=self._saved_dialog_settings.get('mgy', '10'))
        ttk.Spinbox(pf2, from_=0, to=50, width=3, textvariable=mgy).pack(side=tk.LEFT, padx=2)

        ttk.Label(pf2, text="排版强度:").pack(side=tk.LEFT, padx=(8,0))
        self.layout_level_var = tk.StringVar(value=self._saved_dialog_settings.get('layout_level', '中等'))
        ttk.Combobox(pf2, values=["关闭","轻微","中等","明显","狂野"],
                      textvariable=self.layout_level_var, width=5, state="readonly").pack(side=tk.LEFT, padx=2)

        ttk.Label(pf2, text="间距随机:").pack(side=tk.LEFT, padx=(8,0))
        self.spacing_level_var = tk.StringVar(value=self._saved_dialog_settings.get('spacing_level', '中等'))
        ttk.Combobox(pf2, values=["关闭","轻微","中等","明显","狂野"],
                      textvariable=self.spacing_level_var, width=5, state="readonly").pack(side=tk.LEFT, padx=2)

        # ── 左右分栏：左A4预览 + 右文本输入 ──
        main_frame = ttk.Frame(dlg)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 4))

        # 左侧：A4 预览
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)

        a4_canvas = tk.Canvas(left_frame, width=A4_W_PX, height=A4_H_PX,
                    bg="#ffffff", highlightthickness=0,
                    relief=tk.SUNKEN, borderwidth=2)
        a4_canvas.pack()
        a4_scale = A4_W_PX / 210.0

        # 画模板背景
        def draw_a4_bg():
            a4_canvas.delete("bg")
            if self._current_template and hasattr(self, "_template_pil_images") and self._current_template in self._template_pil_images:
                try:
                    from PIL import Image, ImageTk
                    p = self._template_image_paths[self._current_template]
                    img = Image.open(p).convert('RGB')
                    img = img.resize((A4_W_PX, A4_H_PX), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    a4_canvas._bg_img = tk_img
                    a4_canvas.create_image(0, 0, image=tk_img, anchor=tk.NW, tags="bg")
                except: pass
            else:
                a4_canvas.create_rectangle(0, 0, A4_W_PX, A4_H_PX,
                    fill=WORK_AREA_BG, outline="", tags="bg")
        draw_a4_bg()

        # 右侧：文本输入框（与A4等高等宽比例）
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # 持久化之前保存的文字
        if not hasattr(self, '_saved_dialog_text'):
            self._saved_dialog_text = "你好世界\n写字机器人测试"

        text_widget = scrolledtext.ScrolledText(
            right_frame, font=("Microsoft YaHei", 14), wrap=tk.NONE)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert("1.0", self._saved_dialog_text)

        self._last_dialog_strokes = None

        def render_a4(randomize=False):
            """渲染预览。randomize=True 使用实际随机等级，否则全为0（干净预览）"""
            a4_canvas.delete("all")
            # 先画模板背景
            draw_a4_bg()
            txt = text_widget.get("1.0", tk.END).strip()
            if not txt:
                self._last_dialog_strokes = None
                return
            try:
                import text_layout as tl
            except ImportError:
                return
            font_size = float(fs.get())
            if randomize:
                hw_lvl = self._hw_level_to_int()
                lay_lvl = self._layout_level_to_int()
                sp_lvl = self._spacing_level_to_int()
            else:
                hw_lvl = lay_lvl = sp_lvl = 0
            layout = tl.TextLayout(
                font_size_mm=font_size, align=al.get(),
                char_spacing=float(csp.get()),
                line_spacing=float(lsp.get()),
                margin_x=int(mgx.get()), margin_y=int(mgy.get()),
                handwriting_level=hw_lvl,
                layout_level=lay_lvl,
                spacing_randomness_level=sp_lvl)
            self._last_dialog_strokes = layout.layout(txt)
            for stroke in self._last_dialog_strokes:
                pts = stroke["points_mm"]
                if len(pts) < 2:
                    continue
                coords = []
                for px_mm, py_mm in pts:
                    coords.extend([px_mm * a4_scale,
                    A4_H_PX - py_mm * a4_scale])
                a4_canvas.create_line(*coords, fill="#2c3e50", width=1.5)

        # 初始显示干净预览
        dlg.after(300, lambda: render_a4(False))

        # ── 底部按钮 ──
        def do_apply():
            """预览并应用：将当前预览的笔画发送到主画布，不关对话框"""
            if not self._last_dialog_strokes:
                return
            save_dialog_settings()
            # 保存文字
            self._saved_dialog_text = text_widget.get("1.0", tk.END).strip()
            self.strokes.clear()
            self.strokes = self._last_dialog_strokes
            self._text_position_confirmed = False
            self._redraw_canvas()
            self._update_stroke_count()
            self.confirm_pos_btn.pack(side=tk.LEFT, padx=2)

        def do_refresh():
            """刷新：用当前参数重新随机生成"""
            render_a4(True)

        # 关闭时保存文字
        def save_dialog_settings():
            self._saved_dialog_settings['fs'] = fs.get()
            self._saved_dialog_settings['csp'] = csp.get()
            self._saved_dialog_settings['lsp'] = lsp.get()
            self._saved_dialog_settings['al'] = al.get()
            self._saved_dialog_settings['mgx'] = mgx.get()
            self._saved_dialog_settings['mgy'] = mgy.get()
            self._saved_dialog_settings['hw_level'] = self.hw_level_var.get()
            self._saved_dialog_settings['layout_level'] = self.layout_level_var.get()
            self._saved_dialog_settings['spacing_level'] = self.spacing_level_var.get()

        def on_close():
            save_dialog_settings()
            self._saved_dialog_text = text_widget.get("1.0", tk.END).strip()
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", on_close)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="🔄 刷新",
                   command=do_refresh).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📄 预览并应用",
                   command=do_apply).pack(side=tk.RIGHT)

    def _confirm_text_position(self):
        """确认文字位置，锁定不可移动"""
        self._text_position_confirmed = True
        self._text_drag_data = None
        self.confirm_pos_btn.pack_forget()
        self._redraw_canvas()

    # ── 笔迹采集（米字格对话框）────────────────────────────────

    _CAPTURE_CHARS = ["永", "的", "是", "了", "我", "人", "大", "中", "小", "月"]
    _capture_data = {}
    _CAPTURE_SIZE = 400

    def _hw_level_to_int(self):
        """手写强度文字转数字"""
        mapping = {"关闭":0, "轻微":1, "自然":2, "明显":3, "狂草":4}
        return mapping.get(self.hw_level_var.get(), 2)

    def _layout_level_to_int(self):
        """排版强度文字转数字"""
        mapping = {"关闭":0, "轻微":1, "中等":2, "明显":3, "狂野":4}
        return mapping.get(self.layout_level_var.get(), 2)

    def _spacing_level_to_int(self):
        """间距随机文字转数字"""
        mapping = {"关闭":0, "轻微":1, "中等":2, "明显":3, "狂野":4}
        return mapping.get(self.spacing_level_var.get(), 2)

    # ── 模板管理 ──────────────────────────────────────────

    def _load_template_list(self):
        """加载模板列表，返回 {name: filename}"""
        try:
            with open(self._templates_file, 'r', encoding='utf-8') as f:
                data = f.read().strip()
                if data:
                    return json.loads(data)
        except: pass
        # 文件不存在或为空，创建默认
        try:
            os.makedirs(self._templates_dir, exist_ok=True)
            with open(self._templates_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False)
        except: pass
        return {}

    def _save_template_list(self, data):
        with open(self._templates_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def _get_template_names(self):
        """返回模板名列表（含"空白"）"""
        tl = self._load_template_list()
        return ["空白"] + sorted(tl.keys())

    def _load_template_image(self, name):
        """加载模板：存 PIL Image 对象，不预缩放"""
        if not hasattr(self, '_template_pil_images'):
            self._template_pil_images = {}
        tl = self._load_template_list()
        if name not in tl:
            self._current_template = None
            return
        path = os.path.join(self._templates_dir, tl[name])
        if not os.path.exists(path):
            return
        try:
            from PIL import Image
            self._template_pil_images[name] = Image.open(path).convert('RGB')
            self._template_image_paths[name] = path
            self._template_images[name] = True
        except Exception as e:
            pass

    def _select_template(self, name):
        """选择模板"""
        if name == "空白" or not name:
            self._current_template = None
        else:
            self._current_template = name
            if name not in self._template_images:
                self._load_template_image(name)
        if hasattr(self, 'template_var'):
            self.template_var.set(name if name else "空白")
        self._redraw_canvas()

    def _import_template(self):
        """导入模板图片"""
        from tkinter import filedialog, simpledialog, messagebox
        path = filedialog.askopenfilename(
            title="选择模板图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("所有文件", "*.*")]
        )
        if not path:
            return
        name = simpledialog.askstring("模板名称", "给这个模板起个名字：", parent=self.root)
        if not name:
            return
        try:
            import shutil
            os.makedirs(self._templates_dir, exist_ok=True)
            ext = os.path.splitext(path)[1] or '.png'
            fname = f"{name}{ext}"
            dst = os.path.join(self._templates_dir, fname)
            shutil.copy2(path, dst)
            # 更新索引
            tl = self._load_template_list()
            tl[name] = fname
            self._save_template_list(tl)
            # 加载图片
            self._load_template_image(name)
            # 设置当前模板+刷新UI
            self._current_template = name
            if hasattr(self, 'template_menu'):
                self.template_menu['values'] = self._get_template_names()
                self.template_var.set(name)
            self._redraw_canvas()
            messagebox.showinfo("导入成功", f"模板「{name}」已导入", parent=self.root)
        except Exception as e:
            messagebox.showerror("导入失败", f"导入出错：{e}", parent=self.root)

    def _refresh_template_dropdown(self):
        """刷新模板下拉列表"""
        if hasattr(self, 'template_menu'):
            names = self._get_template_names()
            self.template_menu['values'] = names
            if self._current_template:
                self.template_var.set(self._current_template)
            else:
                self.template_var.set("空白")

    def _on_font_change(self, font_name):
        """切换字体"""
        if _HERSHEY_AVAILABLE:
            fn = hr.FONT_OPTIONS.get(font_name, "STRK-Lemi.json")
            hr.set_font(fn)
            self.status_lbl.config(text=f"字体: {font_name}")

    def _start_capture(self):
        self._capture_data = {}
        self._capture_idx = 0
        self._open_capture_dialog()

    def _open_capture_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("笔迹采集")
        dlg.transient(self.root)
        dlg.grab_set()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dlg.geometry(f"+{sw//2-250}+{sh//2-300}")
        dlg.resizable(False, False)

        char = self._CAPTURE_CHARS[self._capture_idx]
        title_lbl = ttk.Label(dlg, text=f"「{char}」  ({self._capture_idx+1}/{len(self._CAPTURE_CHARS)})",
                    font=("", 16, "bold"))
        title_lbl.pack(pady=(10, 2))
        ttk.Label(dlg, text="在米字格内书写，尽量与灰色参考字重叠",
                  font=("", 9)).pack()

        canvas = tk.Canvas(dlg, width=self._CAPTURE_SIZE, height=self._CAPTURE_SIZE,
                    bg="white", highlightthickness=1, highlightbackground="#ccc")
        canvas.pack(padx=10, pady=5)

        data = {"active": False, "stroke": [], "strokes": []}

        # 画米字格
        s = self._CAPTURE_SIZE
        canvas.create_rectangle(2, 2, s-2, s-2, outline="#c00", width=2)
        canvas.create_line(s//2, 2, s//2, s-2, fill="#c00", width=1)
        canvas.create_line(2, s//2, s-2, s//2, fill="#c00", width=1)
        canvas.create_line(2, 2, s-2, s-2, fill="#c00", width=1)
        canvas.create_line(s-2, 2, 2, s-2, fill="#c00", width=1)
        for i in [s//4, 3*s//4]:
            canvas.create_line(i, 2, i, s-2, fill="#c00", dash=(2,4), width=1)
            canvas.create_line(2, i, s-2, i, fill="#c00", dash=(2,4), width=1)

        # 画灰色参考字
        if _HERSHEY_AVAILABLE:
            ref = hr.get_strokes(char)
            if ref:
                margin = 40
                sc = s - 2*margin
                for st in ref:
                    coords = []
                    for x_n, y_n in st:
                        coords.extend([margin + x_n*sc, margin + y_n*sc])
                    canvas.create_line(*coords, fill="#ddd", width=3, dash=(4,4))

        # 鼠标事件
        def on_down(ev):
            data["active"] = True
            data["stroke"] = [(ev.x, ev.y)]
            canvas.create_oval(ev.x-2, ev.y-2, ev.x+2, ev.y+2, fill="#333", outline="", tags="draw")
        def on_move(ev):
            if not data["active"]: return
            x, y = ev.x, ev.y
            lx, ly = data["stroke"][-1]
            data["stroke"].append((x, y))
            canvas.create_line(lx, ly, x, y, fill="#333", width=3, tags="draw")
        def on_up(ev):
            data["active"] = False
            if len(data["stroke"]) >= 2:
                data["strokes"].append(list(data["stroke"]))

        canvas.bind("<Button-1>", on_down)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_up)

        def clear_all():
            canvas.delete("draw")
            data["stroke"] = []
            data["strokes"] = []

        def skip_back():
            if self._capture_idx <= 0: return
            self._capture_idx -= 1
            canvas.delete("draw")
            data["stroke"] = []
            data["strokes"] = []
            ch = self._CAPTURE_CHARS[self._capture_idx]
            title_lbl.config(text=f"「{ch}」  ({self._capture_idx+1}/{len(self._CAPTURE_CHARS)})")
            # 重新画参考字
            canvas.delete("ref")
            if _HERSHEY_AVAILABLE:
                ref = hr.get_strokes(ch)
                if ref:
                    margin = 40; sc = self._CAPTURE_SIZE - 2*margin
                    for st in ref:
                        coords = []
                        for x_n, y_n in st:
                            coords.extend([margin + x_n*sc, margin + y_n*sc])
                        canvas.create_line(*coords, fill="#ddd", width=3, dash=(4,4), tags="ref")

        def next_char():
            if not data["strokes"]:
                messagebox.showwarning("提示", "请先书写！", parent=dlg)
                return
            ch = self._CAPTURE_CHARS[self._capture_idx]
            s = self._CAPTURE_SIZE
            norm = []
            for st in data["strokes"]:
                n = [((x-2)/(s-4), (y-2)/(s-4)) for x, y in st]
                norm.append(n)
            self._capture_data[ch] = norm
            self._capture_idx += 1
            if self._capture_idx >= len(self._CAPTURE_CHARS):
                self._save_capture_data()
                dlg.destroy()
                return
            canvas.delete("draw")
            canvas.delete("ref")
            data["stroke"] = []
            data["strokes"] = []
            ch = self._CAPTURE_CHARS[self._capture_idx]
            title_lbl.config(text=f"「{ch}」  ({self._capture_idx+1}/{len(self._CAPTURE_CHARS)})")
            # 画参考字
            if _HERSHEY_AVAILABLE:
                ref = hr.get_strokes(ch)
                if ref:
                    margin = 40; sc = self._CAPTURE_SIZE - 2*margin
                    for st in ref:
                        coords = []
                        for x_n, y_n in st:
                            coords.extend([margin + x_n*sc, margin + y_n*sc])
                        canvas.create_line(*coords, fill="#ddd", width=3, dash=(4,4), tags="ref")

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        ttk.Button(btn_frame, text="↩ 重写", command=clear_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="◀ 上一个", command=skip_back).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="下一个 ▶", command=next_char).pack(side=tk.RIGHT, padx=2)

    def _save_capture_data(self):
        import json
        base = os.path.dirname(sys.argv[0]) if getattr(sys, "frozen", False) else self.__path_of_host
        path = os.path.join(base, "capture_data.json")
        with open(path, "w", encoding="utf-8") as f:
            jd = {}
            for ch, strokes in self._capture_data.items():
                jd[ch] = [[list(pt) for pt in st] for st in strokes]
            json.dump(jd, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("笔迹采集", f"采集完成！已保存到:\n{path}")
    def _simplify_points(self, pts, min_dist_mm=0.3):
        """Douglas-Peucker-like simplification: remove close points."""
        if len(pts) <= 2:
            return pts
        result = [pts[0]]
        for p in pts[1:]:
            dx = p[0] - result[-1][0]
            dy = p[1] - result[-1][1]
            if math.sqrt(dx*dx + dy*dy) >= min_dist_mm:
                result.append(p)
        if result[-1] != pts[-1]:
            result.append(pts[-1])
        return result

    def parse_to_binary(self):
        """将笔画直接解析为二进制包, 显示十六进制转储"""
        try:
            if not self.strokes:
                messagebox.showinfo("解析提示", "没有笔画可解析，请先在画布上绘图。")
                return

            working_strokes = self.strokes

            packets = []
            move_count = 0
            pen_down_count = 0
            pen_up_count = 0


            for stroke in working_strokes:
                pts_raw = stroke["points_mm"]
                pts = self._simplify_points(pts_raw, 0.3)
                if len(pts) < 2:
                    continue

                stroke_speed = stroke.get("speed", None)

                # 抬笔快速移动到起始点（绝对坐标）
                rapid_spd = SPEED_F3000
                x0_st = int(round(pts[0][0] * MM_TO_STEPS))
                y0_st = int(round(pts[0][1] * MM_TO_STEPS))
                packets.append(self._make_packet(PKT_MOVE_TO, x0_st, y0_st, rapid_spd))
                move_count += 1

                # 落笔
                packets.append(self._make_packet(PKT_PEN_DOWN, 0, 0, 0))
                pen_down_count += 1

                # 画线段
                prev = pts[0]
                for p in pts[1:]:
                    x_st = int(round(p[0] * MM_TO_STEPS))
                    y_st = int(round(p[1] * MM_TO_STEPS))
                    if stroke_speed is not None:
                        spd = stroke_speed
                    else:
                        dx = abs(p[0] - prev[0])
                        dy = abs(p[1] - prev[1])
                        dist = math.sqrt(dx*dx + dy*dy)
                        is_ortho = (dx < 0.1 or dy < 0.1)
                        if is_ortho:
                            spd = SPEED_F500
                        else:
                            if dist > 50:
                                spd = SPEED_F1200
                            elif dist > 10:
                                spd = SPEED_F800
                            else:
                                spd = SPEED_F500
                    packets.append(self._make_packet(PKT_MOVE_TO, x_st, y_st, spd))
                    move_count += 1
                    prev = p

                # 抬笔
                packets.append(self._make_packet(PKT_PEN_UP, 0, 0, 0))
                pen_up_count += 1


            self.binary_packets = packets

            # ── Render hex dump ──
            cmd_names = {
                PKT_MOVE_TO:  "MOVE_TO",
                PKT_PEN_UP:   "PEN_UP ",
                PKT_PEN_DOWN: "PEN_DOWN",
                PKT_SYNC:     "SYNC   ",
                PKT_ESTOP:    "ESTOP  ",
            }
            speed_names = ["F500", "F800", "F1200", "F3000"]

            lines = []
            lines.append(f"; 笔画数: {len(self.strokes)}  |  包总数: {len(packets)}")
            lines.append(f"; MOVE_TO: {move_count}  PEN_DOWN: {pen_down_count}  PEN_UP: {pen_up_count}")
            lines.append(f"; 旋转: {self.rotation}°  |  单位: 80 steps/mm")
            lines.append("")

            for i, pkt in enumerate(packets):
                cmd = pkt[1]
                x_s = int.from_bytes(pkt[2:4], 'big', signed=True)
                y_s = int.from_bytes(pkt[4:6], 'big', signed=True)
                spd = pkt[6]
                hex_str = ' '.join(f'{b:02X}' for b in pkt)

                name = cmd_names.get(cmd, f"0x{cmd:02X}")
                if cmd == PKT_MOVE_TO:
                    spd_name = speed_names[spd] if spd < 4 else "?"
                    anno = f"  X={x_s}  Y={y_s}  {spd_name}"
                elif cmd == PKT_PEN_UP:
                    anno = ""
                elif cmd == PKT_PEN_DOWN:
                    anno = ""
                else:
                    anno = ""

                lines.append(f"[{i+1:03d}] {name}{anno}")
                lines.append(f"       {hex_str}")
                lines.append("")

            total_bytes = len(packets) * 8
            lines.append(f"; 总字节数: {total_bytes}  (含 {len(packets)} 个包 × 8 字节)")

            text = '\n'.join(lines)
            self.gcode_text.config(state=tk.NORMAL)
            self.gcode_text.delete("1.0", tk.END)
            self.gcode_text.insert("1.0", text)
            self.gcode_text.config(state=tk.DISABLED)

            n_strokes = len([s for s in self.strokes if len(s["points_mm"]) >= 2])
            self.parse_btn.config(text=f"⚙ 已解析({n_strokes} 笔 {len(packets)} 包)")
            self.send_btn.config(state=tk.NORMAL)
            self.root.after(3000, lambda: self.parse_btn.config(
                text=f"⚙ 解析为二进制"))

        except Exception as e:
            import traceback
            err = traceback.format_exc()
            messagebox.showerror("解析错误", f"{e}\n\n{err}")

    def copy_gcode(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.gcode_text.get("1.0", tk.END))
        self._flash_status("📋 已复制")

    def clear_gcode_preview(self):
        self.binary_packets = None
        self.gcode_text.config(state=tk.NORMAL)
        self.gcode_text.delete("1.0", tk.END)
        self.gcode_text.config(state=tk.DISABLED)
        self.send_btn.config(state=tk.DISABLED)

    # ── Send / Communication ─────────────────────────────────

    def send_gcode(self):
        """直接发送已解析的二进制数据"""
        if not self.binary_packets:
            messagebox.showinfo("发送提示", "没有二进制指令，请先点击'解析为二进制'。")
            return
        if not self.ser or not self.ser.is_open:
            messagebox.showinfo("发送提示", "未连接到串口，请先连接。")
            return

        threading.Thread(target=self._send_packets, args=(self.binary_packets,), daemon=True).start()

    def cancel_send(self):
        self._sending = False
        if self.ser and self.ser.is_open:
            try:
                for _ in range(5):
                    self.ser.write(b'!')
                    time.sleep(0.01)
            except Exception:
                pass

    def _async_echo(self, msg):
        self.root.after(0, self._echo, msg)

    def _make_packet(self, cmd, x_steps, y_steps, speed):
        """Build an 8-byte binary protocol packet."""
        raw = struct.pack('>BBhhB', PKT_SOF, cmd, x_steps, y_steps, speed)
        cs = 0
        for b in raw:
            cs ^= b
        return raw + bytes([cs])

    def _send_packets(self, packets):
        """批量发送二进制数据 — BATCH_SIZE 个包插入 SYNC 等待 ACK"""
        self._sending = True
        self.cancel_btn.config(state=tk.NORMAL)
        self.send_btn.config(text="发送中...", state=tk.DISABLED)

        self._async_echo(f"--- 开始发送 — {len(packets)} 个包 (批次大小 {BATCH_SIZE}) ---")

        sent_ok = False
        sent_count = 0
        with self.serial_lock:
            try:
                pos = 0
                while pos < len(packets):
                    if not self._sending:
                        self._async_echo("--- 发送已取消 ---")
                        break
                    if not self.ser or not self.ser.is_open:
                        self._async_echo("--- 串口已断开 ---")
                        break

                    end = min(pos + BATCH_SIZE, len(packets))
                    batch = packets[pos:end]

                    # 清空串口输入缓存，丢弃残留数据
                    self.ser.reset_input_buffer()

                    for pkt in batch:
                        self.ser.write(pkt)
                    pos = end
                    sent_count = pos

                    # SYNC checkpoint
                    self.ser.write(self._make_packet(PKT_SYNC, 0, 0, 0))

                    resp = ""
                    retries = 0
                    while self._sending and retries < 600:   # 60s timeout
                        if not self.ser or not self.ser.is_open:
                            break
                        r = self.ser.readline()
                        if r:
                            resp = r.decode('utf-8', errors='replace').strip()
                            break
                        retries += 1
                        time.sleep(0.1)

                    if resp == "ok":
                        self._async_echo(f"  ✅ 批次完成 ({sent_count}/{len(packets)})")
                    else:
                        self._async_echo(f"<<< 超时 — 第{sent_count}/{len(packets)} 个包之后卡住")
                        self._sending = False
                        break
                else:
                    sent_ok = True
            except Exception as e:
                self._async_echo(f"<<< 错误: {e}")

        if sent_ok:
            self._async_echo("✅ 所有包已发送完成")
        self.root.after(0, self._send_done, sent_count, len(packets))

    def _send_done(self, sent, total):
        self.send_btn.config(text="全部发送", state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        if sent >= total and self._sending:
            self._flash_status(f"✅ 已全部发送 ({sent}/{total} 包)")
        elif sent > 0:
            self._flash_status(f"⚠️  部分发送 ({sent}/{total} 包)")
        else:
            self._flash_status(f"⚠️  发送失败 ({sent}/{total} 包)")

    def _flash_status(self, msg, duration_ms=3000):
        old = self.status_lbl.cget("text")
        old_fg = self.status_lbl.cget("foreground")
        self.status_lbl.config(text=msg, foreground="#2980b9")
        self.root.after(duration_ms,
                        lambda: self.status_lbl.config(
                    text=old, foreground=old_fg))

    # ── Cleanup ───────────────────────────────────────────────

    def on_close(self):
        self._sending = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ════════════════════════════════════════════════════════════════
#  Entry
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = PenPlotterHost()
    app.run()
