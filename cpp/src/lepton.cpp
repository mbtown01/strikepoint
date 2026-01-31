#include <chrono>
#include <ctime>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <linux/types.h>
#include <memory.h>
#include <stdexcept>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include "LEPTON_AGC.h"
#include "LEPTON_ErrorCodes.h"
#include "LEPTON_OEM.h"
#include "LEPTON_RAD.h"
#include "LEPTON_SDK.h"
#include "LEPTON_SYS.h"
#include "error.h"
#include "lepton.h"

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

using namespace strikepoint;

class reboot_error : public bail_error {
  public:
    reboot_error(const char *file, int line, const char *format, ...) :
        bail_error(file, line, format)
    {
    }
};

#define REBOOT(fmt, ...) \
    throw reboot_error(__FILE__, __LINE__, fmt, ##__VA_ARGS__)

/*********************************************************************
 * LeptonDriver - constructor for the Lepton driver
 *********************************************************************/
LeptonDriver::LeptonDriver(Logger &logger,
                           SPLIB_TemperatureUnit temp_unit,
                           const char *log_file_path) :
    _logger(logger),
    _spi_fd(0),
    _temp_unit(temp_unit),
    _has_frame(false),
    _shutdown_requested(false),
    _isRunning(false)
{

    _frame_info.event_id = 0;
    _frame_info.buffer.resize(FRAME_WIDTH * FRAME_HEIGHT);

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
    _spi_fd = open("/dev/spidev0.0", O_RDWR);
    if (_spi_fd < 0)
        BAIL("Could not open SPI device");
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_WR_MODE, &spiMode));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_RD_MODE, &spiMode));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_WR_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_RD_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &spiSpeed));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_RD_MAX_SPEED_HZ, &spiSpeed));

    // Initialize and open the camera port (example values)
    LOG_INFO(_logger, "Configuring camera port");
    _port_desc.portType = LEP_CCI_TWI;
    _port_desc.portID = 99;
    _port_desc.deviceAddress = 0x2A;               // Example I2C address
    _port_desc.portBaudRate = (LEP_UINT16) 400000; // 400 kHz
    BAIL_ON_FAILED_LEP(LEP_OpenPort(1, LEP_CCI_TWI, 400, &_port_desc));

    BAIL_ON_FAILED_LEP(LEP_SetAgcEnableState(&_port_desc, LEP_AGC_DISABLE));
    BAIL_ON_FAILED_LEP(LEP_SetRadEnableState(&_port_desc, LEP_RAD_ENABLE));

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
    BAIL_ON_FAILED_LEP(LEP_SetSysFfcShutterModeObj(&_port_desc, ffcMode));
    usleep(200000); // Wait for a second to allow FFC to complete

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&_port_desc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&_port_desc, LEP_VIDEO_OUTPUT_ENABLE));

    // Show status some known interesting settings
    LEP_SYS_FLIR_SERIAL_NUMBER_T serialNumber;
    BAIL_ON_FAILED_LEP(LEP_GetSysFlirSerialNumber(&_port_desc, &serialNumber));
    LOG_INFO(_logger, "STARTUP Camera Serial Number: %llu", (unsigned long long) serialNumber);

    LEP_SYS_UPTIME_NUMBER_T upTime;
    BAIL_ON_FAILED_LEP(LEP_GetSysCameraUpTime(&_port_desc, &upTime));
    LOG_INFO(_logger, "STARTUP Camera Uptime: %u seconds", (unsigned int) (upTime));

    LEP_SYS_AUX_TEMPERATURE_CELCIUS_T auxTemp;
    LEP_GetSysAuxTemperatureCelcius(&_port_desc, &auxTemp);
    LOG_INFO(_logger, "STARTUP aux temperature: %.2f F", auxTemp * 9.0f / 5.0f + 32.0f);

    LEP_SYS_FPA_TEMPERATURE_CELCIUS_T fpaTemp;
    BAIL_ON_FAILED_LEP(LEP_GetSysFpaTemperatureCelcius(&_port_desc, &fpaTemp));
    LOG_INFO(_logger, "STARTUP FPA Temperature: %.2f F", fpaTemp * 9.0f / 5.0f + 32.0f);

    LEP_RAD_ENABLE_E radState;
    LEP_GetRadEnableState(&_port_desc, &radState);
    LOG_INFO(_logger, "STARTUP Radiometry enabled: %d", radState);

    LEP_AGC_ENABLE_E agcState;
    LEP_GetAgcEnableState(&_port_desc, &agcState);
    LOG_INFO(_logger, "STARTUP AGC enabled: %d", agcState);

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));
    LOG_INFO(_logger, "STARTUP Camera status: %d", statusDesc.camStatus);
}

/*********************************************************************
 * LeptonDriver - destructor for the Lepton driver
 *********************************************************************/
LeptonDriver::~LeptonDriver()
{
    for (const auto &kv : _timers)
        printf("%-30s %s\n", kv.first.c_str(), kv.second.to_str().c_str());

    close(_spi_fd);
    LEP_ClosePort(&_port_desc);
}

/*********************************************************************
 * shutdown - shutdown the Lepton driver and camera
 *********************************************************************/
void
LeptonDriver::shutdown()
{
    _shutdown_requested = true;

    // wake any waiters (notify all)
    {
        std::lock_guard<std::mutex> lk(_frame_mutex);
        // nothing else to do inside lock; lock/unlock establishes happens-before
    }
    _frame_cond.notify_all();

    if (_thread.joinable())
        _thread.join();

    if (_isRunning)
        LOG_ERROR(_logger, "shutdown() called but session is still running");
}

/*********************************************************************
 * getDriverInfo - retrieve information about the driver
 *********************************************************************/
void
LeptonDriver::getDriverInfo(SPLIB_DriverInfo *info)
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
 *
 * Uses std::thread instead of pthread_create.
 *********************************************************************/
void
LeptonDriver::startPolling()
{
    if (_isRunning)
        BAIL("Attempt to start already running polling thread");

    // Kickoff the driver thread
    LOG_INFO(_logger, "Starting frame capture thread");

    // start std::thread which calls the static wrapper that handles exceptions
    _thread = std::thread(&LeptonDriver::_spiPollingThreadMain, this);

    // Give the thread 5 seconds to start up (same behavior as before)
    for (int i = 0; i < 5000 && !_isRunning; i++)
        usleep(1000);
    if (!_isRunning)
        BAIL("Somehow the polling thread never started");
}

/*********************************************************************
 * cameraDisable - disable the camera
 *********************************************************************/
void
LeptonDriver::cameraDisable()
{
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));

    do {
        rtn = LEP_RunOemPowerDown(&_port_desc);
        usleep(250000);
    } while (rtn != LEP_OK);

    do {
        rtn = LEP_GetSysStatus(&_port_desc, &statusDesc);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

}

/*********************************************************************
 * cameraEnable - enable the camera
 *********************************************************************/
void
LeptonDriver::cameraEnable()
{
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));

    do {
        rtn = LEP_RunOemPowerOn(&_port_desc);
        usleep(250000);
    } while (rtn != LEP_OK);

    usleep(1000000);

    do {
        rtn = LEP_GetSysStatus(&_port_desc, &statusDesc);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&_port_desc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&_port_desc, LEP_VIDEO_OUTPUT_ENABLE));
    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));

    while (statusDesc.camStatus != LEP_SYSTEM_FLAT_FIELD_IN_PROCESS) {
        usleep(250000);
        BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));
    }
}

/*********************************************************************
 * getFrame - capture a single frame from the Lepton camera
 *
 * The Lepton v2.5 only generates frames at ~8.7 FPS, so this function
 * will block until a new frame is available from the camera.
 *********************************************************************/
void
LeptonDriver::getFrame(LeptonDriver::frameInfo &frame_info)
{
    if (!_isRunning)
        BAIL("Frame requested but SPI polling thread not running");
    if (_shutdown_requested)
        BAIL("SDK is shutting down");

    std::unique_lock<std::mutex> lk(_frame_mutex);
    _frame_cond.wait(lk, [this] { return _has_frame.load() || _shutdown_requested.load(); });

    if (_has_frame) {
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        frame_info.t_ns = _frame_info.t_ns;
        frame_info.event_id = _frame_info.event_id;
        frame_info.buffer = _frame_info.buffer;
    }
    _has_frame.store(false);
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
 * _spiPollingThreadMain - thread entry point wrapper
 *********************************************************************/
void
LeptonDriver::_spiPollingThreadMain(LeptonDriver *driver)
{
    bool threwException = true;

    try {
        driver->_isRunning = true;
        driver->_driverMain();
        threwException = false;
    } catch (const bail_error &e) {
        driver->_logger.log(
            e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR, e.what());
    } catch (const std::exception &e) {
        driver->_logger.log(
            __FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR, e.what());
    }

    driver->_isRunning = false;

    if (threwException) {
        std::lock_guard<std::mutex> lk(driver->_frame_mutex);
        driver->_has_frame = false;
        // notify any waiter that thread failed
        driver->_frame_cond.notify_all();
    }
}

/*********************************************************************
 * _driverMain - Driver logic main loop
 *********************************************************************/
void
LeptonDriver::_driverMain()
{
    uint8_t raw_buffer[PACKETS_PER_FRAME * PACKET_SIZE];
    const int pixel_count = FRAME_WIDTH * FRAME_HEIGHT;
    float local_buffer[pixel_count], prev_buffer[pixel_count];
    int stale_frame_count = 0;

    TIMER_GUARD_BLOCK(_timers["thermal_capture"])
    while (_shutdown_requested == false) {
        try {
            // Read from SPI until we see the start of a frame
            _safeRead(_spi_fd, raw_buffer, PACKET_SIZE);
            unsigned int attempt_count = 0;
            while ((raw_buffer[0] & 0x0F) != 0 && raw_buffer[1] != 0) {
                if (attempt_count++ > 100)
                    REBOOT("trouble syncing frame start");
                usleep(10000);
                _safeRead(_spi_fd, raw_buffer, PACKET_SIZE);
            }

            // After seeing the start of a frame, read the rest of the packets
            for (int p = 1; p < PACKETS_PER_FRAME; p++) {
                uint8_t *raw_buf = raw_buffer + p * PACKET_SIZE;
                _safeRead(_spi_fd, raw_buf, PACKET_SIZE);
                if ((raw_buf[0] & 0x0F) != 0 || raw_buf[1] != p)
                    REBOOT("bad frame received at (%d/%d)", p, PACKETS_PER_FRAME);
            }

            // Updated the shared frame buffer and signal any waiters
            bool matches_last_frame = true;
            for (int r = 0; r < FRAME_HEIGHT; ++r) {
                uint8_t *raw_row = raw_buffer + (r * PACKET_SIZE + 4);
                float *out_row = local_buffer + r * FRAME_WIDTH;
                float *prev_row = prev_buffer + r * FRAME_WIDTH;
                for (int c = 0; c < FRAME_WIDTH; ++c) {
                    uint16_t v = ((uint16_t) raw_row[2 * c] << 8) | raw_row[2 * c + 1];
                    float k = v * 0.01f;
                    out_row[c] = k;
                    matches_last_frame &= (prev_row[c] == k);
                    prev_row[c] = k;
                }
            }

            // Every now and then, we see the camera start to return the same
            // frame over and over again.  If we see that happening for roughly
            // a full second, reboot the camera
            if (matches_last_frame && stale_frame_count++ > 27)
                REBOOT("stale frames detected");

            // Only wake up a getFrame caller if this frame is unique
            if (!matches_last_frame) {
                if (_temp_unit == SPLIB_TEMP_UNITS_CELCIUS)
                    for (int i = 0; i < pixel_count; ++i)
                        local_buffer[i] -= 273.15f;
                if (_temp_unit == SPLIB_TEMP_UNITS_FAHRENHEIT)
                    for (int i = 0; i < pixel_count; ++i)
                        local_buffer[i] = (local_buffer[i] - 273.15f) * 9.0f / 5.0f + 32.0f;

                struct timespec ts;
                clock_gettime(CLOCK_MONOTONIC, &ts);
                uint64_t t = (uint64_t) ts.tv_sec * 1000000000 + (uint64_t) ts.tv_nsec;

                std::lock_guard<std::mutex> lk(_frame_mutex);
                memcpy(&(_frame_info.buffer[0]), local_buffer, sizeof(local_buffer));
                _frame_info.event_id++;
                _frame_info.t_ns = t;
                _has_frame = true;
                _frame_cond.notify_one();
                stale_frame_count = 0;
            }

        } catch (const reboot_error &e) {
            char msg[2048];
            snprintf(msg, sizeof(msg), "REBOOTING due to %s", e.what());
            LOG_WARNING(_logger, msg);
            cameraDisable();
            cameraEnable();
            stale_frame_count = 0;
        }
    }

    LOG_DEBUG(_logger, "Driver thread exiting");
}
