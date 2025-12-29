#ifndef __LEPTON_H__
#define __LEPTON_H__

#ifdef __cplusplus
extern "C"
{
#endif


#define LEPDRV_VERSION_MAJOR 1
#define LEPDRV_VERSION_MINOR 2

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef void *LEPDRV_SessionHandle;

typedef struct {
    uint8_t versionMajor;
    uint8_t versionMinor;
    uint16_t frameWidth;
    uint16_t frameHeight;
    uint32_t maxLogEntries;
} LEPDRV_DriverInfo;

typedef enum {
    LEPDRV_TEMP_UNITS_KELVIN = 0,
    LEPDRV_TEMP_UNITS_CELCIUS,
    LEPDRV_TEMP_UNITS_FAHRENHEIT,
    LEPDRV_TEMP_UNITS_MAX
} LEPDRV_TemperatureUnit;

typedef enum {
    LEPDRV_LOG_LEVEL_DEBUG = 0,
    LEPDRV_LOG_LEVEL_INFO,
    LEPDRV_LOG_LEVEL_WARNING,
    LEPDRV_LOG_LEVEL_ERROR,
    LEPDRV_LOG_LEVEL_CRITICAL,
    LEPDRV_LOG_LEVEL_MAX
} LEPDRV_LogLevel;

// Create a new session
int LEPDRV_Init(LEPDRV_SessionHandle *hndlPtr,
                LEPDRV_DriverInfo *info,
                const char *logFilePath);

// Start the SPI polling thread
int LEPDRV_StartPolling(LEPDRV_SessionHandle hndl);

// disable the camera and put it into power down mode
int LEPDRV_CameraDisable(LEPDRV_SessionHandle hndl);

// enable the camera
int LEPDRV_CameraEnable(LEPDRV_SessionHandle hndl);

// Set temperature units for frames
int LEPDRV_SetTemperatureUnits(LEPDRV_SessionHandle hndl,
                               LEPDRV_TemperatureUnit unit);

// Get the next log entry from the driver, in the case the log file
// was set to NULL
int LEPDRV_GetNextLogEntry(LEPDRV_SessionHandle hndl,
                           LEPDRV_LogLevel *level,
                           char *buffer, size_t bufferLen);

// Gets the next (raw) frame of data from the device in degC (or degF)
int LEPDRV_GetFrame(LEPDRV_SessionHandle hndl, float *frameBuffer);

// Close a session
int LEPDRV_Shutdown(LEPDRV_SessionHandle hndl);

#ifdef __cplusplus
}
#endif

#endif