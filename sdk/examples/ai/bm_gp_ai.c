/*
 * bm_gp_ai.c - gp slice ai1 example mod: AI rival pace for every race through "bmashup.ai", plus a probe that logs what the AI
 * really does (cap, target, car speed, schedule zone of every rival), so a run shows the gameplay effect, not only the request.
 *
 * Build-time settings (one module per setting, each its own sha256 / approval):
 *   -DGP_PACE=0.8          the pace asked for at start (0.5 .. 1.5); negative = probe only
 *   -DGP_SEQ=1.0,0.7,1.3,1.0   validation tool: one pace per race of the process (the next one when the race is left)
 * The probe logs every GP_PROBE_STEPS game steps while racing, and a per-segment summary when the race state changes.
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_ai.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef GP_PACE
#define GP_PACE 0.8
#endif
#ifndef GP_PROBE_STEPS
#define GP_PROBE_STEPS 120u
#endif
#ifdef GP_SEQ
static const double k_seq[] = {GP_SEQ};
#define GP_SEQ_N (sizeof k_seq / sizeof k_seq[0])
static unsigned s_seq;
#endif

static const td_host_api *s_api;
static const bm_ai_api *s_ai;
static int s_asked;
static uint32_t s_last_step, s_last_state = 0xFFFFFFFFu, s_samples;
static double s_sum_ai_speed, s_sum_ai_cap, s_sum_p1_speed;
static unsigned s_n_ai;
static uint32_t s_zone_sum_last;

static void say(const char *t)
{
    if (s_api)
        s_api->log(s_api->host, TD_LOG_INFO, t);
}

static void ask_value(double v, unsigned race)
{
    char line[200];
    int32_t rc = s_ai->set_pace(s_api->host, v);
    snprintf(line, sizeof line, "ai: race %u pace %.2f asked: %s", race, v,
             rc == BM_AI_OK ? "accepted (used from the next AI update)" : rc == BM_AI_CONFLICT ? "REFUSED (another mod owns the pace)" :
             rc == BM_AI_OUT_OF_RANGE ? "REFUSED (out of range)" : "REFUSED");
    say(line);
}

static void ask(void)
{
    if (s_asked || !s_ai)
        return;
    s_asked = 1;
#ifdef GP_SEQ
    ask_value(k_seq[0], 1);
#else
    if (GP_PACE < 0.0)
        say("ai: probe only (no pace asked)");
    else
        ask_value(GP_PACE, 1);
#endif
}

static void sample(const td_race_snapshot *s, int print)
{
    char line[900];
    int n = 0;
    uint32_t cnt = s_ai->count(s_api->host), zones = 0;
    n += snprintf(line + n, sizeof line - (size_t)n, "ai probe: t %.1f place %d p1 %.1f |", (double)s->race_time_s, (int)s->place,
                  (double)s->speed_mps);
    for (uint32_t i = 0; i < cnt && n < (int)sizeof line - 80; i++) {
        bm_ai_racer r;
        r.struct_size = sizeof r;
        if (s_ai->get(s_api->host, i, &r) != BM_AI_OK)
            continue;
        if (!r.is_player) {
            s_sum_ai_speed += r.car_speed;
            s_sum_ai_cap += r.speed_cap;
            s_n_ai++;
            zones += r.zone;
        }
        n += snprintf(line + n, sizeof line - (size_t)n, " %u%s cap %.1f tgt %.1f v %.1f off %.1f z %u x%.2f;", (unsigned)i,
                      r.is_player ? "P" : "", (double)r.speed_cap, (double)r.target_speed, (double)r.car_speed,
                      (double)r.schedule_offset, (unsigned)r.zone, (double)r.pace_applied);
    }
    s_sum_p1_speed += s->speed_mps;
    s_samples++;
    s_zone_sum_last = zones;
    if (print)
        say(line);
}

static void TD_CALL on_update(const td_race_snapshot *s, void *user)
{
    char line[300];
    (void)user;
    if (!s_ai)
        return;
    if (s->state != s_last_state) {
        if (s_last_state == TD_RACE_RACING && s_samples) {
            double pace = 0;
            s_ai->get_pace(s_api->host, &pace);
            snprintf(line, sizeof line, "ai probe: segment summary (pace now %.2f): %u samples, mean AI car speed %.2f, mean AI cap %.2f, "
                     "mean p1 speed %.2f, AI zone sum at the end %u", pace, (unsigned)s_samples,
                     s_n_ai ? s_sum_ai_speed / s_n_ai : 0.0, s_n_ai ? s_sum_ai_cap / s_n_ai : 0.0, s_sum_p1_speed / s_samples,
                     (unsigned)s_zone_sum_last);
            say(line);
        }
#ifdef GP_SEQ
        if ((s_last_state == TD_RACE_RACING || s_last_state == TD_RACE_PAUSED || s_last_state == TD_RACE_FINISHED) &&
            s->state != TD_RACE_RACING && s->state != TD_RACE_PAUSED && s->state != TD_RACE_FINISHED && s_seq + 1 < GP_SEQ_N) {
            s_seq++;
            ask_value(k_seq[s_seq], s_seq + 1);
        }
#endif
        if (s->state == TD_RACE_RACING) {
            s_samples = 0, s_n_ai = 0;
            s_sum_ai_speed = s_sum_ai_cap = s_sum_p1_speed = 0;
        }
        snprintf(line, sizeof line, "ai probe: state %u at step %u", (unsigned)s->state, (unsigned)s->step);
        say(line);
        s_last_state = s->state;
        s_last_step = s->step;
    }
    if (s->state == TD_RACE_RACING && s->step - s_last_step >= GP_PROBE_STEPS) {
        s_last_step = s->step;
        sample(s, 1);
    }
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("gp ai example: waiting for bmashup.ai / takedawn.race");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    (void)api;
    if (!strcmp(name, BM_AI_SERVICE) && version >= 1 && table) {
        const bm_ai_api *t = (const bm_ai_api *)table;
        if (t->struct_size < sizeof(bm_ai_api))
            return 1;
        s_ai = t;
        ask();
        return TD_OK;
    }
    if (!strcmp(name, TD_RACE_SERVICE) && version >= 1 && table) {
        const td_race_api *r = (const td_race_api *)table;
        if (r->struct_size < sizeof(td_race_api))
            return 1;
        r->on_update(s_api->host, on_update, NULL);
        return TD_OK;
    }
    return 1;
}
