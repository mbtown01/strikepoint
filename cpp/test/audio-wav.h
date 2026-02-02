#pragma once

#include "audio.h"
#include <sndfile.h>
#include <string>

namespace strikepoint {

class WavAudioSource : public AudioEngine::IAudioSource {

  public:
    WavAudioSource(std::string fileName);
    ~WavAudioSource() override;

    void read(float *buffer, size_t frames) override;

    uint64_t now_ns() override { return _now_ns; }

    bool is_eof() override { return _is_eof; }

  private:
    SNDFILE *_file;
    bool _is_eof;
    uint64_t _now_ns;
};

} // namespace strikepoint