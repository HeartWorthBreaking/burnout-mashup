# bmashup-sdk 0.6.0 example (bm-finish-camera). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_finish_camera LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_finish_camera
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_finish_camera.c
    MOD_DIR bm-finish-camera
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)