
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
    SPLIB_TEMP_UNITS_KELVIN = 0,
    SPLIB_TEMP_UNITS_CELCIUS,
    SPLIB_TEMP_UNITS_FAHRENHEIT
} SPLIB_TemperatureUnit;

typedef enum {
    SPLIB_LOG_LEVEL_DEBUG = 0,
    SPLIB_LOG_LEVEL_INFO,
    SPLIB_LOG_LEVEL_WARN,
    SPLIB_LOG_LEVEL_ERROR
} SPLIB_LogLevel;

// Create a new session
int SPLIB_Init(SPLIB_SessionHandle *hndl_ptr,
               SPLIB_DriverInfo *info,
               SPLIB_TemperatureUnit temp_unit,
               const char *log_file_path);

// Start the SPI polling thread
int SPLIB_LeptonStartPolling(SPLIB_SessionHandle hndl);

// disable the camera and put it into power down mode
int SPLIB_LeptonDisable(SPLIB_SessionHandle hndl);

// enable the camera
int SPLIB_LeptonEnable(SPLIB_SessionHandle hndl);

// Gets the next (raw) frame of data from the device in degC (or degF)
int SPLIB_LeptonGetFrame(SPLIB_SessionHandle hndl,
                         float *buffer,
                         size_t buffer_size,
                         uint32_t *event_id,
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