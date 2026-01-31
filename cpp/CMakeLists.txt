cmake_minimum_required(VERSION 3.14)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_C_FLAGS "-fno-omit-frame-pointer")
set(CMAKE_CXX_FLAGS "-fno-omit-frame-pointer")
set(CMAKE_C_FLAGS_DEBUG "${CMAKE_C_FLAGS} -g -O0 -DDEBUG=1")
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS} -g -O0 -DDEBUG=1")
set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS} -O3")
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS} -O3")
set(CMAKE_EXE_LINKER_FLAGS_DEBUG "-g")
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

project(strikepoint C CXX)

# Common include dir for the C driver headers
set(LEPTON_DIR ${CMAKE_SOURCE_DIR})
include_directories(${LEPTON_DIR}/sdk)
include_directories(${LEPTON_DIR}/src)

# Convert glob to actual source list (only .c/.cpp files)
file(GLOB LEPTON_SRCS "${LEPTON_DIR}/sdk/*.c"
                      "${LEPTON_DIR}/src/*.c"
                      "${LEPTON_DIR}/src/*.cpp") 

add_library(strikepoint_objs OBJECT ${LEPTON_SRCS})
set_target_properties(strikepoint_objs PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Optionally set include dirs for the object target
target_include_directories(strikepoint_objs PRIVATE ${LEPTON_DIR})

# Define DEBUG only for Debug builds. Use generator-expression so the define
# is added when CONFIG is Debug and not for Release/RelWithDebInfo/etc.
target_compile_definitions(
    strikepoint_objs PRIVATE $<$<CONFIG:Debug>:DEBUG=1>)

add_library(strikepoint_driver_static STATIC $<TARGET_OBJECTS:strikepoint_objs>)
add_library(strikepoint_driver SHARED $<TARGET_OBJECTS:strikepoint_objs>)

# Position independent for shared lib
set_target_properties(strikepoint_driver_static PROPERTIES OUTPUT_NAME strikepoint)
set_target_properties(strikepoint_driver PROPERTIES OUTPUT_NAME strikepoint)

# Link standard libs commonly used by the driver
find_package(Threads REQUIRED)
target_link_libraries(strikepoint_driver_static PRIVATE Threads::Threads m dl asound sndfile)
target_link_libraries(strikepoint_driver PRIVATE 
    Threads::Threads m dl asound sndfile liquid)

# Optional: build a capture executable if the source exists
if(EXISTS "${LEPTON_DIR}/utils/capture.c")
    add_executable(capture "${LEPTON_DIR}/utils/capture.c")
    target_include_directories(capture PRIVATE ${LEPTON_DIR})
    target_link_libraries(capture PRIVATE strikepoint_driver_static 
        Threads::Threads m dl asound liquid sndfile)
endif()

# GoogleTest-based tests (optional)
find_package(GTest QUIET)
if(GTest_FOUND)
    enable_testing()
    file(GLOB LEPTON_TEST_SRCS "${LEPTON_DIR}/test/*.cpp") 
    add_executable(gtest_driver ${LEPTON_TEST_SRCS})
    target_include_directories(gtest_driver PRIVATE ${LEPTON_DIR})
    target_link_libraries(gtest_driver PRIVATE GTest::gtest_main strikepoint_driver_static 
        asound Threads::Threads m dl liquid sndfile)
    add_test(NAME gtest_driver COMMAND gtest_driver)
endif()

# CTest convenience target
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# install rules (optional)
install(TARGETS strikepoint_driver strikepoint_driver_static
        RUNTIME DESTINATION bin
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib)

