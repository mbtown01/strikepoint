#pragma once

#include "lepton.h"

namespace strikepoint {

class LeptonFileImp : public LeptonDriver::ILeptonImpl {
  public:
    LeptonFileImp(strikepoint::Logger &logger, std::string filePath);
    ~LeptonFileImp();

    void cameraEnable() override;
    void cameraDisable() override;
    int spiFd() override { return _spi_fd; }

  private:
    LEP_CAMERA_PORT_DESC_T _port_desc;
    strikepoint::Logger &_logger;
    int _spi_fd;
};

} // namespace strikepoint