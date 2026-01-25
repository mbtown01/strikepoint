#pragma once

#include "audio.h"
#include <sndfile.h>
#include <string>

class WavAudioSource : public AudioEngine::IAudioSource {

  public:
    WavAudioSource(std::string fileName);
    ~WavAudioSource() override;

    void read(float *buffer, size_t frames) override;

    uint64_t nowNs() override { return _currentTime_ns; }

    unsigned int sampleRate_Hz() override { return _sampleRate_Hz; }

    bool isEOF() override { return _isEof; }

  private:
    SNDFILE *_file;
    bool _isEof;
    int _sampleRate_Hz;
    uint64_t _currentTime_ns;
};