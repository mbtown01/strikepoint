#pragma once

#include "lepton.h"

namespace strikepoint {

class LeptonHardwareImpl : public LeptonDriver::ILeptonImpl {
  public:
    LeptonHardwareImpl(strikepoint::Logger &logger);
    ~LeptonHardwareImpl();

    void cameraEnable() override;
    void cameraDisable() override;
    void spiRead(void *buf, size_t len) override;

  private:
    LEP_CAMERA_PORT_DESC_T _port_desc;
    strikepoint::Logger &_logger;
    int _spi_fd;
};

} // namespace strikepoint