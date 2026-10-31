# bmashup-sdk 0.6.0 example (bm-garage-stats). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_garage_stats LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_garage_stats
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_garage_stats.c
    MOD_DIR bm-garage-stats
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)