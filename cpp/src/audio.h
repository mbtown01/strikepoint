#pragma once

#include <atomic>
#include <liquid/liquid.h>
#include <mutex>
#include <queue>
#include <thread>

class AudioEngine {

  public:
    typedef struct {
        unsigned int blockSize; // e.g. 1024
        unsigned int queueSize; // e.g. 256
        float cutoff_hz;        // high-pass filter cutoff frequency (e.g. 8000.0)
        float refractory_s;     // e.g. 0.07
        float minThresh;        // absolute lower bound (e.g. 0.002)
    } config;

    typedef struct {
        uint64_t t_ns;    // CLOCK_MONOTONIC timestamp
        float score;      // composite score (rms * peakiness)
        float rms;        // rms of high-pass signal
        float peakiness;  // peak/rms
        uint32_t eventId; // increments each hit
    } event;

    class IAudioSource {
      public:
        virtual ~IAudioSource() = default;
        virtual void read(float *buffer, size_t frames) = 0;
        virtual uint64_t nowNs() = 0;
        virtual unsigned int sampleRate_Hz() = 0;
        virtual bool isEOF() { return false; }
    };

  public:
    AudioEngine(IAudioSource &source, AudioEngine::config &cfg);
    ~AudioEngine();

    // set default config values
    static void defaults(AudioEngine::config &cfg);

    // retrieve all pending events
    void getEvents(std::vector<AudioEngine::event> &out);

  private:
    // capture loop and helpers (camelCase names)
    void _captureLoop();

  private:
    IAudioSource &_source;
    AudioEngine::config _cfg;
    iirfilt_rrrf _hp;
    std::thread _thread;
    std::atomic<bool> _running;
    std::queue<AudioEngine::event> _queue;
    std::mutex _mtx;
};
