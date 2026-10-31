# bmashup-sdk example (n): bmashup.events 6 CRASH_RESULT + bmashup.crash 1 - logs every Crash result, keeps the session best.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_crash_scores LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_crash_scores
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_crash_scores.c
    MOD_DIR bmashup-sdk-crash-scores
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
