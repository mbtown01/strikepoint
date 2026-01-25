#pragma once

#include <alsa/asoundlib.h>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <liquid/liquid.h>
#include <mutex>
#include <queue>
#include <stdint.h>
#include <thread>

class IAudioSource {
  public:
    virtual ~IAudioSource() = default;
    virtual void read(float *buffer, size_t frames) = 0;
    virtual uint64_t nowNs() = 0;
    virtual bool isEOF() { return false; }
};

class AudioEngine {
  public:
    typedef struct {
        unsigned int sample_rate; // e.g. 48000
        unsigned int block_size;  // e.g. 1024
        unsigned int queue_size;  // e.g. 256
        float cutoff_hz;          // high-pass filter cutoff frequency (e.g. 8000.0)
        float mult;               // threshold multiplier over noise floor (e.g. 8.0)
        float peakiness_min;      // e.g. 7.0 (higher => fewer false positives)
        float refractory_s;       // e.g. 0.07
        float min_thresh;         // absolute lower bound (e.g. 0.002)
        float noise_alpha;        // noise smoother (e.g. 0.01)
    } config;

    typedef struct {
        uint64_t t_ns;     // CLOCK_MONOTONIC timestamp
        float score;       // composite score (rms * peakiness)
        float rms;         // rms of high-pass signal
        float peakiness;   // peak/rms
        uint32_t event_id; // increments each hit
    } event;

  public:
    AudioEngine(IAudioSource &source, AudioEngine::config &cfg);
    ~AudioEngine();

    // set default config values
    static void defaults(AudioEngine::config &cfg);

    // start/stop the capture thread; returns 0 on success
    void start(const AudioEngine::config *cfg);
    void stop();

    // non-blocking and blocking event retrieval
    int pollEvent(AudioEngine::event *out);
    // blocks indefinitely until event is available
    int waitEvent(AudioEngine::event *out, int timeout_ms);

  private:
    // capture loop and helpers (camelCase names)
    void _captureLoop();
    void _qPush(const AudioEngine::event &e);
    int _qPop(AudioEngine::event *out);

  private:
    IAudioSource &_source;
    AudioEngine::config _cfg;
    iirfilt_rrrf _hp;
    std::thread _thread;
    std::atomic<bool> _running;
    std::queue<AudioEngine::event> _queue;
    std::mutex _mtx;
    std::condition_variable _cv;
};
