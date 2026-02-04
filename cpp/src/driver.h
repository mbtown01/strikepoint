
#ifndef __DRIVER_H__
#define __DRIVER_H__

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void *SPLIB_SessionHandle;

typedef struct {
    uint8_t versionMajor;
    uint8_t versionMinor;
    uint16_t frameWidth;
    uint16_t frameHeight;
} SPLIB_DriverInfo;

typedef enum {
    SPLIB_LOG_LEVEL_DEBUG = 0,
    SPLIB_LOG_LEVEL_INFO,
    SPLIB_LOG_LEVEL_WARN,
    SPLIB_LOG_LEVEL_ERROR,
    SPLIB_LOG_LEVEL_CRITICAL
} SPLIB_LogLevel;

extern const char *SPLIB_LOG_LEVEL_NAMES[];

// Create a new session
int SPLIB_Init(SPLIB_SessionHandle *hndl_ptr,
               SPLIB_DriverInfo *info,
               const char *log_file_path);

// Gets the next (raw) frame of data from the device in degC
int SPLIB_LeptonGetFrame(SPLIB_SessionHandle hndl,
                         float *buffer,
                         size_t buffer_size,
                         uint32_t *frame_seq,
                         uint64_t *timestamp_ns);

// Check if there are log entries available
int SPLIB_LogHasEntries(SPLIB_SessionHandle hndl, int *has_entries);

// Get the next log entry from the driver
int SPLIB_LogGetNextEntry(SPLIB_SessionHandle hndl,
                          SPLIB_LogLevel *log_level,
                          char *buffer,
                          size_t buffer_size);

// Retrieve strike event timestamps (in ns)
int SPLIB_GetAudioStrikeEvents(SPLIB_SessionHandle hndl,
                               uint64_t *event_times,
                               size_t max_events,
                               size_t *num_events);

// Close a session
int SPLIB_Shutdown(SPLIB_SessionHandle hndl);

#ifdef __cplusplus
}
#endif

#endif