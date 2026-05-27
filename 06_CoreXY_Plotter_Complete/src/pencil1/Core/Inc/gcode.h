#ifndef __GCODE_H
#define __GCODE_H

#include <stdint.h>

#define GCODE_LINE_MAX   128
#define GCODE_BUF_MAX    8

/* G-code modal state (persistent across commands) */
typedef struct {
    uint8_t  motion_mode;    /* 0=none, 0=G0 rapid, 1=G1 linear */
    uint8_t  distance_mode;  /* 0=absolute (G90), 1=relative (G91) */
    uint8_t  units;          /* 0=mm (G21), 1=inch (G20) */
    uint8_t  spindle;        /* 0=off, 1=on (M3=on, M5=off) */
    int32_t  offset_x;       /* G92 offset (steps) */
    int32_t  offset_y;       /* G92 offset (steps) */
} GCodeModal;

/* Parsed result of a single G-code line */
typedef struct {
    uint8_t  has_g;
    uint8_t  has_m;
    uint8_t  g;
    uint8_t  m;
    uint8_t  has_x, has_y, has_z, has_f, has_p;
    int32_t  x_steps;        /* X target in steps (absolute after G90/G91 resolution) */
    int32_t  y_steps;        /* Y target in steps */
    int32_t  z_steps;        /* Z target */
    float    f_value;        /* feed rate mm/min */
    uint16_t p_dwell_ms;     /* dwell time in ms */
} ParsedGCode;

/* --- API --- */

/* Initialize modal state */
void gcode_modal_init(GCodeModal *m);

/* Parse one complete G-code line into ParsedGCode.
 * current_steps_x/y: current machine position in steps (for G91 relative mode).
 * On success returns 1, on error/empty/comment returns 0.
 */
int gcode_parse_line(const char *line, ParsedGCode *out, GCodeModal *modal,
                     int32_t current_steps_x, int32_t current_steps_y);

#endif /* __GCODE_H */
