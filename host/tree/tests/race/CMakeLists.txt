# race - the plugins' "takedawn.race" service (src/game/race_service.c,
# include/takedawn_race.h) against a stand-in for the game's memory: every
# state and field, the speed, the copies bounded by the caller's size,
# on_update and a reader on another thread. No game data.
#   cmake --build <build> --target bo3_race_test && ctest -R bo3_race
add_executable(bo3_race_test test_main.c ${CMAKE_CURRENT_LIST_DIR}/../../src/game/race_service.c)
target_include_directories(bo3_race_test PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../../src/game
    ${CMAKE_CURRENT_LIST_DIR}/../../include)
if(NOT WIN32)
    find_package(Threads REQUIRED)
    target_link_libraries(bo3_race_test PRIVATE Threads::Threads m)
endif()
enable_testing()
add_test(NAME bo3_race COMMAND bo3_race_test)
