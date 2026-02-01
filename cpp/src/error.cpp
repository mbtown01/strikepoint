#include "error.h"

using namespace strikepoint;

strikepoint::bail_error::bail_error(const char *file,
                                    int line,
                                    const std::string &message) :
    _file(file),
    _line(line),
    std::runtime_error(message)
{
}

std::string
strikepoint::bail_error::format(const char *format, ...)
{
    char msg_str[4096];
    va_list args;

    va_start(args, format);
    vsnprintf(msg_str, sizeof(msg_str), format, args);
    va_end(args);

    return std::string(msg_str);
}
