cmake_minimum_required(VERSION 3.22)
project(pyxpo_jni C)

# PYXPO_DIST/<abi> comes from native/android/build_cpython.py (include/python3.13, lib/libpython3.13.so)
set(PY_PREFIX "${PYXPO_DIST}/${ANDROID_ABI}/prefix")
add_library(python3.13 SHARED IMPORTED)
set_target_properties(python3.13 PROPERTIES IMPORTED_LOCATION "${PY_PREFIX}/lib/libpython3.13.so")

add_library(pyxpo_jni SHARED pyxpo_jni.c "${PYXPO_NATIVE_COMMON}/pyxpo_bridge.c")
target_include_directories(pyxpo_jni PRIVATE "${PY_PREFIX}/include/python3.13" "${PYXPO_NATIVE_COMMON}")
target_link_libraries(pyxpo_jni python3.13 log)
target_link_options(pyxpo_jni PRIVATE -Wl,-z,max-page-size=16384)
