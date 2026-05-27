#!/usr/bin/env python3
"""ttf_to_strokes.py — TTF→单线笔画JSON，稳定版"""

from PIL import Image, ImageFont, ImageDraw
from skimage.morphology import skeletonize
from skimage.measure import label as sklabel, regionprops
import numpy as np, json, math, argparse, os


def walk_component(coords, min_px=3):
    if len(coords) < min_px: return []
    cs = set((int(y), int(x)) for y, x in coords)
    adj = {}
    for y, x in cs:
        nbs = [(y + dy, x + dx) for dy, dx in
               [(-1, 0), (1, 0), (0, -1), (0, 1),
                (-1, -1), (-1, 1), (1, -1), (1, 1)]
               if (y + dy, x + dx) in cs]
        adj[(y, x)] = nbs
    eps = [p for p, n in adj.items() if len(n) <= 1]
    start = eps[0] if eps else list(cs)[0]
    p = [start]; vis = {start}; cur = start
    while len(vis) < len(cs):
        nbs = [n for n in adj[cur] if n not in vis]
        if not nbs:
            best = None; bd = float('inf')
            for uv in cs - vis:
                d = abs(uv[0] - cur[0]) + abs(uv[1] - cur[1])
                if d < bd: bd = d; best = uv
            if best is None: break
            p.append(best); vis.add(best); cur = best; continue
        if len(p) >= 2:
            dpy = cur[0] - p[-2][0]; dpx = cur[1] - p[-2][1]
            best = min(nbs, key=lambda n: abs(n[0] - cur[0] - dpy) + abs(n[1] - cur[1] - dpx))
        else: best = nbs[0]
        p.append(best); vis.add(best); cur = best
    return [p] if len(p) >= min_px else []


def rdp_simplify(pts, eps=0.004):
    if len(pts) <= 2: return pts
    dx = pts[-1][0] - pts[0][0]; dy = pts[-1][1] - pts[0][1]
    L2 = max(dx * dx + dy * dy, 1e-6); dm = 0; ix = 0
    for i in range(1, len(pts) - 1):
        d2 = (dy * pts[i][0] - dx * pts[i][1] + pts[-1][0] * pts[0][1] - pts[-1][1] * pts[0][0]) ** 2
        if d2 > dm: dm = d2; ix = i
    if dm / L2 > eps * eps:
        left = rdp_simplify(pts[:ix + 1], eps)
        right = rdp_simplify(pts[ix:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def stroke_len(pts):
    return sum(math.sqrt((pts[i][0] - pts[i-1][0])**2 + (pts[i][1] - pts[i-1][1])**2) for i in range(1, len(pts)))


def convert_ttf(font_path, output_path=None, resolution=300, min_len=0.12,
                first_cjk=0x4E00, last_cjk=0x9FFF, char_list_path=None, verbose=True):
    from fontTools.ttLib import TTFont
    ft = TTFont(font_path, fontNumber=0)
    cmap = ft.getBestCmap()
    codes = sorted([c for c in cmap if first_cjk <= c <= last_cjk])
    if char_list_path:
        with open(char_list_path, 'r', encoding='utf-8') as f:
            valid = set(json.load(f))
        codes = [c for c in codes if chr(c) in valid]
    if verbose: print(f"转换 {len(codes)} 字符 @ {resolution}px")

    fpil = ImageFont.truetype(font_path, resolution)
    W = H = resolution; cnt = 0; res = {}
    for code in codes:
        ch = chr(code)
        try:
            im = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(im)
            bb = dr.textbbox((0, 0), ch, font=fpil)
            dr.text(((W - (bb[2] - bb[0])) // 2 - bb[0], (H - (bb[3] - bb[1])) // 2 - bb[1]), ch, 255, font=fpil)
            skel = skeletonize(np.array(im) > 128)
            labeled = sklabel(skel, connectivity=2)
            strokes = []
            for region in regionprops(labeled):
                pts = walk_component(region.coords)
                for st in pts:
                    pts2 = [(p[1] / W, p[0] / H) for p in st]
                    s = rdp_simplify(pts2)
                    if len(s) >= 2 and stroke_len(s) >= min_len:
                        strokes.append([(float(p[0]), float(p[1])) for p in s])
            if strokes: res[f"U+{code:04X}"] = strokes; cnt += 1
        except: pass
        if verbose and cnt % 1000 == 0: print(f"  {cnt}/{len(codes)}...")
    if verbose: print(f"完成: {cnt}字符")
    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f: json.dump(res, f, ensure_ascii=False)
    return res


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("font"); p.add_argument("output", nargs="?")
    p.add_argument("--resolution", type=int, default=300)
    p.add_argument("--min-length", type=float, default=0.12)
    p.add_argument("--char-list")
    a = p.parse_args()
    if not os.path.exists(a.font): print("错误: 文件不存在"); exit(1)
    o = a.output or f"STRK-{os.path.splitext(os.path.basename(a.font))[0]}.json"
    convert_ttf(a.font, o, a.resolution, a.min_length, char_list_path=a.char_list)
