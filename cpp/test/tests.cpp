#include <gtest/gtest.h>

extern "C" {
#include "driver.h"
}

TEST(DriverApi, InitNullArgs)
{
    int rc = SPLIB_Init(NULL, NULL, NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, GetFrameNull)
{
    float buf[1024];
    // original test calls two-arg GetFrame(NULL, buf)
    int rc = SPLIB_LeptonGetFrame(NULL, buf);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, ShutdownNull)
{
    int rc = SPLIB_Shutdown(NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, CameraEnableDisableNull)
{
    int rc = SPLIB_LeptonDisable(NULL);
    EXPECT_EQ(rc, -1);
    rc = SPLIB_LeptonEnable(NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, SimpleFramePoll)
{
    SPLIB_SessionHandle hndl;
    SPLIB_DriverInfo info;
    int rc;

    rc = SPLIB_Init(&hndl, &info, NULL);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_LeptonStartPolling(hndl);
    EXPECT_EQ(rc, 0);

    float buffer[info.frameWidth * info.frameHeight];
    rc = SPLIB_LeptonGetFrame(hndl, buffer);
    EXPECT_EQ(rc, 0);

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

    rc = SPLIB_LeptonDisable(hndl);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_LeptonStartPolling(hndl);
    EXPECT_EQ(rc, 0);

    float buffer[info.frameWidth * info.frameHeight];
    rc = SPLIB_LeptonGetFrame(hndl, buffer);
    EXPECT_EQ(rc, 0);

    rc = SPLIB_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

int main(int argc, char **argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}