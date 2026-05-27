#ifndef __FUNCTION_H
#define __FUNCTION_H

#include <stdint.h>

#define MM_TO_STEPS(mm) ((int32_t)((mm) * 80))

/* Command modes for the queue */
#define CMD_MOVE       1   /* G0/G1 — move XY, no pen change at end */
#define CMD_PEN_DOWN   5   /* M3 — lower pen */
#define CMD_PEN_UP     6   /* M5 — raise pen */
#define CMD_HOME       7   /* G28 — rapid to origin */
#define CMD_DWELL      8   /* G4 — pause */

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
void bresenham_init_steps(X_Y* xy, int32_t X0_steps, int32_t Y0_steps,
                          int32_t X1_steps, int32_t Y1_steps);
void bresenham_step(X_Y* x_y);
int  isMotionComplete(X_Y* x_y);

/* Pen state – updated by state machine */
extern volatile uint8_t pen_is_down;

#endif /* __FUNCTION_H */

