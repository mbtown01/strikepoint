#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <memory.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "error.h"
#include "lepton-hardware.h"

#include "LEPTON_AGC.h"
#include "LEPTON_ErrorCodes.h"
#include "LEPTON_OEM.h"
#include "LEPTON_RAD.h"
#include "LEPTON_SDK.h"
#include "LEPTON_SYS.h"

#define BAIL_ON_FAILED_LEP(cmd)                                  \
    do {                                                         \
        LEP_RESULT rtn = cmd;                                    \
        if (rtn != LEP_OK)                                       \
            BAIL("'%s' returned LEP_RESULT code %d", #cmd, rtn); \
    } while (0)

#define BAIL_ON_FAILED_ERRNO(cmd)                                     \
    do {                                                              \
        int rtn = cmd;                                                \
        if (rtn < 0)                                                  \
            BAIL("'%s' returned %d: %s", #cmd, rtn, strerror(errno)); \
    } while (0)

strikepoint::LeptonHardwareImpl::LeptonHardwareImpl(strikepoint::Logger &logger) :
    _logger(logger),
    _spi_fd(-1)
{
    LEP_STATUS_T statusDesc;
    unsigned char spiMode = SPI_MODE_3;
    unsigned char spiBitsPerWord = 8;
    unsigned int spiSpeed = 10000000;

    LOG_INFO(_logger, "Configuring /def/spidev0.0: mode=%d, bitsPerWord=%d, speed=%d Hz",
             spiMode, spiBitsPerWord, spiSpeed);
    _spi_fd = open("/dev/spidev0.0", O_RDWR);
    if (_spi_fd < 0)
        BAIL("Could not open SPI device");
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_WR_MODE, &spiMode));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_RD_MODE, &spiMode));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_WR_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_RD_BITS_PER_WORD, &spiBitsPerWord));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &spiSpeed));
    BAIL_ON_FAILED_ERRNO(
        ioctl(_spi_fd, SPI_IOC_RD_MAX_SPEED_HZ, &spiSpeed));

    // Initialize and open the camera port (example values)
    LOG_INFO(_logger, "Configuring camera port");
    _port_desc.portType = LEP_CCI_TWI;
    _port_desc.portID = 99;
    _port_desc.deviceAddress = 0x2A;               // Example I2C address
    _port_desc.portBaudRate = (LEP_UINT16) 400000; // 400 kHz
    BAIL_ON_FAILED_LEP(LEP_OpenPort(1, LEP_CCI_TWI, 400, &_port_desc));

    BAIL_ON_FAILED_LEP(LEP_SetAgcEnableState(&_port_desc, LEP_AGC_DISABLE));
    BAIL_ON_FAILED_LEP(LEP_SetRadEnableState(&_port_desc, LEP_RAD_ENABLE));

    LEP_SYS_FFC_SHUTTER_MODE_OBJ_T ffcMode;
    ffcMode.shutterMode = LEP_SYS_FFC_SHUTTER_MODE_MANUAL;
    ffcMode.tempLockoutState = LEP_SYS_SHUTTER_LOCKOUT_INACTIVE;
    ffcMode.videoFreezeDuringFFC = LEP_SYS_DISABLE;
    ffcMode.ffcDesired = LEP_SYS_ENABLE;
    ffcMode.elapsedTimeSinceLastFfc = 0;
    ffcMode.desiredFfcPeriod = 60000; // 60 seconds
    ffcMode.explicitCmdToOpen = false;
    ffcMode.desiredFfcTempDelta = 0;
    ffcMode.imminentDelay = 0;
    BAIL_ON_FAILED_LEP(LEP_SetSysFfcShutterModeObj(&_port_desc, ffcMode));
    usleep(200000); // Wait for a second to allow FFC to complete

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&_port_desc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&_port_desc, LEP_VIDEO_OUTPUT_ENABLE));

    // Show status some known interesting settings
    LEP_SYS_FLIR_SERIAL_NUMBER_T serialNumber;
    BAIL_ON_FAILED_LEP(LEP_GetSysFlirSerialNumber(&_port_desc, &serialNumber));
    LOG_INFO(_logger, "STARTUP Camera Serial Number: %llu", (unsigned long long) serialNumber);

    LEP_SYS_UPTIME_NUMBER_T upTime;
    BAIL_ON_FAILED_LEP(LEP_GetSysCameraUpTime(&_port_desc, &upTime));
    LOG_INFO(_logger, "STARTUP Camera Uptime: %u seconds", (unsigned int) (upTime));

    LEP_SYS_AUX_TEMPERATURE_CELCIUS_T auxTemp;
    LEP_GetSysAuxTemperatureCelcius(&_port_desc, &auxTemp);
    LOG_INFO(_logger, "STARTUP aux temperature: %.2f F", auxTemp * 9.0f / 5.0f + 32.0f);

    LEP_SYS_FPA_TEMPERATURE_CELCIUS_T fpaTemp;
    BAIL_ON_FAILED_LEP(LEP_GetSysFpaTemperatureCelcius(&_port_desc, &fpaTemp));
    LOG_INFO(_logger, "STARTUP FPA Temperature: %.2f F", fpaTemp * 9.0f / 5.0f + 32.0f);

    LEP_RAD_ENABLE_E radState;
    LEP_GetRadEnableState(&_port_desc, &radState);
    LOG_INFO(_logger, "STARTUP Radiometry enabled: %d", radState);

    LEP_AGC_ENABLE_E agcState;
    LEP_GetAgcEnableState(&_port_desc, &agcState);
    LOG_INFO(_logger, "STARTUP AGC enabled: %d", agcState);

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));
    LOG_INFO(_logger, "STARTUP Camera status: %d", statusDesc.camStatus);
}

strikepoint::LeptonHardwareImpl::~LeptonHardwareImpl()
{
    close(_spi_fd);
    LEP_ClosePort(&_port_desc);
}

void
strikepoint::LeptonHardwareImpl::cameraEnable()
{
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));

    do {
        rtn = LEP_RunOemPowerOn(&_port_desc);
        usleep(250000);
    } while (rtn != LEP_OK);

    usleep(1000000);

    do {
        rtn = LEP_GetSysStatus(&_port_desc, &statusDesc);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);

    BAIL_ON_FAILED_LEP(LEP_RunSysFFCNormalization(&_port_desc));
    BAIL_ON_FAILED_LEP(
        LEP_SetOemVideoOutputEnable(&_port_desc, LEP_VIDEO_OUTPUT_ENABLE));
    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));

    while (statusDesc.camStatus != LEP_SYSTEM_FLAT_FIELD_IN_PROCESS) {
        usleep(250000);
        BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));
    }
}

void
strikepoint::LeptonHardwareImpl::cameraDisable()
{
    LEP_STATUS_T statusDesc;
    LEP_RESULT rtn;

    BAIL_ON_FAILED_LEP(LEP_GetSysStatus(&_port_desc, &statusDesc));

    do {
        rtn = LEP_RunOemPowerDown(&_port_desc);
        usleep(250000);
    } while (rtn != LEP_OK);

    do {
        rtn = LEP_GetSysStatus(&_port_desc, &statusDesc);
        usleep(250000);
    } while (rtn != LEP_OK || statusDesc.camStatus != LEP_SYSTEM_READY);
}
