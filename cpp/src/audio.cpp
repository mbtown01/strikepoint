#include "audio.h"
#include "error.h"
#include <chrono>
#include <cmath>
#include <ctime>

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
        _cfg.cutoff_hz / (float) _source.sampleRate_Hz(),
        0.0f, // f0 unused for high-pass
        1.0f, // Ap (passband ripple) unused for Butterworth
        60.0f // As (stopband attenuation) unused for Butterworth
    );

    if (!_hp)
        BAIL("Failed to create liquid-dsp high-pass filter");

    _running.store(true);
    _thread = std::thread([this] { _captureLoop(); });
}

AudioEngine::~AudioEngine()
{
    if (_running.load()) {
        _running.store(false);
        if (_thread.joinable())
            _thread.join();
    }
}

void
AudioEngine::defaults(AudioEngine::config &cfg)
{
    cfg.blockSize = 2048;
    cfg.queueSize = 256;
    cfg.cutoff_hz = 15000.0f;
    cfg.refractory_s = 1.0f;
    cfg.minThresh = 0.03f;
}

void
AudioEngine::_captureLoop()
{
    // BUFFER SETUP
    // frameSize = number of samples per processing block provided by the source.
    const int frameSize = _cfg.blockSize;
    std::vector<float> buf(frameSize), buf_hp(frameSize);

    // Detector state
    float noise = 0.0f;     // running noise floor estimate (smoothed RMS)
    uint64_t lastHit = 0;   // last detected event timestamp (ns)
    uint32_t eventId = 0;   // monotonically increasing event id
    AudioEngine::event e{}; // reused event struct to push into queue

    // Main capture/detection loop:
    // - read raw samples from the IAudioSource
    // - apply high-pass filter to remove low-frequency content (room rumble, DC)
    // - compute energy/peak metrics on the high-passed signal
    // - update noise estimate and decide whether the block contains a strike
    while (!_source.isEOF() && _running.load(std::memory_order_relaxed)) {
        // Read a block of samples (blocking or non-blocking depending on source)
        _source.read(&(buf[0]), frameSize);

        // Apply configured high-pass IIR (liquid-dsp) to the raw samples.
        // This removes low-frequency components so we focus on transient, percussive energy.
        float y = 0;
        for (int i = 0; i < frameSize; ++i) {
            iirfilt_rrrf_execute(_hp, buf[i], &y);
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

        // peakiness = peak / rms
        // A transient (strike) tends to have a sharp peak relative to its RMS.
        // float peakiness = max / (rms + 1e-12f);

        // Timing: timestamp this block using the source's monotonic clock.
        uint64_t t = _source.nowNs();
        double since_hit_s = (lastHit == 0) ? 999.0 : (double) (t - lastHit) / 1e9;

        // Decision rule:
        // - rms must exceed the dynamic threshold
        // - the waveform must be sufficiently peaky (reduces sustained noise false positives)
        // - respect the refractory period to avoid multiple detections for one strike
        if (since_hit_s >= _cfg.refractory_s && rms > _cfg.minThresh) {
            lastHit = t;
            e.t_ns = t;
            e.rms = rms;
            // e.peakiness = peakiness;
            // e.score = rms * peakiness; // composite score for ranking
            e.eventId = ++eventId;

            std::lock_guard<std::mutex> lk(_mtx);
            if (_queue.size() >= _cfg.queueSize)
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
