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
    _driverLog(session, __FILE__, __LINE__, "DEBUG", fmt, ##__VA_ARGS__)
#define LOG_INFO(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, "INFO", fmt, ##__VA_ARGS__)
#define LOG_WARNING(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, "WARNING", fmt, ##__VA_ARGS__)
#define LOG_ERROR(fmt, ...) \
    _driverLog(session, __FILE__, __LINE__, "ERROR", fmt, ##__VA_ARGS__)

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

#define BAIL_ON_FAILED_SYS(cmd)                       \
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

typedef struct {
    LEP_CAMERA_PORT_DESC_T portDesc;
    pthread_t thread;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int spiFd;

    FILE *logFile;
    float frameBuffer[FRAME_WIDTH * FRAME_HEIGHT];
    LEPDRV_TemperatureUnit tempUnit;
    bool hasFrame, shutdownRequested, isRunning;
    int threadRtn;
} LEPDRV_Session;

/*********************************************************************
 * _driverLog - log an error message with variable arguments
 *********************************************************************/
void _driverLog(LEPDRV_Session *session,
                const char *file,
                const int line,
                const char *msgType,
                const char *format, ...) {
    time_t rawtime;
    struct tm *timeinfo;
    char timeStr[80], msgStr[4096];
    va_list args;

    time(&rawtime);
    timeinfo = localtime(&rawtime);
    strftime(timeStr, sizeof(timeStr), "%Y-%m-%d %H:%M:%S", timeinfo);

    va_start(args, format);
    vsnprintf(msgStr, sizeof(msgStr), format, args);
    va_end(args);

    fprintf(session->logFile, "%s [%s] %s:%d - %s\n",
            timeStr, msgType, file, line, msgStr);
    fflush(session->logFile);
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
    ssize_t bytesRead;

    while (session->shutdownRequested == false && failedAttempsRemaining > 0) {
        // Read from SPI until we see the start of a frame
        int tries = 1000;
        BAIL_ON_FAILED_SYS(
            _safeRead(session, session->spiFd, buff[0], PACKET_SIZE));
        while ((buff[0][0] & 0x0F) != 0 && buff[0][1] != 0 && tries-- > 0) {
            usleep(10000);
            BAIL_ON_FAILED_SYS(
                _safeRead(session, session->spiFd, buff[0], PACKET_SIZE));
        }
        if (tries == 0)
            continue;

        // After seeing the start of a frame, read the rest of the packets
        int goodPackets = 1;
        for (int p = 1; p < PACKETS_PER_FRAME; p++, goodPackets++) {
            BAIL_ON_FAILED_SYS(
                _safeRead(session, session->spiFd, buff[p], PACKET_SIZE));
            if ((buff[p][0] & 0x0F) != 0 || buff[p][1] != p)
                break;
        }

        // If we didn't see all the packetes in the frame, reboot the camera
        if (goodPackets != PACKETS_PER_FRAME) {
            LOG_DEBUG("Bad frame received (%d/%d packets), rebooting camera",
                      goodPackets, PACKETS_PER_FRAME);
            BAIL_ON_FAILED_LEP(LEPDRV_CameraDisable(session));
            BAIL_ON_FAILED_LEP(LEPDRV_CameraEnable(session));
            failedAttempsRemaining--;
            LOG_DEBUG("Camera rebooted remaining=%d",
                      failedAttempsRemaining - 1);
            continue;
        }

        // Updated the shared frame buffer and signal any waiters
        pthread_mutex_lock(&session->mutex);
        for (int i = 0; i < pixelsPerFrame; i++) {
            int r = i / FRAME_WIDTH, c = i % FRAME_WIDTH;
            uint16_t v = (buff[r][4 + 2 * c] << 8) + buff[r][4 + 2 * c + 1];
            float k = (float) v * 0.01f;
            if (session->tempUnit == LEPDRV_TEMP_UNITS_CELCIUS)
                k = k - 273.15f;
            else if (session->tempUnit == LEPDRV_TEMP_UNITS_FAHRENHEIT)
                k = ((k - 273.15f) * 9.0f / 5.0f) + 32.0f;

            session->frameBuffer[i] = k;
        }

        session->hasFrame = true;
        pthread_cond_signal(&session->cond);
        pthread_mutex_unlock(&session->mutex);
        failedAttempsRemaining = maxFailedAttempts;
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
    session->isRunning = false;
    return NULL;
}

/*********************************************************************
 * LEPDRV_Init - initialize the Lepton driver and camera
 *********************************************************************/
int LEPDRV_Init(LEPDRV_SessionHandle *hndlPtr, LEPDRV_DriverInfo *info) {
    if (hndlPtr == NULL)
        return -1;
    if (info == NULL)
        return -1;

    LEPDRV_Session localSession;
    memset(&localSession, 0, sizeof(LEPDRV_Session));
    LEPDRV_Session *session = &localSession;

    session->spiFd = open("/dev/spidev0.0", O_RDWR);
    session->tempUnit = LEPDRV_TEMP_UNITS_FAHRENHEIT;
    session->shutdownRequested = false;
    session->hasFrame = false;
    session->isRunning = false;
    session->logFile = stdout;
    session->threadRtn = 0;
    if (session->spiFd < 0)
        BAIL("Could not open SPI device");

    info->versionMajor = 1;
    info->versionMinor = 0;
    info->frameWidth = FRAME_WIDTH;
    info->frameHeight = FRAME_HEIGHT;

    session = (LEPDRV_Session *) calloc(1, sizeof(LEPDRV_Session));
    if (session == NULL)
        BAIL("Could not allocate memory for session");
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

    LOG_DEBUG("Starting SPI polling thread");

    unsigned char spiMode = SPI_MODE_3;
    unsigned char spiBitsPerWord = 8;
    unsigned int spiSpeed = 10000000;

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
    BAIL_ON_FAILED_LEP(LEP_SetSysFfcShutterModeObj(&session->portDesc, ffcMode));
    usleep(200000); // Wait for a second to allow FFC to complete

    LEP_SYS_AUX_TEMPERATURE_CELCIUS_T auxTemp;
    LEP_GetSysAuxTemperatureCelcius(&session->portDesc, &auxTemp);
    LOG_DEBUG("Starting aux temperature: %.2f F", auxTemp * 9.0f / 5.0f + 32.0f);

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&session->portDesc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&session->portDesc, LEP_OEM_ENABLE));

    // Verify settings
    LEP_RAD_ENABLE_E radState;
    LEP_AGC_ENABLE_E agcState;
    LEP_STATUS_T statusDesc;

    LEP_GetRadEnableState(&session->portDesc, &radState);
    LEP_GetAgcEnableState(&session->portDesc, &agcState);
    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));

    LOG_DEBUG("Camera status: %d", statusDesc.camStatus);
    LOG_DEBUG("Command count: %d", statusDesc.commandCount);
    LOG_DEBUG("Radiometry enabled: %d", radState);
    LOG_DEBUG("AGC enabled: %d", agcState);

    // Kickoff the driver thread
    BAIL_ON_FAILED_SYS(pthread_mutex_init(&session->mutex, NULL));
    BAIL_ON_FAILED_SYS(pthread_cond_init(&session->cond, NULL));
    BAIL_ON_FAILED_SYS(pthread_create(
        &session->thread, NULL, _spiPollingThreadMain, (void *) session));

    // Sync with thread before returning
    for( int i=0; i<1000 && !session->isRunning; i++)
        usleep(1000);
    if (!session->isRunning)
        BAIL("Somehow the polling thread never started");

    return 0;
}

/*********************************************************************
 * LEPDRV_GetFrame - capture a single frame from the Lepton camera
 *********************************************************************/
int LEPDRV_GetFrame(LEPDRV_SessionHandle hndl,
                    float *frameBuffer) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (!session->isRunning)
        BAIL("Frame requested before SPI polling thread started");
    if (session->shutdownRequested)
        BAIL("SDK is shutting down");

    pthread_mutex_lock(&session->mutex);
    while (session->hasFrame == false)
        pthread_cond_wait(&session->cond, &session->mutex);
    memcpy(frameBuffer, session->frameBuffer, sizeof(session->frameBuffer));
    session->hasFrame = false;
    pthread_mutex_unlock(&session->mutex);
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
    pthread_join(session->thread, &rtnval);
    pthread_mutex_destroy(&session->mutex);
    pthread_cond_destroy(&session->cond);

    BAIL_ON_FAILED_SYS(close(session->spiFd));
    BAIL_ON_FAILED_LEP(LEP_ClosePort(&session->portDesc));

    if (session->isRunning)
        LOG_ERROR("Somehow we shutdown but the session is still running");
    if (session->threadRtn)
        LOG_ERROR("SPI polling thread returned abnormally, rtn=%d", session->threadRtn);

    LOG_DEBUG("Driver shutdown complete");
    LEPDRV_SetLogFile(hndl, "stdout");
    free(session);
    return (0);
}

/*********************************************************************
 * LEPDRV_CheckIsRunning - check if the driver is running
 *********************************************************************/
int LEPDRV_CheckIsRunning(LEPDRV_SessionHandle *hndlPtr, bool *isRunning) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndlPtr;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (isRunning == NULL)
        BAIL("isRunning is NULL");

    *isRunning = session->isRunning;
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
 * LEPDRV_SetLogFile - set the log file for driver messages
 *********************************************************************/
int LEPDRV_SetLogFile(LEPDRV_SessionHandle hndl, char *logFilePath) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");
    if (logFilePath == NULL)
        BAIL("logFilePath is NULL");

    if (session->logFile != stdout && session->logFile != stderr)
        fclose(session->logFile);
    if (strncmp(logFilePath, "stdout", 6) == 0)
        session->logFile = stdout;
    else if (strncmp(logFilePath, "stderr", 6) == 0)
        session->logFile = stderr;
    else {
        FILE *newLogFile = fopen(logFilePath, "a");
        if (newLogFile == NULL)
            BAIL("Could not open log file %s", logFilePath);
        session->logFile = newLogFile;
    }

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

    LOG_DEBUG("Disabling camera");
    LEP_STATUS_T statusDesc;
    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_DEBUG("Camera status before: %d", statusDesc.camStatus);
    if (statusDesc.camStatus != LEP_SYSTEM_READY) {
        BAIL_ON_FAILED_LEP(LEP_RunOemPowerDown(&(session->portDesc)));
        usleep(50000);
        BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
        LOG_DEBUG("Camera status after disable: %d", statusDesc.camStatus);
    }

    return statusDesc.camStatus == LEP_SYSTEM_READY ? 0 : -1;
}

/*********************************************************************
 * LEPDRV_CameraEnable - enable the camera
 *********************************************************************/
int LEPDRV_CameraEnable(LEPDRV_SessionHandle hndl) {
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session == NULL)
        BAIL("SDK not initialized");

    LOG_DEBUG("Enabling camera");
    LEP_STATUS_T statusDesc;
    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_DEBUG("Camera status before: %d", statusDesc.camStatus);
    for (int i = 0; i < 20 && statusDesc.camStatus == LEP_SYSTEM_READY; i++) {
        usleep(250000);
        if (LEP_OK != LEP_RunOemPowerOn(&(session->portDesc)))
            continue;
        usleep(1500000);
        BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    }

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
    LOG_DEBUG("Camera status after enable: %d", statusDesc.camStatus);

    LOG_DEBUG("Enabling camera DONE");
    return statusDesc.camStatus != LEP_SYSTEM_READY ? 0 : -1;
}
