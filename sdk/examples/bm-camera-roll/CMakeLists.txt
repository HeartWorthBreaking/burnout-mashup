# bmashup-sdk 0.6.0 example (bm-camera-roll). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_camera_roll LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_camera_roll
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_camera_roll.c
    MOD_DIR bm-camera-roll
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)