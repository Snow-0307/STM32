/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "dma.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "function.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
X_Y g_xy;

typedef enum {
    STATE_IDLE,
    STATE_MOVING,
    STATE_DONE,
    STATE_PEN_UP_WAIT
} MachineState;

typedef enum {
    STATE_WAIT_START,
    STATE_WAIT_MODE,
    STATE_WAIT_X_H,
    STATE_WAIT_X_L,
    STATE_WAIT_Y_H,
    STATE_WAIT_Y_L,
    STATE_WAIT_END
} ParseState_t;

typedef struct {
    uint8_t mode;
    int16_t x;
    int16_t y;
} Command;

#define CMD_QUEUE_SIZE  16

Command  cmdQueue[CMD_QUEUE_SIZE];
volatile uint8_t cmdHead = 0;
volatile uint8_t cmdTail = 0;
volatile uint8_t cmdCount = 0;

volatile MachineState machineState = STATE_IDLE;
volatile ParseState_t rx_state = STATE_WAIT_START;
volatile uint8_t temporary_mode;
volatile int16_t temporary_X;
volatile int16_t temporary_Y;
volatile uint8_t pendingCommand = 0;
volatile int X0 = 0, Y0 = 0, X1 = 0, Y1 = 0;
uint8_t rx_byte;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
#define WAIT_MOTOR_COMPLETE(x_y) while(!isMotionComplete(x_y)) {}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_TIM1_Init();
  MX_USART2_UART_Init();
  MX_TIM15_Init();
  MX_TIM3_Init();
  /* USER CODE BEGIN 2 */
	__HAL_TIM_SET_AUTORELOAD(&htim1, 300-1);
	__HAL_TIM_SET_AUTORELOAD(&htim15, 300-1);
	__HAL_TIM_SET_AUTORELOAD(&htim3, 300-1);
	__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
	__HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 0);
	__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
	HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2);
	HAL_TIM_PWM_Start(&htim15, TIM_CHANNEL_1);
	HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2);
	__HAL_TIM_ENABLE_IT(&htim1, TIM_IT_UPDATE);
	__HAL_TIM_ENABLE_IT(&htim15, TIM_IT_UPDATE);
	__HAL_TIM_ENABLE_IT(&htim3, TIM_IT_UPDATE);
	
	HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
		switch (machineState)
		{
			case STATE_IDLE:
				if (cmdCount > 0)
				{
					uint8_t idx = cmdTail;
					cmdTail = (cmdTail + 1) % CMD_QUEUE_SIZE;
					cmdCount--;
					
					pendingCommand = cmdQueue[idx].mode;
					X1 = cmdQueue[idx].x;
					Y1 = cmdQueue[idx].y;
					
					HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);
					HAL_UART_Transmit_IT(&huart2, (uint8_t *)"Start\r\n", strlen("Start\r\n"));
					
					bresenham_init(&g_xy, X0, Y0, X1, Y1);
					
					if (pendingCommand == 1 || pendingCommand == 2)
					{
						machineState = STATE_MOVING;
					}else if (pendingCommand == 3)
					{
						pen_down(&g_xy);
						machineState = STATE_MOVING;
					}
				}
				break;
			case STATE_MOVING:
				WAIT_MOTOR_COMPLETE(&g_xy);
				if (g_xy.interpStep < g_xy.totalSteps)
				{
					bresenham_step(&g_xy);
					
				}else
				{
					if (pendingCommand == 1)
					{
						machineState = STATE_DONE;
					}else if (pendingCommand == 2)
					{
						pen_down(&g_xy);
						machineState = STATE_PEN_UP_WAIT;
					}else if (pendingCommand == 3)
					{
						pen_up(&g_xy);
						machineState = STATE_DONE;
					}
				}
				break;
			case STATE_PEN_UP_WAIT:
				WAIT_MOTOR_COMPLETE(&g_xy);
				if (pendingCommand == 2)
				{
					pen_up(&g_xy);
					machineState = STATE_DONE;
				}
				break;
			case STATE_DONE:
				WAIT_MOTOR_COMPLETE(&g_xy);
				pendingCommand = 0;
				X0 = X1; Y0 = Y1;
				
				if (cmdCount > 0)
				{
					machineState = STATE_IDLE;
				}
				else
				{
					X1 = 0; Y1 = 0;
					machineState = STATE_IDLE;
					HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_RESET);
					HAL_UART_Transmit_IT(&huart2, (uint8_t *)"Done\r\n", 6);
				}
				break;
		}
    /* USER CODE END 3 */
  }
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSIDiv = RCC_HSI_DIV1;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV1;
  RCC_OscInitStruct.PLL.PLLN = 8;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
	if (htim->Instance == TIM1)
	{
		if (g_xy.currentStep_X < g_xy.targetSteps_X)
		{
      g_xy.currentStep_X++;
    }
		if (g_xy.currentStep_X >= g_xy.targetSteps_X)
		{
      __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
    }
	}
	if (htim->Instance == TIM15)
	{
		if (g_xy.currentStep_Y < g_xy.targetSteps_Y)
		{
      g_xy.currentStep_Y++;
    }
		if (g_xy.currentStep_Y >= g_xy.targetSteps_Y)
		{
      __HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 0);
    }
	}
	if (htim->Instance == TIM3)
	{
		if (g_xy.currentStep_Z < g_xy.targetSteps_Z)
		{
      g_xy.currentStep_Z++;
    }
		if (g_xy.currentStep_Z >= g_xy.targetSteps_Z)
		{
      __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
    }
	}
}

void HAL_GPIO_EXTI_Falling_Callback(uint16_t GPIO_Pin)
{
	if (GPIO_Pin == GPIO_PIN_13)
	{
		cmdCount = 0;
		cmdHead = 0;
		cmdTail = 0;
		X1 = 0;
		Y1 = 0;
		pendingCommand = 1;
		machineState = STATE_IDLE;
	}
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
	if (huart->Instance == USART2)
	{
		switch (rx_state)
		{
			case STATE_WAIT_START:
				if (rx_byte == 0xAA)
				{
					temporary_mode = 0;
					temporary_X = 0;
					temporary_Y = 0;
					rx_state = STATE_WAIT_MODE;
				}
				break;

			case STATE_WAIT_MODE:
				temporary_mode = rx_byte;
				rx_state = STATE_WAIT_X_H;
				break;

			case STATE_WAIT_X_H:
				temporary_X = (int16_t)(rx_byte << 8);
				rx_state = STATE_WAIT_X_L;
				break;

			case STATE_WAIT_X_L:
				temporary_X |= rx_byte;
				rx_state = STATE_WAIT_Y_H;
				break;

			case STATE_WAIT_Y_H:
				temporary_Y = (int16_t)(rx_byte << 8);
				rx_state = STATE_WAIT_Y_L;
				break;

			case STATE_WAIT_Y_L:
				temporary_Y |= rx_byte;
				rx_state = STATE_WAIT_END;
				break;

			case STATE_WAIT_END:
				if (rx_byte == 0xBB)
				{
					if (cmdCount < CMD_QUEUE_SIZE)
					{
						cmdQueue[cmdHead].mode = temporary_mode;
						cmdQueue[cmdHead].x = temporary_X;
						cmdQueue[cmdHead].y = temporary_Y;
						cmdHead = (cmdHead + 1) % CMD_QUEUE_SIZE;
						cmdCount++;
					}
					else
					{
						uint8_t nack = 0xFF;
						HAL_UART_Transmit(&huart2, &nack, 1, 10);
					}
				}
				rx_state = STATE_WAIT_START;
				break;

			default:
				rx_state = STATE_WAIT_START;
				break;
		}

		HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
	}
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
