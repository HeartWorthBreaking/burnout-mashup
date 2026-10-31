# bmashup-sdk example (m): bmashup.ai 1 - one source, two mods: slower rivals (pace 0.8) and a probe that changes nothing.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_ai LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_gp_ai_slow
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_gp_ai.c
    DEFINES GP_PACE=0.8
    MOD_DIR bmashup-sdk-ai-slow
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/slow/mod.toml)
set_target_properties(bm_gp_ai_slow PROPERTIES OUTPUT_NAME bm_gp_ai)
bmsdk_add_plugin(bm_gp_ai_probe
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_gp_ai.c
    DEFINES GP_PACE=-1.0
    MOD_DIR bmashup-sdk-ai-probe
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/probe/mod.toml)
set_target_properties(bm_gp_ai_probe PROPERTIES OUTPUT_NAME bm_gp_ai)
