#!/usr/bin/env python3
"""hershey_reader.py — 加载 chinese-hershey-font JSON 笔画数据"""

import json
import os
import math
import random

# ── 默认数据路径 ──
DATA_DIR = os.path.join(os.path.dirname(__file__), "hershey_data", "dist", "json")
DEFAULT_FONT = "STRK-Lemi.json"

# ── 可用字体列表 ──
FONT_OPTIONS = {
    "乐米栀夏浅风体": "STRK-Lemi.json",
    # 英文单线笔画字体
    "English Cursive":  "EN-cursive.json",
    "English Script":   "EN-scripts.json",
    "English Serif":    "EN-timesr.json",
    "English Italic":   "EN-timesi.json",
    "English Gothic":   "EN-gothiceng.json",
    "English Sans":     "EN-futural.json",
}
_current_font = DEFAULT_FONT

# ── ASCII 后备 ──
try:
    import ascii_strokes as _ascii
    HAS_ASCII = True
except ImportError:
    HAS_ASCII = False

# ── 自定义标点符号（嵌入乐米字体，替换原来的标点） ──
_PUNCT_DATA = None
_PUNCT_FILE = "STRK-Punct.json"
def _load_punct():
    global _PUNCT_DATA
    if _PUNCT_DATA is None:
        try:
            p = os.path.join(DATA_DIR, _PUNCT_FILE)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    _PUNCT_DATA = json.load(f)
        except:
            _PUNCT_DATA = {}
    return _PUNCT_DATA

# ── 全局缓存 ──
_cache = {}


def load_font(font_name=None):
    """加载字体 JSON 文件到缓存"""
    if font_name is None:
        font_name = DEFAULT_FONT
    if font_name in _cache:
        return _cache[font_name]

    path = os.path.join(DATA_DIR, font_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"字体文件未找到: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    _cache[font_name] = data
    return data


def unicode_key(char):
    """将字符转为 JSON 中的 key 格式"""
    return f"U+{ord(char):04X}"


# ── 英文标点 → 中文标点映射 ──
_PUNCT_MAP = {
    ',': '，',
    '!': '！',
    '?': '？',
    ';': '；',
    ':': '：',
    '(': '（',
    ')': '）',
    '<': '《',
    '>': '》',
    '[': '【',
    ']': '】',
    '~': '～',
}


def set_font(font_name):
    """切换当前字体"""
    global _current_font
    _current_font = font_name


def get_strokes(char, font_name=None):
    """获取单个字符的所有笔画
    
    返回: list[list[tuple[float,float]]]
    """
    fn = font_name or _current_font
    is_en_font = fn.startswith("EN-")

    # 英文标点 → 中文标点（仅中文字体时）
    if not is_en_font and char in _PUNCT_MAP:
        char = _PUNCT_MAP[char]

    # 非英文字体：先查自定义标点库（替换乐米字体中的标点/数字）
    if not is_en_font:
        pdata = _load_punct()
        if pdata:
            key = f"U+{ord(char):04X}"
            raw = pdata.get(key)
            if raw is not None:
                return [[(pt[0], pt[1]) for pt in stroke] for stroke in raw]

    if is_en_font:
        # 英文字体：先查英文字库，再到 ascii 后备
        data = load_font(fn)
        key = f"U+{ord(char):04X}" if ord(char) > 127 else char
        raw = data.get(key)
        if raw is not None:
            return [[(pt[0], pt[1]) for pt in stroke] for stroke in raw]
        if HAS_ASCII:
            ascii_result = _ascii.get_strokes(char)
            if ascii_result is not None:
                return ascii_result
    else:
        # 中文字体：先查 ascii 后备，再到中文字库
        # 英文标点 → 中文标点
        if char in _PUNCT_MAP:
            char = _PUNCT_MAP[char]
        if HAS_ASCII:
            ascii_result = _ascii.get_strokes(char)
            if ascii_result is not None:
                return ascii_result
        data = load_font(fn)
        key = unicode_key(char)
        raw = data.get(key)
        if raw is not None:
            return [[(pt[0], pt[1]) for pt in stroke] for stroke in raw]
    return None


def has_char(char, font_name=None):
    """检查字体中是否有该字符"""
    data = load_font(font_name)
    return unicode_key(char) in data


def strokes_to_mm(strokes, char_x_mm, char_y_mm, font_size_mm=10):
    """将归一化笔画坐标转换为毫米坐标
    
    参数:
        strokes: get_strokes() 返回的笔画数据
        char_x_mm, char_y_mm: 字符左上角在 A4 纸上的位置 (mm)
        font_size_mm: 字号 (mm)，默认为 10mm
    
    返回: list[list[tuple[float,float]]]
        每笔是 (x_mm, y_mm) 坐标列表
        坐标系: A4 左下角为原点，y 向上
    """
    result = []
    for stroke in strokes:
        mm_stroke = []
        for x_norm, y_norm in stroke:
            # 归一化坐标 → mm，注意 Y 轴反转
            x_mm = char_x_mm + x_norm * font_size_mm
            y_mm = char_y_mm + (1.0 - y_norm) * font_size_mm  # Y 反转
            mm_stroke.append((x_mm, y_mm))
        result.append(mm_stroke)
    return result


# ── V2 手写随机性 ──────────────────────────────

# 5级手写强度预设（字内干净，只有字级旋转+平移）
HANDWRITING_LEVELS = {
    0: {"label": "关闭",  "rot": 0,   "trans": 0},
    1: {"label": "轻微",  "rot": 0.3, "trans": 0.08},
    2: {"label": "自然",  "rot": 0.6, "trans": 0.15},
    3: {"label": "明显",  "rot": 1.0, "trans": 0.3},
    4: {"label": "狂草",  "rot": 1.8, "trans": 0.5},
}


def _smooth_noise_1d(t, num_ctrl=5, amp=1.0):
    """
    1D 平滑噪声：在 [0,1] 上生成 num_ctrl 个随机控制点，
    用三次 Hermite 插值产生连续曲线。
    返回 noise(t) 在 t 处的值，范围 ~[-amp, amp]。
    """
    ctrl = [random.uniform(-1, 1) for _ in range(num_ctrl)]
    t_clamped = max(0, min(1, t))
    pos = t_clamped * (num_ctrl - 1)
    i = int(pos)
    if i >= num_ctrl - 1:
        return ctrl[-1] * amp
    f = pos - i
    # Hermite 三次插值 (smoothstep)
    h00 = 2 * f ** 3 - 3 * f ** 2 + 1
    h10 = f ** 3 - 2 * f ** 2 + f
    h01 = -2 * f ** 3 + 3 * f ** 2
    h11 = f ** 3 - f ** 2
    # 用有限差分近似导数
    d_i = (ctrl[min(i + 1, num_ctrl - 1)] - ctrl[max(i - 1, 0)]) / 2
    d_ij = (ctrl[min(i + 2, num_ctrl - 1)] - ctrl[max(i, 0)]) / 2
    val = (h00 * ctrl[i] + h10 * d_i +
           h01 * ctrl[min(i + 1, num_ctrl - 1)] + h11 * d_ij)
    return val * amp


def _stroke_center(stroke):
    """计算笔画中点"""
    xs = [p[0] for p in stroke]
    ys = [p[1] for p in stroke]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _rotate_point(x, y, cx, cy, angle_deg):
    """绕 (cx,cy) 旋转角度（度）"""
    rad = math.radians(angle_deg)
    sin_a = math.sin(rad)
    cos_a = math.cos(rad)
    dx = x - cx
    dy = y - cy
    return (cx + dx * cos_a - dy * sin_a,
            cy + dx * sin_a + dy * cos_a)


def _stroke_rotate(stroke, angle_deg):
    """旋转整笔"""
    if abs(angle_deg) < 0.001:
        return stroke
    cx, cy = _stroke_center(stroke)
    return [_rotate_point(x, y, cx, cy, angle_deg) for x, y in stroke]


def _stroke_translate(stroke, dx, dy):
    """平移整笔"""
    if abs(dx) < 0.001 and abs(dy) < 0.001:
        return stroke
    return [(x + dx, y + dy) for x, y in stroke]


def _stroke_smooth_noise(stroke, amp):
    """沿笔画路径叠加平滑噪声（垂直方向偏移）"""
    if amp <= 0 or len(stroke) < 2:
        return stroke
    # 累计路径长度
    cum = [0.0]
    for i in range(1, len(stroke)):
        dx = stroke[i][0] - stroke[i - 1][0]
        dy = stroke[i][1] - stroke[i - 1][1]
        cum.append(cum[-1] + math.sqrt(dx * dx + dy * dy))
    total = cum[-1] if cum[-1] > 0 else 1
    result = []
    for i, (x, y) in enumerate(stroke):
        t = cum[i] / total
        noise = _smooth_noise_1d(t, num_ctrl=max(4, len(stroke)//3), amp=amp)
        # 垂直路径方向偏移
        if i > 0:
            dx = stroke[i][0] - stroke[i - 1][0]
            dy = stroke[i][1] - stroke[i - 1][1]
            l = math.sqrt(dx * dx + dy * dy)
            if l > 0.001:
                nx, ny = -dy / l, dx / l
                x += nx * noise
                y += ny * noise
        result.append((x, y))
    return result


def _stroke_end_jitter(stroke, amp, n_points=3):
    """笔画首尾微小偏折"""
    if amp <= 0 or len(stroke) < 4:
        return stroke
    result = list(stroke)
    n = min(n_points, len(stroke) // 2)
    for i in range(n):
        factor = 1.0 - i / n  # 越靠近端部越强
        jx = random.uniform(-amp, amp) * factor
        jy = random.uniform(-amp, amp) * factor
        x, y = result[i]
        result[i] = (x + jx, y + jy)
        # 尾部对称
        jx = random.uniform(-amp, amp) * factor
        jy = random.uniform(-amp, amp) * factor
        x, y = result[-1 - i]
        result[-1 - i] = (x + jx, y + jy)
    return result


def _baseline_drift(strokes, amp):
    """整行基线漂移：所有笔画叠加同一条平滑曲线"""
    if amp <= 0 or not strokes:
        return strokes
    # 收集所有点
    all_pts = [p for st in strokes for p in st]
    if not all_pts:
        return strokes
    xs = [p[0] for p in all_pts]
    min_x, max_x = min(xs), max(xs)
    span = max(max_x - min_x, 1)
    result = []
    for stroke in strokes:
        new_stroke = []
        for x, y in stroke:
            t = (x - min_x) / span
            drift = _smooth_noise_1d(t, num_ctrl=3, amp=amp)
            new_stroke.append((x, y + drift))
        result.append(new_stroke)
    return result


def naturalize(strokes, level=2):
    """
    字级手写随机化：仅旋转 + 平移，笔内干净，无噪声。
    
    参数:
        strokes: list[list[tuple[float,float]]] — 毫米坐标的笔画
        level: int — 0~4，对应 HANDWRITING_LEVELS
    
    返回: (strokes, speeds) 扰动后的笔画和速度分配
    """
    level = max(0, min(4, int(level)))
    cfg = HANDWRITING_LEVELS[level]

    result = []
    for stroke in strokes:
        s = stroke[:]
        angle = random.uniform(-cfg["rot"], cfg["rot"])
        s = _stroke_rotate(s, angle)
        dx = random.uniform(-cfg["trans"], cfg["trans"])
        dy = random.uniform(-cfg["trans"], cfg["trans"])
        s = _stroke_translate(s, dx, dy)
        result.append(s)

    # 速度分配
    speeds = []
    for stroke in result:
        length = sum(math.sqrt((stroke[i][0] - stroke[i - 1][0]) ** 2 +
                               (stroke[i][1] - stroke[i - 1][1]) ** 2)
                     for i in range(1, len(stroke)))
        if length < 5:
            base = 0
        elif length < 15:
            base = 1
        elif length < 30:
            base = 2
        else:
            base = 3
        if random.random() < 0.4:
            base = max(0, min(3, base + random.choice([-1, 1])))
        speeds.append(base)

    return result, speeds


# ── 快捷测试 ──
if __name__ == "__main__":
    # 测试：加载"永"字并打印坐标
    strokes = get_strokes("永")
    if strokes:
        print(f"永字笔画数: {len(strokes)}")
        mm = strokes_to_mm(strokes, 50, 50, 10)
        for i, s in enumerate(mm):
            print(f"  第{i+1}笔: {len(s)}个点, 首={s[0]}, 末={s[-1]}")
    else:
        print("未找到该字符")
