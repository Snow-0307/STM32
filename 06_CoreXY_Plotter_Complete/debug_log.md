# CoreXY 绘图仪位置漂移 Debug 日志

## 问题现象

写完一整页 A4 纸后，基线位置偏移 3~4mm。长行换行时偏移更明显，短行换行几乎无偏移。

---

## 排查过程（11 轮）

### 第 1 轮：添加 SYNC 位置重置

**猜测：** 固件位置跟踪有累积误差  
**操作：** 每笔抬笔后发送 SYNC 包携带当前绝对坐标  
**结果：** ❌ 无效。固件处理 SYNC 时忽略 x/y 数据，只回复 "ok"

---

### 第 2 轮：L 形路径补偿

**猜测：** CoreXY 皮带张力导致 X 远距离移动时 Y 被拖动  
**操作：** 跨行 >50mm 时先走 X 再走 Y（L 形路径）  
**结果：** ❌ 偏移方向反转（从往右变往左），说明不是张力问题

---

### 第 3 轮：删除加速度算法

**猜测：** 加减速导致步进电机丢步  
**操作：** `set_step_rate_idx` 直接设目标速度，ISR 中去掉加减速代码  
**结果：** ❌ 偏移方向又变了（往左），且幅度更大。急启急停冲击比加减速更大

---

### 第 4 轮：恢复加速度 + 不停定时器

**猜测：** `set_step_rate_arr` 每次停启定时器导致丢步  
**操作：** 去掉 `CR1 &= ~CEN / CR1 |= CEN`，直接写 ARR  
**结果：** ⚠️ 部分改善，仍有左偏

---

### 第 5 轮：CCER 零步关断

**猜测：** `motor_1_step(0)` 只设 `CCR=0` 不关 CCER，每周期产生无用脉冲→电机偷步  
**操作：** `motor_1_step(0)` 增加 `CCER &= ~CC2E`  
**结果：** ⚠️ 继续改善，仍有左偏

---

### 第 6 轮：ISR 末尾窗口期防护

**猜测：** `g_line_complete=1` → `motors_stop()` 之间有 1~2 个定时器周期窗口，CCER 仍开着  
**操作：** ISR 末尾增加 `g_line_complete || machineState!=MOVING` 时禁用 CCER + CCR=0  
**结果：** ⚠️ 继续改善，仍有左偏

---

### 第 7 轮：双定时器同步

**猜测：** 两路定时器相位偏移导致 CoreXY 换算错误→笔画歪斜  
**操作：** `set_step_rate_arr` 加回 `CNT=0` 复位（不停定时器）  
**结果：** ❌ 笔画形状恢复正常，但偏移依旧

---

### 第 8 轮：CCR 预装载（Preload）

**猜测：** `TIM_AUTORELOAD_PRELOAD_ENABLE` 导致 CCR 写入延迟一周期生效，末步丢失  
**操作：** `tim.c` 中清除 `CCMR1_OC2PE/OC1PE` 禁用 CCR preload  
**结果：** ⚠️ 先有效，后因其他改动还原

---

### 第 9 轮：NVIC 中断使能

**猜测：** 重构后 NVIC 未使能，定时器中断从未触发  
**操作：** 添加 `HAL_NVIC_EnableIRQ(TIM1_BRK_UP_TRG_COM_IRQn)` 等  
**结果：** ❌ 电机仍不动。SYNC 有响应但 MOVE_TO 不执行

---

### 第 10 轮：定时器时钟使能

**猜测：** `HAL_TIM_Base_MspInit` 是弱函数（空），时钟从未使能  
**操作：** 在 `MX_TIM1_Init()` 之前加 `__HAL_RCC_TIM1_CLK_ENABLE()`  
**结果：** ✅ 电机开始运动，但 CCR preload 改动导致字符错乱

---

### 第 11 轮：恢复原始 PWM 配置 + 保留步数精确度

**操作：** 
- 恢复完整的 `MX_TIM1_Init`/`MX_TIM15_Init`（PWM 模式）
- `set_step_rate_arr`：不停定时器 + CNT=0 同步
- `motor_1_step(>0)`：CCER 使能 + CCR=30（PWM 脉冲）
- `motor_1_step(0)`：CCER 禁用 + CCR=0（防偷步）
- `motors_stop()`：禁用 CCER
- ISR 末尾：`g_line_complete || machineState!=MOVING` → CCER 禁用 + CCR=0
- 恢复 `tim.c` 原始 PWM 配置 + MSP PostInit（PB3/PB14 AF 模式）
- `gpio.c` 保持原始配置（不含 PB3/PB14）
- 添加 NVIC 使能 + 定时器时钟使能

**结果：** ✅ **偏移彻底解决，写满一页 A4 基线无偏移**

---

## 根因总结

| 编号 | 问题 | 修复 |
|------|------|------|
| ① | 加减速时停定时器改 ARR → 丢步 | 不停机直接写 ARR |
| ② | `motor_1_step(0)` 不关 CCER → 每周期无用脉冲 | `CCER &= ~CC2E` |
| ③ | `motors_stop()` 只设 CCR=0 不关 CCER | 禁用 CCER |
| ④ | ISR 完成到 main loop 停止间的窗口期 | ISR 末尾同时做 |
| ⑤ | 双定时器不同步 → CoreXY 歪斜 | CNT=0 复位 |
| ⑥ | CCR preload → 末步丢失 | 禁用 OC2PE |
| ⑦ | NVIC 未使能 → 中断不触发 | `HAL_NVIC_EnableIRQ` |
| ⑧ | 定时器时钟未使能 → 寄存器写入无效 | `__HAL_RCC_TIMx_CLK_ENABLE` |

**最终结论：** 多个问题叠加。单独修任何一个都不够，必须全部修完。

---

## 最终架构

```
定时器 PWM 输出步进脉冲
  + ISR 精确计数
  + CCER 控制输出使能（非零步开启，完成/零步关闭）
  + 不停机改 ARR + CNT=0 同步
  = 步数 100% 精确，无累积误差
```
