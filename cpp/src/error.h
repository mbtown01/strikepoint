#ifndef __ERROR_H__
#define __ERROR_H__

#include <stdarg.h>
#include <stdexcept>

namespace strikepoint {

class bail_error : public std::runtime_error {
    public:
        bail_error(std::string message, const char *file, int line)
            : _file(file),
              _line(line),
              std::runtime_error(message) {}

        const std::string &file() const noexcept { return _file; }

        int line() const noexcept { return _line; }

        static void bail(const char *fileName,
                         const int line,
                         const char *format, ...);

    private:
        std::string _file;
        int _line;
};

#define BAIL(fmt, ...) \
    strikepoint::bail_error::bail(__FILE__, __LINE__, fmt, ##__VA_ARGS__)

} // namespace strikepoint

#endif // __ERROR_H__