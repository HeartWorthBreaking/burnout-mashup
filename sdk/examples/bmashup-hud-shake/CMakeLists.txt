# bmashup-sdk 0.6.0 example (bmashup-hud-shake). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_hud_shake LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_hud_shake
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_hud_shake.c
    MOD_DIR bmashup-hud-shake
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)