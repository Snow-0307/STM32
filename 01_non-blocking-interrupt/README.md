# STM32 非阻塞前后台系统

## 功能
- 按键（PC13下降沿中断）触发LED闪烁5次（50ms翻转周期）
- 串口（USART2中断接收）收到任意字符触发LED闪烁3次（500ms翻转周期）
- **两个任务可并行执行，互不阻塞**：串口闪灯期间按键可打断并优先执行

## 解决什么问题
传统 `HAL_Delay` 阻塞延时下，一个任务执行时另一个任务完全无响应（如串口慢闪3秒期间按键失效）。
本方案用 **时间戳 + 状态机** 替代阻塞延时，任务只在时间到达时执行一个“动作步”，其余时间CPU继续轮询其他任务，实现多任务并发。

## 涉及知识
- GPIO 外部中断（EXTI4_15，下降沿触发，内部上拉）
- UART 中断接收/发送（USART2，115200bps）
- 非阻塞编程（`HAL_GetTick` 时间戳 + 状态机状态切换）
- 前后台系统架构（中断设标志位，主循环轮询执行）

## 硬件
NUCLEO-G070RB （板载LED LD4 接 PA5，用户按键B1 接 PC13，ST-Link虚拟串口 USART2）

## 效果演示
[![视频](https://img.shields.io/badge/B站-视频演示-00a1d6)](https://www.bilibili.com/video/BV1trRNBwEM2/)

## 快速开始
用 Keil v5 打开项目目录"src\Target_1\STM32CubeMX\MDK-ARM\"的 `STM32CubeMX.uvprojx` 文件，编译后通过 ST-Link 烧录到 NUCLEO-G070RB。
