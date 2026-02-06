#pragma once

#include <atomic>
#include <liquid/liquid.h>
#include <map>
#include <mutex>
#include <queue>
#include <thread>

#include "logging.h"
#include "timer.h"

namespace strikepoint {

class AudioEngine {

  public:
    typedef struct {
        unsigned int block_size; // e.g. 1024
        unsigned int queue_size; // e.g. 256
        float cutoff_hz;         // high-pass filter cutoff frequency (e.g. 8000.0)
        float refractory_s;      // e.g. 0.07
        float min_thresh;        // absolute lower bound (e.g. 0.002)
    } config;

    typedef struct {
        uint64_t t_ns;     // CLOCK_MONOTONIC timestamp
        float rms;         // rms of high-pass signal
        uint32_t event_seq; // increments each hit
    } event;

    class IAudioSource {
      public:
        IAudioSource();
        IAudioSource(unsigned int sample_rate_hz);
        virtual ~IAudioSource() = default;
        virtual void read(float *buffer, size_t frames) = 0;
        virtual uint64_t now_ns() = 0;
        virtual bool is_eof() { return false; }
        unsigned int sample_rate_hz() const noexcept { return _sample_rate_hz; }

      protected:
        void _set_sample_rate_hz(unsigned int sampleRate_Hz) noexcept;

      private:
        unsigned int _sample_rate_hz;
    };

  public:
    AudioEngine(Logger &logger, IAudioSource &source, AudioEngine::config &cfg);
    ~AudioEngine();

    // set default config values
    static void defaults(AudioEngine::config &cfg);

    // retrieve all pending events
    void getEvents(std::vector<AudioEngine::event> &out);

  private:
    // capture loop and helpers (camelCase names)
    void _captureLoop(iirfilt_rrrf &hp);

  private:
    IAudioSource &_source;
    AudioEngine::config _cfg;
    strikepoint::Logger &_logger;
    std::thread _thread;
    std::atomic<bool> _is_running;
    std::queue<AudioEngine::event> _queue;
    std::mutex _mtx;
    std::map<std::string, Timer> _timers;
};

} // namespace strikepoint