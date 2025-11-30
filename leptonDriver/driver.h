#ifndef __LEPTON_H__
#define __LEPTON_H__

#include <stdint.h>
#include <stdbool.h>

typedef void *LEPSDK_SessionHandle;

typedef struct
{
    uint8_t versionMajor;
    uint8_t versionMinor;
    uint16_t frameWidth;
    uint16_t frameHeight;
} LEPSDK_DriverInfo;

// Create a new session
LEPSDK_SessionHandle LEPSDK_Init(LEPSDK_DriverInfo *info);

// Gets the next (raw) frame of data from the device in degC (or degF)
int LEPSDK_GetFrame(
    LEPSDK_SessionHandle hndl, float *frameBuffer, bool asFahrenheit);

// Close a session
int LEPSDK_Shutdown(LEPSDK_SessionHandle hndl);

#endif