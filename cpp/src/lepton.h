#pragma once

#include <atomic>
#include <condition_variable>
#include <map>
#include <mutex>
#include <string>
#include <thread>

#include "LEPTON_Types.h"
#include "driver.h"
#include "logging.h"
#include "timer.h"

namespace strikepoint {

class LeptonDriver {

  public:
    typedef struct {
        uint64_t t_ns;             // CLOCK_MONOTONIC timestamp
        uint32_t frame_seq;        // increments each frame
        std::vector<float> buffer; // pointer to frame buffer (in degF)
    } frameInfo;

    DECLARE_SPECIALIZED_BAIL_ERROR(eof_error);
    
    class ILeptonImpl {
      public:
        virtual ~ILeptonImpl() = default;
        virtual void reboot_camera() = 0;
        virtual void spi_read(void *buf, size_t len) = 0;
    };

  public:
    LeptonDriver(strikepoint::Logger &logger, ILeptonImpl &impl);
    ~LeptonDriver();

    void get_driver_info(SPLIB_DriverInfo *info);
    void get_frame(frameInfo &frame_info);

  private:
    void _driver_main();

  private:
    std::thread _thread;
    std::mutex _frame_mutex;
    std::condition_variable _frame_cond;
    std::atomic<bool> _has_frame;
    std::atomic<bool> _is_running;
    std::atomic<bool> _shutdown_requested;
    std::map<std::string, Timer> _timers;
    strikepoint::Logger &_logger;
    frameInfo _frame_info;
    ILeptonImpl &_impl;
};

} // namespace strikepoint