# bm_events - the engine-point dispatcher (src/game/bm_events.c) and Burnout
# Mashup's private "bmashup.events" service over it (bm_events_service.c), with
# the real bmashup.autopilot / bmashup.boost as its writers, against a stand-in
# for the game's memory: order, re-entry, register state, capacity, closing,
# the stop, two plugin observers of one event, a rule-breaking observer. No
# game data.
#   cmake --build <build> --target bo3_bm_events_test && ctest -R bo3_bm_events
add_executable(bo3_bm_events_test test_main.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_events.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_events_service.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_autopilot.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_boost.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/ai_takeover.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/race_service.c)
target_include_directories(bo3_bm_events_test PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game
    ${CMAKE_CURRENT_LIST_DIR}/../../include)
target_include_directories(bo3_bm_events_test SYSTEM PRIVATE
    ${XBOXRECOMP_DIR}/templates/runtime
    ${XBOXRECOMP_DIR}/src
    ${XBOXRECOMP_DIR}/src/kernel)
if(NOT WIN32)
    target_link_libraries(bo3_bm_events_test PRIVATE m)
endif()
enable_testing()
add_test(NAME bo3_bm_events COMMAND bo3_bm_events_test)
