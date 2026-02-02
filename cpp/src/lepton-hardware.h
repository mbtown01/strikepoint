#pragma once

#include "lepton.h"

namespace strikepoint {

class LeptonHardwareImpl : public LeptonDriver::ILeptonImpl {
  public:
    LeptonHardwareImpl(strikepoint::Logger &logger);
    ~LeptonHardwareImpl();

    void cameraEnable() override;
    void cameraDisable() override;
    int spiFd() override { return _spi_fd; }

  private:
    LEP_CAMERA_PORT_DESC_T _port_desc;
    strikepoint::Logger &_logger;
    int _spi_fd;
};

} // namespace strikepoint