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

// Create a new session
LEPDRV_SessionHandle LEPDRV_Init(LEPDRV_DriverInfo *info);

// Gets the next (raw) frame of data from the device in degC (or degF)
int LEPDRV_GetFrame(LEPDRV_SessionHandle hndl, float *frameBuffer,
                    bool asFahrenheit);

// Close a session
int LEPDRV_Shutdown(LEPDRV_SessionHandle hndl);

#endif