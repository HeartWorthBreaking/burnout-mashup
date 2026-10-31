# main21 (next SDK) example (bm-ai-names). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_ai_names LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_ai_names
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_ai_names.c
    MOD_DIR bm-ai-names
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
