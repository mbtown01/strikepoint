#pragma once

#include "audio.h"
#include <sndfile.h>
#include <string>

class WavAudioSource : public IAudioSource {
  public:
    WavAudioSource(std::string fileName);

    ~WavAudioSource() override;

    void read(float *buffer, size_t frames) override;

    uint64_t nowNs() override;

    bool isEOF() override { return _isEof; }

  private:
    SNDFILE *_file;
    bool _isEof;
    uint64_t _currentNs;

};