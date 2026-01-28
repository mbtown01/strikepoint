#include "audio-pcm.h"
#include "error.h"

using namespace strikepoint;

PcmAudioSource::PcmAudioSource(std::string device,
                               unsigned int sampleRateHz,
                               int channels,
                               int bufferSize) :
    _pcm(nullptr),
    AudioEngine::IAudioSource(sampleRateHz)
{
    const char *dev = device.c_str();
    int err = 0;

    err = snd_pcm_open(&_pcm, dev, SND_PCM_STREAM_CAPTURE, 0);
    if (err < 0)
        BAIL("snd_pcm_open(%s) failed: %s", dev, snd_strerror(err));

    snd_pcm_uframes_t period = (snd_pcm_uframes_t) bufferSize;
    snd_pcm_uframes_t bufsize = period * 4;

    snd_pcm_hw_params_t *hw;
    snd_pcm_hw_params_alloca(&hw);
    snd_pcm_hw_params_any(_pcm, hw);
    snd_pcm_hw_params_set_access(_pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED);
    snd_pcm_hw_params_set_format(_pcm, hw, SND_PCM_FORMAT_S16_LE);
    snd_pcm_hw_params_set_channels(_pcm, hw, channels);
    snd_pcm_hw_params_set_rate_near(_pcm, hw, &sampleRateHz, nullptr);
    snd_pcm_hw_params_set_period_size_near(_pcm, hw, &period, nullptr);
    snd_pcm_hw_params_set_buffer_size_near(_pcm, hw, &bufsize);

    err = snd_pcm_hw_params(_pcm, hw);
    if (err < 0) {
        snd_pcm_close(_pcm);
        _pcm = nullptr;
        BAIL("snd_pcm_hw_params() failed: %s", snd_strerror(err));
    }
}

PcmAudioSource::~PcmAudioSource()
{
    if (_pcm) {
        snd_pcm_drop(_pcm);
        snd_pcm_close(_pcm);
        _pcm = nullptr;
    }
}

void
PcmAudioSource::read(float *buffer, size_t size)
{
    if (_buffer.size() < size)
        _buffer.resize(size);

    size_t totalRead = 0;
    while (totalRead < size) {
        int err = snd_pcm_readi(_pcm, _buffer.data() + totalRead, size - totalRead);
        if (err < 0) {
            if (err == -EAGAIN)
                continue;
            err = snd_pcm_recover(_pcm, err, 1);
            if (err < 0)
                BAIL("ERROR: Recover failed: %s\n", snd_strerror(err));
        } else
            totalRead += err;
    }

    // convert to float
    for (size_t i = 0; i < size; ++i)
        buffer[i] = (float) _buffer[i] / 32768.0f;
}

uint64_t
PcmAudioSource::now_ns()
{
    timespec ts{};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t) ts.tv_sec * 1000000000ull + (uint64_t) ts.tv_nsec;
}
