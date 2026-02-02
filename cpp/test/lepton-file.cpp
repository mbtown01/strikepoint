#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <memory.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "error.h"
#include "lepton-file.h"

strikepoint::LeptonFileImp::LeptonFileImp(strikepoint::Logger &logger,
                                          std::string filePath) :
    _logger(logger),
    _spi_fd(-1)
{
    _spi_fd = open(filePath.c_str(), O_RDONLY);
    if (_spi_fd < 0)
        BAIL("Could not open %s: %s", filePath.c_str(), strerror(errno)); 
}

strikepoint::LeptonFileImp::~LeptonFileImp()
{
    close(_spi_fd);
}

void
strikepoint::LeptonFileImp::cameraEnable()
{
}

void
strikepoint::LeptonFileImp::cameraDisable()
{
}
