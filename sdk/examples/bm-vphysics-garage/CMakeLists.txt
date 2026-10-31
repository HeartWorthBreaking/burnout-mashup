# bmashup-sdk 0.6.0 example (bm-vphysics-garage). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_vphysics_garage LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_vphysics_garage
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_vphysics_garage.c
    MOD_DIR bm-vphysics-garage
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)