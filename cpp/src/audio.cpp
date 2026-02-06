#include <chrono>
#include <cmath>
#include <ctime>
#include <unistd.h>

#include "audio.h"
#include "error.h"

using namespace strikepoint;

AudioEngine::AudioEngine(Logger &logger,
                         IAudioSource &source, AudioEngine::config &cfg) :
    _is_running(false),
    _source(source),
    _cfg(cfg),
    _logger(logger)
{
    _thread = std::thread([this] {
        iirfilt_rrrf hp = iirfilt_rrrf_create_prototype(
            LIQUID_IIRDES_BUTTER,
            LIQUID_IIRDES_HIGHPASS,
            LIQUID_IIRDES_SOS,
            4,
            _cfg.cutoff_hz / (float) _source.sample_rate_hz(),
            0.0f, // f0 unused for high-pass
            1.0f, // Ap (passband ripple) unused for Butterworth
            60.0f // As (stopband attenuation) unused for Butterworth
        );
        try {
            if (!hp)
                BAIL("Failed to create liquid-dsp high-pass filter");
            _captureLoop(hp);
        } catch (const bail_error &e) {
            _logger.log(
                e.file().c_str(), e.line(), SPLIB_LOG_LEVEL_ERROR, e.what());
        } catch (const std::exception &e) {
            _logger.log(
                __FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR, e.what());
        } catch (...) {
            _logger.log(
                __FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR,
                "Unknown exception in audio capture thread");
        }

        if (hp)
            iirfilt_rrrf_destroy(hp);
    });
    for (int i = 0; i < 5000 && !_is_running.load(); i++)
        usleep(1000);
    if (!_is_running.load())
        BAIL("Somehow the listening thread never started");
}

AudioEngine::~AudioEngine()
{
    if (_is_running.load()) {
        _is_running.store(false);
        if (_thread.joinable())
            _thread.join();
    }

    for (const auto &kv : _timers)
        printf("%-30s %s\n", kv.first.c_str(), kv.second.to_str().c_str());
}

void
AudioEngine::defaults(AudioEngine::config &cfg)
{
    cfg.block_size = 2048;
    cfg.queue_size = 256;
    cfg.cutoff_hz = 15000.0f;
    cfg.refractory_s = 1.0f;
    cfg.min_thresh = 0.03f;
}

void
AudioEngine::_captureLoop(iirfilt_rrrf &hp)
{
    // BUFFER SETUP
    // frameSize = number of samples per processing block provided by the source.
    const int frameSize = _cfg.block_size;
    std::vector<float> buf(frameSize), buf_hp(frameSize);

    // Detector state
    float noise = 0.0f;     // running noise floor estimate (smoothed RMS)
    uint64_t lastHit = 0;   // last detected event timestamp (ns)
    uint32_t eventSeq = 0;   // monotonically increasing event id
    AudioEngine::event e{}; // reused event struct to push into queue

    // Main capture/detection loop:
    // - read raw samples from the IAudioSource
    // - apply high-pass filter to remove low-frequency content (room rumble, DC)
    // - compute energy/peak metrics on the high-passed signal
    // - update noise estimate and decide whether the block contains a strike
    TIMER_GUARD_BLOCK(_timers["audio_capture"])
    _is_running.store(true);
    while (!_source.is_eof() && _is_running.load(std::memory_order_relaxed)) {
        // Read a block of samples (blocking or non-blocking depending on source)
        _source.read(&(buf[0]), frameSize);

        // Apply configured high-pass IIR (liquid-dsp) to the raw samples.
        // This removes low-frequency components so we focus on transient, percussive energy.
        float y = 0;
        for (int i = 0; i < frameSize; ++i) {
            iirfilt_rrrf_execute(hp, buf[i], &y);
            buf_hp[i] = y;
        }

        // Compute energy metrics on the high-passed buffer:
        // - sumsq: sum of squared samples => used for RMS
        // - max: peak absolute sample in this block (small epsilon added later)
        double sumsq = 0.0;
        double max = 0.0;
        for (float v : buf_hp) {
            sumsq += (double) v * (double) v;
            // accumulate peak; add tiny epsilon to avoid zero division later
            // max = std::fmax(max, std::fabs(v)) + 1e-12;
        }

        // RMS of the block (energy per sample). We add a tiny floor to avoid NaNs.
        float rms = std::sqrt((float) (sumsq / (double) buf_hp.size() + 1e-12));

        // Timing: timestamp this block using the source's monotonic clock.
        uint64_t t = _source.now_ns();
        double since_hit_s = (lastHit == 0) ? 999.0 : (double) (t - lastHit) / 1e9;

        // Decision rule:
        // - rms must exceed the dynamic threshold
        // - the waveform must be sufficiently peaky (reduces sustained noise false positives)
        // - respect the refractory period to avoid multiple detections for one strike
        if (since_hit_s >= _cfg.refractory_s && rms > _cfg.min_thresh) {
            lastHit = t;
            e.t_ns = t;
            e.rms = rms;
            e.event_seq = ++eventSeq;

            std::lock_guard<std::mutex> lk(_mtx);
            if (_queue.size() >= _cfg.queue_size)
                _queue.pop(); // drop oldest
            _queue.push(e);
        }
    }
}

void
AudioEngine::getEvents(std::vector<AudioEngine::event> &out)
{
    std::lock_guard<std::mutex> lk(_mtx);
    while (!_queue.empty()) {
        out.push_back(_queue.front());
        _queue.pop();
    }
}

AudioEngine::IAudioSource::IAudioSource() :
    _sample_rate_hz(0)
{
}

AudioEngine::IAudioSource::IAudioSource(unsigned int sample_rate_hz) :
    _sample_rate_hz(sample_rate_hz)
{
}

void
AudioEngine::IAudioSource::_set_sample_rate_hz(
    unsigned int sample_rate_hz) noexcept
{
    _sample_rate_hz = sample_rate_hz;
}
