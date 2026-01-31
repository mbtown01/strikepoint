#include <gtest/gtest.h>

extern "C" {
#include "driver.h"
}

TEST(DriverApi, InitNullArgs)
{
    int rc = SPLIB_Init(NULL, NULL, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
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

TEST(DriverApi, CameraEnableNullHandle)
{
    int rc = SPLIB_LeptonEnable(NULL);
    EXPECT_EQ(rc, -2);
}
TEST(DriverApi, CameraDisableNullHandle)
{
    int rc = SPLIB_LeptonDisable(NULL);
    EXPECT_EQ(rc, -2);
}

TEST(DriverApi, SimpleFramePoll)
{
    SPLIB_SessionHandle hndl;
    SPLIB_DriverInfo info;
    int rc;

    rc = SPLIB_Init(&hndl, &info, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_LeptonStartPolling(hndl);
    EXPECT_EQ(rc, 0);

    const size_t pixel_count = info.frameWidth * info.frameHeight;
    float buffer[pixel_count];
    uint32_t event_id;
    uint64_t timestamp_ns;
    rc = SPLIB_LeptonGetFrame(hndl, buffer, pixel_count, &event_id, &timestamp_ns);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

TEST(DriverApi, RecoveryFramePollOnStartup)
{
    SPLIB_SessionHandle hndl;
    SPLIB_DriverInfo info;
    int rc;

    rc = SPLIB_Init(&hndl, &info, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_LeptonDisable(hndl);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_LeptonStartPolling(hndl);
    EXPECT_EQ(rc, 0);

    const size_t pixel_count = info.frameWidth * info.frameHeight;
    float buffer[pixel_count];
    uint32_t event_id;
    uint64_t timestamp_ns;
    rc = SPLIB_LeptonGetFrame(hndl, buffer, pixel_count, &event_id, &timestamp_ns);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}
