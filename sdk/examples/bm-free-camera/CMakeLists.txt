# main21 (next SDK) example (bm-free-camera). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_free_camera LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_free_camera
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_free_camera.c
    MOD_DIR bm-free-camera
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
