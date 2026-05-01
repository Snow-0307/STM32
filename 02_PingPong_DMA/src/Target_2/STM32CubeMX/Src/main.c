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
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>

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
typedef enum{
	TASK_IDLE = 0,
	TASK_RUNNING
}TaskState;

uint8_t i = 0;
uint8_t active_buffer_is_A = 1;
uint8_t dma_data_ready = 0;
uint8_t RxBuffer_A[10];
uint8_t RxBuffer_B[10];

TaskState keyTaskState = TASK_IDLE;
uint8_t keyBlinkCount = 0;
uint32_t keyLastToggleTick = 0;

TaskState uartTaskState = TASK_IDLE;
uint8_t uartBlinkCount = 0;
uint32_t uartLastToggleTick = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */


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
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
	HAL_UART_Receive_DMA(&huart2, (uint8_t *)&RxBuffer_A, 10);
	HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
		uint32_t now = HAL_GetTick();
		
		if (keyTaskState == TASK_RUNNING)
		{
			if (now - keyLastToggleTick >= 50)
			{	
				HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);
				keyLastToggleTick = now;
				keyBlinkCount--;
				if (keyBlinkCount == 0)
				{
					keyTaskState = TASK_IDLE;
					HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);
				}
			}
		}
		
		if (uartTaskState == TASK_RUNNING)
		{
			if (now - uartLastToggleTick >=100)
			{	
				HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);
				uartLastToggleTick = now;
				uartBlinkCount--;
				if (uartBlinkCount == 0)
				{
					uartTaskState = TASK_IDLE;
					HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);
				}
			}
		}
		
		if (dma_data_ready == 1)
		{
			HAL_UART_Transmit(&huart2, (uint8_t *)" full_A ", 10, HAL_MAX_DELAY);
			dma_data_ready = 0;
		}else if (dma_data_ready == 2)
		{
			HAL_UART_Transmit(&huart2, (uint8_t *)" full_B ", 10, HAL_MAX_DELAY);
			dma_data_ready = 0;
		}
  }
  /* USER CODE END 3 */
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
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
void HAL_GPIO_EXTI_Falling_Callback(uint16_t GPIO_Pin)
{
  if(GPIO_Pin == GPIO_PIN_13)
  {
		keyTaskState = TASK_RUNNING;
		keyBlinkCount = 10;
		keyLastToggleTick = HAL_GetTick();
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
	if (active_buffer_is_A == 1)
	{
		uartTaskState = TASK_RUNNING;
		uartBlinkCount = 10 * 2;
		uartLastToggleTick = HAL_GetTick();
		HAL_UART_Receive_DMA(huart, (uint8_t *)&RxBuffer_B, 10);
		active_buffer_is_A = 0;
		dma_data_ready = 1;
	}else
	{
		uartTaskState = TASK_RUNNING;
		uartBlinkCount = 10 * 2;
		uartLastToggleTick = HAL_GetTick();
		HAL_UART_Receive_DMA(huart, (uint8_t *)&RxBuffer_A, 10);
		active_buffer_is_A = 1;
		dma_data_ready = 2;
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
