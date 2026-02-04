#include <chrono>
#include <linux/types.h>
#include <memory.h>
#include <unistd.h>

#include "error.h"
#include "lepton.h"

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60
#define PACKET_SIZE (4 + 2 * FRAME_WIDTH)
#define SPLIB_VERSION_MAJOR 2
#define SPLIB_VERSION_MINOR 0

using namespace strikepoint;

DECLARE_SPECIALIZED_BAIL_ERROR(retry_error);
DECLARE_SPECIALIZED_BAIL_ERROR(reboot_error);

#define RETRY(fmt, ...) BAIL_WITH_ERROR(retry_error, fmt, ##__VA_ARGS__)
#define REBOOT(fmt, ...) BAIL_WITH_ERROR(reboot_error, fmt, ##__VA_ARGS__)

/*********************************************************************
 * LeptonDriver - constructor for the Lepton driver
 *********************************************************************/
LeptonDriver::LeptonDriver(Logger &logger, ILeptonImpl &impl) :
    _logger(logger),
    _has_frame(false),
    _is_running(false),
    _shutdown_requested(false),
    _impl(impl)
{
    _frame_info.buffer.resize(FRAME_WIDTH * FRAME_HEIGHT);

#ifdef DEBUG
    LOG_INFO(_logger, "Lepton driver v%d.%d DEBUG initializing...",
             SPLIB_VERSION_MAJOR, SPLIB_VERSION_MINOR);
#else
    LOG_INFO(_logger, "Lepton driver v%d.%d RELEASE initializing...",
             SPLIB_VERSION_MAJOR, SPLIB_VERSION_MINOR);
#endif

    _thread = std::thread([this] {
        _is_running.store(true);
        try {
            _driverMain();
        } catch (const LeptonDriver::eof_error &e) {
            // gracefully exit on eof
        } catch (const bail_error &e) {
            _logger.log(
                e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR, e.what());
        } catch (const std::exception &e) {
            _logger.log(
                __FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR, e.what());
        } catch (...) {
            _logger.log(
                __FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR,
                "Unknown exception in driver thread");
        }

        _is_running.store(false);
        std::lock_guard<std::mutex> lk(_frame_mutex);
        _frame_cond.notify_all();
    });
    for (int i = 0; i < 5000 && !_is_running.load(); i++)
        usleep(1000);
    if (!_is_running.load())
        BAIL("Unable to start the polling thread");
    _thread.detach();
}

/*********************************************************************
 * LeptonDriver - destructor for the Lepton driver
 *********************************************************************/
LeptonDriver::~LeptonDriver()
{
    if (!_shutdown_requested.load())
        _shutdown_requested.store(true);
    for (int i = 0; i < 5000 && _is_running.load(); i++) {
        LOG_DEBUG(_logger, "Waiting for thread to shut down...");
        usleep(1000);
    }
    if (_is_running.load())
        LOG_WARNING(_logger, "Driver destructor ran, thread still running");

    for (const auto &kv : _timers)
        printf("%-30s %s\n", kv.first.c_str(), kv.second.to_str().c_str());
}

/*********************************************************************
 * cameraDisable - disable the camera
 *********************************************************************/
void
LeptonDriver::cameraDisable()
{
    _impl.cameraDisable();
}

/*********************************************************************
 * cameraEnable - enable the camera
 *********************************************************************/
void
LeptonDriver::cameraEnable()
{
    _impl.cameraEnable();
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
 * getFrame - capture a single frame from the Lepton camera
 *
 * The Lepton v2.5 only generates frames at ~8.7 FPS, so this function
 * will block until a new frame is available from the camera.
 *********************************************************************/
void
LeptonDriver::getFrame(LeptonDriver::frameInfo &frame_info)
{
    std::unique_lock<std::mutex> lk(_frame_mutex);
    _frame_cond.wait(lk, [this] { return _has_frame.load() ||
                                         _shutdown_requested.load(); });

    if (_shutdown_requested.load())
        BAIL("Requested a frame but the driver is terminating");
    if (!_has_frame.load())
        BAIL("Spurious wakeup from frame condition variable");

    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    frame_info.t_ns = _frame_info.t_ns;
    frame_info.frame_seq = _frame_info.frame_seq;
    frame_info.buffer = _frame_info.buffer;
    _has_frame.store(false);
}

/*********************************************************************
 * _safeRead - read exactly len bytes from fd into buf
 *********************************************************************/
void
LeptonDriver::ILeptonImpl::safeRead(int fd, void *buf, size_t len)
{
    size_t totalRead = 0;
    while (totalRead < len) {
        ssize_t bytesRead =
            read(fd, (uint8_t *) buf + totalRead, len - totalRead);
        if (bytesRead < 0)
            BAIL("read failed, error=%s", strerror(errno));
        if (bytesRead == 0)
            BAIL("reached end of file for SPI data");
        totalRead += bytesRead;
    }
}

/*********************************************************************
 * _driverMain - Driver logic main loop
 *********************************************************************/
void
LeptonDriver::_driverMain()
{
    uint8_t raw_buffer[FRAME_HEIGHT * PACKET_SIZE]{};
    const unsigned int pixel_count = FRAME_HEIGHT * FRAME_WIDTH;
    float local_buffer[pixel_count]{}, prev_buffer[pixel_count]{};
    unsigned int retry_count = 0, stale_frame_count = 0;
    uint32_t frame_seq = -1;
    struct timespec ts{};

    TIMER_GUARD_BLOCK(_timers["thermal_capture"])
    _is_running.store(true);
    while (!_shutdown_requested.load()) {
        try {
            // Make sure we don't retry forever
            if (retry_count > 20)
                REBOOT("too many retries");

            // Read until we see the start of a frame, but reboot if we can't
            // sync after a reasonable number of attempts
            unsigned int sync_attempt_count = 0;
            _impl.spiRead(raw_buffer, PACKET_SIZE);
            while ((raw_buffer[0] & 0x0F) != 0 || raw_buffer[1] != 0) {
                if (sync_attempt_count++ > 300)
                    REBOOT("trouble syncing frame start");
                LOG_DEBUG(_logger, "re-sync %d/300", sync_attempt_count);
                usleep(10000);
                _impl.spiRead(raw_buffer, PACKET_SIZE);
            }

            // After syncing to the start of a frame, read the remaining packets
            // into the raw buffer all together (will process them next)
            for (int r = 1; r < FRAME_HEIGHT; r++) {
                uint8_t *raw_row = raw_buffer + r * PACKET_SIZE;
                _impl.spiRead(raw_row, PACKET_SIZE);
                if ((raw_row[0] & 0x0F) != 0 || raw_row[1] != r)
                    RETRY("bad frame received at (%d/%d)", r, FRAME_HEIGHT);
            }

            // Updated the shared frame buffer with full frame data coming
            // in 16bit values in centiKelvin, convert to float degF
            bool matches_last_frame = true;
            frame_seq++;
            for (int r = 0; r < FRAME_HEIGHT; r++) {
                uint8_t *raw_ptr = raw_buffer + r * PACKET_SIZE + 4;
                float *out_row = local_buffer + r * FRAME_WIDTH;
                float *prev_row = prev_buffer + r * FRAME_WIDTH;
                for (int c = 0; c < FRAME_WIDTH; ++c) {
                    uint16_t v = ((uint16_t) raw_ptr[0] << 8) | raw_ptr[1];
                    float f = (v * 0.01f - 273.15f) * 9.0f / 5.0f + 32.0f;
                    matches_last_frame &= (prev_row[c] == f);
                    out_row[c] = prev_row[c] = f;
                    raw_ptr += 2;
                }
            }

            // Check for frames not changing over ~1s of capture
            if (matches_last_frame && stale_frame_count++ > 27)
                REBOOT("stale frame detected");

            // We receive frames at ~27hz, but new data is at every 3rd frame,
            // so only update consumers when we see changes
            if (!matches_last_frame) {
                std::lock_guard<std::mutex> lk(_frame_mutex);
                clock_gettime(CLOCK_MONOTONIC, &ts);
                memcpy(&(_frame_info.buffer[0]), local_buffer, sizeof(local_buffer));
                _frame_info.frame_seq = frame_seq;
                _frame_info.t_ns = (uint64_t) ts.tv_sec * 1000000000 + (uint64_t) ts.tv_nsec;
                _has_frame.store(true);
                _frame_cond.notify_one();
                stale_frame_count = 0;
                retry_count = 0;
            }
        } catch (const retry_error &e) {
            LOG_WARNING(_logger, "RETRYING due to %s", e.what());
            usleep(50000);
            retry_count++;
        } catch (const reboot_error &e) {
            LOG_ERROR(_logger, "REBOOTING due to %s", e.what());
            cameraDisable();
            cameraEnable();
            memset(prev_buffer, 0, sizeof(prev_buffer));
            retry_count = 0;
        }
    }

    LOG_DEBUG(_logger, "Driver thread exiting");
}
