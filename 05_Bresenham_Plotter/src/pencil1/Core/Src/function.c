#include "main.h"
#include "tim.h"
#include "gpio.h"
#include "function.h"
#include <stdlib.h>

void set_motor_dir(int motor_id, int dir) {
    if (motor_id == 1)
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, dir);
    else
        HAL_GPIO_WritePin(GPIOA, GPIO_PIN_8, dir);
}

void motor_1_step(int step) {
    if (step > 0)
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 150);
    else
        __HAL_TIM_SET_COMPARE(&htim1, TIM_CHANNEL_2, 0);
}

void motor_2_step(int step) {
    if (step > 0)
        __HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 150);
    else
        __HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, 0);
}

void pen_down(X_Y* xy) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_RESET);
    xy->targetSteps_Z = 600;
    xy->currentStep_Z = 0;
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 150);
}

void pen_up(X_Y* xy) {
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
    xy->targetSteps_Z = 800;
    xy->currentStep_Z = 0;
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 150);
}

void bresenham_init(X_Y* xy, int X0, int Y0, int X1, int Y1) {
    int dx_raw = MM_TO_STEPS(X1) - MM_TO_STEPS(X0);
    int dy_raw = MM_TO_STEPS(Y1) - MM_TO_STEPS(Y0);

    xy->dx_sign = (dx_raw > 0) ? 1 : (dx_raw < 0) ? -1 : 0;
    xy->dy_sign = (dy_raw > 0) ? 1 : (dy_raw < 0) ? -1 : 0;

    xy->dx = abs(dx_raw);
    xy->dy = abs(dy_raw);

    if (xy->dx == 0 && xy->dy == 0)
		{
			xy->steep = -1;
			xy->totalSteps = 0;
			xy->interpStep = 0;
			xy->targetSteps_X = xy->targetSteps_Y = xy->targetSteps_Z = 0;
			xy->currentStep_X = xy->currentStep_Y = xy->currentStep_Z = 0;
			return;
    }
    if (xy->dx == 0)
		{
			xy->steep = 3;
			xy->totalSteps = xy->dy;
			xy->interpStep = 0;
			xy->targetSteps_X = xy->targetSteps_Y = xy->targetSteps_Z = 0;
			xy->currentStep_X = xy->currentStep_Y = xy->currentStep_Z = 0;
			return;
    }
    if (xy->dy == 0)
		{
			xy->steep = 4;
			xy->totalSteps = xy->dx;
			xy->interpStep = 0;
			xy->targetSteps_X = xy->targetSteps_Y = xy->targetSteps_Z = 0;
			xy->currentStep_X = xy->currentStep_Y = xy->currentStep_Z = 0;
			return;
    }

    if (xy->dy < xy->dx)
		{
			xy->steep = 0;
			xy->D = 2 * xy->dy - xy->dx;
			xy->totalSteps = xy->dx;
    }else if (xy->dy > xy->dx)
		{
			xy->steep = 1;
			xy->D = 2 * xy->dx - xy->dy;
			xy->totalSteps = xy->dy;
    }else
		{
			xy->steep = 2;
			xy->totalSteps = xy->dx;
    }
    xy->interpStep = 0;
    xy->targetSteps_X = xy->targetSteps_Y = xy->targetSteps_Z = 0;
    xy->currentStep_X = xy->currentStep_Y = xy->currentStep_Z = 0;
}

int isMotionComplete(X_Y* xy) {
	return (xy->currentStep_X >= xy->targetSteps_X &&
					xy->currentStep_Y >= xy->targetSteps_Y &&
					xy->currentStep_Z >= xy->targetSteps_Z);
}

void bresenham_step(X_Y* xy) {
    if (xy->interpStep >= xy->totalSteps) return;

    int step_x = 0, step_y = 0;

    if (xy->steep == 3)
		{
			step_y = xy->dy_sign;
		 
			int m1 = -step_y;
			int m2 = -step_y;
			set_motor_dir(1, (m1 >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);
			set_motor_dir(2, (m2 >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);
			xy->targetSteps_X = abs(m1);
			xy->targetSteps_Y = abs(m2);
			xy->currentStep_X = xy->currentStep_Y = 0;
			motor_1_step(xy->targetSteps_X);
			motor_2_step(xy->targetSteps_Y);
			xy->interpStep++;
			return;
    }

    if (xy->steep == 4)
		{
			step_x = xy->dx_sign;
			
			int m1 = step_x;
			int m2 = -step_x;
			set_motor_dir(1, (m1 >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);
			set_motor_dir(2, (m2 >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);
			xy->targetSteps_X = abs(m1);
			xy->targetSteps_Y = abs(m2);
			xy->currentStep_X = xy->currentStep_Y = 0;
			motor_1_step(xy->targetSteps_X);
			motor_2_step(xy->targetSteps_Y);
			xy->interpStep++;
			return;
    }

    if (xy->steep == 0)
		{
			step_x = xy->dx_sign;
			step_y = (xy->D >= 0) ? xy->dy_sign : 0;
			if (step_y != 0) xy->D -= 2 * xy->dx;
			xy->D += 2 * xy->dy;
    }else if (xy->steep == 1)
		{
			step_y = xy->dy_sign;
			step_x = (xy->D >= 0) ? xy->dx_sign : 0;
			if (step_x != 0) xy->D -= 2 * xy->dy;
			xy->D += 2 * xy->dx;
    }else
		{
			step_x = xy->dx_sign;
			step_y = xy->dy_sign;
    }

    int motor1_steps = step_x - step_y;
    int motor2_steps = -step_x - step_y;

    set_motor_dir(1, (motor1_steps >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    set_motor_dir(2, (motor2_steps >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);

    xy->targetSteps_X = abs(motor1_steps);
    xy->targetSteps_Y = abs(motor2_steps);
    xy->currentStep_X = xy->currentStep_Y = 0;
    motor_1_step(xy->targetSteps_X);
    motor_2_step(xy->targetSteps_Y);

    xy->interpStep++;
}