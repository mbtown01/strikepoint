#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <linux/types.h>
#include <memory.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
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

#define ASSERT_CALL_SYS(cmd)                                                   \
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
    bool asFahrenheit;

    pthread_t thread;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    float frameBuffer[FRAME_WIDTH * FRAME_HEIGHT];
    bool hasFrame;
    bool shutdownRequested;
} LEPDRV_Session;

void *_threadMain(void *arg);

/*********************************************************************
 * LEPDRV_Init - initialize the Lepton driver and camera
 *********************************************************************/
int LEPDRV_Init(LEPDRV_SessionHandle *hndlPtr, LEPDRV_DriverInfo *info) {
    if (hndlPtr == NULL)
        return -1;
    if (info == NULL)
        return -1;

    LEPDRV_Session localSession;
    LEPDRV_Session *session = &localSession;

    session->spiMode = SPI_MODE_3;
    session->spiBitsPerWord = 8;
    session->spiSpeed = 10000000;
    session->spiFd = open("/dev/spidev0.0", O_RDWR);
    if (session->spiFd < 0)
        ERROR("Error - Could not open SPI device");

    ASSERT_CALL_SYS(
        ioctl(session->spiFd, SPI_IOC_WR_MODE, &session->spiMode));
    ASSERT_CALL_SYS(
        ioctl(session->spiFd, SPI_IOC_RD_MODE, &session->spiMode));
    ASSERT_CALL_SYS(
        ioctl(session->spiFd, SPI_IOC_WR_BITS_PER_WORD, &session->spiBitsPerWord));
    ASSERT_CALL_SYS(
        ioctl(session->spiFd, SPI_IOC_RD_BITS_PER_WORD, &session->spiBitsPerWord));
    ASSERT_CALL_SYS(
        ioctl(session->spiFd, SPI_IOC_WR_MAX_SPEED_HZ, &session->spiSpeed));
    ASSERT_CALL_SYS(
        ioctl(session->spiFd, SPI_IOC_RD_MAX_SPEED_HZ, &session->spiSpeed));

    // Initialize and open the camera port (example values)
    session->portDesc.portType = LEP_CCI_TWI;
    session->portDesc.portID = 99;
    session->portDesc.deviceAddress = 0x2A;               // Example I2C address
    session->portDesc.portBaudRate = (LEP_UINT16) 400000; // 400 kHz
    ASSERT_CALL_LEP(LEP_OpenPort(1, LEP_CCI_TWI, 400, &session->portDesc));

    ASSERT_CALL_LEP(LEP_SetAgcEnableState(&session->portDesc, LEP_AGC_DISABLE));
    ASSERT_CALL_LEP(LEP_SetRadEnableState(&session->portDesc, LEP_RAD_ENABLE));

    LEP_SYS_FFC_SHUTTER_MODE_OBJ_T ffcMode;
    ffcMode.shutterMode = LEP_SYS_FFC_SHUTTER_MODE_MANUAL;
    ffcMode.tempLockoutState = LEP_SYS_SHUTTER_LOCKOUT_INACTIVE;
    ASSERT_CALL_LEP(LEP_SetSysFfcShutterModeObj(&session->portDesc, ffcMode));
    usleep(200000); // Wait for a second to allow FFC to complete

    ASSERT_CALL_LEP(LEP_RunSysFFCNormalization(&session->portDesc));
    ASSERT_CALL_LEP(
        LEP_SetOemVideoOutputEnable(&session->portDesc, LEP_OEM_ENABLE));

    // Verify settings
    LEP_RAD_ENABLE_E radState;
    LEP_AGC_ENABLE_E agcState;
    LEP_STATUS_T statusDesc;

    LEP_GetRadEnableState(&session->portDesc, &radState);
    LEP_GetAgcEnableState(&session->portDesc, &agcState);
    ASSERT_CALL_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));

    printf("Camera status: %d\n", statusDesc.camStatus);
    printf("Command count: %d\n", statusDesc.commandCount);
    printf("Radiometry enabled: %d\n", radState);
    printf("AGC enabled: %d\n", agcState);

    info->versionMajor = 1;
    info->versionMinor = 0;
    info->frameWidth = FRAME_WIDTH;
    info->frameHeight = FRAME_HEIGHT;

    // Once successful startup, malloc and assign final session handle
    session = (LEPDRV_Session *) malloc(sizeof(LEPDRV_Session));
    memcpy(session, &localSession, sizeof(LEPDRV_Session));
    hndlPtr[0] = (LEPDRV_SessionHandle) session;

    // Kickoff the driver thread
    ASSERT_CALL_SYS(pthread_mutex_init(&session->mutex, NULL));
    ASSERT_CALL_SYS(pthread_cond_init(&session->cond, NULL));
    session->asFahrenheit = true;
    session->shutdownRequested = false;
    session->hasFrame = false;
    ASSERT_CALL_SYS(pthread_create(
        &session->thread, NULL, _threadMain, (void *) session));

    return 0;
}

/*********************************************************************
 * LEPDRV_GetFrame - capture a single frame from the Lepton camera
 *********************************************************************/
int LEPDRV_GetFrame(LEPDRV_SessionHandle hndl,
                    float *frameBuffer,
                    bool asFahrenheit) {
    if (hndl == NULL)
        ERROR("SDK not initialized");
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;
    if (session->shutdownRequested)
        ERROR("SDK is shutting down");

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
    if (hndl == NULL)
        ERROR("SDK not initialized");
    LEPDRV_Session *session = (LEPDRV_Session *) hndl;

    session->shutdownRequested = true;
    pthread_join(session->thread, NULL);
    pthread_mutex_destroy(&session->mutex);
    pthread_cond_destroy(&session->cond);

    ASSERT_CALL_SYS(close(session->spiFd));
    ASSERT_CALL_LEP(LEP_ClosePort(&session->portDesc));

    free(session);
    return (0);
}

/*********************************************************************
 * _driverMain - Driver logic main loop
 *********************************************************************/
int _driverMain(LEPDRV_Session *session) {
    uint8_t buff[PACKETS_PER_FRAME][PACKET_SIZE];
    float floatBuffer[FRAME_WIDTH * FRAME_HEIGHT];
    const int maxFailedAttempts = 30;
    int failedAttempsRemaining = maxFailedAttempts;
    CRC16 lastCrc = 0;

    while (session->shutdownRequested == false && failedAttempsRemaining > 0) {
        int tries = 1000;
        read(session->spiFd, buff[0], PACKET_SIZE);
        while (buff[0][0] & 0x0F != 0 && buff[0][1] != 0 && tries-- > 0) {
            usleep(10000);
            read(session->spiFd, buff[0], PACKET_SIZE);
        }
        if (tries == 0)
            continue;

        // printf("[HDR] tries=%d %02x %02x %02x %02x\n",
        //        tries, buff[0][0], buff[0][1], buff[0][3], buff[0][3]);
        int goodPackets = 1;
        for (int p = 1; p < PACKETS_PER_FRAME; p++, goodPackets++) {
            read(session->spiFd, buff[p], PACKET_SIZE);
            if (buff[p][0] & 0x0F != 0 || buff[p][1] != p) {
                // printf("[BAD] p=%d %02x %02x %02x %02x\n", p, buff[0][0],
                //        buff[0][1], buff[0][3], buff[0][3]);
                break;
            }
        }

        if (goodPackets != PACKETS_PER_FRAME) {
            printf("REBOOTING CAMERA...\n");

            LEP_STATUS_T statusDesc;
            ASSERT_CALL_LEP(LEP_RunOemPowerDown(&(session->portDesc)));
            ASSERT_CALL_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
            for (int i = 0; i < 20 && statusDesc.camStatus == LEP_SYSTEM_READY; i++) {
                usleep(250000);
                if (LEP_OK != LEP_RunOemPowerOn(&(session->portDesc)))
                    continue;

                usleep(500000);
                ASSERT_CALL_LEP(LEP_GetSysStatus(&session->portDesc, &statusDesc));
            }

            if (statusDesc.camStatus == LEP_SYSTEM_READY) {
                printf("Camera failed to come back online\n");
                return -1;
            } 

            failedAttempsRemaining--;
            continue;
        }

        for (int i = 0; i < FRAME_WIDTH * FRAME_HEIGHT; i++) {
            int r = i / FRAME_WIDTH, c = i % FRAME_WIDTH;
            uint16_t v = (buff[r][4 + 2 * c] << 8) + buff[r][4 + 2 * c + 1];
            floatBuffer[i] = (float) v * 0.01f - 273.15f; // Convert to Celsius
        }
        if (session->asFahrenheit)
            for (int i = 0; i < FRAME_WIDTH * FRAME_HEIGHT; i++)
                floatBuffer[i] = (floatBuffer[i] * 9.0f / 5.0f) + 32.0f;

        CRC16 crc = CalcCRC16Bytes(sizeof(floatBuffer), (char *) floatBuffer);
        if (crc != lastCrc) {
            pthread_mutex_lock(&session->mutex);
            memcpy(session->frameBuffer, floatBuffer, sizeof(session->frameBuffer));
            session->hasFrame = true;
            pthread_cond_signal(&session->cond); // wake any waiters
            pthread_mutex_unlock(&session->mutex);
            failedAttempsRemaining = maxFailedAttempts;
            lastCrc = crc;
        }
    }

    if (failedAttempsRemaining == 0) {
        printf("ERROR: Too many consecutive frame capture failures, exiting\n");
        return -1;
    }

    return 0;
}

/*********************************************************************
 * _threadMain - pthread entry point
 *********************************************************************/
void *_threadMain(void *arg) {
    LEPDRV_Session *session = (LEPDRV_Session *) arg;
    _driverMain(session);
    printf("_threadMain exiting\n");
    return NULL;
}
