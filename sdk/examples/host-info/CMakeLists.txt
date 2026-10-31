# bmashup-sdk example (h): host-info probe. Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_host_info LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_sdk_host_info
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_host_info.c
    MOD_DIR bmashup-sdk-host-info
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
