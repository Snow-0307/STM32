#include "gcode.h"
#include "function.h"
#include <string.h>
#include <stdlib.h>

/* ------------------------------------------------------------------ */
/*  Low-level: parse a number from s[0..len) into integer steps        */
/*  Parses "10.5" → 13440 steps (1280 steps/mm for 16 µstep). No float. */
/* ------------------------------------------------------------------ */
static int32_t parse_steps(const char *s, int len)
{
    int32_t ip = 0;            /* integer part */
    int32_t fp = 0;            /* fractional-part accumulator */
    int     fd = 1;            /* fractional divisor (1,10,100,…) */
    int     sign = 1;
    int     i = 0;

    if (i >= len) return 0;
    if (s[i] == '-') { sign = -1; i++; }
    else if (s[i] == '+') { i++; }
    if (i >= len) return 0;

    while (i < len && s[i] >= '0' && s[i] <= '9') {
        ip = ip * 10 + (s[i] - '0');
        i++;
    }
    if (i < len && s[i] == '.') {
        i++;
        while (i < len && s[i] >= '0' && s[i] <= '9') {
            if (fd <= 10000) {          /* keep up to 4 decimal digits */
                fp = fp * 10 + (s[i] - '0');
                fd *= 10;
            }
            i++;
        }
    }
    /* steps = mm * MM_TO_STEPS, fractional part: (fp * MM_TO_STEPS) / fd */
    int32_t steps = MM_TO_STEPS(ip);
    if (fd > 1)
        steps += MM_TO_STEPS(fp) / fd;
    return sign * steps;
}

/* Parse a plain float value (for F / P words).  No stdlib atof. */
static float parse_float_val(const char *s, int len)
{
    float ip = 0.0f;
    float fp = 0.0f;
    float fd = 1.0f;
    int   sign = 1;
    int   i = 0;

    if (i >= len) return 0.0f;
    if (s[i] == '-') { sign = -1; i++; }
    else if (s[i] == '+') { i++; }
    if (i >= len) return 0.0f;

    while (i < len && s[i] >= '0' && s[i] <= '9') {
        ip = ip * 10.0f + (float)(s[i] - '0');
        i++;
    }
    if (i < len && s[i] == '.') {
        i++;
        while (i < len && s[i] >= '0' && s[i] <= '9') {
            fp = fp * 10.0f + (float)(s[i] - '0');
            fd *= 10.0f;
            i++;
        }
    }
    return sign * (ip + fp / fd);
}

/* ------------------------------------------------------------------ */
/*  Strip comments  (…) and ;… from a line in-place                   */
/* ------------------------------------------------------------------ */
static void strip_comments(char *line)
{
    char *src = line, *dst = line;
    int paren = 0;
    for (; *src; src++) {
        if (*src == '(')  { paren++; continue; }
        if (*src == ')')  { if (paren) paren--; continue; }
        if (*src == ';')  break;               /* rest is comment */
        if (!paren) *dst++ = *src;
    }
    *dst = '\0';
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */
void gcode_modal_init(GCodeModal *m)
{
    m->motion_mode   = 0;
    m->distance_mode = 0;   /* G90 absolute */
    m->units         = 0;   /* G21 mm */
    m->spindle       = 0;
    m->offset_x      = 0;
    m->offset_y      = 0;
}

int gcode_parse_line(const char *line, ParsedGCode *out,
                     GCodeModal *modal,
                     int32_t current_steps_x, int32_t current_steps_y)
{
    char buf[GCODE_LINE_MAX];
    int  i;

    memset(out, 0, sizeof(*out));

    /* Copy & strip comments */
    if (strlen(line) >= GCODE_LINE_MAX) return 0;
    strcpy(buf, line);
    strip_comments(buf);

    /* Trim leading whitespace */
    char *p = buf;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '\0' || *p == '\n' || *p == '\r') return 0;

    /* ---- Tokenise ---- */
    while (*p) {
        while (*p == ' ' || *p == '\t') { p++; }
        if (*p == '\0') break;

        /* Letter */
        char c = *p;
        if (c >= 'a' && c <= 'z') c -= 32;    /* uppercase */
        if (c < 'A' || c > 'Z') { p++; continue; }
        p++;

        /* Number following the letter */
        const char *num_start = p;
        while (*p == '-' || *p == '+' || *p == '.' || (*p >= '0' && *p <= '9')) p++;
        int num_len = (int)(p - num_start);

        if (num_len == 0 && c != 'G') continue;   /* G without number is actually G0 */

        switch (c) {
        case 'G': {
            int gv = 0;
            for (i = 0; i < num_len; i++) gv = gv * 10 + (num_start[i] - '0');
            out->has_g = 1;
            out->g = gv;

            switch (gv) {
            case 0:  modal->motion_mode = 0; break;
            case 1:  modal->motion_mode = 1; break;
            case 4:  break;  /* dwell – handled by P word */
            case 17: break;  /* XY plane – ignore */
            case 20: modal->units = 1; break;
            case 21: modal->units = 0; break;
            case 28: break;  /* home – handled below */
            case 90: modal->distance_mode = 0; break;
            case 91: modal->distance_mode = 1; break;
            case 92: break;  /* set offset – handled via X/Y words */
            }
            break;
        }
        case 'M': {
            int mv = 0;
            for (i = 0; i < num_len; i++) mv = mv * 10 + (num_start[i] - '0');
            out->has_m = 1;
            out->m = mv;

            switch (mv) {
            case 0: case 1: case 2: case 30:
                /* program pause / end – stop processing */
                break;
            case 3: case 4:
                modal->spindle = 1; break;
            case 5:
                modal->spindle = 0; break;
            }
            break;
        }
        case 'X':
            out->has_x = 1;
            out->x_steps = parse_steps(num_start, num_len);
            break;
        case 'Y':
            out->has_y = 1;
            out->y_steps = parse_steps(num_start, num_len);
            break;
        case 'Z':
            out->has_z = 1;
            out->z_steps = parse_steps(num_start, num_len);
            break;
        case 'F':
            out->has_f = 1;
            out->f_value = parse_float_val(num_start, num_len);
            break;
        case 'P':
            out->has_p = 1;
            out->p_dwell_ms = (uint16_t)(parse_float_val(num_start, num_len) * 1000.0f);
            break;
        case 'I': case 'J': case 'K':
            /* arc params – not yet implemented */
            break;
        }
    }

    /* ---- Resolve coordinates ---- */
    /* Save raw G-code values before applying offset/relative */
    int32_t raw_x = out->x_steps;
    int32_t raw_y = out->y_steps;

    if (out->has_x) {
        if (modal->distance_mode == 0)          /* G90 absolute */
            out->x_steps = raw_x + modal->offset_x;
        else                                     /* G91 relative */
            out->x_steps = current_steps_x + raw_x;
    }
    if (out->has_y) {
        if (modal->distance_mode == 0)          /* G90 absolute */
            out->y_steps = raw_y + modal->offset_y;
        else                                     /* G91 relative */
            out->y_steps = current_steps_y + raw_y;
    }

    /* G28 – override to home (0,0) absolute */
    if (out->has_g && out->g == 28) {
        out->has_x = 0;
        out->has_y = 0;
    }

    /* G92 – set offset (use RAW values, not already-adjusted) */
    if (out->has_g && out->g == 92) {
        if (out->has_x)
            modal->offset_x = current_steps_x - raw_x;
        else
            modal->offset_x = 0;

        if (out->has_y)
            modal->offset_y = current_steps_y - raw_y;
        else
            modal->offset_y = 0;

        out->has_g = 0;     /* no motion generated */
    }

    return out->has_g || out->has_m;
}
