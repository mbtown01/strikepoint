#pragma once

#include "audio.h"
#include <string>
#include <vector>


class PcmAudioSource : public IAudioSource {
  public:
    PcmAudioSource(std::string device = "default",
                   unsigned int sampleRateHz = 48000,
                   int channels = 1,
                   int bufferSize = 1024);

    ~PcmAudioSource() override;

    void read(float *buffer, size_t frames) override;

    uint64_t nowNs() override;

  private:
    snd_pcm_t *_pcm;
    std::vector<int16_t> _buffer;

};