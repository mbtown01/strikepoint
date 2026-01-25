#include <gtest/gtest.h>
#include "audio.h"
#include "audio-wav.h"

extern "C" {
#include "driver.h"
}

TEST(DriverApi, InitNullArgs)
{
    int rc = SPLIB_Init(NULL, NULL, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
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

    rc = SPLIB_Init(&hndl, &info, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
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

    rc = SPLIB_Init(&hndl, &info, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
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

TEST(AudioApi, DoesItWork)
{
    WavAudioSource source("../../dev/test.wav");
    AudioEngine::config config = {};
    AudioEngine::defaults(config);
    AudioEngine audio(source, config);
    audio.start(&config);
    while (!source.isEOF()) {
        AudioEngine::event event;
        int rc = audio.waitEvent(&event, 1000);
        if (rc == 1) {
            // Event received
            EXPECT_GT(event.score, 0.0f);
        }
    }
    audio.stop();
    
    // This is a placeholder test; actual audio tests would require
    // audio hardware and are not implemented here.
    EXPECT_TRUE(true);
}

int
main(int argc, char **argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}