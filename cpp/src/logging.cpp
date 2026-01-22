
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "error.h"
#include "logging.h"

static const char *LOG_LEVEL_MAP[] = {
    "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"};

strikepoint::Logger::Logger(const char *logFilePath) :
    _logFile(stdout)
{
    pthread_mutex_init(&_logMutex, NULL);

    if (logFilePath == NULL)
        _logFile = NULL;
    else if (strncmp(logFilePath, "stdout", 6) == 0)
        _logFile = stdout;
    else if (strncmp(logFilePath, "stderr", 6) == 0)
        _logFile = stderr;
    else {
        FILE *newLogFile = fopen(logFilePath, "w");
        if (newLogFile == NULL)
            throw std::runtime_error("Could not open log file");
        _logFile = newLogFile;
    }
}

strikepoint::Logger::~Logger()
{
    pthread_mutex_destroy(&_logMutex);

    if (_logFile != NULL && _logFile != stdout && _logFile != stderr)
        fclose(_logFile);
}

void
strikepoint::Logger::log(const char *fileName,
                         const int line,
                         const LogLevel logLevel,
                         const char *format, ...)
{
    time_t rawtime;
    struct tm *timeinfo;
    char timeStr[80], msgStr[4096];
    va_list args;

    time(&rawtime);
    timeinfo = localtime(&rawtime);
    strftime(timeStr, sizeof(timeStr), "%Y-%m-%d %H:%M:%S", timeinfo);

    va_start(args, format);
    vsnprintf(msgStr, sizeof(msgStr), format, args);
    va_end(args);

    pthread_mutex_lock(&_logMutex);
    if (_logFile != NULL) {
        fprintf(_logFile, "%s [%s] %s:%d - %s\n",
                timeStr, LOG_LEVEL_MAP[logLevel], fileName, line, msgStr);
        fflush(_logFile);
    } else {
        LogEntry entry;
        memcpy(&entry.timestamp, &rawtime, sizeof(time_t));
        entry.message = std::string(msgStr);
        entry.level = logLevel;
        _logBuffer.push(entry);
    }
    pthread_mutex_unlock(&_logMutex);
}

int
strikepoint::Logger::getMessagesRemaining()
{
    pthread_mutex_lock(&_logMutex);
    int msgCount = _logBuffer.size();
    pthread_mutex_unlock(&_logMutex);
    return msgCount;
}

void
strikepoint::Logger::getNextLogEntry(
    int *logLevel, char *buffer, size_t bufferLen)
{
    if (logLevel == NULL)
        BAIL("level pointer is NULL");
    if (buffer == NULL)
        BAIL("buffer pointer is NULL");
    if (bufferLen == 0)
        BAIL("bufferLen is zero");

    pthread_mutex_lock(&_logMutex);
    if (_logBuffer.empty()) {
        buffer[0] = '\0';
    } else {
        *logLevel = _logBuffer.front().level;
        strncpy(buffer, _logBuffer.front().message.c_str(), bufferLen - 1);
        buffer[bufferLen - 1] = '\0';
        _logBuffer.pop();
    }
    pthread_mutex_unlock(&_logMutex);
}
