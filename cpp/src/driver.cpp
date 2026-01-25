#include <functional>
#include <stdlib.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "audio-pcm.h"
#include "driver.h"
#include "error.h"
#include "lepton.h"

using namespace strikepoint;

typedef struct {
    Logger *logger;
    LeptonDriver *driver;
    PcmAudioSource *source;
    AudioEngine *audioEngine;
} SessionData;

int
_errorHandler(SessionData *sessionData,
              const char *funcName,
              std::function<void(void)> func)
{
    if (sessionData == NULL)
        return -1;

    Logger &logger = *(sessionData->logger);

    try {
        // LOG_DEBUG(logger, "ENTERING %s", funcName);
        func();
        // LOG_DEBUG(logger, "EXITING %s", funcName);
        return 0;
    } catch (const strikepoint::bail_error &e) {
        logger.log(e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR,
                   "Error in call to %s: %s", funcName, e.what());
        logger.log(e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR, e.what());
    } catch (const std::exception &e) {
        logger.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR,
                   "Error in call to %s: %s", funcName, e.what());
        logger.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR, e.what());
    }

    return -2;
}

int
SPLIB_Init(SPLIB_SessionHandle *hndlPtr,
           SPLIB_DriverInfo *info,
           SPLIB_TemperatureUnit tempUnit,
           const char *logFilePath)
{
    SessionData *sessionData = new SessionData;
    sessionData->logger = new Logger(logFilePath);
    return _errorHandler(sessionData, __func__, [=]() {
        AudioEngine::config audioConfig;
        AudioEngine::defaults(audioConfig);
        sessionData->driver =
            new LeptonDriver(*sessionData->logger, tempUnit, logFilePath);
        sessionData->driver->getDriverInfo(info);
        sessionData->source =
            new PcmAudioSource("default", 48000, 1, audioConfig.blockSize);
        sessionData->audioEngine = new AudioEngine(
            *(sessionData->source), audioConfig);
        *hndlPtr = (SPLIB_SessionHandle) sessionData;
    });
}

int
SPLIB_LeptonStartPolling(SPLIB_SessionHandle hndl)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver->startPolling();
    });
}

int
SPLIB_LeptonDisable(SPLIB_SessionHandle hndl)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver->cameraDisable();
    });
}

int
SPLIB_LeptonEnable(SPLIB_SessionHandle hndl)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver->cameraEnable();
    });
}

int
SPLIB_GetNextLogEntry(SPLIB_SessionHandle hndl,
                      SPLIB_LogLevel *logLevel,
                      char *buffer, size_t bufferLen, int *msgRemaining)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->logger->getNextLogEntry((int *) logLevel, buffer, bufferLen);
        *msgRemaining = sessionData->logger->getMessagesRemaining();
    });
}

int
SPLIB_GetAudioStrikeEvents(SPLIB_SessionHandle hndl,
                           uint64_t *eventTimes,
                           size_t maxEvents, size_t *numEvents)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        std::vector<AudioEngine::event> events;
        sessionData->audioEngine->getEvents(events);
        *numEvents = events.size();
        if (*numEvents > maxEvents)
            BAIL("Max events exceeded, max=%zu, found=%zu", maxEvents, *numEvents);
        for (size_t i = 0; i < *numEvents; ++i)
            eventTimes[i] = events[i].t_ns;
    });
}

int
SPLIB_LeptonGetFrame(SPLIB_SessionHandle hndl, float *frameBuffer)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver->getFrame(frameBuffer);
    });
}

int
SPLIB_Shutdown(SPLIB_SessionHandle hndl)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver->shutdown();
        delete sessionData->driver;
        delete sessionData->logger;
        delete sessionData;
    });
}
