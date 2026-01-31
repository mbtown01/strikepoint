#include "error.h"

using namespace strikepoint;

strikepoint::bail_error::bail_error(const char *file, int line, const char *format, ...) :
    _file(file),
    _line(line),
    std::runtime_error("")
{
    char msg_str[4096];
    va_list args;

    va_start(args, format);
    vsnprintf(msg_str, sizeof(msg_str), format, args);
    va_end(args);

    _message = std::string(msg_str);
}
