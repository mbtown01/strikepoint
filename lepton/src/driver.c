#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <linux/types.h>
#include <memory.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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
#include "driver.h"

// All logging methods require a session pointer
#define LOG_DEBUG(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, LEPDRV_LOG_LEVEL_DEBUG, fmt, ##__VA_ARGS__)
#define LOG_INFO(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, LEPDRV_LOG_LEVEL_INFO, fmt, ##__VA_ARGS__)
#define LOG_WARNING(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, LEPDRV_LOG_LEVEL_WARNING, fmt, ##__VA_ARGS__)
#define LOG_ERROR(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, LEPDRV_LOG_LEVEL_ERROR, fmt, ##__VA_ARGS__)
#define LOG_CRITICAL(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, LEPDRV_LOG_LEVEL_CRITICAL, fmt, ##__VA_ARGS__)

#ifndef DEBUG
#undef LOG_DEBUG
#define LOG_DEBUG(fmt, ...) \
    do {                    \
    } while (0)
#endif

#define BAIL(fmt, ...)                 \
    do {                               \
        LOG_ERROR(fmt, ##__VA_ARGS__); \
        return -1;                     \
    } while (0)

#define BAIL_ON_FAILED_LEP(cmd)                                       \
    do {                                                              \
        LEP_RESULT rtn = cmd;                                         \
        if (rtn != LEP_OK) {                                          \
            LOG_ERROR("'%s' returned LEP_RESULT code %d", #cmd, rtn); \
            return -1;                                                \
        }                                                             \
    } while (0)

#define BAIL_ON_FAILED_SYS(cmd)                                            \
    do {                                                                   \
        int rtn = cmd;                                                     \
        if (rtn < 0) {                                                     \
            LOG_ERROR("'%s' returned %d: %s", #cmd, rtn, strerror(errno)); \
            return -1;                                                     \
        }                                                                  \
    } while (0)

#define BAIL_ON_FAILED(cmd)                           \
    do {                                              \
        int rtn = cmd;                                \
        if (rtn < 0) {                                \
            LOG_ERROR("'%s' returned %d", #cmd, rtn); \
            return -1;                                \
        }                                             \
    } while (0)

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60
#define PACKET_SIZE (4 + 2 * FRAME_WIDTH)
#define PACKETS_PER_FRAME FRAME_HEIGHT
#define LOG_BUFFER_SIZE 512
#define LOG_MAX_MESSAGE_LENGTH 4096

typedef struct LEPDRV_LogEntry {
    time_t timestamp;
    LEPDRV_LogLevel level;
    char message[LOG_MAX_MESSAGE_LENGTH];
} LEPDRV_LogEntry;

typedef struct {
    LEP_CAMERA_PORT_DESC_T portDesc;
    pthread_t thread;
    pthread_mutex_t frameMutex, logMutex;
    pthread_cond_t frameCond;
    int spiFd;

    FILE *logFile;
    LEPDRV_LogEntry logBuffer[LOG_BUFFER_SIZE];
    off_t logStartOffset, logLength;
    float frameBuffer[FRAME_WIDTH * FRAME_HEIGHT];
    LEPDRV_TemperatureUnit tempUnit;
    bool hasFrame, shutdownRequested, isRunning;
    int threadRtn;
} LEPDRV_Session;

// Forward declare some utility methods
int _safeRead(LEPDRV_Session *session, int fd, void *buf, size_t len);
int _driverMain(LEPDRV_Session *session);
void *_spiPollingThreadMain(void *arg);
void _driverLog(LEPDRV_Session *session,
                const char *file,
                const int line,
                const LEPDRV_LogLevel logLevel,
                const char *format, ...);

/*********************************************************************
 * LEPDRV_Init - initialize the Lepton driver and camera
 *********************************************************************/
int LEPDRV_Init(LEPDRV_SessionHandle *hndlPtr,
                LEPDRV_DriverInfo *info,
                const char *logFilePath) {
    if (hndlPtr == NULL)
        return -1;
    if (info == NULL)
        return -1;

    LEPDRV_Session localSession;
    memset(&localSession, 0, sizeof(LEPDRV_Session));
    LEPDRV_Session *session = &localSession;

    session->tempUnit = LEPDRV_TEMP_UNITS_FAHRENHEIT;
    session->shutdownRequested = false;
    session->hasFrame = false;
    session->isRunning = false;
    session->logFile = stdout;
    session->threadRtn = 0;
    session->logStartOffset = 0;
    session->logLength = 0;

    info->versionMajor = 1;
    info->versionMinor = 0;
    info->frameWidth = FRAME_WIDTH;
    info->frameHeight = FRAME_HEIGHT;
    info->maxLogEntries = LOG_BUFFER_SIZE;

    if (logFilePath == NULL)
        session->logFile = NULL;
    else if (strncmp(logFilePath, "stdout", 6) == 0)
        session->logFile = stdout;
    else if (strncmp(logFilePath, "stderr", 6) == 0)
        session->logFile = stderr;
    else {
        FILE *newLogFile = fopen(logFilePath, "w");
        if (newLogFile == NULL) {
            LOG_ERROR("Could not open log file %s", logFilePath);
            return -1;
        } else
            session->logFile = newLogFile;
    }

    LOG_INFO("LEPTON Driver Starting Up...");

    LEP_STATUS_T statusDesc;
    unsigned char spiMode = SPI_MODE_3;
    unsigned char spiBitsPerWord = 8;
    unsigned int spiSpeed = 10000000;

    LOG_INFO("Configuring /def/spidev0.0: mode=%d, bitsPerWord=%d, speed=%d Hz",
             spiMode, spiBitsPerWord, spiSpeed);
    session->spiFd = open("/dev/spidev0.0", O_RDWR);
    if (session->spiFd < 0)
        BAIL("Could not open SPI device");
    BAIL_ON_FAILED_SYS(
        ioctl(session->spiFd, SPI_IOC_WR_MODE, &spiMode));
    BAIL_ON_FAILED_SYS(
        ioctl(session->spiFd, SPI_IOC_RD_MODE, &spiMode));
    BAIL_ON_FAILED_SYS(
        ioctl(session->spiFd, SPI_IOC_WR_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_SYS(
        ioctl(session->spiFd, SPI_IOC_RD_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_SYS(
        ioctl(session->spiFd, SPI_IOC_WR_MAX_SPEED_HZ, &spiSpeed));
    BAIL_ON_FAILED_SYS(
        ioctl(session->spiFd, SPI_IOC_RD_MAX_SPEED_HZ, &spiSpeed));

    // Initialize and open the camera port (example values)
    LOG_INFO("Configuring camera port");
    session->portDesc.portType = LEP_CCI_TWI;
    session->portDesc.portID = 99;
    session->portDesc.deviceAddress = 0x2A;               // Example I2C address
    session->portDesc.portBaudRate = (LEP_UINT16) 400000; // 400 kHz
    BAIL_ON_FAILED_LEP(LEP_OpenPort(1, LEP_CCI_TWI, 400, &session->portDesc));

    BAIL_ON_FAILED_LEP(LEP_SetAgcEnableState(&session->portDesc, LEP_AGC_DISABLE));
    BAIL_ON_FAILED_LEP(LEP_SetRadEnableState(&session->portDesc, LEP_RAD_ENABLE));

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
    BAIL_ON_FAILED_LEP(LEP_SetSysFfcShutterModeObj(&session->portDesc, ffcMode));
    usleep(200000); // Wait for a second to allow FFC to complete

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&session->portDesc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&session->portDesc, LEP_VIDEO_OUTPUT_ENABLE));

    // Show status some known interesting settings
    LEP_SYS_FLIR_SERIAL_NUMBER_T serialNumber;
    BAIL_ON_FAILED_LEP(LEP_GetSysFlirSerialNumber(&session->portDesc, &serialNumber));
    LOG_INFO("STARTUP Camera Serial Number: %llu", (unsigned long long) serialNumber);

    LEP_SYS_UPTIME_NUMBER_T upTime;
    BAIL_ON_FAILED_LEP(LEP_GetSysCameraUpTime(&session->portDesc, &upTime));
    LOG_INFO("STARTUP Camera Uptime: %u seconds", (unsigned int) (upTime));

    LEP_SYS_AUX_TEMPERATURE_CELCIUS_T auxTemp;
    LEP_GetSysAuxTemperatureCelcius(&session->portDesc, &auxTemp);
    LOG_INFO("STARTUP aux temperature: %.2f F", auxTemp * 9.0f / 5.0f + 32.0f);

    LEP_SYS_FPA_TEMPERATURE_CELCIUS_T fpaTemp;
    BAIL_ON_FAILED_LEP(LEP_GetSysFpaTemperatureCelcius(&session->portDesc, &fpaTemp));
    LOG_INFO("STARTUP FPA Temperature: %.2f F", fpaTemp * 9.0f / 5.0f + 32.0f);

    LEP_RAD_ENABLE_E radState;
    LEP_GetRadEnableState(&session->portDesc, &radState);
    LOG_INFO("STARTUP Radiometry enabled: %d", radState);

    LEP_AGC_ENABLE_E agcState;
    LEP_GetAgcEnableState(&session->portDesc, &agcState);
    LOG_INFO("STARTUP AGC enabled: %d", agcState);

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_INFO("STARTUP Camera status: %d", statusDesc.camStatus);

    session = (LEPDRV_Session *) calloc(1, sizeof(LEPDRV_Session));
    if (session == NULL)
        BAIL("Could not allocate memory for session: %s", strerror(errno));
    memcpy(session, &localSession, sizeof(LEPDRV_Session));
    hndlPtr[0] = (LEPDRV_SessionHandle) session;
    return 0;
}

/*********************************************************************
 * LEPDRV_StartPolling - start the SPI polling thread
 *********************************************************************/
int LEPDRV_StartPolling(LEPDRV_SessionHandle hndl) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (session->isRunning)
        BAIL("Attempt to start already running polling thread");

    // Kickoff the driver thread
    LOG_INFO("Starting frame capture thread");
    BAIL_ON_FAILED_SYS(pthread_mutex_init(&session->frameMutex, NULL));
    BAIL_ON_FAILED_SYS(pthread_mutex_init(&session->logMutex, NULL));
    BAIL_ON_FAILED_SYS(pthread_cond_init(&session->frameCond, NULL));
    BAIL_ON_FAILED_SYS(pthread_create(
        &session->thread, NULL, _spiPollingThreadMain, (void *) session));

    // Give the pthread 5 seconds to start up
    for (int i = 0; i < 5000 && !session->isRunning; i++)
        usleep(1000);
    if (!session->isRunning)
        BAIL("Somehow the polling thread never started");

    return 0;
}

/*********************************************************************
 * LEPDRV_GetFrame - capture a single frame from the Lepton camera
 *
 * The Lepton v2.5 only generates frames at ~8.7 FPS, so this function
 * will block until a new frame is available from the camera.
 *********************************************************************/
int LEPDRV_GetFrame(LEPDRV_SessionHandle hndl,
                    float *frameBuffer) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (!session->isRunning)
        BAIL("Frame requested but SPI polling thread not running");
    if (session->shutdownRequested)
        BAIL("SDK is shutting down");

    pthread_mutex_lock(&session->frameMutex);
    pthread_cond_wait(&session->frameCond, &session->frameMutex);
    if (session->hasFrame)
        memcpy(frameBuffer, session->frameBuffer, sizeof(session->frameBuffer));
    session->hasFrame = false;
    pthread_mutex_unlock(&session->frameMutex);

    if (session->threadRtn)
        BAIL("Call to LEPDRV_GetFrame failed, polling thread exited abonrmally");

    return 0;
}

/*********************************************************************
 * LEPDRV_GetNextLogEntry - get the next log entry from the driver
 *********************************************************************/
int LEPDRV_GetNextLogEntry(LEPDRV_SessionHandle hndl,
                           LEPDRV_LogLevel *level,
                           char *buffer,
                           size_t bufferLen) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (level == NULL)
        BAIL("level pointer is NULL");
    if (buffer == NULL)
        BAIL("buffer pointer is NULL");
    if (bufferLen == 0)
        BAIL("bufferLen is zero");

    if (session->logLength == 0)
        return -1;

    pthread_mutex_lock(&session->logMutex);
    LEPDRV_LogEntry *entry = session->logBuffer + session->logStartOffset;
    *level = entry->level;
    strncpy(buffer, entry->message, bufferLen - 1);
    buffer[bufferLen - 1] = '\0';
    session->logLength -= 1;
    session->logStartOffset =
        (session->logStartOffset + 1) % LOG_BUFFER_SIZE;
    pthread_mutex_unlock(&session->logMutex);

    return 0;
}

/*********************************************************************
 * LEPDRV_SetTemperatureUnits - set temperature units for frames
 *********************************************************************/
int LEPDRV_SetTemperatureUnits(LEPDRV_SessionHandle hndl,
                               LEPDRV_TemperatureUnit unit) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (unit < 0 || unit >= LEPDRV_TEMP_UNITS_MAX)
        BAIL("Invalid temperature unit %d", unit);
    const char *unitNames[] = {"Kelvin", "Celsius", "Fahrenheit"};

    LOG_DEBUG("Setting temperature units to %s", unitNames[unit]);
    session->tempUnit = unit;
    return 0;
}
/*********************************************************************
 * LEPDRV_CameraDisable - disable the camera and put it into power
 *                          down mode
 *********************************************************************/
int LEPDRV_CameraDisable(LEPDRV_SessionHandle hndl) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");

    LOG_DEBUG("LEPDRV_CameraDisable() START");
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_DEBUG("Camera status before disable: %d", statusDesc.camStatus);

    do {
        rtn = LEP_RunOemPowerDown(&(session->portDesc));
        LOG_DEBUG("Power down command sent, rtn=%d", rtn);
        usleep(250000);
    } while (rtn != LEP_OK);

    do {
        rtn = LEP_GetSysStatus(&session->portDesc, &statusDesc);
        LOG_DEBUG("Camera status test disable: %d, rtn=%d",
                  statusDesc.camStatus, rtn);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

    LOG_DEBUG("LEPDRV_CameraDisable() COMPLETE");
    return 0;
}

/*********************************************************************
 * LEPDRV_CameraEnable - enable the camera
 *********************************************************************/
int LEPDRV_CameraEnable(LEPDRV_SessionHandle hndl) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");

    LOG_DEBUG("LEPDRV_CameraEnable() START");
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_DEBUG("Camera status before enable: %d", statusDesc.camStatus);

    do {
        rtn = LEP_RunOemPowerOn(&(session->portDesc));
        LOG_DEBUG("Power on command sent, rtn=%d", rtn);
        usleep(250000);
    } while (rtn != LEP_OK);

    usleep(1000000);

    do {
        rtn = LEP_GetSysStatus(&session->portDesc, &statusDesc);
        LOG_DEBUG("Camera status test disable: %d, rtn=%d",
                  statusDesc.camStatus, rtn);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&session->portDesc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&session->portDesc, LEP_VIDEO_OUTPUT_ENABLE));

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_DEBUG("STARTUP Camera status: %d", statusDesc.camStatus);

    while (statusDesc.camStatus != LEP_SYSTEM_FLAT_FIELD_IN_PROCESS) {
        usleep(250000);
        BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
        LOG_DEBUG("Camera status waiting for FFC: %d", statusDesc.camStatus);
    }

    LOG_DEBUG("LEPDRV_CameraEnable() COMPLETE");
    return 0;
}

/*********************************************************************
 * LEPDRV_Shutdown - shutdown the Lepton driver and camera
 *********************************************************************/
int LEPDRV_Shutdown(LEPDRV_SessionHandle hndl) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");

    LOG_DEBUG("Driver shutdown requested, waiting for capture thread");
    void *rtnval = NULL;
    session->shutdownRequested = true;
    BAIL_ON_FAILED_SYS(pthread_join(session->thread, &rtnval));
    BAIL_ON_FAILED_SYS(pthread_mutex_destroy(&session->frameMutex));
    BAIL_ON_FAILED_SYS(pthread_mutex_destroy(&session->logMutex));
    BAIL_ON_FAILED_SYS(pthread_cond_destroy(&session->frameCond));

    BAIL_ON_FAILED_SYS(close(session->spiFd));
    BAIL_ON_FAILED_LEP(LEP_ClosePort(&session->portDesc));

    if (session->isRunning)
        LOG_ERROR("Somehow we shutdown but the session is still running");
    if (session->threadRtn)
        LOG_ERROR("SPI polling thread returned abnormally, rtn=%d", session->threadRtn);

    LOG_DEBUG("Driver shutdown complete");

    if (session->logFile != NULL && session->logFile != stdout &&
        session->logFile != stderr)
        fclose(session->logFile);
    memset(session, 0, sizeof(LEPDRV_Session));
    free(session);
    return (0);
}

/*********************************************************************
 * safeRead - read exactly len bytes from fd into buf
 *********************************************************************/
int _safeRead(LEPDRV_Session *session, int fd, void *buf, size_t len) {
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
 * _driverMain - Driver logic main loop
 *********************************************************************/
int _driverMain(LEPDRV_Session *session) {
    uint8_t buff[PACKETS_PER_FRAME][PACKET_SIZE];
    const int maxFailedAttempts = 30;
    const int pixelsPerFrame = FRAME_WIDTH * FRAME_HEIGHT;
    int failedAttempsRemaining = maxFailedAttempts;
    int matchingCrcCount = 0;
    ssize_t bytesRead;
    CRC16 lastCrc = 0;

    while (session->shutdownRequested == false && failedAttempsRemaining > 0) {
        // Read from SPI until we see the start of a frame
        int tries = 100;
        _safeRead(session, session->spiFd, buff[0], PACKET_SIZE);
        while ((buff[0][0] & 0x0F) != 0 && buff[0][1] != 0 && tries-- > 0) {
            usleep(10000);
            _safeRead(session, session->spiFd, buff[0], PACKET_SIZE);
        }
        if (tries == 0)
            continue;

        // After seeing the start of a frame, read the rest of the packets
        int goodPackets = 1;
        for (int p = 1; p < PACKETS_PER_FRAME; p++, goodPackets++) {
            _safeRead(session, session->spiFd, buff[p], PACKET_SIZE);
            if ((buff[p][0] & 0x0F) != 0 || buff[p][1] != p)
                break;
        }

        // If we didn't see all the packetes in the frame, reboot the camera
        if (goodPackets != PACKETS_PER_FRAME) {
            LOG_WARNING("Bad frame received (%d/%d packets), rebooting camera",
                        goodPackets, PACKETS_PER_FRAME);
            BAIL_ON_FAILED(LEPDRV_CameraDisable(session));
            BAIL_ON_FAILED(LEPDRV_CameraEnable(session));
            failedAttempsRemaining--;
            continue;
        }

        // Updated the shared frame buffer and signal any waiters
        float localBuffer[pixelsPerFrame];
        for (int i = 0; i < pixelsPerFrame; i++) {
            int r = i / FRAME_WIDTH, c = i % FRAME_WIDTH;
            uint16_t v = (buff[r][4 + 2 * c] << 8) + buff[r][4 + 2 * c + 1];
            float k = (float) v * 0.01f;
            if (session->tempUnit == LEPDRV_TEMP_UNITS_CELCIUS)
                k = k - 273.15f;
            else if (session->tempUnit == LEPDRV_TEMP_UNITS_FAHRENHEIT)
                k = ((k - 273.15f) * 9.0f / 5.0f) + 32.0f;
            localBuffer[i] = k;
        }

        // Only wake up a getFrame caller if this frame is unique
        CRC16 crc = CalcCRC16Bytes(sizeof(localBuffer), (char *) localBuffer);
        if (lastCrc != crc) {
            pthread_mutex_lock(&session->frameMutex);
            memcpy(session->frameBuffer, localBuffer, sizeof(localBuffer));
            session->hasFrame = true;
            pthread_cond_signal(&session->frameCond);
            pthread_mutex_unlock(&session->frameMutex);
            lastCrc = crc;
            matchingCrcCount = 0;
            failedAttempsRemaining = maxFailedAttempts;
        }

        // Every now and then, we see the camera start to return the same
        // frame over and over again.  If we see that happening for roughly
        // a full second, reboot the camera
        if (matchingCrcCount++ > 27) {
            LOG_WARNING("Stale frames detected, rebooting camera");
            BAIL_ON_FAILED(LEPDRV_CameraDisable(session));
            BAIL_ON_FAILED(LEPDRV_CameraEnable(session));
            matchingCrcCount = 0;
            failedAttempsRemaining--;
            continue;
        }
    }

    if (failedAttempsRemaining == 0)
        BAIL("Too many consecutive frame capture failures, exiting");

    LOG_DEBUG("Driver thread exiting");
    return 0;
}

/*********************************************************************
 * _spiPollingThreadMain - pthread entry point
 *********************************************************************/
void *_spiPollingThreadMain(void *arg) {
    LEPDRV_Session *session = (LEPDRV_Session *) arg;
    session->isRunning = true;
    session->threadRtn = _driverMain(session);
    if (session->threadRtn != 0) {
        pthread_mutex_lock(&session->frameMutex);
        session->hasFrame = false;
        pthread_cond_signal(&session->frameCond);
        pthread_mutex_unlock(&session->frameMutex);
    }

    session->isRunning = false;
    return NULL;
}
/*********************************************************************
 * _driverLog - log an error message with variable arguments
 *********************************************************************/
void _driverLog(LEPDRV_Session *session,
                const char *file,
                const int line,
                const LEPDRV_LogLevel logLevel,
                const char *format, ...) {
    time_t rawtime;
    struct tm *timeinfo;
    char timeStr[80], msgStr[4096];
    va_list args;
    static const char *levelStrings[] = {
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"};

    time(&rawtime);
    timeinfo = localtime(&rawtime);
    strftime(timeStr, sizeof(timeStr), "%Y-%m-%d %H:%M:%S", timeinfo);

    va_start(args, format);
    vsnprintf(msgStr, sizeof(msgStr), format, args);
    va_end(args);

    if (session == NULL) {
        fprintf(stderr, "%s [%s] %s:%d - %s\n",
                timeStr, levelStrings[logLevel], file, line, msgStr);
        return;
    }

    pthread_mutex_lock(&session->logMutex);
    if (session->logFile != NULL) {
        fprintf(session->logFile, "%s [%s] %s:%d - %s\n",
                timeStr, levelStrings[logLevel], file, line, msgStr);
        fflush(session->logFile);
    } else {
        if (session->logLength == LOG_BUFFER_SIZE) {
            fprintf(stderr, "%s [WARNING] - memory log truncated\n", timeStr);
            session->logLength -= 1;
            session->logStartOffset =
                (session->logStartOffset + 1) % LOG_BUFFER_SIZE;
        }

        LEPDRV_LogEntry *entry = session->logBuffer +
                                 (session->logStartOffset + session->logLength) % LOG_BUFFER_SIZE;
        memcpy(&entry->timestamp, &rawtime, sizeof(time_t));
        strncpy(entry->message, msgStr, LOG_MAX_MESSAGE_LENGTH - 1);
        entry->message[LOG_MAX_MESSAGE_LENGTH - 1] = '\0';
        entry->level = logLevel;
        session->logLength += 1;
    }
    pthread_mutex_unlock(&session->logMutex);
}
