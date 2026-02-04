#include <gtest/gtest.h>

extern "C" {
#include "driver.h"
}

TEST(DriverApi, InitNullArgs)
{
    int rc = SPLIB_Init(NULL, NULL, NULL);
    EXPECT_EQ(rc, -2);
}

TEST(DriverApi, GetFrameNullHandle)
{
    const size_t pixel_count = 10;
    float buffer[pixel_count];
    uint32_t eventId;
    uint64_t timestamp_ns;
    int rc = SPLIB_LeptonGetFrame(
        NULL, buffer, pixel_count, &eventId, &timestamp_ns);
    EXPECT_EQ(rc, -2);
}

TEST(DriverApi, ShutdownNullHandle)
{
    int rc = SPLIB_Shutdown(NULL);
    EXPECT_EQ(rc, -2);
}

void _drainLogEntries(SPLIB_SessionHandle hndl)
{
    int logHasEntries = false;
    SPLIB_LogLevel level;
    char logBuffer[4096];

    SPLIB_LogHasEntries(hndl, &logHasEntries);
    while (logHasEntries) {
        SPLIB_LogGetNextEntry(
            hndl, &level, logBuffer, sizeof(logBuffer));
        printf("LOG [%s]: %s\n", SPLIB_LOG_LEVEL_NAMES[level], logBuffer);
        SPLIB_LogHasEntries(hndl, &logHasEntries);
    }
}

TEST(DriverApi, SimpleFramePoll)
{
    SPLIB_SessionHandle hndl;
    SPLIB_DriverInfo info;
    int rc;

    rc = SPLIB_Init(&hndl, &info, NULL);
    EXPECT_EQ(rc, 0);

    const size_t pixel_count = info.frameWidth * info.frameHeight;
    float buffer[pixel_count];
    uint32_t frame_seq;
    uint64_t timestamp_ns;
    rc = SPLIB_LeptonGetFrame(hndl, buffer, pixel_count, &frame_seq, &timestamp_ns);
    EXPECT_EQ(rc, 0);

    _drainLogEntries(hndl);
    rc = SPLIB_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

TEST(DriverApi, RecoveryFramePollOnStartup)
{
    SPLIB_SessionHandle hndl;
    SPLIB_DriverInfo info;
    int rc;

    rc = SPLIB_Init(&hndl, &info, NULL);
    EXPECT_EQ(rc, 0);

    const size_t pixel_count = info.frameWidth * info.frameHeight;
    float buffer[pixel_count];
    uint32_t frame_seq;
    uint64_t timestamp_ns;
    rc = SPLIB_LeptonGetFrame(hndl, buffer, pixel_count, &frame_seq, &timestamp_ns);
    EXPECT_EQ(rc, 0);

    _drainLogEntries(hndl);
    rc = SPLIB_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}
