#ifndef __LEPTON_H__
#define __LEPTON_H__

#include <stdint.h>
#include <stdbool.h>

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60

#define LEP_ERROR(msg)                                                \
    do                                                                \
    {                                                                 \
        printf("ERROR in %s line %d: %s\n", __FILE__, __LINE__, msg); \
        return -1;                                                    \
    } while (0)

#define LEP_ASSERT_ZERO(cmd)                                                            \
    do                                                                                  \
    {                                                                                   \
        LEP_RESULT result = cmd;                                                        \
        if (result != LEP_OK)                                                           \
        {                                                                               \
            printf("ERROR in %s line %d: %d = %s\n", __FILE__, __LINE__, result, #cmd); \
            return result;                                                              \
        }                                                                               \
    } while (0)

typedef struct {
    uint8_t versionMajor;
    uint8_t versionMinor;
    uint16_t frameWidth;
    uint16_t frameHeight;
} LEPSDK_DriverInfo;

int LEPSDK_Init(LEPSDK_DriverInfo *info);
int LEPSDK_GetFrame(float *frameBuffer, bool asFahrenheit);
int LEPSDK_Shutdown();

#endif