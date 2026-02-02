#include <fcntl.h>
#include <gtest/gtest.h>
#include <unistd.h>
#include <errno.h>

#include "driver.h"

#include "error.h"
#include "lepton-file.h"
#include "lepton.h"
#include "logging.h"

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60
#define PACKET_SIZE (4 + 2 * FRAME_WIDTH)

void
generateTestData(std::string fileName)
{
    int fd = open(fileName.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0)
        BAIL("Could not open %s for writing: %s", fileName.c_str(), strerror(errno));

    const size_t frame_size = PACKET_SIZE * FRAME_HEIGHT;
    uint8_t packet_buffer[PACKET_SIZE];

    for (int r = 0; r < FRAME_HEIGHT; r++) {
        packet_buffer[0] = 0x0F; // packet header
        packet_buffer[1] = r;    // packet number
        for (int c = 0; c < FRAME_WIDTH; ++c) {
            packet_buffer[2*c + 0] = r;
            packet_buffer[2*c + 1] = c;
        }
        ssize_t wrote = write(fd, packet_buffer, PACKET_SIZE);
        if (wrote != PACKET_SIZE)
            BAIL("Incomplete write to %s", fileName.c_str());
    }
    syncfs(fd);
    close(fd);
}

TEST(Lepton, GetFrameInfo)
{
    strikepoint::Logger logger("stdout");
    strikepoint::LeptonFileImp leptonFile(logger, "/dev/spidev0.0");
    strikepoint::LeptonDriver leptonDriver(logger, leptonFile);

    SPLIB_DriverInfo driverInfo;
    leptonDriver.getDriverInfo(&driverInfo);
    EXPECT_EQ(driverInfo.frameWidth, FRAME_WIDTH);
    EXPECT_EQ(driverInfo.frameHeight, FRAME_HEIGHT);
}

// TEST(Lepton, GetFrameSuccess1)
// {
//     strikepoint::Logger logger("stdout");
//     strikepoint::LeptonFileImp leptonFile(logger, "/dev/spidev0.0");
//     strikepoint::LeptonDriver leptonDriver(logger, leptonFile);

//     strikepoint::LeptonDriver::frameInfo frame_info;
//     leptonDriver.getFrame(frame_info);
// }
