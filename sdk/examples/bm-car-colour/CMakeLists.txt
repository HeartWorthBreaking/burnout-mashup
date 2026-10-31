# bmashup-sdk 0.6.0 example (bm-car-colour). Part of the SDK's build, or on its own (BUILD.md).
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_car_colour LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_plugin(bm_car_colour
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_car_colour.c
    MOD_DIR bm-car-colour
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)