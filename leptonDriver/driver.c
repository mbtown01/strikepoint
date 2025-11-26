#include <stdio.h>
#include <unistd.h>
#include <memory.h>
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/types.h>
#include <linux/spi/spidev.h>

#include "driver.h"
#include "LEPTON_SDK.h"
#include "LEPTON_ErrorCodes.h"
#include "LEPTON_VID.h"
#include "LEPTON_SYS.h"
#include "LEPTON_OEM.h"

#define PACKET_SIZE 4 + 2 * FRAME_WIDTH
#define PACKETS_PER_FRAME FRAME_HEIGHT

typedef struct
{
    LEP_CAMERA_PORT_DESC_T portDesc;
    unsigned char spiMode;
    unsigned char spiBitsPerWord;
    unsigned int spiSpeed;
    int spiFd;
} LEPSDK_SessionInfo;

LEPSDK_SessionInfo *_gblSession = NULL;
char _glbErrorMsg[4096] = {0};

int LEPSDK_InitSpi()
{
    if (_gblSession != NULL)
        LEP_ERROR("SDK already initialized");

    int rtn;
    LEPSDK_SessionInfo session;
    session.spiMode = SPI_MODE_3;
    session.spiBitsPerWord = 8;
    session.spiSpeed = 10000000;
    session.spiFd = open("/dev/spidev0.0", O_RDWR);
    if (session.spiFd < 0)
        LEP_ERROR("Error - Could not open SPI device");

    rtn = ioctl(session.spiFd, SPI_IOC_WR_MODE, &session.spiMode);
    if (rtn < 0)
        LEP_ERROR("Could not set SPIMode (WR)...ioctl fail");

    rtn = ioctl(session.spiFd, SPI_IOC_RD_MODE, &session.spiMode);
    if (rtn < 0)
        LEP_ERROR("Could not set SPIMode (RD)...ioctl fail");

    rtn = ioctl(session.spiFd, SPI_IOC_WR_BITS_PER_WORD, &session.spiBitsPerWord);
    if (rtn < 0)
        LEP_ERROR("Could not set SPI bitsPerWord (WR)...ioctl fail");

    rtn = ioctl(session.spiFd, SPI_IOC_RD_BITS_PER_WORD, &session.spiBitsPerWord);
    if (rtn < 0)
        LEP_ERROR("Could not set SPI bitsPerWord (RD)...ioctl fail");

    rtn = ioctl(session.spiFd, SPI_IOC_WR_MAX_SPEED_HZ, &session.spiSpeed);
    if (rtn < 0)
        LEP_ERROR("Could not set SPI speed (WR)...ioctl fail");

    rtn = ioctl(session.spiFd, SPI_IOC_RD_MAX_SPEED_HZ, &session.spiSpeed);
    if (rtn < 0)
        LEP_ERROR("Could not set SPI speed (RD)...ioctl fail");

    _gblSession = (LEPSDK_SessionInfo *)malloc(sizeof(LEPSDK_SessionInfo));
    memcpy(_gblSession, &session, sizeof(LEPSDK_SessionInfo));
    return (0);
}

int LEPSDK_CloseSpi()
{
    if (_gblSession == NULL)
        LEP_ERROR("SDK not initialized");

    int rtn = close(_gblSession->spiFd);
    if (rtn < 0)
        LEP_ERROR("Error - Could not close SPI device");

    return (0);
}

int LEPSDK_InitI2C()
{
    LEP_STATUS_T statusDesc;

    // Initialize and open the camera port (example values)
    _gblSession->portDesc.portType = LEP_CCI_TWI;
    _gblSession->portDesc.portID = 99;
    _gblSession->portDesc.deviceAddress = 0x2A;              // Example I2C address
    _gblSession->portDesc.portBaudRate = (LEP_UINT16)400000; // 400 kHz
    LEP_ASSERT_ZERO(LEP_OpenPort(1, LEP_CCI_TWI, 400, &_gblSession->portDesc));

    // Check the system status
    LEP_ASSERT_ZERO(LEP_GetSysStatus(&_gblSession->portDesc, &statusDesc));
    printf("Camera Status: %d, Command Count: %d\n",
           statusDesc.camStatus, statusDesc.commandCount);

    // LEP_POLARITY_E polarityDesc;
    // LEP_ASSERT(LEP_GetVidPolarity(&_gblSession->portDesc, &polarityDesc));
    // printf("Video Polarity: %d\n", polarityDesc);

    LEP_ASSERT_ZERO(LEP_RunSysFFCNormalization(&_gblSession->portDesc));
    usleep(500000); // Wait for a second to allow FFC to complete

    // // Check the system status
    // LEP_ASSERT(LEP_GetSysStatus(&_gblSession->portDesc, &statusDesc));
    // printf("Camera Status: %d, Command Count: %d\n",
    //        statusDesc.camStatus, statusDesc.commandCount);

    return 0;
}

int LEPSDK_CloseI2C()
{
    if (_gblSession == NULL)
        LEP_ERROR("SDK not initialized");

    // Close the camera port
    LEP_ASSERT_ZERO(LEP_ClosePort(&_gblSession->portDesc));

    return (0);
}

int LEPSDK_Init(LEPSDK_DriverInfo *info)
{
    if (NULL == info)
        LEP_ERROR("Invalid argument: info is NULL");

    if (0 != LEPSDK_InitSpi())
        return -1;

    if (0 != LEPSDK_InitI2C())
        return -1;

    info->versionMajor = 1;
    info->versionMinor = 0;
    info->frameWidth = FRAME_WIDTH; 
    info->frameHeight = FRAME_HEIGHT;  

    return (0);
}

int LEPSDK_GetFrame(float *frameBuffer, bool asFahrenheit)
{
    if (_gblSession == NULL)
        LEP_ERROR("SDK not initialized");

    uint8_t buff[PACKETS_PER_FRAME][PACKET_SIZE];

    for (int attempt = 0; attempt < 30; attempt)
    {
        int tries = 1000;
        read(_gblSession->spiFd, buff[0], PACKET_SIZE);
        for (; buff[0][0] & 0x0F != 0 && buff[0][1] != 0 && tries > 0; tries--)
        {
            usleep(1000);
            read(_gblSession->spiFd, buff[0], PACKET_SIZE);
        }
        if (tries == 0)
            LEP_ERROR("Could not sync to packet start");

        int goodPackets = 1;
        for (int p = 1; p < PACKETS_PER_FRAME; p++)
        {
            read(_gblSession->spiFd, buff[p], PACKET_SIZE);
            if (buff[p][0] & 0x0F != 0 || buff[p][1] != p)
                break;
            goodPackets++;
        }

        if (goodPackets != PACKETS_PER_FRAME)
        {
            printf("[REBOOT]");
            LEPSDK_CloseSpi();
            LEP_ASSERT_ZERO(LEP_RunOemReboot(&(_gblSession->portDesc)));
            usleep(750000);
            LEPSDK_InitSpi();
            continue;
        }

        for (int i = 0; i < FRAME_WIDTH * FRAME_HEIGHT; i++)
        {
            int r = i / FRAME_WIDTH, c = i % FRAME_WIDTH;
            uint16_t v = (buff[r][4 + 2 * c] << 8) + buff[r][4 + 2 * c + 1];
            frameBuffer[i] = (float)v * 0.01f - 273.15f; // Convert to Celsius
            if (asFahrenheit)
                frameBuffer[i] = (frameBuffer[i] * 9.0f / 5.0f) + 32.0f;
        }

        return 0;
    }

    LEP_ERROR("Could not read frame after multiple attempts");
}

int LEPSDK_Shutdown()
{
    if (_gblSession == NULL)
        LEP_ERROR("SDK not initialized");

    LEPSDK_CloseSpi();
    LEPSDK_CloseI2C();

    free(_gblSession);
    _gblSession = NULL;
    return (0);
}
