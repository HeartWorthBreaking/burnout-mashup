# bmashup-sdk example (j): bmashup.autopilot 2 - the game's AI drives player 1 in every race (engage2), optional release.
# Build options: -DBMSDK_AUTOPILOT_DEFINES="BM_AP_DEMO_RELEASE_S=8" etc. (README.md). Part of the SDK's build, or on its own.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_autopilot_demo LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
set(BMSDK_AUTOPILOT_DEFINES "" CACHE STRING "compile definitions of the autopilot demo (BM_AP_DEMO_*)")
bmsdk_add_plugin(bm_autopilot_demo
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_autopilot_demo.c
    DEFINES ${BMSDK_AUTOPILOT_DEFINES}
    MOD_DIR bmashup-sdk-autopilot-demo
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
