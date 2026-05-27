#!/usr/bin/env python3
"""text_layout.py — 文字排版引擎（A4纸，210×297mm）"""

import hershey_reader as hr
import random
import math

# ── A4 纸张参数 ──
A4_W = 210.0   # mm
A4_H = 297.0   # mm


class TextLayout:
    """文字排版引擎"""

    def __init__(self, font_size_mm=7, char_spacing=0.8, line_spacing=0.9,
                 align="left", margin_x=10, margin_y=10,
                 handwriting_level=2, layout_level=2, spacing_randomness_level=2):
        """
        参数:
            font_size_mm: 字号 (mm)
            char_spacing: 字间距倍数
            line_spacing: 行距倍数
            align: "left" / "center" / "right"
            margin_x: 左右边距 (mm)
            margin_y: 上下边距 (mm)
            handwriting_level: 手写随机强度 0~4（字旋转+平移）
            layout_level: 排版强度 0~4（基线漂移）
            spacing_randomness_level: 间距随机 0~4（字距/行距/行首波动）
        """
        self.font_size_mm = font_size_mm
        self.char_spacing = char_spacing
        self.line_spacing = line_spacing
        self.align = align
        self.margin_x = margin_x
        self.margin_y = margin_y
        self.handwriting_level = max(0, min(4, int(handwriting_level)))
        # 排版随机（layout_level → 基线漂移）
        ll = max(0, min(4, int(layout_level)))
        max_lvl = 4
        self._baseline_amp = 1.2 * ll / max_lvl
        # 间距随机（spacing_randomness_level → 字距/行距/行首）
        sl = max(0, min(4, int(spacing_randomness_level)))
        self._char_spacing_noise = 0.4 * sl / max_lvl
        self._line_spacing_noise = 1.0 * sl / max_lvl
        self._line_indent_noise = 1.5 * sl / max_lvl

    @property
    def _line_step(self):
        """每行占的高度 (mm)"""
        return self.font_size_mm * self.line_spacing

    @staticmethod
    def _char_type(char):
        """字符分类: cjk / cjk_punct / ascii / ascii_punct / digit / space"""
        c = ord(char)
        if c == 0x20:
            return "space"
        if 0x4E00 <= c <= 0x9FFF or 0x3400 <= c <= 0x4DBF:
            return "cjk"
        if 0x3000 <= c <= 0x303F:  # CJK 符号（。，“”等）
            return "cjk_punct"
        if 0xFF00 <= c <= 0xFFEF:  # 全角 ASCII 兼容（含全角标点）
            # 全角标点类
            if c in (0xFF01,0xFF0C,0xFF0E,0xFF1A,0xFF1B,0xFF1F,0xFF08,0xFF09,0xFF3B,0xFF3D,0xFF5B,0xFF5D,0xFF0F,0xFF3F,0xFF5C):
                return "cjk_punct"
            return "cjk"
        if 0x30 <= c <= 0x39:  # 0-9
            return "digit"
        if 0x41 <= c <= 0x5A or 0x61 <= c <= 0x7A:  # A-Z a-z
            return "ascii"
        # ASCII 标点
        if c in (0x21, 0x22, 0x27, 0x28, 0x29, 0x2C, 0x2D, 0x2E, 0x3A,
                 0x3B, 0x3F, 0x2F, 0x5B, 0x5D, 0x60, 0x7B, 0x7D, 0x7C):
            return "ascii_punct"
        if c in (0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x2014):  # 弯引号
            return "cjk_punct"
        return "cjk"  # fallback

    def _char_width(self, char):
        """脚本感知宽度：中文全角，英文比例，标点半宽"""
        base = self.font_size_mm
        ct = self._char_type(char)
        if ct == "cjk":
            return base * self.char_spacing
        elif ct == "cjk_punct":
            return base * 0.33  # 标点占1/3字宽
        elif ct == "digit":
            return base * 0.33  # 数字占1/3字宽
        elif ct == "ascii":
            # 窄字母如 i l I 1 t f j r 更窄
            thin = "ilIJ1tfjr|"
            if char in thin:
                return base * 0.22
            wide = "mwWM"  # 宽字母
            if char in wide:
                return base * 0.55
            return base * 0.40  # 普通字母比例宽度
        elif ct == "ascii_punct":
            return base * 0.3
        elif ct == "space":
            return base * 0.35
        return base * self.char_spacing

    def _line_width(self, chars):
        """计算一行字符的总宽度"""
        return sum(self._char_width(c) for c in chars)

    def _max_chars_for_line(self, chars):
        """从字符列表头部截取能放入一行的字符（按实际宽度计算）"""
        usable_w = A4_W - 2 * self.margin_x
        w = 0
        for i, c in enumerate(chars):
            w += self._char_width(c)
            if w > usable_w:
                return chars[:i]
        return chars

    def _parse_lines(self, text):
        """解析文本，每行支持独立对齐前缀: [C]居中 [R]右对齐 [L]左对齐
        
        返回: [(chars_list, align), ...]
        """
        raw_lines = text.split('\n')
        result = []
        for line in raw_lines:
            align = self.align
            content = line
            if line.startswith('[C]') or line.startswith('[c]'):
                align = 'center'
                content = line[3:]
            elif line.startswith('[R]') or line.startswith('[r]'):
                align = 'right'
                content = line[3:]
            elif line.startswith('[L]') or line.startswith('[l]'):
                align = 'left'
                content = line[3:]
            if not content:
                result.append(([], align))
                continue
            # 按实际字符宽度自动换行
            chars = list(content)
            while chars:
                wrapped = self._max_chars_for_line(chars)
                if not wrapped:
                    wrapped = chars[:1]
                result.append((wrapped, align))
                chars = chars[len(wrapped):]
        return result

    def _get_line_start_x(self, n_chars, align, chars=None):
        """计算某行的起始 X 坐标（支持混合宽度）"""
        if chars:
            line_w = self._line_width(chars)
        else:
            line_w = n_chars * self.font_size_mm * self.char_spacing
        usable_w = A4_W - 2 * self.margin_x
        if align == "center":
            return self.margin_x + (usable_w - line_w) / 2
        elif align == "right":
            return self.margin_x + usable_w - line_w
        else:
            return self.margin_x

    def layout(self, text):
        """排版文字，返回每笔的毫米坐标（含3层排版随机）
        
        返回: list[dict]
            [{
                "points_mm": [(x, y), ...],
                "color": "#2c3e50"
            }, ...]
        """
        lines = self._parse_lines(text)
        strokes_data = []
        y0 = A4_H - self.margin_y - self.font_size_mm

        # 每行独立基线漂移相位
        line_phase = random.uniform(0, 2 * math.pi)

        for line_chars, line_align in lines:
            if not line_chars:
                y0 -= self._line_step
                continue

            # 行基线漂移
            line_drift = random.uniform(-self._baseline_amp, self._baseline_amp)

            chars_list = list(line_chars)
            n = len(chars_list)
            # 计算这一行各字宽度（预先算好方便间距扰动）
            char_widths = [self._char_width(c) for c in chars_list]

            # 字间距抖动
            if self._char_spacing_noise > 0:
                jittered_widths = []
                for w in char_widths:
                    jit = w + random.uniform(-self._char_spacing_noise, self._char_spacing_noise)
                    jittered_widths.append(max(jit, 1))
            else:
                jittered_widths = list(char_widths)

            line_w = sum(jittered_widths)
            usable_w = A4_W - 2 * self.margin_x

            if line_align == "center":
                start_x = self.margin_x + (usable_w - line_w) / 2
            elif line_align == "right":
                start_x = self.margin_x + usable_w - line_w
            else:
                start_x = self.margin_x + random.uniform(-self._line_indent_noise, self._line_indent_noise)

            cur_x = start_x
            for idx, char in enumerate(chars_list):
                cw = jittered_widths[idx]
                x = cur_x

                # 基线漂移：根据x位置叠加正弦
                if self._baseline_amp > 0:
                    bx = x - self.margin_x
                    span = max(usable_w, 1)
                    t = bx / span
                    baseline_offset = (math.sin(t * 4 * math.pi + line_phase) * 
                                       self._baseline_amp)
                else:
                    baseline_offset = 0

                y = y0 + baseline_offset + line_drift

                strokes = hr.get_strokes(char)
                if strokes is None:
                    cur_x += cw
                    continue

                # 英文/数字比中文略小，标点更小
                ct = self._char_type(char)
                if ct == "ascii":
                    font_size = self.font_size_mm * 0.80
                    scale_x = 0.7
                elif ct == "digit":
                    font_size = self.font_size_mm * 0.8
                    scale_x = 1.0
                elif ct in ("ascii_punct", "cjk_punct"):
                    font_size = self.font_size_mm
                    scale_x = 1.0
                else:
                    font_size = self.font_size_mm
                    scale_x = 1.0

                if scale_x != 1.0:
                    shift = (1.0 - scale_x) / 2
                    strokes_sx = [[(x * scale_x + shift, y) for x, y in s] for s in strokes]
                else:
                    strokes_sx = strokes
                mm_strokes = hr.strokes_to_mm(strokes_sx, x, y, font_size)

                nat_strokes, speeds = hr.naturalize(mm_strokes, self.handwriting_level)

                for i, stroke in enumerate(nat_strokes):
                    speed = speeds[i] if i < len(speeds) else 0
                    strokes_data.append({
                        "points_mm": stroke,
                        "color": "#2c3e50",
                        "speed": speed
                    })

                cur_x += cw

            y0 -= self._line_step
            if y0 < self.margin_y:
                break

        return strokes_data


# ── 快捷测试 ──
if __name__ == "__main__":
    layout = TextLayout(font_size_mm=7, align="left")
    text = "你好世界这是一段测试文字"
    result = layout.layout(text)
    print(f"共 {len(result)} 笔笔画")
    # 显示前几笔
    for i, s in enumerate(result[:5]):
        pts = s["points_mm"]
        print(f"  第{i+1}笔: {len(pts)}点, 首{pts[0]}, 末{pts[-1]}")
