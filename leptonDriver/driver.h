#ifndef __LEPTON_H__
#define __LEPTON_H__

#include <stdbool.h>
#include <stdint.h>

typedef void *LEPDRV_SessionHandle;

typedef struct {
    uint8_t versionMajor;
    uint8_t versionMinor;
    uint16_t frameWidth;
    uint16_t frameHeight;
} LEPDRV_DriverInfo;

typedef enum {
    LEPDRV_TEMP_UNITS_KELVIN = 0,
    LEPDRV_TEMP_UNITS_CELCIUS,
    LEPDRV_TEMP_UNITS_FAHRENHEIT,
    LEPDRV_TEMP_UNITS_MAX
} LEPDRV_TemperatureUnit;

// Create a new session
int LEPDRV_Init(
    LEPDRV_SessionHandle *hndlPtr, LEPDRV_DriverInfo *info);

// Start the SPI polling thread
int LEPDRV_StartPolling(LEPDRV_SessionHandle hndl);

// Check if the driver is running
int LEPDRV_CheckIsRunning(
    LEPDRV_SessionHandle *hndlPtr, bool *isRunning);

    // disable the camera and put it into power down mode
int LEPDRV_CameraDisable(LEPDRV_SessionHandle hndl);

// enable the camera
int LEPDRV_CameraEnable(LEPDRV_SessionHandle hndl);

// Set temperature units for frames
int LEPDRV_SetTemperatureUnits(
    LEPDRV_SessionHandle hndl, LEPDRV_TemperatureUnit unit);

// Set the log file for driver messages
int LEPDRV_SetLogFile(
    LEPDRV_SessionHandle hndl, char *logFilePath);

// Gets the next (raw) frame of data from the device in degC (or degF)
int LEPDRV_GetFrame(
    LEPDRV_SessionHandle hndl, float *frameBuffer);

// Close a session
int LEPDRV_Shutdown(LEPDRV_SessionHandle hndl);

#endif