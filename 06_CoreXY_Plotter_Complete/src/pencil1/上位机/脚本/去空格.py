#!/usr/bin/env python3
"""去空格.py — 删除当前目录下所有 .txt 文件中的空格（半角/全角/制表符）"""

import os
import glob

script_dir = os.path.dirname(os.path.abspath(__file__))

txt_files = glob.glob(os.path.join(script_dir, "*.txt"))

if not txt_files:
    print("当前目录没有 .txt 文件")
    input("按 Enter 退出...")
    exit()

total_removed = 0
for path in txt_files:
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    old_len = len(text)
    for ch in (' ', '\u3000', '\t', '\u00a0'):
        text = text.replace(ch, '')
    removed = old_len - len(text)
    total_removed += removed
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    name = os.path.basename(path)
    print(f"  {name}: 删了 {removed} 个空格" if removed else f"  {name}: 无空格")

print(f"\n共处理 {len(txt_files)} 个文件，删除 {total_removed} 个空格")
input("按 Enter 退出...")
