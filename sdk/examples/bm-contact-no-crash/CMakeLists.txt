# bmashup-sdk 0.6.0 example (bm-contact-no-crash). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_contact_no_crash LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_contact_no_crash
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_contact_no_crash.c
    MOD_DIR bm-contact-no-crash
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)