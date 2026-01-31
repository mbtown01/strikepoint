#include "audio-wav.h"
#include "audio.h"
#include <gtest/gtest.h>

using namespace strikepoint;


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
