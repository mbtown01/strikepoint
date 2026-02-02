#pragma once

#include <stdarg.h>
#include <stdexcept>

namespace strikepoint {

class bail_error : public std::runtime_error {
  public:
    bail_error(const char *file, int line, const std::string &messsage);

    const std::string &file() const noexcept { return _file; }

    const int line() const noexcept { return _line; }

    static std::string format(const char *format, ...);

  private:
    std::string _file;
    int _line;
};

#define DECLARE_SPECIALIZED_BAIL_ERROR(_error_name)                           \
    class _error_name : public strikepoint::bail_error {                      \
      public:                                                                 \
        _error_name(const char *file, int line, const std::string &message) : \
            strikepoint::bail_error(file, line, message)                      \
        {                                                                     \
        }                                                                     \
    };

#define BAIL_WITH_ERROR(_error_name, fmt, ...) \
    throw _error_name(                         \
        __FILE__, __LINE__, strikepoint::bail_error::format(fmt, ##__VA_ARGS__));

#define BAIL(fmt, ...) BAIL_WITH_ERROR(strikepoint::bail_error, fmt, ##__VA_ARGS__)

} // namespace strikepoint
