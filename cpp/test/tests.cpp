#include "audio-wav.h"
#include "audio.h"
#include <gtest/gtest.h>

extern "C" {
#include "driver.h"
}

using namespace strikepoint;

TEST(DriverApi, InitNullArgs)
{
    int rc = SPLIB_Init(NULL, NULL, SPLIB_TEMP_UNITS_FAHRENHEIT, NULL);
    EXPECT_EQ(rc, -2);
}

TEST(DriverApi, GetFrameNull)
{
    const size_t pixel_count = 10;
    float buffer[pixel_count];
    uint32_t eventId;
    uint64_t timestamp_ns;
    int rc = SPLIB_LeptonGetFrame(
        NULL, buffer, pixel_count, &eventId, &timestamp_ns);
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

void
testForStrikeEvents(std::string fileName, std::vector<uint64_t> expectedEventTimes)
{
    WavAudioSource source(fileName);
    AudioEngine::config config = {};
    AudioEngine::defaults(config);
    AudioEngine audio(source, config);

    while (!source.is_eof())
        usleep(10000);

    std::vector<AudioEngine::event> events;
    audio.getEvents(events);
    EXPECT_EQ(events.size(), expectedEventTimes.size());
    for (int i = 0; i < events.size(); i++) {
        EXPECT_GE(events[i].t_ns, expectedEventTimes[i] - 50 * 1000 * 1000);
        EXPECT_LE(events[i].t_ns, expectedEventTimes[i] + 50 * 1000 * 1000);
    }
}

TEST(AudioApi, RealData_01)
{
    uint64_t event_times[] = {
        14463999774, 23466666300, 33685332807, 44650665969, 56426665785};
    std::vector<uint64_t> expectedEventTimes(
        std::begin(event_times), std::end(event_times));
    testForStrikeEvents("../../../strikepoint-test-data/test-01.wav", expectedEventTimes);
}

TEST(AudioApi, RealData_02)
{
    uint64_t event_times[] = {
        5077333333, 11520000000, 21888000000, 33962666666, 44416000000, 54869333333};
    std::vector<uint64_t> expectedEventTimes(
        std::begin(event_times), std::end(event_times));
    testForStrikeEvents("../../../strikepoint-test-data/test-02.wav", expectedEventTimes);
}

int
main(int argc, char **argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}