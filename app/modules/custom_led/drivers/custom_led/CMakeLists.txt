zephyr_library()
zephyr_library_sources(custom_led.c)
zephyr_library_sources_ifdef(CONFIG_CUSTOM_LED_SHELL custom_led_shell.c)
zephyr_include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../../include)
