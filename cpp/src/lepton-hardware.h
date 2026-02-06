#pragma once

#include "lepton.h"

namespace strikepoint {

class LeptonHardwareImpl : public LeptonDriver::ILeptonImpl {
  public:
    LeptonHardwareImpl(strikepoint::Logger &logger);
    ~LeptonHardwareImpl();

    void reboot_camera() override;
    void spi_read(void *buf, size_t len) override;

  private:
    void _camera_disable();
    void _camera_enable();

  private:
    LEP_CAMERA_PORT_DESC_T _port_desc;
    strikepoint::Logger &_logger;
    int _spi_fd;
};

} // namespace strikepoint