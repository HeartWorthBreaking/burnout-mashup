# bmashup-sdk example (l): bmashup.traffic 1 - one source, two mods: half traffic, and a probe that changes nothing.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_traffic LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_gp_traffic_half
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_gp_traffic.c
    DEFINES GP_DENSITY=0.5
    MOD_DIR bmashup-sdk-traffic-half
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/half/mod.toml)
set_target_properties(bm_gp_traffic_half PROPERTIES OUTPUT_NAME bm_gp_traffic)
bmsdk_add_plugin(bm_gp_traffic_probe
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_gp_traffic.c
    DEFINES GP_DENSITY=-1.0
    MOD_DIR bmashup-sdk-traffic-probe
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/probe/mod.toml)
set_target_properties(bm_gp_traffic_probe PROPERTIES OUTPUT_NAME bm_gp_traffic)
