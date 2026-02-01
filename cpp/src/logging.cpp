#include <mutex>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "error.h"
#include "logging.h"

strikepoint::Logger::Logger(const char *log_file_path) :
    _log_file(stdout)
{
    if (log_file_path == NULL)
        _log_file = NULL;
    else if (strncmp(log_file_path, "stdout", 6) == 0)
        _log_file = stdout;
    else if (strncmp(log_file_path, "stderr", 6) == 0)
        _log_file = stderr;
    else {
        FILE *new_log_file = fopen(log_file_path, "w");
        if (new_log_file == NULL)
            throw std::runtime_error("Could not open log file");
        _log_file = new_log_file;
    }
}

strikepoint::Logger::~Logger()
{
    if (_log_file != NULL && _log_file != stdout && _log_file != stderr)
        fclose(_log_file);
}

void
strikepoint::Logger::log(const char *file_name,
                         const int line,
                         const SPLIB_LogLevel log_level,
                         const char *format, ...)
{
    time_t raw_time;
    struct tm *time_info;
    char time_str[80], msg_str[4096];
    va_list args;

    time(&raw_time);
    time_info = localtime(&raw_time);
    strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", time_info);

    va_start(args, format);
    vsnprintf(msg_str, sizeof(msg_str), format, args);
    va_end(args);

    std::lock_guard<std::mutex> lk(_log_mutex);
    if (_log_file != NULL) {
        fprintf(_log_file, "%s [%s] %s:%d - %s\n",
                time_str, SPLIB_LOG_LEVEL_NAMES[log_level], file_name, line, msg_str);
        fflush(_log_file);
    } else {
        LogEntry entry;
        memcpy(&entry.timestamp, &raw_time, sizeof(time_t));
        entry.message = std::string(msg_str);
        entry.level = log_level;
        _log_buffer.push(entry);
    }
}

int
strikepoint::Logger::getEntriesRemaining()
{
    std::lock_guard<std::mutex> lk(_log_mutex);
    int msgCount = _log_buffer.size();
    return msgCount;
}

void
strikepoint::Logger::getNextEntry(
    int *log_level, char *buffer, size_t buffer_size)
{
    if (log_level == NULL)
        BAIL("level pointer is NULL");
    if (buffer == NULL)
        BAIL("buffer pointer is NULL");
    if (buffer_size == 0)
        BAIL("bufferLen is zero");

    std::lock_guard<std::mutex> lk(_log_mutex);
    if (_log_buffer.empty()) {
        *log_level = SPLIB_LOG_LEVEL_DEBUG;
        buffer[0] = '\0';
    } else {
        *log_level = _log_buffer.front().level;
        strncpy(buffer, _log_buffer.front().message.c_str(), buffer_size - 1);
        buffer[buffer_size - 1] = '\0';
        _log_buffer.pop();
    }
}
