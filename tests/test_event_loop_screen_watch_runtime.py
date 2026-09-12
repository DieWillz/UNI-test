def test_screen_watch_runtime_has_time_module_available():
    import uni.event_loop as event_loop

    assert hasattr(event_loop, "time"), (
        "screen-watch appends observations with time.time(); the module must import time"
    )
