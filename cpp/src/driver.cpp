#include <functional>
#include <stdlib.h>

#include <map>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "audio-pcm.h"
#include "driver.h"
#include "error.h"
#include "lepton-hardware.h"
#include "lepton.h"
#include "timer.h"

using namespace strikepoint;

const char *SPLIB_LOG_LEVEL_NAMES[] = {
    "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"};

typedef struct {
    Logger *logger;
    LeptonHardwareImpl *lepton_hardware_impl;
    LeptonDriver *driver;
    PcmAudioSource *source;
    AudioEngine *audio_engine;
    size_t pixel_count;
    std::map<std::string, Timer> timers;
} SessionData;

int
_errorHandler(SessionData *session,
              const char *func_name,
              std::function<void(void)> func)
{
    if (session == NULL)
        return -2;

    try {
        TimerGuard guard(session->timers[func_name]);
        func();
        return 0;
    } catch (const strikepoint::bail_error &e) {
        Logger &logger = *(session->logger);
        logger.log(e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR,
                   "Error in call to %s: %s", func_name, e.what());
        logger.log(e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR, e.what());
    } catch (const std::exception &e) {
        Logger &logger = *(session->logger);
        logger.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR,
                   "Error in call to %s: %s", func_name, e.what());
        logger.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR, e.what());
    } catch (...) {
        Logger &logger = *(session->logger);
        logger.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR,
                   "Unknown error in call to %s", func_name);
    }

    return -1;
}

int
SPLIB_Init(SPLIB_SessionHandle *hndl_ptr,
           SPLIB_DriverInfo *info,
           const char *log_file_path)
{
    if (hndl_ptr == NULL)
        return -2;

    SessionData *session = new SessionData;
    session->logger = new Logger(log_file_path);
    return _errorHandler(session, __func__, [=]() {
        if (info == NULL)
            BAIL("info argument cannot be NULL");
        AudioEngine::config audioConfig;
        AudioEngine::defaults(audioConfig);
        session->lepton_hardware_impl =
            new LeptonHardwareImpl(*(session->logger));
        session->driver = new LeptonDriver(
            *session->logger, *session->lepton_hardware_impl);
        session->driver->getDriverInfo(info);
        session->pixel_count =
            (size_t) info->frameWidth * (size_t) info->frameHeight;
        session->source =
            new PcmAudioSource("default", 48000, 1, audioConfig.block_size);
        session->audio_engine = new AudioEngine(
            *(session->logger), *(session->source), audioConfig);
        *hndl_ptr = (SPLIB_SessionHandle) session;
    });
}

int
SPLIB_LogHasEntries(SPLIB_SessionHandle hndl, int *hasEntries)
{
    SessionData *session = static_cast<SessionData *>(hndl);
    return _errorHandler(session, __func__, [=]() {
        if (hasEntries == NULL)
            BAIL("hasEntries argument cannot be NULL");
        *hasEntries = session->logger->getEntriesRemaining() > 0;
    });
}

int
SPLIB_LogGetNextEntry(SPLIB_SessionHandle hndl,
                      SPLIB_LogLevel *logLevel,
                      char *buffer, size_t bufferLen)
{
    SessionData *session = static_cast<SessionData *>(hndl);
    return _errorHandler(session, __func__, [=]() {
        if (logLevel == NULL)
            BAIL("logLevel argument cannot be NULL");
        if (buffer == NULL)
            BAIL("buffer argument cannot be NULL");
        session->logger->getNextEntry((int *) logLevel, buffer, bufferLen);
    });
}

int
SPLIB_GetAudioStrikeEvents(SPLIB_SessionHandle hndl,
                           uint64_t *event_times,
                           size_t max_events, size_t *num_events)
{
    SessionData *session = static_cast<SessionData *>(hndl);
    return _errorHandler(session, __func__, [=]() {
        if (event_times == NULL)
            BAIL("event_times argument cannot be NULL");
        if (num_events == NULL)
            BAIL("num_events argument cannot be NULL");
        std::vector<AudioEngine::event> events;
        session->audio_engine->getEvents(events);
        *num_events = events.size();
        if (*num_events > max_events)
            BAIL("Max events exceeded, max=%zu, found=%zu", max_events, *num_events);
        for (size_t i = 0; i < *num_events; ++i)
            event_times[i] = events[i].t_ns;
    });
}

int
SPLIB_LeptonGetFrame(SPLIB_SessionHandle hndl,
                     float *buffer,
                     size_t buffer_size,
                     uint32_t *frame_seq,
                     uint64_t *timestamp_ns)
{
    SessionData *session = static_cast<SessionData *>(hndl);
    return _errorHandler(session, __func__, [=]() {
        if (buffer == NULL)
            BAIL("buffer argument cannot be NULL");
        if (frame_seq == NULL)
            BAIL("frame_seq argument cannot be NULL");
        if (timestamp_ns == NULL)
            BAIL("timestamp_ns argument cannot be NULL");
        if (buffer_size < session->pixel_count)
            BAIL("Frame buffer too small, required=%zu floats, received %zu",
                 session->pixel_count, buffer_size);
        LeptonDriver::frameInfo frameInfo;
        session->driver->getFrame(frameInfo);
        *frame_seq = frameInfo.frame_seq;
        *timestamp_ns = frameInfo.t_ns;
        memcpy(buffer, &frameInfo.buffer[0],
               sizeof(float) * session->pixel_count);
    });
}

int
SPLIB_Shutdown(SPLIB_SessionHandle hndl)
{
    SessionData *session = static_cast<SessionData *>(hndl);
    return _errorHandler(session, __func__, [=]() {
        for (const auto &kv : session->timers)
            printf("%-30s %s\n", kv.first.c_str(), kv.second.to_str().c_str());
        delete session->driver;
        delete session->audio_engine;
        delete session->source;
        delete session->logger;
        delete session;
    });
}
