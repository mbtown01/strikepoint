

#include "audio-wav.h"
#include "error.h"
#include <cassert>
#include <cstring>

WavAudioSource::WavAudioSource(std::string fileName) :
    _file(nullptr),
    _isEof(false),
    _currentTime_ns(0),
    _sampleRate_Hz(0)
{
    SF_INFO info{};
    SNDFILE *file = sf_open(fileName.c_str(), SFM_READ, &info);
    if (!file)
        BAIL("Failed to open file: %s", sf_strerror(nullptr));

    _file = file;
    _sampleRate_Hz = info.samplerate;
    assert(info.channels == 1);     // mono only for now
    assert(info.format == 0x10002); // WAV + PCM 32-bit float
}

WavAudioSource::~WavAudioSource()
{
    if (_file) {
        sf_close(_file);
        _file = nullptr;
    }
}

void
WavAudioSource::read(float *buffer, size_t size)
{
    sf_count_t totalRead = 0;
    while (!_isEof && totalRead < size) {
        int err = sf_readf_float(_file, buffer + totalRead, size - totalRead);
        if (err < 0)
            BAIL("ERROR: Recover failed: %s\n", sf_strerror(_file));
        _isEof = (err == 0);
        totalRead += err;
        _currentTime_ns += (uint64_t) (1000000000ull * err / _sampleRate_Hz);
    }
}