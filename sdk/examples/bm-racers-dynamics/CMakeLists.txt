# bmashup-sdk 0.6.0 example (bm-racers-dynamics). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_racers_dynamics LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_racers_dynamics
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_racers_dynamics.c
    MOD_DIR bm-racers-dynamics
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)