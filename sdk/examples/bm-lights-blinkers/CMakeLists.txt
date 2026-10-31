# bmashup-sdk 0.6.0 example (bm-lights-blinkers). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_lights_blinkers LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_lights_blinkers
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_lights_blinkers.c
    MOD_DIR bm-lights-blinkers
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)