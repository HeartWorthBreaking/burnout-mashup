# bmashup-sdk example (o): bmashup.settings 1 + bmashup.camera 1 - a CAMERA FOV setting (MOD SETTINGS) for the race camera.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_camera_fov LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_gp_camera_fov
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_gp_camera_fov.c
    MOD_DIR bmashup-sdk-camera-fov
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
