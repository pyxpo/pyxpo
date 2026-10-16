# pyxpo_native.dll for the Windows shell: bridge + layout engine (shared with iOS/Android) + the Python host.
# Configure with the CPython 3.13 (x64) whose embeddable zip the shell ships:
#   cmake -S windows/native -B build/native -A x64 -DPython3_ROOT_DIR=<python 3.13>
#   cmake --build build/native --config Release
cmake_minimum_required(VERSION 3.20)
project(pyxpo_native C)

find_package(Python3 3.13 EXACT REQUIRED COMPONENTS Development.Embed)

set(COMMON ${CMAKE_CURRENT_SOURCE_DIR}/../../src/pyxpo/_native/common)
add_library(pyxpo_native SHARED
    pyxpo_host.c
    ${COMMON}/pyxpo_bridge.c
    ${COMMON}/pyxpo_layout.c
    pyxpo_native.def)
target_include_directories(pyxpo_native PRIVATE ${COMMON})
target_link_libraries(pyxpo_native PRIVATE Python3::Python)
target_compile_definitions(pyxpo_native PRIVATE _CRT_SECURE_NO_WARNINGS WIN32_LEAN_AND_MEAN)
if(MSVC)
    target_compile_options(pyxpo_native PRIVATE /W3 /utf-8)
    # Release CRT even in Debug builds: python313.dll is a release build.
    set_property(TARGET pyxpo_native PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
endif()
