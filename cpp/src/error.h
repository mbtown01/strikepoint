#pragma once

#include <stdarg.h>
#include <stdexcept>

namespace strikepoint {

class bail_error : public std::runtime_error {
  public:
    bail_error(const char *file, int line, const char *format, ...);

    const std::string &file() const noexcept { return _file; }

    int line() const noexcept { return _line; }

    virtual const char *what() const noexcept override
    {
        return _message.c_str();
    }

  private:
    std::string _file, _message;
    int _line;
};

#define BAIL(fmt, ...) \
    throw strikepoint::bail_error(__FILE__, __LINE__, fmt, ##__VA_ARGS__)

} // namespace strikepoint
