#include "timer.h"
#include "error.h"

using namespace strikepoint;

Timer::Timer() :
    _call_count(0),
    _elapsed_real(0.0),
    _elapsed_user(0.0),
    _elapsed_sys(0.0),
    _running(false)
{
}

void
Timer::start()
{
    if (_running)
        BAIL("Timer started that is already running");

    clock_gettime(CLOCK_MONOTONIC, &_wall_start);
    getrusage(RUSAGE_SELF, &_usage_start);
    _running = true;
}

void
Timer::stop()
{
    if (!_running)
        BAIL("Timer stopped that was not running");

    timespec wall_end;
    rusage usage_end;
    clock_gettime(CLOCK_MONOTONIC, &wall_end);
    getrusage(RUSAGE_SELF, &usage_end);

    _running = false;
    _call_count += 1;
    _elapsed_real +=
        (wall_end.tv_sec - _wall_start.tv_sec) +
        (wall_end.tv_nsec - _wall_start.tv_nsec) * 1e-9;
    _elapsed_user +=
        (usage_end.ru_utime.tv_sec - _usage_start.ru_utime.tv_sec) +
        (usage_end.ru_utime.tv_usec - _usage_start.ru_utime.tv_usec) * 1e-6;
    _elapsed_sys +=
        (usage_end.ru_stime.tv_sec - _usage_start.ru_stime.tv_sec) +
        (usage_end.ru_stime.tv_usec - _usage_start.ru_stime.tv_usec) * 1e-6;
}

std::string
strikepoint::Timer::to_str() const
{
    char buff[256];
    snprintf(buff, sizeof(buff),
             "%7.2f/%6.3f real %7.2f/%6.3f user %7.2f/%6.3f sys (calls=%d)",
             _elapsed_real, _elapsed_real / (float) _call_count,
             _elapsed_user, _elapsed_user / (float) _call_count,
             _elapsed_sys, _elapsed_sys / (float) _call_count,
             _call_count);
    return std::string(buff);
}

