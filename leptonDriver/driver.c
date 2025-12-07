#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <linux/types.h>
#include <memory.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "LEPTON_ErrorCodes.h"
#include "LEPTON_OEM.h"
#include "LEPTON_RAD.h"
#include "LEPTON_SDK.h"
#include "LEPTON_SYS.h"
#include "LEPTON_VID.h"
#include "LEPTON_Types.h"
#include "LEPTON_AGC.h"
#include "crc16.h"
#include "driver.h"

#define ERROR(msg)                                               \
    do {                                                         \
        printf("ERROR at %s:%d: %s\n", __FILE__, __LINE__, msg); \
        return -1;                                               \
    } while (0)

#define ASSERT_CALL_LEP(cmd)                                               \
    do {                                                                   \
        LEP_RESULT rtn = cmd;                                              \
        if (rtn != LEP_OK) {                                               \
            printf("ERROR at %s:%d: Call to '%s' returned %d\n", __FILE__, \
                   __LINE__, #cmd, rtn);                                   \
            return rtn;                                                    \
        }                                                                  \
    } while (0)

#define ASSERT_CALL_IO(cmd)                                                    \
    do {                                                                       \
        int rtn = cmd;                                                         \
        if (rtn < 0) {                                                         \
            printf("ERROR at %s:%d: Call to '%s' returned %d: %s\n", __FILE__, \
                   __LINE__, #cmd, rtn, strerror(errno));                      \
            return rtn;                                                        \
        }                                                                      \
    } while (0)

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60
#define PACKET_SIZE 4 + 2 * FRAME_WIDTH
#define PACKETS_PER_FRAME FRAME_HEIGHT

typedef struct {
    LEP_CAMERA_PORT_DESC_T portDesc;
    unsigned char spiMode;
    unsigned char spiBitsPerWord;
    unsigned int spiSpeed;
    int spiFd;
} LEPDRV_Session;

int _initSpi(LEPDRV_Session *session) {
    int rtn;
    session->spiMode = SPI_MODE_3;
    session->spiBitsPerWord = 8;
    session->spiSpeed = 10000000;
    session->spiFd = open("/dev/spidev0.0", O_RDWR);
    if (session->spiFd < 0)
        ERROR("Error - Could not open SPI device");

    ASSERT_CALL_IO(
        ioctl(session->spiFd, SPI_IOC_WR_MODE, &session->spiMode));
    ASSERT_CALL_IO(
        ioctl(session->spiFd, SPI_IOC_RD_MODE, &session->spiMode));
    ASSERT_CALL_IO(
        ioctl(session->spiFd, SPI_IOC_WR_BITS_PER_WORD, &session->spiBitsPerWord));
    ASSERT_CALL_IO(
        ioctl(session->spiFd, SPI_IOC_RD_BITS_PER_WORD, &session->spiBitsPerWord));
    ASSERT_CALL_IO(
        ioctl(session->spiFd, SPI_IOC_WR_MAX_SPEED_HZ, &session->spiSpeed));
    ASSERT_CALL_IO(
        ioctl(session->spiFd, SPI_IOC_RD_MAX_SPEED_HZ, &session->spiSpeed));

    return (0);
}

int _closeSpi(LEPDRV_Session *session) {
    int rtn = close(session->spiFd);
    if (rtn < 0)
        ERROR("Error - Could not close SPI device");

    return (0);
}

int _initI2C(LEPDRV_Session *session) {
    LEP_STATUS_T statusDesc;

    // Initialize and open the camera port (example values)
    session->portDesc.portType = LEP_CCI_TWI;
    session->portDesc.portID = 99;
    session->portDesc.deviceAddress = 0x2A;               // Example I2C address
    session->portDesc.portBaudRate = (LEP_UINT16) 400000; // 400 kHz
    ASSERT_CALL_LEP(LEP_OpenPort(1, LEP_CCI_TWI, 400, &session->portDesc));

    // Check the system status
    ASSERT_CALL_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));

    /***************************************************************************
     * 1. DISABLE AGC  (critical for real temperature deltas)
     ***************************************************************************/
    ASSERT_CALL_LEP(LEP_SetAgcEnableState(&session->portDesc, LEP_AGC_DISABLE));

    /***************************************************************************
     * 2. ENABLE RADIOMETRY (ensures RAW14 has stable temperature relation)
     ***************************************************************************/
    ASSERT_CALL_LEP(LEP_SetRadEnableState(&session->portDesc, LEP_RAD_ENABLE));

    /***************************************************************************
     * 3. SET FFC MODE TO MANUAL
     ***************************************************************************/
    LEP_SYS_FFC_SHUTTER_MODE_OBJ_T ffcMode;
    ffcMode.shutterMode = LEP_SYS_FFC_SHUTTER_MODE_MANUAL;
    ffcMode.tempLockoutState = LEP_SYS_SHUTTER_LOCKOUT_INACTIVE;
    ASSERT_CALL_LEP(LEP_SetSysFfcShutterModeObj(&session->portDesc, ffcMode));

    /***************************************************************************
     * 4. INITIAL FFC NORMALIZATION (do this once after warm-up)
     ***************************************************************************/
    ASSERT_CALL_LEP(LEP_RunSysFFCNormalization(&session->portDesc));

    /***************************************************************************
     * 6. ENABLE TELEMETRY (helps normalize data per frame)
     ***************************************************************************/
    ASSERT_CALL_LEP(
        LEP_SetOemVideoOutputEnable(&session->portDesc, LEP_OEM_ENABLE));

    // LEP_OEM_THERMAL_SHUTDOWN_ENABLE_T thermalShutdownEnable;
    // thermalShutdownEnable.oemThermalShutdownEnable = LEP_OEM_ENABLE;
    // ASSERT_CALL_LEP(LEP_SetOemThermalShutdownEnable(&port,
    // thermalShutdownEnable));
    // ASSERT_CALL_LEP(LEP_SetOemTelemetryEnableState(&port, LEP_OEM_ENABLE));

    /***************************************************************************
     * 7. VERIFY SETTINGS
     ***************************************************************************/
    LEP_RAD_ENABLE_E radState;
    LEP_AGC_ENABLE_E agcState;

    usleep(200000); // Wait for a second to allow FFC to complete

    LEP_GetRadEnableState(&session->portDesc, &radState);
    LEP_GetAgcEnableState(&session->portDesc, &agcState);
    ASSERT_CALL_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));

    printf("Camera status: %d\n", statusDesc.camStatus);
    printf("Command count: %d\n", statusDesc.commandCount);
    printf("Radiometry enabled: %d\n", radState);
    printf("AGC enabled: %d\n", agcState);

    /***************************************************************************
     * Camera is now configured for optimal small-delta detection
     ***************************************************************************/

    return 0;
}

int _closeI2C(LEPDRV_Session *session) {
    if (session == NULL)
        ERROR("SDK not initialized");

    // Close the camera port
    ASSERT_CALL_LEP(LEP_ClosePort(&session->portDesc));

    return (0);
}

LEPDRV_SessionHandle LEPDRV_Init(LEPDRV_DriverInfo *info) {
    if (NULL == info)
        return NULL;

    LEPDRV_Session localSession;
    if (0 != _initSpi(&localSession))
        return NULL;
    if (0 != _initI2C(&localSession))
        return NULL;

    info->versionMajor = 1;
    info->versionMinor = 0;
    info->frameWidth = FRAME_WIDTH;
    info->frameHeight = FRAME_HEIGHT;

    LEPDRV_Session *session = (LEPDRV_Session *) malloc(sizeof(LEPDRV_Session));
    memcpy(session, &localSession, sizeof(LEPDRV_Session));
    return session;
}

int LEPDRV_GetFrame(LEPDRV_SessionHandle hndl, float *frameBuffer,
                    bool asFahrenheit) {
    if (hndl == NULL)
        ERROR("SDK not initialized");
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;

    uint8_t buff[PACKETS_PER_FRAME][PACKET_SIZE];
    int failedAttemptCount = 0;

    while (failedAttemptCount < 30) {
        int tries = 10000;
        read(session->spiFd, buff[0], PACKET_SIZE);
        for (; (buff[0][0] & 0x0F) != 0 && buff[0][1] != 0 && tries > 0;
             tries--) {
            usleep(1000);
            read(session->spiFd, buff[0], PACKET_SIZE);
        }
        if (tries == 0)
            ERROR("Could not sync to packet start");

        // printf("[HDR] tries=%d %02x %02x %02x %02x\n",
        //        tries, buff[0][0], buff[0][1], buff[0][3], buff[0][3]);
        int goodPackets = 1;
        for (int p = 1; p < PACKETS_PER_FRAME; p++, goodPackets++) {
            read(session->spiFd, buff[p], PACKET_SIZE);
            if (buff[p][0] & 0x0F != 0 || buff[p][1] != p) {
                printf("[BAD] p=%d %02x %02x %02x %02x\n", p, buff[0][0],
                       buff[0][1], buff[0][3], buff[0][3]);
                break;
            }
        }

        if (goodPackets != PACKETS_PER_FRAME) {
            printf("[WAIT] only received %d good packets\n", goodPackets);
            // _closeSpi(session);
            // ASSERT_CALL_LEP(LEP_RunOemReboot(&(session->portDesc)));
            usleep(50000);
            ++failedAttemptCount;
            continue;
        }

        failedAttemptCount = 0;
        for (int i = 0; i < FRAME_WIDTH * FRAME_HEIGHT; i++) {
            int r = i / FRAME_WIDTH, c = i % FRAME_WIDTH;
            uint16_t v = (buff[r][4 + 2 * c] << 8) + buff[r][4 + 2 * c + 1];
            frameBuffer[i] = (float) v * 0.01f - 273.15f; // Convert to Celsius
            if (asFahrenheit)
                frameBuffer[i] = (frameBuffer[i] * 9.0f / 5.0f) + 32.0f;
        }

        // printf("Frame\n");

        return 0;
    }

    ERROR("Could not read frame after multiple attempts");
}

int LEPDRV_Shutdown(LEPDRV_SessionHandle hndl) {
    if (hndl == NULL)
        ERROR("SDK not initialized");
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;

    _closeSpi(session);
    _closeI2C(session);
    free(session);
    return (0);
}
