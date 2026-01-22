#include <cstring>
#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <linux/types.h>
#include <memory.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdexcept>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include "LEPTON_AGC.h"
#include "LEPTON_ErrorCodes.h"
#include "LEPTON_OEM.h"
#include "LEPTON_RAD.h"
#include "LEPTON_SDK.h"
#include "LEPTON_SYS.h"
#include "LEPTON_Types.h"
#include "LEPTON_VID.h"
#include "crc16.h"
#include "error.h"
#include "lepton.h"

#include <stdexcept>
#include <string>
#include <utility>

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60
#define PACKET_SIZE (4 + 2 * FRAME_WIDTH)
#define PACKETS_PER_FRAME FRAME_HEIGHT
#define LOG_MAX_MESSAGE_LENGTH 4096
#define SPLIB_VERSION_MAJOR 2
#define SPLIB_VERSION_MINOR 0

#define BAIL_ON_FAILED_LEP(cmd)                                  \
    do {                                                         \
        LEP_RESULT rtn = cmd;                                    \
        if (rtn != LEP_OK)                                       \
            BAIL("'%s' returned LEP_RESULT code %d", #cmd, rtn); \
    } while (0)

#define BAIL_ON_FAILED_ERRNO(cmd)                                     \
    do {                                                              \
        int rtn = cmd;                                                \
        if (rtn < 0)                                                  \
            BAIL("'%s' returned %d: %s", #cmd, rtn, strerror(errno)); \
    } while (0)

#define BAIL_ON_FAILED(cmd)                      \
    do {                                         \
        int rtn = cmd;                           \
        if (rtn < 0)                             \
            BAIL("'%s' returned %d", #cmd, rtn); \
    } while (0)

/*********************************************************************
 * LeptonDriver - constructor for the Lepton driver
 *********************************************************************/
strikepoint::LeptonDriver::LeptonDriver(strikepoint::Logger &logger,
                                        const char *logFilePath) :
    _logger(logger),
    spiFd(0),
    tempUnit(SPLIB_TEMP_UNITS_FAHRENHEIT),
    hasFrame(false),
    shutdownRequested(false),
    isRunning(false),
    threadRtn(0)
{
    BAIL_ON_FAILED_ERRNO(pthread_mutex_init(&frameMutex, NULL));
    BAIL_ON_FAILED_ERRNO(pthread_cond_init(&frameCond, NULL));
    _frameBuffer.resize(FRAME_WIDTH * FRAME_HEIGHT);

#ifdef DEBUG
    LOG_INFO(_logger, "Lepton driver v%d.%d DEBUG initializing...",
             SPLIB_VERSION_MAJOR, SPLIB_VERSION_MINOR);
#else
    LOG_INFO(_logger, "Lepton driver v%d.%d RELEASE initializing...",
             SPLIB_VERSION_MAJOR, SPLIB_VERSION_MINOR);
#endif

    LEP_STATUS_T statusDesc;
    unsigned char spiMode = SPI_MODE_3;
    unsigned char spiBitsPerWord = 8;
    unsigned int spiSpeed = 10000000;

    LOG_INFO(_logger, "Configuring /def/spidev0.0: mode=%d, bitsPerWord=%d, speed=%d Hz",
             spiMode, spiBitsPerWord, spiSpeed);
    spiFd = open("/dev/spidev0.0", O_RDWR);
    if (spiFd < 0)
        BAIL("Could not open SPI device");
    BAIL_ON_FAILED_ERRNO(
        ioctl(spiFd, SPI_IOC_WR_MODE, &spiMode));
    BAIL_ON_FAILED_ERRNO(
        ioctl(spiFd, SPI_IOC_RD_MODE, &spiMode));
    BAIL_ON_FAILED_ERRNO(
        ioctl(spiFd, SPI_IOC_WR_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_ERRNO(
        ioctl(spiFd, SPI_IOC_RD_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_ERRNO(
        ioctl(spiFd, SPI_IOC_WR_MAX_SPEED_HZ, &spiSpeed));
    BAIL_ON_FAILED_ERRNO(
        ioctl(spiFd, SPI_IOC_RD_MAX_SPEED_HZ, &spiSpeed));

    // Initialize and open the camera port (example values)
    LOG_INFO(_logger, "Configuring camera port");
    _portDesc.portType = LEP_CCI_TWI;
    _portDesc.portID = 99;
    _portDesc.deviceAddress = 0x2A;               // Example I2C address
    _portDesc.portBaudRate = (LEP_UINT16) 400000; // 400 kHz
    BAIL_ON_FAILED_LEP(LEP_OpenPort(1, LEP_CCI_TWI, 400, &_portDesc));

    BAIL_ON_FAILED_LEP(LEP_SetAgcEnableState(&_portDesc, LEP_AGC_DISABLE));
    BAIL_ON_FAILED_LEP(LEP_SetRadEnableState(&_portDesc, LEP_RAD_ENABLE));

    LEP_SYS_FFC_SHUTTER_MODE_OBJ_T ffcMode;
    ffcMode.shutterMode = LEP_SYS_FFC_SHUTTER_MODE_MANUAL;
    ffcMode.tempLockoutState = LEP_SYS_SHUTTER_LOCKOUT_INACTIVE;
    ffcMode.videoFreezeDuringFFC = LEP_SYS_DISABLE;
    ffcMode.ffcDesired = LEP_SYS_ENABLE;
    ffcMode.elapsedTimeSinceLastFfc = 0;
    ffcMode.desiredFfcPeriod = 60000; // 60 seconds
    ffcMode.explicitCmdToOpen = false;
    ffcMode.desiredFfcTempDelta = 0;
    ffcMode.imminentDelay = 0;
    BAIL_ON_FAILED_LEP(LEP_SetSysFfcShutterModeObj(&_portDesc, ffcMode));
    usleep(200000); // Wait for a second to allow FFC to complete

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&_portDesc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&_portDesc, LEP_VIDEO_OUTPUT_ENABLE));

    // Show status some known interesting settings
    LEP_SYS_FLIR_SERIAL_NUMBER_T serialNumber;
    BAIL_ON_FAILED_LEP(LEP_GetSysFlirSerialNumber(&_portDesc, &serialNumber));
    LOG_INFO(_logger, "STARTUP Camera Serial Number: %llu", (unsigned long long) serialNumber);

    LEP_SYS_UPTIME_NUMBER_T upTime;
    BAIL_ON_FAILED_LEP(LEP_GetSysCameraUpTime(&_portDesc, &upTime));
    LOG_INFO(_logger, "STARTUP Camera Uptime: %u seconds", (unsigned int) (upTime));

    LEP_SYS_AUX_TEMPERATURE_CELCIUS_T auxTemp;
    LEP_GetSysAuxTemperatureCelcius(&_portDesc, &auxTemp);
    LOG_INFO(_logger, "STARTUP aux temperature: %.2f F", auxTemp * 9.0f / 5.0f + 32.0f);

    LEP_SYS_FPA_TEMPERATURE_CELCIUS_T fpaTemp;
    BAIL_ON_FAILED_LEP(LEP_GetSysFpaTemperatureCelcius(&_portDesc, &fpaTemp));
    LOG_INFO(_logger, "STARTUP FPA Temperature: %.2f F", fpaTemp * 9.0f / 5.0f + 32.0f);

    LEP_RAD_ENABLE_E radState;
    LEP_GetRadEnableState(&_portDesc, &radState);
    LOG_INFO(_logger, "STARTUP Radiometry enabled: %d", radState);

    LEP_AGC_ENABLE_E agcState;
    LEP_GetAgcEnableState(&_portDesc, &agcState);
    LOG_INFO(_logger, "STARTUP AGC enabled: %d", agcState);

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_portDesc, &statusDesc));
    LOG_INFO(_logger, "STARTUP Camera status: %d", statusDesc.camStatus);
}

/*********************************************************************
 * LeptonDriver - constructor for the Lepton driver
 *********************************************************************/
strikepoint::LeptonDriver::~LeptonDriver()
{
    BAIL_ON_FAILED_ERRNO(pthread_mutex_destroy(&frameMutex));
    BAIL_ON_FAILED_ERRNO(pthread_cond_destroy(&frameCond));

    BAIL_ON_FAILED_ERRNO(close(spiFd));
    BAIL_ON_FAILED_LEP(LEP_ClosePort(&_portDesc));
}

/*********************************************************************
 * shutdown - shutdown the Lepton driver and camera
 *********************************************************************/
void
strikepoint::LeptonDriver::shutdown()
{
    LOG_DEBUG(_logger, "Driver shutdown requested, waiting for capture thread");
    void *rtnval = NULL;
    shutdownRequested = true;
    BAIL_ON_FAILED_ERRNO(pthread_join(_thread, &rtnval));

    if (isRunning)
        LOG_ERROR(_logger, "shutdown() called but session is still running");
    if (threadRtn)
        LOG_ERROR(_logger, "SPI polling thread rtn=%d", threadRtn);

    LOG_DEBUG(_logger, "Driver shutdown complete");
}

/*********************************************************************
 * getDriverInfo - retrieve information about the driver
 *********************************************************************/
void
strikepoint::LeptonDriver::getDriverInfo(SPLIB_DriverInfo *info)
{
    if (info == NULL)
        throw std::invalid_argument("info pointer is NULL");

    info->versionMajor = SPLIB_VERSION_MAJOR;
    info->versionMinor = SPLIB_VERSION_MINOR;
    info->frameWidth = FRAME_WIDTH;
    info->frameHeight = FRAME_HEIGHT;
}

/*********************************************************************
 * startPolling - start the SPI polling thread
 *********************************************************************/
void
strikepoint::LeptonDriver::startPolling()
{
    if (isRunning)
        BAIL("Attempt to start already running polling thread");

    // Kickoff the driver thread
    LOG_INFO(_logger, "Starting frame capture thread");
    BAIL_ON_FAILED_ERRNO(pthread_create(
        &_thread, NULL, _spiPollingThreadMain, (void *) this));

    // Give the pthread 5 seconds to start up
    for (int i = 0; i < 5000 && !isRunning; i++)
        usleep(1000);
    if (!isRunning)
        BAIL("Somehow the polling thread never started");
}

/*********************************************************************
 * cameraDisable - disable the camera
 *********************************************************************/
void
strikepoint::LeptonDriver::cameraDisable()
{
    LOG_DEBUG(_logger, "SPLIB_LeptonDisable() START");
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_portDesc, &statusDesc));
    LOG_DEBUG(_logger, "Camera status before disable: %d", statusDesc.camStatus);

    do {
        rtn = LEP_RunOemPowerDown(&_portDesc);
        LOG_DEBUG(_logger, "Power down command sent, rtn=%d", rtn);
        usleep(250000);
    } while (rtn != LEP_OK);

    do {
        rtn = LEP_GetSysStatus(&_portDesc, &statusDesc);
        LOG_DEBUG(_logger, "Camera status test disable: %d, rtn=%d",
                  statusDesc.camStatus, rtn);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

    LOG_DEBUG(_logger, "SPLIB_LeptonDisable() COMPLETE");
}

/*********************************************************************
 * cameraEnable - enable the camera
 *********************************************************************/
void
strikepoint::LeptonDriver::cameraEnable()
{
    LOG_DEBUG(_logger, "SPLIB_LeptonEnable() START");
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_portDesc, &statusDesc));
    LOG_DEBUG(_logger, "Camera status before enable: %d", statusDesc.camStatus);

    do {
        rtn = LEP_RunOemPowerOn(&_portDesc);
        LOG_DEBUG(_logger, "Power on command sent, rtn=%d", rtn);
        usleep(250000);
    } while (rtn != LEP_OK);

    usleep(1000000);

    do {
        rtn = LEP_GetSysStatus(&_portDesc, &statusDesc);
        LOG_DEBUG(_logger, "Camera status test disable: %d, rtn=%d",
                  statusDesc.camStatus, rtn);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&_portDesc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&_portDesc, LEP_VIDEO_OUTPUT_ENABLE));

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_portDesc, &statusDesc));
    LOG_DEBUG(_logger, "STARTUP Camera status: %d", statusDesc.camStatus);

    while (statusDesc.camStatus != LEP_SYSTEM_FLAT_FIELD_IN_PROCESS) {
        usleep(250000);
        BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_portDesc, &statusDesc));
        LOG_DEBUG(_logger, "Camera status waiting for FFC: %d", statusDesc.camStatus);
    }

    LOG_DEBUG(_logger, "SPLIB_LeptonEnable() COMPLETE");
}

/*********************************************************************
 * setTemperatureUnits - set the temperature units for returned frames
 *********************************************************************/
void
strikepoint::LeptonDriver::setTemperatureUnits(SPLIB_TemperatureUnit unit)
{
    if (unit < 0 || unit >= SPLIB_TEMP_UNITS_MAX)
        BAIL("Invalid temperature unit %d", unit);
    const char *unitNames[] = {"Kelvin", "Celsius", "Fahrenheit"};

    LOG_DEBUG(_logger, "Setting temperature units to %s", unitNames[unit]);
    tempUnit = unit;
}

/*********************************************************************
 * getFrame - capture a single frame from the Lepton camera
 *
 * The Lepton v2.5 only generates frames at ~8.7 FPS, so this function
 * will block until a new frame is available from the camera.
 *********************************************************************/
void
strikepoint::LeptonDriver::getFrame(float *frameBuffer)
{
    if (!isRunning)
        BAIL("Frame requested but SPI polling thread not running");
    if (shutdownRequested)
        BAIL("SDK is shutting down");

    pthread_mutex_lock(&frameMutex);
    pthread_cond_wait(&frameCond, &frameMutex);
    if (hasFrame)
        memcpy(frameBuffer, &(_frameBuffer[0]),
               sizeof(float) * FRAME_HEIGHT * FRAME_WIDTH);
    hasFrame = false;
    pthread_mutex_unlock(&frameMutex);

    if (threadRtn)
        BAIL("Call to SPLIB_LeptonGetFrame failed, polling thread exited abonrmally");
}

/*********************************************************************
 * _safeRead - read exactly len bytes from fd into buf
 *********************************************************************/
int
_safeRead(int fd, void *buf, size_t len)
{
    size_t totalRead = 0;
    while (totalRead < len) {
        ssize_t bytesRead =
            read(fd, (uint8_t *) buf + totalRead, len - totalRead);
        if (bytesRead < 0)
            BAIL("read failed, error=%s", strerror(errno));
        totalRead += bytesRead;
    }

    return totalRead;
}

/*********************************************************************
 * _spiPollingThreadMain - pthread entry point
 *********************************************************************/
void *
strikepoint::LeptonDriver::_spiPollingThreadMain(void *arg)
{
    LeptonDriver *driver = static_cast<LeptonDriver *>(arg);
    bool threwException = true;

    try {
        driver->isRunning = true;
        driver->_driverMain();
        threwException = false;
    } catch (const strikepoint::bail_error &e) {
        driver->_logger.log(
            e.file().c_str(), e.line(), LOG_LEVEL_ERROR, e.what());
    } catch (const std::exception &e) {
        driver->_logger.log(
            __FILE__, __LINE__, LOG_LEVEL_ERROR, e.what());
    }

    if (threwException) {
        pthread_mutex_lock(&driver->frameMutex);
        driver->hasFrame = false;
        pthread_cond_signal(&driver->frameCond);
        pthread_mutex_unlock(&driver->frameMutex);
    }

    driver->isRunning = false;
    return NULL;
}

/*********************************************************************
 * _driverMain - Driver logic main loop
 *********************************************************************/
void
strikepoint::LeptonDriver::_driverMain()
{
    uint8_t buff[PACKETS_PER_FRAME][PACKET_SIZE];
    const int maxFailedAttempts = 30;
    const int pixelsPerFrame = FRAME_WIDTH * FRAME_HEIGHT;
    int failedAttempsRemaining = maxFailedAttempts;
    int matchingCrcCount = 0;
    ssize_t bytesRead;
    CRC16 lastCrc = 0;

    while (shutdownRequested == false && failedAttempsRemaining > 0) {
        // Read from SPI until we see the start of a frame
        int tries = 100;
        _safeRead(spiFd, buff[0], PACKET_SIZE);
        while ((buff[0][0] & 0x0F) != 0 && buff[0][1] != 0 && tries-- > 0) {
            usleep(10000);
            _safeRead(spiFd, buff[0], PACKET_SIZE);
        }
        if (tries == 0)
            continue;

        // After seeing the start of a frame, read the rest of the packets
        int goodPackets = 1;
        for (int p = 1; p < PACKETS_PER_FRAME; p++, goodPackets++) {
            _safeRead(spiFd, buff[p], PACKET_SIZE);
            if ((buff[p][0] & 0x0F) != 0 || buff[p][1] != p)
                break;
        }

        // If we didn't see all the packetes in the frame, reboot the camera
        if (goodPackets != PACKETS_PER_FRAME) {
            LOG_WARNING(_logger, "Bad frame received (%d/%d), rebooting camera",
                        goodPackets, PACKETS_PER_FRAME);
            cameraDisable();
            cameraEnable();
            failedAttempsRemaining--;
            continue;
        }

        // Updated the shared frame buffer and signal any waiters
        float localBuffer[pixelsPerFrame];
        for (int i = 0; i < pixelsPerFrame; i++) {
            int r = i / FRAME_WIDTH, c = i % FRAME_WIDTH;
            uint16_t v = (buff[r][4 + 2 * c] << 8) + buff[r][4 + 2 * c + 1];
            float k = (float) v * 0.01f;
            if (tempUnit == SPLIB_TEMP_UNITS_CELCIUS)
                k = k - 273.15f;
            else if (tempUnit == SPLIB_TEMP_UNITS_FAHRENHEIT)
                k = ((k - 273.15f) * 9.0f / 5.0f) + 32.0f;
            localBuffer[i] = k;
        }

        // Only wake up a getFrame caller if this frame is unique
        CRC16 crc = CalcCRC16Bytes(sizeof(localBuffer), (char *) localBuffer);
        if (lastCrc != crc) {
            pthread_mutex_lock(&frameMutex);
            memcpy(&_frameBuffer[0], localBuffer, sizeof(localBuffer));
            hasFrame = true;
            pthread_cond_signal(&frameCond);
            pthread_mutex_unlock(&frameMutex);
            lastCrc = crc;
            matchingCrcCount = 0;
            failedAttempsRemaining = maxFailedAttempts;
        }

        // Every now and then, we see the camera start to return the same
        // frame over and over again.  If we see that happening for roughly
        // a full second, reboot the camera
        if (matchingCrcCount++ > 27) {
            LOG_WARNING(_logger, "Stale frames detected, rebooting camera");
            cameraDisable();
            cameraEnable();
            matchingCrcCount = 0;
            failedAttempsRemaining--;
            continue;
        }
    }

    if (failedAttempsRemaining == 0)
        BAIL("Too many consecutive frame capture failures, exiting");

    LOG_DEBUG(_logger, "Driver thread exiting");
}
