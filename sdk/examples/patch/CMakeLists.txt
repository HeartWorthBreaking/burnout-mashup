# bmashup-sdk example (g): a published-site patch. Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_patch_demo LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_sdk_patch_demo
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_patch_demo.c
    MOD_DIR bmashup-sdk-patch-demo
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
