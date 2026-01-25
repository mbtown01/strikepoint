

#include <cstring>
#include <iostream>
#include <vector>

#include "audio-wav.h"
#include "error.h"

WavAudioSource::WavAudioSource(std::string fileName) :
    _file(nullptr),
    _isEof(false)
{
    SF_INFO info{};
    SNDFILE *file = sf_open(fileName.c_str(), SFM_READ, &info);
    if (!file)
        BAIL("Failed to open file: %s", sf_strerror(nullptr));
    _file = file;

    std::cout << "Sample rate: " << info.samplerate << "\n";
    std::cout << "Channels:    " << info.channels << "\n";
    std::cout << "Frames:      " << info.frames << "\n";
    std::cout << "Format:      0x" << std::hex << info.format << std::dec << "\n";
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
        _currentNs += (uint64_t) (1000000000ull * err / 48000);
    }
}

uint64_t
WavAudioSource::nowNs()
{
    return _currentNs;
}
