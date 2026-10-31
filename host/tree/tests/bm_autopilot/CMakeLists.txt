# bm_autopilot - Burnout Mashup's private "bmashup.autopilot" service
# (src/game/bm_autopilot.c over ai_takeover.c and race_service.c) against a
# stand-in for the game's memory: each refusal, the staged request, the
# takeover in the car update, requests that must not survive, the end of the
# race without a hand-back, another thread. No game data.
#   cmake --build <build> --target bo3_bm_autopilot_test && ctest -R bo3_bm_autopilot
add_executable(bo3_bm_autopilot_test test_main.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_autopilot.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_boost.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_events.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/ai_takeover.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/race_service.c)
target_include_directories(bo3_bm_autopilot_test PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game
    ${CMAKE_CURRENT_LIST_DIR}/../../include)
target_include_directories(bo3_bm_autopilot_test SYSTEM PRIVATE
    ${XBOXRECOMP_DIR}/templates/runtime
    ${XBOXRECOMP_DIR}/src
    ${XBOXRECOMP_DIR}/src/kernel)
if(NOT WIN32)
    find_package(Threads REQUIRED)
    target_link_libraries(bo3_bm_autopilot_test PRIVATE Threads::Threads m)
endif()
enable_testing()
add_test(NAME bo3_bm_autopilot COMMAND bo3_bm_autopilot_test)
