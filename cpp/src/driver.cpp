#include <functional>
#include <stdlib.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "driver.h"
#include "error.h"
#include "lepton.h"

using namespace strikepoint;

typedef struct {
        Logger *logger;
        LeptonDriver *driver;
} SessionData;

int
_errorHandler(SessionData *sessionData,
              const char *funcName,
              std::function<void(void)> func)
{
    if (sessionData == NULL) {
        fprintf(stderr, "Error: NULL session data in %s\n", funcName);
        return -1;
    }

    Logger &logger = *(sessionData->logger);

    try {
        // LOG_DEBUG(logger, "ENTERING %s", funcName);
        func();
        // LOG_DEBUG(logger, "EXITING %s", funcName);
        return 0;
    } catch (const strikepoint::bail_error &e) {
        logger.log(e.file().c_str(), e.line(), LOG_LEVEL_ERROR,
                   "Error in call to %s: %s", funcName, e.what());
        logger.log(e.file().c_str(), e.line(), LOG_LEVEL_ERROR, e.what());
    } catch (const std::exception &e) {
        logger.log(__FILE__, __LINE__, LOG_LEVEL_ERROR,
                   "Error in call to %s: %s", funcName, e.what());
        logger.log(__FILE__, __LINE__, LOG_LEVEL_ERROR, e.what());
    }

    return -1;
}

int
SPLIB_Init(SPLIB_SessionHandle *hndlPtr,
           SPLIB_DriverInfo *info,
           const char *logFilePath)
{
    SessionData *sessionData = new SessionData;
    sessionData->logger = new Logger(logFilePath);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver =
            new LeptonDriver(*sessionData->logger, logFilePath);
        sessionData->driver->getDriverInfo(info);
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
SPLIB_LeptonSetTemperatureUnits(SPLIB_SessionHandle hndl,
                                SPLIB_TemperatureUnit unit)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->driver->setTemperatureUnits(unit);
    });
}

int
SPLIB_GetNextLogEntry(SPLIB_SessionHandle hndl,
                      int *logLevel,
                      char *buffer, size_t bufferLen, int *msgRemaining)
{
    SessionData *sessionData = static_cast<SessionData *>(hndl);
    return _errorHandler(sessionData, __func__, [=]() {
        sessionData->logger->getNextLogEntry(logLevel, buffer, bufferLen);
        *msgRemaining = sessionData->logger->getMessagesRemaining();
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
