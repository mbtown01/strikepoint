#pragma once

#include "driver.h"
#include <pthread.h>
#include <queue>
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
    Logger(const char *logFilePath);
    ~Logger();

    void log(const char *fileName,
             const int line,
             const SPLIB_LogLevel logLevel,
             const char *format, ...);

    int getMessagesRemaining();

    void getNextLogEntry(int *logLevel, char *buffer, size_t bufferLen);

  private:
    pthread_mutex_t _logMutex;
    std::queue<LogEntry> _logBuffer;
    FILE *_logFile;
};

} // namespace strikepoint
