#pragma once

#include <ctime>
#include <map>
#include <string>
#include <sys/resource.h>
#include <utility>

namespace strikepoint {

class Timer {

  public:
    Timer();

    void start();
    void stop();
    std::string to_str() const;

    unsigned int call_count() const { return _call_count; }
    double elapsed_real() const { return _elapsed_real; }
    double elapsed_user() const { return _elapsed_user; }
    double elapsed_sys() const { return _elapsed_sys; }

  private:
    timespec _wall_start;
    rusage _usage_start;
    double _elapsed_real, _elapsed_user, _elapsed_sys;
    unsigned int _call_count;
    bool _running;
};

class TimerGuard {
  public:
    TimerGuard(Timer &timer) :
        _timer(timer),
        _loop_count(0)
    {
        _timer.start();
    }
    ~TimerGuard() { _timer.stop(); }

    unsigned int loop_count() const { return _loop_count; }

    void loop() { _loop_count++; }

  private:
    Timer &_timer;
    unsigned int _loop_count;
};

#define TIMER_GUARD_BLOCK(timer) \
    for (TimerGuard __g(timer); __g.loop_count() < 1; __g.loop())

} // namespace strikepoint