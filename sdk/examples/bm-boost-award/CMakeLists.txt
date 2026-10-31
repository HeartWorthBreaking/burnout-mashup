# bmashup-sdk 0.6.0 example (bm-boost-award). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_boost_award LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_boost_award
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_boost_award.c
    MOD_DIR bm-boost-award
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)