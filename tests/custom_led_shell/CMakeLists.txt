# SPDX-License-Identifier: Apache-2.0
# Builds the student's driver module from app/modules/, as the course's app does.
cmake_minimum_required(VERSION 3.20.0)

list(APPEND ZEPHYR_EXTRA_MODULES ${CMAKE_CURRENT_LIST_DIR}/../../app/modules)
list(APPEND DTS_ROOT ${CMAKE_CURRENT_LIST_DIR}/../../app/modules)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(custom_led_shell_test)

target_sources(app PRIVATE src/test_task1.c)
# task2 scenarios add the extension API / set command tests (testcase.yaml: TEST_TASK2=1)
if(TEST_TASK2)
  target_sources(app PRIVATE src/test_task2.c)
endif()
