#pragma once

#include "driver.h"
#include <queue>
#include <mutex>
#include <string>
#include <time.h>

#define LOG_DEBUG(l, fmt, ...) \
    l.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_DEBUG, fmt, ##__VA_ARGS__)
#define LOG_INFO(l, fmt, ...) \
    l.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_INFO, fmt, ##__VA_ARGS__)
#define LOG_WARNING(l, fmt, ...) \
    l.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_WARN, fmt, ##__VA_ARGS__)
#define LOG_ERROR(l, fmt, ...) \
    l.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_ERROR, fmt, ##__VA_ARGS__)
#define LOG_CRITICAL(l, fmt, ...) \
    l.log(__FILE__, __LINE__, SPLIB_LOG_LEVEL_CRITICAL, fmt, ##__VA_ARGS__)

#ifndef DEBUG
#undef LOG_DEBUG
#define LOG_DEBUG(fmt, ...) \
    do {                    \
    } while (0)
#endif

namespace strikepoint {

typedef struct {
    time_t timestamp;
    SPLIB_LogLevel level;
    std::string message;
} LogEntry;

class Logger {
  public:
    Logger(const char *log_file_path);
    ~Logger();

    void log(const char *file_name,
             const int line,
             const SPLIB_LogLevel log_level,
             const char *format, ...);

    int get_entries_remaining();

    void get_next_entry(int *log_level, char *buffer, size_t buffer_size);

  private:
    std::mutex _log_mutex;
    std::queue<LogEntry> _log_buffer;
    FILE *_log_file;
};

} // namespace strikepoint
