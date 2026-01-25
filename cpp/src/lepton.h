#pragma once

#include <pthread.h>
#include <queue>
#include <string>
#include <time.h>
#include <vector>

#include "LEPTON_Types.h"
#include "driver.h"
#include "logging.h"

namespace strikepoint {

class LeptonDriver {

  public:
    LeptonDriver(strikepoint::Logger &logger,
                 SPLIB_TemperatureUnit tempUnit,
                 const char *logFilePath);

    ~LeptonDriver();

    void getDriverInfo(SPLIB_DriverInfo *info);

    void startPolling();

    void shutdown();

    void cameraDisable();

    void cameraEnable();

    void getFrame(float *frameBuffer);

  private:
    static void *_spiPollingThreadMain(void *arg);

    void _driverMain();

  private:
    LEP_CAMERA_PORT_DESC_T _portDesc;
    pthread_t _thread;
    pthread_mutex_t _frameMutex;
    pthread_cond_t _frameCond;
    std::vector<float> _frameBuffer;
    strikepoint::Logger &_logger;
    SPLIB_TemperatureUnit _tempUnit;
    bool _hasFrame, _shutdownRequested, _isRunning;
    int _spiFd;
};

} // namespace strikepoint