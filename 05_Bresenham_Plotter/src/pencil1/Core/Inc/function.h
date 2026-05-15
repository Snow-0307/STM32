#ifndef __FUNCTION_H
#define __FUNCTION_H

#include <stdint.h>

#define MM_TO_STEPS(mm) ((int32_t)((mm) * 80))

typedef struct 
{
	int dx, dy, D, steep, totalSteps, interpStep;
    int targetSteps_X, currentStep_X;
    int targetSteps_Y, currentStep_Y;
    int targetSteps_Z, currentStep_Z;
	int dx_sign, dy_sign;
}X_Y;

void set_motor_dir(int motor_id, int dir);
void motor_1_step(int step);
void motor_2_step(int step);
void pen_return (X_Y* x_y);
void pen_z_return (X_Y* x_y);
void pen_down(X_Y* x_y);
void pen_up(X_Y* x_y);
void bresenham_init(X_Y* x_y, int X0, int Y0, int X1, int Y1);
void bresenham_step(X_Y* x_y);
int isMotionComplete(X_Y* x_y);

#endif /* __FUNCTION_H */

