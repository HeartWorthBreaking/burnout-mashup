# bm_boost - Burnout Mashup's private "bmashup.boost" service (src/game/bm_boost.c,
# through bm_autopilot.c's car-update handler, over race_service.c) against a
# stand-in for the game's memory and a stand-in of the game's add-boost
# routine: each refusal, the staged request, the call in the car update with
# every register put back, the cap, requests that must not survive, both
# services in one car update, another thread. No game data.
#   cmake --build <build> --target bo3_bm_boost_test && ctest -R bo3_bm_boost
add_executable(bo3_bm_boost_test test_main.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_boost.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_autopilot.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/bm_events.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/ai_takeover.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game/race_service.c)
target_include_directories(bo3_bm_boost_test PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game
    ${CMAKE_CURRENT_LIST_DIR}/../../include)
target_include_directories(bo3_bm_boost_test SYSTEM PRIVATE
    ${XBOXRECOMP_DIR}/templates/runtime
    ${XBOXRECOMP_DIR}/src
    ${XBOXRECOMP_DIR}/src/kernel)
if(NOT WIN32)
    find_package(Threads REQUIRED)
    target_link_libraries(bo3_bm_boost_test PRIVATE Threads::Threads m)
endif()
enable_testing()
add_test(NAME bo3_bm_boost COMMAND bo3_bm_boost_test)
