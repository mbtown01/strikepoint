#pragma once

#include "audio.h"
#include <alsa/asoundlib.h>
#include <string>
#include <vector>

class PcmAudioSource : public AudioEngine::IAudioSource {

  public:
    PcmAudioSource(std::string device = "default",
                   unsigned int sampleRate_Hz = 48000,
                   int channels = 1,
                   int bufferSize = 1024);
    ~PcmAudioSource() override;

    void read(float *buffer, size_t frames) override;

    unsigned int sampleRate_Hz() override { return _sampleRate_Hz; }

    uint64_t nowNs() override;

  private:
    snd_pcm_t *_pcm;
    unsigned int _sampleRate_Hz;
    std::vector<int16_t> _buffer;
};