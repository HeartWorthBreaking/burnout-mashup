# main21 (next SDK) example (bm-traffic-attack). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_traffic_attack LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_traffic_attack
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_traffic_attack.c
    MOD_DIR bm-traffic-attack
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
