/*
 * bm_gp_traffic.c - gp slice traffic1 example mod: traffic density for every race through "bmashup.traffic" (plus a probe that
 * logs the traffic count, so a run shows the real effect, not only the request).
 *
 * Build-time settings (one module per setting, each its own sha256 / approval):
 *   -DGP_DENSITY=0.5   the density asked for at start (0.0 .. 2.0); a negative value = probe only, nothing asked
 *   -DGP_PROBE=1       log "[PLUGIN <id>] traffic probe: ..." every GP_PROBE_STEPS game steps while a race runs
 * The density is asked once, in takedawn_plugin_service when both services are known (the game's thread, before the game
 * starts), so every race of the process uses it from its traffic set-up on. Nothing else is touched.
 *
 * Build (llvm-mingw): clang -shared -O2 -fvisibility=hidden -Wl,--no-insert-timestamp -I<tree>\include -DGP_DENSITY=0.5 ...
 */
#include <stdio.h>
#include <string.h>

#include "bmashup_traffic.h"
#include "takedawn_plugin.h"
#include "takedawn_race.h"
#include "takedawn_services.h"

#ifndef GP_DENSITY
#define GP_DENSITY 0.5
#endif
#ifndef GP_PROBE
#define GP_PROBE 1
#endif
#ifndef GP_PROBE_STEPS
#define GP_PROBE_STEPS 120u
#endif

/* GP_SEQ (validation tool): a list of densities, one per race of the process, e.g. -DGP_SEQ=1.0,0.0,0.5,1.0. The first is asked
 * at start; the next one when the race is left (racing / paused / finished -> any other state), so the next traffic set-up uses
 * it. The probe logs the density each set-up really applied. */
#ifdef GP_SEQ
static const double k_seq[] = {GP_SEQ};
#define GP_SEQ_N (sizeof k_seq / sizeof k_seq[0])
static unsigned s_seq;
#endif

static const td_host_api *s_api;
static const bm_traffic_api *s_tr;
static int s_asked;
static uint32_t s_last_step, s_last_state = 0xFFFFFFFFu, s_samples;
static unsigned long s_sum_active;

static void say(const char *t)
{
    if (s_api)
        s_api->log(s_api->host, TD_LOG_INFO, t);
}

static void ask(void)
{
    char line[200];
    int32_t rc;
    if (s_asked || !s_tr)
        return;
    s_asked = 1;
#ifdef GP_SEQ
    rc = s_tr->set_density(s_api->host, k_seq[0]);
    snprintf(line, sizeof line, "traffic sequence: race 1 density %.2f asked: rc %d", k_seq[0], (int)rc);
    say(line);
    return;
#endif
    if (GP_DENSITY < 0.0) {
        say("traffic: probe only (no density asked)");
        return;
    }
    rc = s_tr->set_density(s_api->host, GP_DENSITY);
    snprintf(line, sizeof line, "traffic: density %.2f asked: %s", (double)GP_DENSITY,
             rc == BM_TRAFFIC_OK ? "accepted (used from the next traffic set-up)" :
             rc == BM_TRAFFIC_CONFLICT ? "REFUSED (another mod owns the density)" :
             rc == BM_TRAFFIC_OUT_OF_RANGE ? "REFUSED (out of range)" : "REFUSED");
    say(line);
}

static void probe(const td_race_snapshot *s)
{
    bm_traffic_status st;
    char line[300];
    int32_t rc;
    if (!s_tr)
        return;
    if (s->state != s_last_state) {
        st.struct_size = sizeof st;
        rc = s_tr->status(s_api->host, &st);
        snprintf(line, sizeof line, "traffic probe: state %u at step %u (rc %d): active %u pool %u flags %u triggers %u flows %u "
                 "start flow %.1f (game %.1f) density %.2f applied %.2f applications %u refusals %u",
                 (unsigned)s->state, (unsigned)s->step, (int)rc, (unsigned)st.active, (unsigned)st.pool, (unsigned)st.set_flags,
                 (unsigned)st.triggers, (unsigned)st.flow_entries, (double)st.flow_start_now, (double)st.flow_start_game,
                 (double)st.density, (double)st.density_applied, (unsigned)st.applications, (unsigned)st.refusals);
        say(line);
        if (s_last_state == TD_RACE_RACING && s_samples) {
            snprintf(line, sizeof line, "traffic probe: race segment summary: %u samples, mean active %.2f", (unsigned)s_samples,
                     (double)s_sum_active / s_samples);
            say(line);
        }
        if (s->state == TD_RACE_RACING)
            s_samples = 0, s_sum_active = 0;
#ifdef GP_SEQ
        if ((s_last_state == TD_RACE_RACING || s_last_state == TD_RACE_PAUSED || s_last_state == TD_RACE_FINISHED) &&
            s->state != TD_RACE_RACING && s->state != TD_RACE_PAUSED && s->state != TD_RACE_FINISHED && s_seq + 1 < GP_SEQ_N) {
            s_seq++;
            rc = s_tr->set_density(s_api->host, k_seq[s_seq]);
            snprintf(line, sizeof line, "traffic sequence: race %u density %.2f asked (used from the next traffic set-up): rc %d",
                     s_seq + 1, k_seq[s_seq], (int)rc);
            say(line);
        }
#endif
        s_last_state = s->state;
        s_last_step = s->step;
    }
    if (GP_PROBE && s->state == TD_RACE_RACING && s->step - s_last_step >= GP_PROBE_STEPS) {
        s_last_step = s->step;
        st.struct_size = sizeof st;
        if (s_tr->status(s_api->host, &st) == BM_TRAFFIC_OK) {
            s_samples++;
            s_sum_active += st.active;
            snprintf(line, sizeof line, "traffic probe: t %.1f lap %u place %d speed %.1f active %u", (double)s->race_time_s,
                     (unsigned)s->lap, (int)s->place, (double)s->speed_mps, (unsigned)st.active);
            say(line);
        }
    }
}

static void TD_CALL on_update(const td_race_snapshot *snapshot, void *user)
{
    (void)user;
    probe(snapshot);
}

TD_EXPORT uint32_t TD_CALL takedawn_plugin_api_version(void)
{
    return TD_PLUGIN_API_VERSION;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_init(const td_host_api *api, td_plugin_info *info)
{
    (void)info;
    s_api = api;
    say("gp traffic example: waiting for bmashup.traffic / takedawn.race");
    return TD_OK;
}

TD_EXPORT int32_t TD_CALL takedawn_plugin_service(const td_host_api *api, const char *name, uint32_t version, const void *table)
{
    (void)api;
    if (!strcmp(name, BM_TRAFFIC_SERVICE) && version >= 1 && table) {
        const bm_traffic_api *t = (const bm_traffic_api *)table;
        if (t->struct_size < sizeof(bm_traffic_api))
            return 1;
        s_tr = t;
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
