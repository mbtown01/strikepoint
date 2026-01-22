
#ifndef __DRIVER_H__
#define __DRIVER_H__

// #include "logging.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void *SPLIB_SessionHandle;

typedef struct {
        uint8_t versionMajor;
        uint8_t versionMinor;
        uint16_t frameWidth;
        uint16_t frameHeight;
} SPLIB_DriverInfo;

typedef enum {
    SPLIB_TEMP_UNITS_KELVIN = 0,
    SPLIB_TEMP_UNITS_CELCIUS,
    SPLIB_TEMP_UNITS_FAHRENHEIT,
    SPLIB_TEMP_UNITS_MAX
} SPLIB_TemperatureUnit;

// Create a new session
int SPLIB_Init(SPLIB_SessionHandle *hndlPtr,
               SPLIB_DriverInfo *info,
               const char *logFilePath);

// Start the SPI polling thread
int SPLIB_LeptonStartPolling(SPLIB_SessionHandle hndl);

// disable the camera and put it into power down mode
int SPLIB_LeptonDisable(SPLIB_SessionHandle hndl);

// enable the camera
int SPLIB_LeptonEnable(SPLIB_SessionHandle hndl);

// Set temperature units for frames
int SPLIB_LeptonSetTemperatureUnits(SPLIB_SessionHandle hndl,
                                    SPLIB_TemperatureUnit unit);

// Gets the next (raw) frame of data from the device in degC (or degF)
int SPLIB_LeptonGetFrame(SPLIB_SessionHandle hndl, float *frameBuffer);

// Get the next log entry from the driver, in the case the log file
// was set to NULL
int SPLIB_GetNextLogEntry(SPLIB_SessionHandle hndl,
                          int *logLevel,
                          char *buffer,
                          size_t bufferLen,
                          int *msgRemaining);

// Close a session
int SPLIB_Shutdown(SPLIB_SessionHandle hndl);

#ifdef __cplusplus
}
#endif

#endif