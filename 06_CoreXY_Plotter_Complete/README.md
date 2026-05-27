# CoreXY 写字机器人

基于 CoreXY 结构的钢笔绘图仪/写字机器人。上位机用 Python + tkinter 开发，下位机用 STM32G070 驱动步进电机，字体使用 makemeahanzi 开源中文单线笔画数据。

## 项目结构

| 模块 | 技术栈 | 说明 |
|------|--------|------|
| 上位机 | Python tkinter, PIL, PySerial | GUI画布、文字排版、手写随机化、模板导入 |
| 固件 | STM32G070, HAL库, Keil MDK | Bresenham插补、梯形加减速、8字节协议、指令队列 |
| 字体 | makemeahanzi + Hershey | 中文9574字单线笔画 + 英文6种风格 |
| 机械 | CoreXY | 两个步进电机XY协同 + 一个抬落笔电机 |

## 功能特性

- 自定义8字节二进制UART通信协议（SOF + CMD + X + Y + SPEED + CHECKSUM）
- Bresenham直线插补 + CoreXY运动学换算
- 梯形加减速（10%加速 + 80%巡航 + 10%减速）
- 256深度环形指令队列
- 手写随机化：字级旋转平移、基线正弦漂移、间距抖动
- 中英文混排、标点半宽处理
- 模板图片导入（PIL/Pillow）
- PyInstaller打包独立EXE

## 硬件

- 主控：NUCLEO-G070RB
- 驱动：A4988 / DRV8825
- 电机：三个步进电机
- 结构：CoreXY（参考大鱼DIY写字机v2.2）

## 关键问题与解决

本项目最大难点是CoreXY位置漂移，写完一页A4纸后整体偏移数毫米。
经过11轮排查，最终定位到定时器PWM输出使能（CCER）未正确关断，
导致加减速时额外产生脉冲。详细排查记录见 `debug_log.md`。

## 参考项目

- [makemeahanzi](https://github.com/makemeahanzi/graphics.txt) - 中文单线笔画数据
- [HersheyText](https://github.com/techninja/HersheyText) - 英文单线字体
- [chinese-hershey-font](https://github.com/LingDong-/chinese-hershey-font) - 中文Hershey字体

## 效果演示

[B站视频](https://www.bilibili.com/video/BV1hdG161EFK)