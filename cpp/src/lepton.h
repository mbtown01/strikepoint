#pragma once

#include <queue>
#include <string>
#include <time.h>
#include <vector>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>

#include "LEPTON_Types.h"
#include "driver.h"
#include "logging.h"

namespace strikepoint {

class LeptonDriver {

  public:
    typedef struct {
        uint64_t t_ns;             // CLOCK_MONOTONIC timestamp
        std::vector<float> buffer; // pointer to frame buffer
        uint32_t event_id;          // increments each frame
    } frameInfo;

  public:
    LeptonDriver(strikepoint::Logger &logger,
                 SPLIB_TemperatureUnit temp_unit,
                 const char *log_file_path);

    ~LeptonDriver();

    void getDriverInfo(SPLIB_DriverInfo *info);

    void startPolling();

    void shutdown();

    void cameraDisable();

    void cameraEnable();

    void getFrame(frameInfo &frame_info);

  private:
    static void _spiPollingThreadMain(LeptonDriver *self);

    void _driverMain();

  private:
    LEP_CAMERA_PORT_DESC_T _port_desc;
    std::thread _thread;
    std::mutex _frame_mutex;
    std::condition_variable _frame_cond;
    std::atomic<bool> _has_frame;
    std::atomic<bool> _shutdown_requested;
    std::atomic<bool> _isRunning;
    strikepoint::Logger &_logger;
    SPLIB_TemperatureUnit _temp_unit;
    frameInfo _frame_info;
    int _spi_fd;
};

} // namespace strikepoint