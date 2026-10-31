# bmashup-sdk 0.6.0 example (bm-takedown-pitch). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_takedown_pitch LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_takedown_pitch
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_takedown_pitch.c
    MOD_DIR bm-takedown-pitch
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)