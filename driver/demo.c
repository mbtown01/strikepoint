#include "LEPTON_SDK.h"
#include "LEPTON_ErrorCodes.h"
#include "LEPTON_VID.h"
#include "LEPTON_SYS.h"
#include "LEPTON_OEM.h"
#include "driver.h"
#include <stdio.h>
#include <unistd.h>
#include <memory.h>

#define LEP_ASSERT(cmd)                                     \
    do                                                      \
    {                                                       \
        LEP_RESULT result = cmd;                            \
        if (result != LEP_OK)                               \
        {                                                   \
            printf("Error calling %s: %d\n", #cmd, result); \
            return result;                                  \
        }                                                   \
    } while (0)

#include <stdint.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <getopt.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/types.h>
#include <linux/spi/spidev.h>

#define PACKET_SIZE 164
#define PACKET_SIZE_UINT16 (PACKET_SIZE / 2)
#define PACKETS_PER_FRAME 60
#define FRAME_SIZE_UINT16 (PACKET_SIZE_UINT16 * PACKETS_PER_FRAME)
#define FPS 27;

int spi_cs0_fd = -1;
int spi_cs1_fd = -1;

unsigned char spi_mode = SPI_MODE_3;
unsigned char spi_bitsPerWord = 8;
unsigned int spi_speed = 10000000;

int SpiOpenPort(int spi_device, unsigned int useSpiSpeed)
{
    int status_value = -1;
    int *spi_cs_fd;

    //----- SET SPI MODE -----
    // SPI_MODE_0 (0,0)  CPOL=0 (Clock Idle low level), CPHA=0 (SDO transmit/change edge active to idle)
    // SPI_MODE_1 (0,1)  CPOL=0 (Clock Idle low level), CPHA=1 (SDO transmit/change edge idle to active)
    // SPI_MODE_2 (1,0)  CPOL=1 (Clock Idle high level), CPHA=0 (SDO transmit/change edge active to idle)
    // SPI_MODE_3 (1,1)  CPOL=1 (Clock Idle high level), CPHA=1 (SDO transmit/change edge idle to active)
    spi_mode = SPI_MODE_3;

    //----- SET BITS PER WORD -----
    spi_bitsPerWord = 8;

    //----- SET SPI BUS SPEED -----
    spi_speed = useSpiSpeed; // 1000000 = 1MHz (1uS per bit)

    if (spi_device)
        spi_cs_fd = &spi_cs1_fd;
    else
        spi_cs_fd = &spi_cs0_fd;

    if (spi_device)
        *spi_cs_fd = open("/dev/spidev0.1", O_RDWR);
    else
        *spi_cs_fd = open("/dev/spidev0.0", O_RDWR);

    if (*spi_cs_fd < 0)
    {
        perror("Error - Could not open SPI device");
        exit(1);
    }

    status_value = ioctl(*spi_cs_fd, SPI_IOC_WR_MODE, &spi_mode);
    if (status_value < 0)
    {
        perror("Could not set SPIMode (WR)...ioctl fail");
        exit(1);
    }

    status_value = ioctl(*spi_cs_fd, SPI_IOC_RD_MODE, &spi_mode);
    if (status_value < 0)
    {
        perror("Could not set SPIMode (RD)...ioctl fail");
        exit(1);
    }

    status_value = ioctl(*spi_cs_fd, SPI_IOC_WR_BITS_PER_WORD, &spi_bitsPerWord);
    if (status_value < 0)
    {
        perror("Could not set SPI bitsPerWord (WR)...ioctl fail");
        exit(1);
    }

    status_value = ioctl(*spi_cs_fd, SPI_IOC_RD_BITS_PER_WORD, &spi_bitsPerWord);
    if (status_value < 0)
    {
        perror("Could not set SPI bitsPerWord(RD)...ioctl fail");
        exit(1);
    }

    status_value = ioctl(*spi_cs_fd, SPI_IOC_WR_MAX_SPEED_HZ, &spi_speed);
    if (status_value < 0)
    {
        perror("Could not set SPI speed (WR)...ioctl fail");
        exit(1);
    }

    status_value = ioctl(*spi_cs_fd, SPI_IOC_RD_MAX_SPEED_HZ, &spi_speed);
    if (status_value < 0)
    {
        perror("Could not set SPI speed (RD)...ioctl fail");
        exit(1);
    }
    return (status_value);
}

int SpiClosePort(int spi_device)
{
    int status_value = -1;
    int *spi_cs_fd;

    if (spi_device)
        spi_cs_fd = &spi_cs1_fd;
    else
        spi_cs_fd = &spi_cs0_fd;

    status_value = close(*spi_cs_fd);
    if (status_value < 0)
    {
        perror("Error - Could not close SPI device");
        exit(1);
    }
    return (status_value);
}

int mainOld()
{
    LEP_CAMERA_PORT_DESC_T portDesc;
    // LEP_RESULT result;
    LEP_STATUS_T statusDesc;

    // Initialize and open the camera port (example values)
    portDesc.portType = LEP_CCI_TWI;
    portDesc.portID = 99;
    portDesc.deviceAddress = 0x2A;  // Example I2C address
    portDesc.portBaudRate = 400000; // 400 kHz
    LEP_ASSERT(LEP_OpenPort(1, LEP_CCI_TWI, 400, &portDesc));

    // Check the system status
    LEP_ASSERT(LEP_GetSysStatus(&portDesc, &statusDesc));
    printf("Camera Status: %d, Command Count: %d\n",
           statusDesc.camStatus, statusDesc.commandCount);

    LEP_POLARITY_E polarityDesc;
    LEP_ASSERT(LEP_GetVidPolarity(&portDesc, &polarityDesc));
    printf("Video Polarity: %d\n", polarityDesc);

    LEP_ASSERT(LEP_RunSysFFCNormalization(&portDesc));
    sleep(1); // Wait for a second to allow FFC to complete

    // Check the system status
    LEP_ASSERT(LEP_GetSysStatus(&portDesc, &statusDesc));
    printf("Camera Status: %d, Command Count: %d\n",
           statusDesc.camStatus, statusDesc.commandCount);

    const unsigned int spiSpeed = 10000000; // 10 MHz
    SpiOpenPort(0, spiSpeed);

    // Close the camera port
    LEP_ASSERT(LEP_ClosePort(&portDesc));

    uint16_t n_wrong_segment = 0;
    uint16_t n_zero_value_drop_frame = 0;
    uint8_t result[PACKET_SIZE * PACKETS_PER_FRAME];
    uint8_t shelf[4][PACKET_SIZE * PACKETS_PER_FRAME];
    uint16_t *frameBuffer;

    while (true)
    {
        // read data packets from lepton over SPI
        int resets = 0;
        int segmentNumber = -1;
        for (int j = 0; j < PACKETS_PER_FRAME; j++)
        {
            // if it's a drop packet, reset j to 0, set to -1 so he'll be at 0 again loop
            read(spi_cs0_fd, result + PACKET_SIZE * j, sizeof(uint8_t) * PACKET_SIZE);
            int headerVal = result[j * PACKET_SIZE];
            int packetNumber = result[j * PACKET_SIZE + 1];
            printf("[PACKET hrd=%02x FRAME=%02d]\n", headerVal, packetNumber);
            if (packetNumber != j)
            {
                printf("[PACKET RESET]\n");

                j = -1;
                resets += 1;
                usleep(1000);
                // Note: we've selected 750 resets as an arbitrary limit, since there should never be 750 "null" packets between two valid transmissions at the current poll rate
                // By polling faster, developers may easily exceed this count, and the down period between frames may then be flagged as a loss of sync
                if (resets == 750)
                {
                    SpiClosePort(0);
                    LEP_ASSERT(LEP_RunOemReboot(&portDesc));
                    n_wrong_segment = 0;
                    n_zero_value_drop_frame = 0;
                    usleep(750000);
                    SpiOpenPort(0, spiSpeed);
                }
                continue;
            }
        }
        if (resets >= 30)
            printf("done reading, resets: %d\n", resets);

        memcpy(shelf[0], result, sizeof(uint8_t) * PACKET_SIZE * PACKETS_PER_FRAME);
        const int iSegmentStart = 1;
        const int iSegmentStop = 1;

        int row, column;
        uint16_t value;
        uint16_t valueFrameBuffer;
        for (int iSegment = iSegmentStart; iSegment <= iSegmentStop; iSegment++)
        {
            int ofsRow = 30 * (iSegment - 1);
            for (int i = 0; i < FRAME_SIZE_UINT16; i++)
            {
                // skip the first 2 uint16_t's of every packet, they're 4 header bytes
                if (i % PACKET_SIZE_UINT16 < 2)
                    continue;

                // flip the MSB and LSB at the last second
                valueFrameBuffer = (shelf[iSegment - 1][i * 2] << 8) + shelf[iSegment - 1][i * 2 + 1];
                if (valueFrameBuffer == 0)
                {
                    // Why this value is 0?
                    n_zero_value_drop_frame++;
                    if ((n_zero_value_drop_frame % 12) == 0)
                        printf("[WARNING] Found zero-value. Drop the frame continuously %d times", n_zero_value_drop_frame);
                    break;
                }

                // //
                // value = (valueFrameBuffer - minValue) * scale;
                // int ofs_r = 3 * value + 0;
                // if (colormapSize <= ofs_r)
                //     ofs_r = colormapSize - 1;
                // int ofs_g = 3 * value + 1;
                // if (colormapSize <= ofs_g)
                //     ofs_g = colormapSize - 1;
                // int ofs_b = 3 * value + 2;
                // if (colormapSize <= ofs_b)
                //     ofs_b = colormapSize - 1;
                // color = qRgb(colormap[ofs_r], colormap[ofs_g], colormap[ofs_b]);
                // if (typeLepton == 3)
                // {
                //     column = (i % PACKET_SIZE_UINT16) - 2 + (myImageWidth / 2) * ((i % (PACKET_SIZE_UINT16 * 2)) / PACKET_SIZE_UINT16);
                //     row = i / PACKET_SIZE_UINT16 / 2 + ofsRow;
                // }
                // else
                // {
                //     column = (i % PACKET_SIZE_UINT16) - 2;
                //     row = i / PACKET_SIZE_UINT16;
                // }
                // myImage.setPixel(column, row, color);
            }
        }

        if (n_zero_value_drop_frame != 0)
        {
            printf("[WARNING] Found zero-value. Drop the frame continuously %d times [RECOVERED]", n_zero_value_drop_frame);
            n_zero_value_drop_frame = 0;
        }
    }

    SpiClosePort(0);

    printf("Camera port operations completed successfully.\n");
    return 0;
}

int main(int argc, char *argv[])
{
    uint16_t buffer[80*60];
    LEPSDK_Init();
    LEPSDK_GetFrame(buffer);
    LEPSDK_Shutdown();

    return(0);

}