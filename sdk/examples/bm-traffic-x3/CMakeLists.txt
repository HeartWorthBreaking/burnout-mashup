# bmashup-sdk 0.6.0 example (bm-traffic-x3). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_traffic_x3 LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_traffic_x3
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_traffic_x3.c
    MOD_DIR bm-traffic-x3
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)