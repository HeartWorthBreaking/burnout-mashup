# bmashup-sdk 0.6.0 example (bmashup-input-log). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_input_log LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_input_log
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_input_log.c
    MOD_DIR bmashup-input-log
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)