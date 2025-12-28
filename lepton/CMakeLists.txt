cmake_minimum_required(VERSION 3.14)
project(strikepoint C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_BUILD_TYPE Debug CACHE STRING "" FORCE)
set(CMAKE_C_FLAGS_DEBUG "-g -O0 -fno-omit-frame-pointer")
set(CMAKE_EXE_LINKER_FLAGS_DEBUG "-g")
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Common include dir for the C driver headers
set(LEPTON_DIR ${CMAKE_SOURCE_DIR})
include_directories(${LEPTON_DIR}/sdk)
include_directories(${LEPTON_DIR}/src)

# Convert glob to actual source list (only .c files)
file(GLOB LEPTON_SRCS "${LEPTON_DIR}/sdk/*.c" "${LEPTON_DIR}/src/*.c*") 

add_library(lepton_objs OBJECT ${LEPTON_SRCS})
set_target_properties(lepton_objs PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Optionally set include dirs for the object target
target_include_directories(lepton_objs PRIVATE ${LEPTON_DIR})

# Define DEBUG only for Debug builds. Use generator-expression so the define
# is added when CONFIG is Debug and not for Release/RelWithDebInfo/etc.
target_compile_definitions(
    lepton_objs PRIVATE $<$<CONFIG:Debug>:DEBUG=1>)

add_library(lepton_driver_static STATIC $<TARGET_OBJECTS:lepton_objs>)
add_library(lepton_driver SHARED $<TARGET_OBJECTS:lepton_objs>)

# Position independent for shared lib
set_target_properties(lepton_driver_static PROPERTIES OUTPUT_NAME lepton)
set_target_properties(lepton_driver PROPERTIES OUTPUT_NAME lepton)

# Link standard libs commonly used by the driver
find_package(Threads REQUIRED)
target_link_libraries(lepton_driver_static PRIVATE Threads::Threads m dl)
target_link_libraries(lepton_driver PRIVATE Threads::Threads m dl)

# Optional: build a capture executable if the source exists
if(EXISTS "${LEPTON_DIR}/utils/capture.c")
    add_executable(capture "${LEPTON_DIR}/utils/capture.c")
    target_include_directories(capture PRIVATE ${LEPTON_DIR})
    target_link_libraries(capture PRIVATE lepton_driver_static Threads::Threads m dl)
endif()

# GoogleTest-based tests (optional)
find_package(GTest QUIET)
if(GTest_FOUND)
    enable_testing()
    file(GLOB LEPTON_TEST_SRCS "${LEPTON_DIR}/test/*.cpp") 
    add_executable(gtest_driver ${LEPTON_TEST_SRCS})
    target_include_directories(gtest_driver PRIVATE ${LEPTON_DIR})
    target_link_libraries(gtest_driver PRIVATE GTest::gtest_main lepton_driver_static Threads::Threads m dl)
    add_test(NAME gtest_driver COMMAND gtest_driver)
endif()

# CTest convenience target
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# install rules (optional)
install(TARGETS lepton_driver lepton_driver_static
        RUNTIME DESTINATION bin
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib)

