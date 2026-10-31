# bmashup-sdk example (bm-headlights). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_headlights LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_headlights
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_headlights.c
    MOD_DIR bm-headlights
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
