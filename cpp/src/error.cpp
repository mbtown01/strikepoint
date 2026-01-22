#include "error.h"

void
strikepoint::bail_error::bail(const char *fileName,
                              const int line,
                              const char *format, ...)
{
    char msgStr[4096];
    va_list args;

    va_start(args, format);
    vsnprintf(msgStr, sizeof(msgStr), format, args);
    va_end(args);

    throw strikepoint::bail_error(std::string(msgStr), fileName, line);
}
