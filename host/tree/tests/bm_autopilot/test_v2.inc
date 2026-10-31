/* tests/bm_autopilot - version 2 (gp I4): engage2 (an explicit policy, bound
 * to one race), release (the title's hand-back), the lifecycle (LOAD_DONE /
 * RACE_EXIT from bm_lifecycle.c) and the sequences a process goes through:
 * race 1 -> results -> race exit -> front end -> race 2, a restart, a quit to
 * the menu, the front end itself. Included in main() of test_main.c, before
 * the concurrency block (which needs the lifecycle left allowing a race). */
    {
#define PHYS       0x00400000u                  /* player 1's car's physics object (stand-in) */
#define ONE        0x003B168Cu                  /* .rdata 1.0 */
#define LC_LOAD    1u                           /* BO3_LC_EV_LOAD_DONE */
#define LC_EXIT    2u                           /* BO3_LC_EV_RACE_EXIT */
#define LD_TRACK   1u
#define LD_FE      2u
#define LD_PARTIAL 3u
#define LD_RESTART 4u
#define E2(car_, race_) (s_req.struct_size = 12, s_req.policy = BM_AP_POLICY_ONCE_PER_RACE, s_req.race = (race_), \
                         s_want = 2, s_rc = -1, tick(car_), s_rc)
#define REL(car_) (s_want = 3, s_rc = -1, tick(car_), s_rc)
#define PHYS_SET() do { M32(CAR + 0x2440u) = PHYS; M32(PHYS + 0x1580u) = CAR; M32(PHYS + 0x1524u) = 4; \
                        MF(PHYS + 0x1534u) = 0.25f; M32(ONE) = 0x3F800000u; } while (0)
#define PHYS_SAME() (M32(PHYS + 0x1524u) == 4 && MF(PHYS + 0x1534u) == 0.25f)
#define FRONT_END() do { M32(STATE) = 5; M32(MODULE) = 0; tick(0); } while (0)
#define NEW_RACE() do { game(0); M8(CAR + AI) = 0; tick(1); game(2); tick(1); r = st().race; } while (0)
#define ENGAGED_RACE() do { NEW_RACE(); PHYS_SET(); E2(0, r); tick(1); } while (0)
        uint32_t r, er0, cen0, rel0;
        int c0;
        bm_autopilot_status s2;

        game(0);
        M8(CAR + AI) = 0;
        tick(1);                                /* a new race to start from (no lifecycle event seen yet) */
        game(2);
        tick(1);
        PHYS_SET();
        r = st().race;
        er0 = st().engaged_races;

        /* engage2: bad requests refused, nothing written, the status unchanged */
        c0 = s_calls;
        s = st();
        snap_mem();
        s_req.struct_size = 12;
        s_req.policy = BM_AP_POLICY_ONCE_PER_RACE;
        s_req.race = 0;
        CHECK(s_api->engage2(HOST, NULL) == BM_AP_BAD_ARG && s_api->engage2(NULL, &s_req) == BM_AP_BAD_ARG,
              "engage2 without a request or a host: a bad argument");
        s_req.struct_size = 8;
        CHECK(s_api->engage2(HOST, &s_req) == BM_AP_BAD_ARG, "engage2 with a request below 12 bytes: a bad argument");
        s_req.struct_size = 12;
        s_req.policy = 0;
        CHECK(s_api->engage2(HOST, &s_req) == BM_AP_BAD_ARG, "engage2 without a policy: a bad argument");
        s_req.policy = 2;
        CHECK(s_api->engage2(HOST, &s_req) == BM_AP_BAD_ARG, "engage2 with an unknown policy: a bad argument");
        CHECK(mem_same() && st().state == s.state && st().reason == s.reason && s_calls == c0,
              "bad requests: nothing written, the status as it was");

        /* bound to one race */
        snap_mem();
        CHECK(E2(0, r + 7) == BM_AP_WRONG_RACE && E2(0, r - 1) == BM_AP_WRONG_RACE && mem_same() && st().state == s.state
              && st().reason == s.reason && st().race == r, "engage2 for another race: WRONG_RACE, the status unchanged");
        CHECK(REL(0) == BM_AP_NOT_ENGAGED && st().state == s.state && st().release_reason == BM_AP_OK,
              "release with nothing engaged: NOT_ENGAGED, the status unchanged");
        CHECK(E2(0, r) == BM_AP_OK && st().state == BM_AP_STATE_PENDING && mem_same(), "engage2 for this race: PENDING, no write");
        c0 = s_calls;
        tick(1);
        s2 = st();
        CHECK(s_calls == c0 + 1 && s2.state == BM_AP_STATE_ENGAGED && s2.engaged_races == er0 + 1 && M8(CAR + AI) == 1,
              "engage2: the takeover at the next car update; engaged races +1");
        CHECK(E2(1, r) == BM_AP_ALREADY_USED && E2(1, 0) == BM_AP_ALREADY_USED && s_calls == c0 + 1,
              "once per race: again in this race refused");

        /* release: staged, then the title's hand-back at the next car update */
        snap_mem();
        CHECK(REL(0) == BM_AP_OK && mem_same() && st().state == BM_AP_STATE_ENGAGED, "release accepted; nothing written yet");
        CHECK(REL(0) == BM_AP_ALREADY_PENDING, "release again while staged: already pending");
        MF(NOW) = 777.0f;
        rel0 = bo3_bm_autopilot_releases();
        tick(1);
        s2 = st();
        CHECK(s2.state == BM_AP_STATE_RELEASED && s2.release_reason == BM_AP_OK && M8(CAR + AI) == 0
              && MF(PHYS + 0x1534u) == 1.0f && M32(PHYS + 0x1524u) == 0 && s_calls == c0 + 1
              && bo3_bm_autopilot_releases() == rel0 + 1,
              "the release: AI byte 0, physics + 0x1534 = 1.0, + 0x1524 4 -> 0, no AI call; RELEASED");
        CHECK(MF(CTLS + 0x184u) != 777.0f && M8(CAR2 + AI) == 0, "the release's car update stamps nothing; player 2 untouched");
        MF(NOW) = 888.0f;
        snap_mem();
        tick(1);
        tick(1);
        CHECK(mem_same() && s_calls == c0 + 1, "released: the cleared byte is not taken again, no stamp, nothing written");
        CHECK(E2(1, r) == BM_AP_ALREADY_USED && REL(1) == BM_AP_NOT_ENGAGED,
              "released: no new takeover in this race; release again: not engaged");
        M32(CAR + PHASE) = 3;
        tick(1);
        CHECK(st().state == BM_AP_STATE_RELEASED && M8(CAR + AI) == 0 && s_calls == c0 + 1,
              "the finish after a release: still RELEASED, nothing written");

        /* race N finished -> results -> race exit -> front end -> race N+1 */
        M8(CAR + AI) = 1;                       /* the title's own finish takeover */
        cen0 = bo3_bm_autopilot_censuses();
        bo3_bm_autopilot_lifecycle(LC_EXIT, LD_TRACK);
        CHECK(bo3_bm_autopilot_censuses() == cen0 + 1 && st().state == BM_AP_STATE_RELEASED,
              "a race exit: one census line, the state kept");
        FRONT_END();
        snap_mem();
        CHECK(E2(0, 0) == BM_AP_ALREADY_USED && st().state == BM_AP_STATE_RELEASED && mem_same(),
              "the front end after a used race: ALREADY_USED (the state is kept until the next race), nothing written");
        CHECK(REL(0) == BM_AP_NOT_ENGAGED, "the front end: release not engaged");
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_FE);
        game(2);                                /* the race memory still looks like a race */
        M8(CAR + AI) = 0;
        tick(1);
        snap_mem();
        CHECK(E2(1, 0) == BM_AP_NOT_IN_RACE && mem_same() && s_calls == c0 + 1,
              "a front-end load since the race exit: refused although the memory looks like a race");
        FRONT_END();
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_TRACK);
        game(0);
        M8(CAR + AI) = 0;                       /* the title's car reset (sub_0018C470) */
        tick(1);
        s2 = st();
        CHECK(s2.state == BM_AP_STATE_IDLE && s2.race != r && s2.release_reason == BM_AP_OK, "race N+1: IDLE, a new race");
        r = s2.race;
        game(2);
        tick(1);
        CHECK(E2(0, r) == BM_AP_OK, "race N+1: accepted");
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENGAGED && st().engaged_races == er0 + 2 && s_calls == c0 + 2,
              "race N+1: engaged again: one takeover in each race of the process");
        cen0 = bo3_bm_autopilot_censuses();
        tick(1);
        tick(1);
        CHECK(bo3_bm_autopilot_censuses() == cen0, "the GO census once a race, not at each car update");

        /* a restart (RESTART load) while engaged: ENDED; the next countdown is a new race */
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_RESTART);
        CHECK(st().state == BM_AP_STATE_ENDED, "a restart load while engaged: ENDED");
        snap_mem();
        tick(1);
        tick(1);
        CHECK(mem_same(), "after it: nothing written (no stamp, no re-take)");
        game(0);
        M8(CAR + AI) = 1;                       /* the title's rolling start holds the car */
        tick(1);
        CHECK(st().state == BM_AP_STATE_IDLE && st().race != r, "the restarted race: a new race");
        r = st().race;
        CHECK(E2(1, r) == BM_AP_COUNTDOWN, "the countdown: refused");
        game(2);
        M8(CAR + AI) = 1;
        tick(1);
        CHECK(E2(1, r) == BM_AP_AI_OWNED && st().reason == BM_AP_AI_OWNED && M8(CAR + AI) == 1,
              "after the GO the title's AI still holds it: AI_OWNED, never cleared by the service");
        M8(CAR + AI) = 0;                       /* the rolling start's end */
        CHECK(E2(0, r) == BM_AP_OK, "asked again once the title let go: accepted");
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENGAGED && st().engaged_races == er0 + 3, "engaged in the restarted race");

        /* a quit to the menu while engaged, with a release staged */
        CHECK(REL(0) == BM_AP_OK, "release staged (quit next)");
        rel0 = bo3_bm_autopilot_releases();
        bo3_bm_autopilot_lifecycle(LC_EXIT, LD_RESTART);
        s2 = st();
        CHECK(s2.state == BM_AP_STATE_ENDED && s2.release_reason == BM_AP_STALE, "a race exit: ENDED, the staged release dropped");
        snap_mem();
        tick(1);
        tick(1);
        CHECK(mem_same() && bo3_bm_autopilot_releases() == rel0 && M8(CAR + AI) == 1,
              "after the race exit: nothing written, no hand-back");

        /* a request dropped by a load end; a partial load allows no race */
        FRONT_END();
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_TRACK);
        NEW_RACE();
        c0 = s_calls;
        CHECK(E2(0, r) == BM_AP_OK, "staged (a load end next)");
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_PARTIAL);
        CHECK(st().state == BM_AP_STATE_REFUSED && st().reason == BM_AP_STALE, "a load end before its car update: dropped");
        tick(1);
        CHECK(s_calls == c0 && M8(CAR + AI) == 0, "and never done");
        CHECK(E2(1, r) == BM_AP_NOT_IN_RACE, "after a partial load: refused until a track or restart load");
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_RESTART);

        /* release refusals at the car update: still ENGAGED, nothing of the hand-back written, the reason kept */
        ENGAGED_RACE();
        CHECK(st().state == BM_AP_STATE_ENGAGED, "engaged (physics link broken)");
        CHECK(REL(0) == BM_AP_OK, "release staged (physics link broken)");
        M32(PHYS + 0x1580u) = CAR2;
        rel0 = bo3_bm_autopilot_releases();
        tick(1);
        s2 = st();
        CHECK(s2.state == BM_AP_STATE_ENGAGED && s2.release_reason == BM_AP_NO_CAR && M8(CAR + AI) == 1 && PHYS_SAME()
              && bo3_bm_autopilot_releases() == rel0, "the physics object is another car's: refused there, still ENGAGED");
        M32(PHYS + 0x1580u) = CAR;
        CHECK(REL(0) == BM_AP_OK, "release asked again");
        tick(1);
        CHECK(st().state == BM_AP_STATE_RELEASED && M8(CAR + AI) == 0, "then released");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (no physics object)");
        M32(CAR + 0x2440u) = 0;
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENGAGED && st().release_reason == BM_AP_NO_CAR && M8(CAR + AI) == 1 && PHYS_SAME(),
              "no physics object: refused there");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (the .rdata 1.0 changed)");
        M32(ONE) = 0x3F000000u;
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENGAGED && st().release_reason == BM_AP_UNSUPPORTED && M8(CAR + AI) == 1 && PHYS_SAME(),
              "another build (the 1.0 the hand-back copies): unsupported");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (another car)");
        M32(CAR) = 0x003B1204u;
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENGAGED && st().release_reason == BM_AP_NO_CAR && M8(CAR + AI) == 1 && PHYS_SAME(),
              "another object at player 1's car: refused there");
        M32(CAR) = VT_CAR;

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (pause next)");
        M32(PAUSED) = 0;
        tick(0);
        CHECK(st().state == BM_AP_STATE_ENGAGED && st().release_reason == BM_AP_STALE, "a pause before its car update: dropped");
        M32(PAUSED) = 0xFFFFFFFFu;
        tick(1);
        CHECK(M8(CAR + AI) == 1 && PHYS_SAME(), "and never done later");
        CHECK(REL(1) == BM_AP_OK, "release staged (pause at the car update)");
        M32(PAUSED) = 1;
        M32(STEP) += 1;
        g_esi = CAR;
        s_mark();
        CHECK(st().release_reason == BM_AP_PAUSED && M8(CAR + AI) == 1 && PHYS_SAME(), "paused at its car update: refused there");
        M32(PAUSED) = 0xFFFFFFFFu;
        M32(PAUSED) = 0;
        tick(0);
        CHECK(REL(0) == BM_AP_PAUSED && st().release_reason == BM_AP_PAUSED && st().state == BM_AP_STATE_ENGAGED,
              "release while paused: refused, the reason kept");
        M32(PAUSED) = 0xFFFFFFFFu;
        tick(1);

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (steps jump)");
        tick_n(31, 1);
        CHECK(st().release_reason == BM_AP_STALE && M8(CAR + AI) == 1 && PHYS_SAME(), "31 steps before its car update: dropped");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (no car update)");   /* its own update counts as the first */
        tick(0);
        tick(0);
        CHECK(st().release_reason == BM_AP_OK, "still staged 3 updates on");
        tick(0);
        CHECK(st().release_reason == BM_AP_STALE, "the 4th: dropped");
        tick(1);
        CHECK(M8(CAR + AI) == 1 && PHYS_SAME() && st().state == BM_AP_STATE_ENGAGED, "and never done");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (the finish at the car update)");
        M32(CAR + PHASE) = 3;
        tick(1);
        CHECK(st().state == BM_AP_STATE_ENDED && st().release_reason == BM_AP_RACE_OVER && M8(CAR + AI) == 1 && PHYS_SAME(),
              "the finish at its car update: dropped, ENDED (the title's finish is its own)");
        CHECK(REL(1) == BM_AP_NOT_ENGAGED, "after the finish: not engaged");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (the title cleared the byte first)");
        M8(CAR + AI) = 0;
        rel0 = bo3_bm_autopilot_releases();
        c0 = s_calls;
        tick(1);
        CHECK(st().state == BM_AP_STATE_RELEASED && M8(CAR + AI) == 0 && PHYS_SAME() && s_calls == c0
              && bo3_bm_autopilot_releases() == rel0 + 1,
              "the title had cleared the byte: RELEASED with no write (and not taken again)");

        ENGAGED_RACE();
        CHECK(REL(0) == BM_AP_OK, "release staged (another thread asks too)");
        s_th_release = 1;
        th_start(0);
        th_join();
        s_th_release = 0;
        CHECK(s_thread_rc == BM_AP_WRONG_THREAD, "release from another thread: refused");
        M32(PHYS + 0x1524u) = 2;
        tick(1);
        CHECK(st().state == BM_AP_STATE_RELEASED && M32(PHYS + 0x1524u) == 2 && MF(PHYS + 0x1534u) == 1.0f,
              "+ 0x1524 other than 4 is left as it is (as the title does)");

        /* leave the lifecycle allowing a race (the concurrency block next) */
        FRONT_END();
        bo3_bm_autopilot_lifecycle(LC_LOAD, LD_TRACK);
        game(0);
        tick(1);
#undef PHYS
#undef ONE
#undef E2
#undef REL
#undef PHYS_SET
#undef PHYS_SAME
#undef FRONT_END
#undef NEW_RACE
#undef ENGAGED_RACE
    }
