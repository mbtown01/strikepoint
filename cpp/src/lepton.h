#ifndef __LEPTON_H__
#define __LEPTON_H__

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
                     const char *logFilePath);

        ~LeptonDriver();

        void getDriverInfo(SPLIB_DriverInfo *info);

        void startPolling();

        void shutdown();

        void cameraDisable();

        void cameraEnable();

        void setTemperatureUnits(SPLIB_TemperatureUnit unit);

        void getFrame(float *frameBuffer);

    private:
        static void *_spiPollingThreadMain(void *arg);

        void _driverMain();

    private:
        LEP_CAMERA_PORT_DESC_T _portDesc;
        pthread_t _thread;
        pthread_mutex_t frameMutex;
        pthread_cond_t frameCond;
        int spiFd;

        std::vector<float> _frameBuffer;
        strikepoint::Logger &_logger;
        SPLIB_TemperatureUnit tempUnit;
        bool hasFrame, shutdownRequested, isRunning;
        int threadRtn;
};

} // namespace strikepoint

#endif // __LEPTON_H__