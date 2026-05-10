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
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define MM_TO_STEPS(mm) ((uint32_t)((mm) * 80))

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
typedef enum {
    MACHINE_IDLE = 0,
		MACHINE_START,
    MACHINE_PEN_DOWN,
    MACHINE_MOVING,
    MACHINE_PEN_UP,
    MACHINE_PEN_RETURN,
		MACHINE_DRAW_UP,
    MACHINE_DRAW_LEFT,
    MACHINE_DRAW_DOWN,
    MACHINE_DRAW_RIGHT,
    MACHINE_DONE
} MachineState;


volatile MachineState machineState = MACHINE_IDLE;
volatile uint8_t startFlag = 0;
volatile uint8_t speed = 0;
volatile uint32_t xStepCount = 0;
uint32_t xTargetSteps = MM_TO_STEPS(50);
uint32_t p_TargetSteps = MM_TO_STEPS(7);
uint32_t p_r_TargetSteps = MM_TO_STEPS(10);
uint8_t ch;

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
  MX_TIM1_Init();
  MX_USART2_UART_Init();
  MX_TIM15_Init();
  MX_TIM3_Init();
  /* USER CODE BEGIN 2 */
	HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_SET);
	HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
	HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
	
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

	HAL_UART_Receive_IT(&huart2, &ch, 1);
	
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
		switch (machineState)
		{
			case MACHINE_IDLE:
			break;
			
			case MACHINE_PEN_RETURN:
				__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 150);
				if (xStepCount >= p_r_TargetSteps)
        {
          xStepCount = 0;
					
					__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
					machineState = MACHINE_IDLE;
        }
			break;
			
			case MACHINE_START:
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);
				HAL_UART_Transmit_IT(&huart2, (uint8_t *)"Start\r\n", strlen("Start\r\n"));
					
				xStepCount = 0;
				if (startFlag == 1)
				{
					machineState = MACHINE_MOVING;
					
					__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
					
					__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 150);
					__HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 150);
				}else if (startFlag == 2)
				{
					machineState = MACHINE_PEN_DOWN;
					
					HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_RESET);
					__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 150);
				}
				
			break;
			
			case MACHINE_PEN_DOWN:
				if (xStepCount >= p_TargetSteps)
				{
					__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
					
					__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 150);
					__HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 150);
					
					machineState = MACHINE_DRAW_DOWN;
					xStepCount = 0;
				}	
			break;
				
			case MACHINE_MOVING:
				if (xStepCount >= xTargetSteps)
        {
          xStepCount = 0;
					
					__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
					__HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 0);
          machineState = MACHINE_DONE;
        }
			break;
			
			case MACHINE_DRAW_UP:
				HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_SET);
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_RESET);
			
				if (xStepCount >= xTargetSteps)
        {
          xStepCount = 0;
					
          machineState = MACHINE_DRAW_RIGHT;
        }
			break;
				
			case MACHINE_DRAW_DOWN:
				HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_RESET);
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
			
				if (xStepCount >= xTargetSteps)
        {
          xStepCount = 0;
					
          machineState = MACHINE_DRAW_LEFT;
        }
			break;
				
			case MACHINE_DRAW_LEFT:
				HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_RESET);
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_RESET);
			
				if (xStepCount >= xTargetSteps)
        {
          xStepCount = 0;
					
          machineState = MACHINE_DRAW_UP;
        }
			break;
				
			case MACHINE_DRAW_RIGHT:
				HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_SET);
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
			
				if (xStepCount >= xTargetSteps)
        {
          xStepCount = 0;
					
          machineState = MACHINE_PEN_UP;
        }
			break;
				
			case MACHINE_PEN_UP:
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
				__HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
				__HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 0);
				__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 150);
				
				if (xStepCount >= p_TargetSteps)
				{
					xStepCount = 0;
					
					__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
					machineState = MACHINE_DONE;
				}			
			break;
				
			case MACHINE_DONE:
				HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_RESET);
				HAL_UART_Transmit_IT(&huart2, (uint8_t *)"Stop\r\n", strlen("Stop\r\n"));
			
				startFlag = 0;
				machineState = MACHINE_IDLE;
			break;
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
        xStepCount++;
    }
}

void HAL_GPIO_EXTI_Falling_Callback(uint16_t GPIO_Pin)
{
	if (GPIO_Pin == GPIO_PIN_13)
  {
		startFlag = 2;
		machineState = MACHINE_START;
	}
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
	if (ch == 's')
	{
		HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_RESET);
		HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
		
		startFlag = 1;
		machineState = MACHINE_START;
		
		HAL_UART_Receive_IT(&huart2, &ch, 1);
	}else if (ch == 'd')
	{
		HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_SET);
		HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_SET);
		
		startFlag = 1;
		machineState = MACHINE_START;
		
		HAL_UART_Receive_IT(&huart2, &ch, 1);
	}else if (ch == 'w')
	{
		HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_SET);
		HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_RESET);
		
		startFlag = 1;
		machineState = MACHINE_START;
		
		HAL_UART_Receive_IT(&huart2, &ch, 1);
	}else if (ch == 'a')
	{
		HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_RESET);
		HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, GPIO_PIN_RESET);
		
		startFlag = 1;
		machineState = MACHINE_START;
		
		HAL_UART_Receive_IT(&huart2, &ch, 1);
	}else if (ch == 'r')
	{
		HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
		
		xStepCount = 0;	
		machineState = MACHINE_PEN_RETURN;
		
		HAL_UART_Receive_IT(&huart2, &ch, 1);
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
