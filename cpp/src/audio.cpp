#include "audio.h"
#include "error.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <ctime>
#include <memory>
#include <thread>

#include <alsa/asoundlib.h>
#include <liquid/liquid.h>

#include <atomic>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

AudioEngine::AudioEngine(IAudioSource &source, AudioEngine::config &cfg) :
    _running(false),
    _source(source),
    _hp(nullptr),
    _cfg(cfg)
{
    _hp = iirfilt_rrrf_create_prototype(
        LIQUID_IIRDES_BUTTER,
        LIQUID_IIRDES_HIGHPASS,
        LIQUID_IIRDES_SOS,
        4,
        _cfg.cutoff_hz / (float) _cfg.sample_rate,
        0.0f, // f0 unused for high-pass
        1.0f, // Ap (passband ripple) unused for Butterworth
        60.0f // As (stopband attenuation) unused for Butterworth
    );

    if (!_hp)
        BAIL("Failed to create liquid-dsp high-pass filter");
}

AudioEngine::~AudioEngine()
{
    stop();
}

void
AudioEngine::defaults(AudioEngine::config &cfg)
{
    cfg.sample_rate = 48000;
    cfg.block_size = 1024;
    cfg.queue_size = 256;
    cfg.cutoff_hz = 8000.0f;
    cfg.mult = 8.0f;
    cfg.peakiness_min = 7.0f;
    cfg.refractory_s = 0.12f;
    cfg.min_thresh = 0.03f;
    cfg.noise_alpha = 0.01f;
}

void
AudioEngine::_qPush(const AudioEngine::event &e)
{
    std::lock_guard<std::mutex> lk(_mtx);
    if (_queue.size() >= 256)
        _queue.pop(); // drop oldest
    _queue.push(e);
    _cv.notify_all();
}

int
AudioEngine::_qPop(AudioEngine::event *out)
{
    std::lock_guard<std::mutex> lk(_mtx);
    if (_queue.empty())
        return 0;
    *out = _queue.front();
    _queue.pop();
    return 1;
}

void
AudioEngine::_captureLoop()
{
    const int frameSize = _cfg.block_size;
    std::vector<float> buf(frameSize), buf_hp(frameSize);
    float noise = 0.0f;
    uint64_t last_hit = 0;
    uint32_t event_id = 0;
    AudioEngine::event e{};

    while (!_source.isEOF() && _running.load(std::memory_order_relaxed)) {
        _source.read(&(buf[0]), frameSize);

        float y = 0;
        for (int i = 0; i < frameSize; ++i) {
            iirfilt_rrrf_execute(_hp, buf[i], &y);
            buf_hp[i] = y;
        }

        double sumsq = 0.0, max = 0.0;
        for (float v : buf_hp) {
            sumsq += (double) v * (double) v;
            max = std::fmax(max, std::fabs(v)) + 1e-12;
        }
        float rms = std::sqrt((float) (sumsq / (double) buf_hp.size() + 1e-12));
        float peakiness = max / (rms + 1e-12f);

        uint64_t t = _source.nowNs();
        double since_hit_s = (last_hit == 0) ? 999.0 : (double) (t - last_hit) / 1e9;

        if (since_hit_s >= _cfg.refractory_s && rms > _cfg.min_thresh) {
            last_hit = t;
            e.t_ns = t;
            e.rms = rms;
            e.peakiness = peakiness;
            e.score = rms * peakiness;
            e.event_id = ++event_id;
            _qPush(e);
        }
    }
}

void
AudioEngine::start(const AudioEngine::config *cfg)
{
    if (!cfg)
        BAIL("null config");
    if (_running.load())
        BAIL("already running");

    _cfg = *cfg;
    if (_cfg.mult <= 0)
        _cfg.mult = 8.0f;
    if (_cfg.peakiness_min <= 0)
        _cfg.peakiness_min = 7.0f;
    if (_cfg.refractory_s <= 0)
        _cfg.refractory_s = 0.07f;
    if (_cfg.min_thresh <= 0)
        _cfg.min_thresh = 0.002f;
    if (_cfg.noise_alpha <= 0)
        _cfg.noise_alpha = 0.01f;

    // clear any pending events
    {
        std::lock_guard<std::mutex> lk(_mtx);
        while (!_queue.empty())
            _queue.pop();
    }
    _running.store(true);
    _thread = std::thread([this] { _captureLoop(); });
}

void
AudioEngine::stop()
{
    if (_running.load()) {
        _running.store(false);
        if (_thread.joinable())
            _thread.join();
        _cv.notify_all();
    }
}

int
AudioEngine::pollEvent(AudioEngine::event *out)
{
    if (!out)
        return -1;
    return _qPop(out);
}

int
AudioEngine::waitEvent(AudioEngine::event *out, int timeout_ms)
{
    if (!out)
        return -1;

    if (_qPop(out))
        return 1;

    std::unique_lock<std::mutex> lk(_mtx);
    if (!_running.load())
        return 0;
    if (timeout_ms < 0)
        timeout_ms = 0;

    bool signaled = _cv.wait_for(lk, std::chrono::milliseconds(timeout_ms), [&] {
        return !_queue.empty() || !_running.load();
    });

    if (!signaled)
        return 0;
    if (_queue.empty())
        return 0;
    *out = _queue.front();
    _queue.pop();
    return 1;
}
