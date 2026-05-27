/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body — Binary step protocol + ISR Bresenham
  ******************************************************************************
  */
/* USER CODE END Header */
#include "main.h"
#include "dma.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* USER CODE BEGIN Includes */
#include "function.h"
#include <string.h>
/* USER CODE END Includes */

/* USER CODE BEGIN PD */
#define PKT_SOF         0xAA
#define PKT_MOVE_TO     0x01
#define PKT_PEN_UP      0x02
#define PKT_PEN_DOWN    0x03
#define PKT_SYNC        0x04
#define PKT_ESTOP       0x05

#define CMD_QUEUE_SIZE  256
#define SPD_F500   0
#define SPD_F800   1
#define SPD_F1200  2
#define SPD_F3000  3
/* USER CODE END PD */

/* USER CODE BEGIN PV */
X_Y g_xy;
volatile uint8_t pen_is_down = 0;
volatile int32_t g_steps_X0 = 0, g_steps_Y0 = 0;
volatile int32_t g_steps_X1 = 0, g_steps_Y1 = 0;

#define RX_RING_SIZE  512
static volatile uint8_t  rx_ring[RX_RING_SIZE];
static volatile uint16_t rx_ring_head = 0, rx_ring_tail = 0;
static uint8_t           rx_byte;

typedef struct {
    uint8_t  cmd;
    int32_t  x_steps, y_steps;
    uint8_t  speed_idx;
} BinCommand;
BinCommand          cmdQueue[CMD_QUEUE_SIZE];
volatile uint16_t   cmdHead=0, cmdTail=0, cmdCount=0;
volatile uint8_t    pendingCommand = 0, machineHalt = 0;

typedef enum { STATE_IDLE, STATE_MOVING, STATE_PEN_WAIT } MachineState;
volatile MachineState machineState = STATE_IDLE;
volatile uint8_t g_line_complete = 0, g_pending_sync = 0;

static const uint16_t speed_arr[] = {800, 400, 250, 110};
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static void system_reset(void);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */
static void serial_puts(const char *s) {
    while (*s) {
        while (!(USART2->ISR & USART_ISR_TXE_TXFNF));
        USART2->TDR = *s++;
    }
    while (!(USART2->ISR & USART_ISR_TC));
}

static uint16_t g_target_arr = 500;

static void set_step_rate_arr(uint16_t arr) {
    TIM1->ARR = arr;  TIM15->ARR = arr;
    TIM1->CNT = 0;    TIM15->CNT = 0;
}

static void set_step_rate_idx(uint8_t idx) {
    if (idx >= 4) idx = SPD_F800;
    g_target_arr = speed_arr[idx];
    uint16_t start_arr = speed_arr[idx] * 3;
    if (start_arr > 3000) start_arr = 3000;
    set_step_rate_arr(start_arr);
    TIM1->CR1 |= TIM_CR1_CEN;   TIM15->CR1 |= TIM_CR1_CEN;
    TIM1->DIER |= TIM_DIER_UIE; TIM15->DIER |= TIM_DIER_UIE;
}

static void motors_stop(void) {
    TIM1->CCER &= ~TIM_CCER_CC2E;  TIM15->CCER &= ~TIM_CCER_CC1E;
    TIM1->CCR2 = 0;                TIM15->CCR1 = 0;
}

static int enqueue_bin_cmd(uint8_t cmd, int32_t x, int32_t y, uint8_t spd) {
    if (cmdCount >= CMD_QUEUE_SIZE) return 0;
    cmdQueue[cmdHead].cmd = cmd;
    cmdQueue[cmdHead].x_steps = x;
    cmdQueue[cmdHead].y_steps = y;
    cmdQueue[cmdHead].speed_idx = spd;
    cmdHead = (cmdHead + 1) % CMD_QUEUE_SIZE;
    cmdCount++;
    return 1;
}

static void process_rx_byte_pkt(uint8_t c) {
    static uint8_t stage = 0, buf[8];
    if (stage == 0) {
        if (c == '?') {
            serial_puts(machineHalt ? "<Hold>\n" : (machineState == STATE_IDLE && cmdCount == 0) ? "<Idle>\n" : "<Run>\n");
            return;
        }
        if (c == '!') { machineHalt = 1; motors_stop(); return; }
        if (c == '~') { machineHalt = 0; return; }
        if (c == 0x18) { system_reset(); return; }
    }
    switch (stage) {
    case 0: if (c == PKT_SOF) { buf[0]=c; stage=1; } break;
    case 1: buf[1]=c; stage=2; break;
    case 2: case 3: case 4: case 5: buf[stage]=c; stage++; break;
    case 6: buf[6]=c; stage=7; break;
    case 7:
        buf[7]=c;
        {   uint8_t cs=0;
            for (int i=0;i<7;i++) cs ^= buf[i];
            if (cs==c) {
                uint8_t cmd = buf[1];
                int32_t x = (int32_t)(int16_t)((buf[2]<<8)|buf[3]);
                int32_t y = (int32_t)(int16_t)((buf[4]<<8)|buf[5]);
                uint8_t spd = buf[6];
                switch (cmd) {
                    case PKT_MOVE_TO: enqueue_bin_cmd(PKT_MOVE_TO,x,y,spd); break;
                    case PKT_PEN_UP:  enqueue_bin_cmd(PKT_PEN_UP,0,0,0); break;
                    case PKT_PEN_DOWN: enqueue_bin_cmd(PKT_PEN_DOWN,0,0,0); break;
                    case PKT_SYNC:    g_pending_sync=1; break;
                    case PKT_ESTOP:   machineHalt=1; motors_stop(); break;
                    default: break;
                }
            }
        }
        stage=0; break;
    default: stage=0; break;
    }
}

static void serial_poll_and_process(void) {
    while (rx_ring_tail != rx_ring_head) {
        uint8_t c = rx_ring[rx_ring_tail];
        rx_ring_tail = (rx_ring_tail + 1) % RX_RING_SIZE;
        process_rx_byte_pkt(c);
    }
}

static void system_reset(void) {
    motors_stop();
    cmdCount=0; cmdHead=0; cmdTail=0;
    machineState=STATE_IDLE; machineHalt=0;
    pendingCommand=0; g_line_complete=0; g_pending_sync=0;
    if (pen_is_down) {
        X_Y tmp; bresenham_init_steps(&tmp,0,0,0,0);
        pen_up(&tmp); pen_is_down=0;
    }
    g_steps_X1=g_steps_X0; g_steps_Y1=g_steps_Y0;
    HAL_GPIO_WritePin(GPIOA,GPIO_PIN_5,GPIO_PIN_RESET);
    serial_puts("[RESET]\n");
}
/* USER CODE END 0 */

int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_DMA_Init();
    /* 使能定时器时钟 */
    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_TIM15_CLK_ENABLE();
    __HAL_RCC_TIM3_CLK_ENABLE();

    MX_TIM1_Init();
    MX_USART2_UART_Init();
    MX_TIM15_Init();
    MX_TIM3_Init();

    /* USER CODE BEGIN 2 */

    __HAL_TIM_SET_AUTORELOAD(&htim1,300-1);
    __HAL_TIM_SET_AUTORELOAD(&htim15,300-1);
    __HAL_TIM_SET_AUTORELOAD(&htim3,300-1);
    __HAL_TIM_SET_COMPARE(&htim1,TIM_CHANNEL_2,0);
    __HAL_TIM_SET_COMPARE(&htim15,TIM_CHANNEL_1,0);
    __HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,0);

    HAL_NVIC_SetPriority(TIM1_BRK_UP_TRG_COM_IRQn,1,0); HAL_NVIC_EnableIRQ(TIM1_BRK_UP_TRG_COM_IRQn);
    HAL_NVIC_SetPriority(TIM15_IRQn,1,0);               HAL_NVIC_EnableIRQ(TIM15_IRQn);
    HAL_NVIC_SetPriority(TIM3_IRQn,1,0);                HAL_NVIC_EnableIRQ(TIM3_IRQn);

    HAL_TIM_PWM_Start(&htim1,TIM_CHANNEL_2);
    HAL_TIM_PWM_Start(&htim15,TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim3,TIM_CHANNEL_2);
    __HAL_TIM_ENABLE_IT(&htim1,TIM_IT_UPDATE);
    __HAL_TIM_ENABLE_IT(&htim15,TIM_IT_UPDATE);
    __HAL_TIM_ENABLE_IT(&htim3,TIM_IT_UPDATE);

    HAL_UART_Receive_IT(&huart2,&rx_byte,1);
    /* USER CODE END 2 */

    while (1) {
        serial_poll_and_process();
        if (machineHalt) { motors_stop(); continue; }
        switch (machineState) {
        case STATE_IDLE:
            if (cmdCount > 0) {
                uint16_t idx = cmdTail;
                cmdTail = (cmdTail+1)%CMD_QUEUE_SIZE; cmdCount--;
                switch (cmdQueue[idx].cmd) {
                case PKT_MOVE_TO:
                    g_steps_X1 = cmdQueue[idx].x_steps;
                    g_steps_Y1 = cmdQueue[idx].y_steps;
                    set_step_rate_idx(cmdQueue[idx].speed_idx);
                    bresenham_init_steps(&g_xy,g_steps_X0,g_steps_Y0,g_steps_X1,g_steps_Y1);
                    g_xy.interpStep=0; g_line_complete=0;
                    machineState = STATE_MOVING;
                    break;
                case PKT_PEN_DOWN: pendingCommand=PKT_PEN_DOWN; pen_down(&g_xy); machineState=STATE_PEN_WAIT; break;
                case PKT_PEN_UP:   pendingCommand=PKT_PEN_UP;   pen_up(&g_xy);   machineState=STATE_PEN_WAIT; break;
                }
            } else if (g_pending_sync) {
                g_pending_sync=0; serial_puts("ok\n");
            }
            break;
        case STATE_MOVING:
            if (g_line_complete) {
                g_line_complete=0;
                g_steps_X0=g_steps_X1; g_steps_Y0=g_steps_Y1;
                motors_stop();
                machineState=STATE_IDLE;
            }
            break;
        case STATE_PEN_WAIT:
            if (isMotionComplete(&g_xy)) {
                if (pendingCommand==PKT_PEN_DOWN) pen_is_down=1;
                if (pendingCommand==PKT_PEN_UP)   pen_is_down=0;
                pendingCommand=0; machineState=STATE_IDLE;
            }
            break;
        }
    }
}

void SystemClock_Config(void) {
    RCC_OscInitTypeDef RCC_OscInitStruct={0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct={0};
    HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);
    RCC_OscInitStruct.OscillatorType=RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState=RCC_HSI_ON;
    RCC_OscInitStruct.HSIDiv=RCC_HSI_DIV1;
    RCC_OscInitStruct.HSICalibrationValue=RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState=RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource=RCC_PLLSOURCE_HSI;
    RCC_OscInitStruct.PLL.PLLM=RCC_PLLM_DIV1;
    RCC_OscInitStruct.PLL.PLLN=8;
    RCC_OscInitStruct.PLL.PLLP=RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLR=RCC_PLLR_DIV2;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);
    RCC_ClkInitStruct.ClockType=RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_PCLK1;
    RCC_ClkInitStruct.SYSCLKSource=RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider=RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider=RCC_HCLK_DIV1;
    HAL_RCC_ClockConfig(&RCC_ClkInitStruct,FLASH_LATENCY_2);
}

/* USER CODE BEGIN 4 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance==USART2) {
        uint16_t next=(rx_ring_head+1)%RX_RING_SIZE;
        if (next!=rx_ring_tail) { rx_ring[rx_ring_head]=rx_byte; rx_ring_head=next; }
        HAL_UART_Receive_IT(&huart2,&rx_byte,1);
    }
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim) {
    /* ── 步进计数 ── */
    if (htim->Instance==TIM1 && g_xy.currentStep_X<g_xy.targetSteps_X) g_xy.currentStep_X++;
    if (htim->Instance==TIM15 && g_xy.currentStep_Y<g_xy.targetSteps_Y) g_xy.currentStep_Y++;
    if (htim->Instance==TIM3 && g_xy.currentStep_Z<g_xy.targetSteps_Z) g_xy.currentStep_Z++;

    /* ── Bresenham 自推进 ── */
    if (machineState==STATE_MOVING &&
        g_xy.currentStep_X>=g_xy.targetSteps_X &&
        g_xy.currentStep_Y>=g_xy.targetSteps_Y &&
        g_xy.currentStep_Z>=g_xy.targetSteps_Z) {
        if (g_xy.interpStep < g_xy.totalSteps) {
            if (g_xy.totalSteps>=10) {
                uint32_t p = (g_xy.interpStep*100)/g_xy.totalSteps;
                uint16_t na = g_target_arr;
                if (p<10)          { na += (10-p)*g_target_arr/10; }
                else if (p>90)     { na += (p-90)*g_target_arr/10; }
                if (na>3000) na=3000;
                set_step_rate_arr(na);
            }

            bresenham_step(&g_xy);
        } else {
            set_step_rate_arr(g_target_arr*2>3000?3000:g_target_arr*2);
            g_line_complete=1;
        }
    }

    /* ── 完成/非移动时关断输出 ── */
    if (g_line_complete || machineState!=STATE_MOVING) {
        if (htim->Instance==TIM1) { TIM1->CCER&=~TIM_CCER_CC2E; __HAL_TIM_SET_COMPARE(&htim1,TIM_CHANNEL_2,0); }
        if (htim->Instance==TIM15) { TIM15->CCER&=~TIM_CCER_CC1E; __HAL_TIM_SET_COMPARE(&htim15,TIM_CHANNEL_1,0); }
    }
    if (htim->Instance==TIM3 && g_xy.currentStep_Z>=g_xy.targetSteps_Z)
        __HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,0);
}

void HAL_GPIO_EXTI_Falling_Callback(uint16_t GPIO_Pin) {
    if (GPIO_Pin==GPIO_PIN_13) system_reset();
}
/* USER CODE END 4 */

void Error_Handler(void) { __disable_irq(); while(1){} }

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) { /* USER CODE BEGIN 6 */ /* USER CODE END 6 */ }
#endif
