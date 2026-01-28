#include "error.h"

using namespace strikepoint;

void
bail_error::bail(const char *file_name,
                              const int line,
                              const char *format, ...)
{
    char msg_str[4096];
    va_list args;

    va_start(args, format);
    vsnprintf(msg_str, sizeof(msg_str), format, args);
    va_end(args);

    throw bail_error(std::string(msg_str), file_name, line);
}
