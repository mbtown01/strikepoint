#pragma once

#include "audio.h"
#include <alsa/asoundlib.h>
#include <string>
#include <vector>

namespace strikepoint {

class PcmAudioSource : public AudioEngine::IAudioSource {

  public:
    PcmAudioSource(std::string device = "default",
                   unsigned int sampleRate_Hz = 48000,
                   int channels = 1,
                   int bufferSize = 1024);
    ~PcmAudioSource() override;

    void read(float *buffer, size_t frames) override;

    uint64_t now_ns() override;

  private:
    snd_pcm_t *_pcm;
    std::vector<int16_t> _buffer;
};

} // namespace strikepoint