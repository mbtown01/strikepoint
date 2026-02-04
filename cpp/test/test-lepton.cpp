#include <errno.h>
#include <fcntl.h>
#include <gtest/gtest.h>
#include <unistd.h>
#include <vector>

#include "driver.h"
#include "error.h"
#include "lepton.h"
#include "logging.h"

using namespace strikepoint;

#define FRAME_HEIGHT 60
#define FRAME_WIDTH 80
#define PACKET_SIZE (4 + 2 * FRAME_WIDTH)

class LeptonTestImpl : public LeptonDriver::ILeptonImpl {

  public:
    LeptonTestImpl();
    ~LeptonTestImpl() override;

    void cameraEnable() override;

    void appendGoodFrame(uint16_t pixelValue);
    void appendBadFrameAllRows(uint16_t pixelValue);
    void appendBadFrameOneRow(uint16_t pixelValue);
    void spiRead(void *buf, size_t len) override;
    void finalize();
    unsigned int cameraEnabledCount() const { return _camera_enabled_count; }

  private:
    void _buildFrame(uint16_t value, std::vector<uint8_t> &frameBuffer);

    std::vector<uint8_t> _data;
    std::atomic<bool> _trigger_eof, _at_eof;
    std::condition_variable _cv;
    std::mutex _mutex;
    off64_t _offset;
    unsigned int _camera_enabled_count;
};

LeptonTestImpl::LeptonTestImpl() :
    _offset(0),
    _trigger_eof(false),
    _at_eof(false),
    _camera_enabled_count(0)
{
}

LeptonTestImpl::~LeptonTestImpl()
{
    _trigger_eof.store(true);
}

void
LeptonTestImpl::cameraEnable()
{
    ++_camera_enabled_count;
}

void
LeptonTestImpl::appendGoodFrame(uint16_t pixelValue)
{
    std::vector<uint8_t> framebuffer;
    _buildFrame(pixelValue, framebuffer);
    std::lock_guard<std::mutex> lk(_mutex);
    _data.insert(_data.end(), framebuffer.begin(), framebuffer.end());
    _cv.notify_one();
}

void
LeptonTestImpl::appendBadFrameAllRows(uint16_t pixelValue)
{
    std::vector<uint8_t> framebuffer;
    _buildFrame(pixelValue, framebuffer);
    uint8_t *data_start = &(framebuffer[0]);
    for (int r = 0; r < FRAME_HEIGHT; r++) {
        uint8_t *packet_buffer = data_start + r * PACKET_SIZE;
        packet_buffer[1] = 0; // packet number
    }

    std::lock_guard<std::mutex> lk(_mutex);
    _data.insert(_data.end(), framebuffer.begin(), framebuffer.end());
    _cv.notify_one();
}

void
LeptonTestImpl::appendBadFrameOneRow(uint16_t pixelValue)
{
    std::vector<uint8_t> framebuffer;
    _buildFrame(pixelValue, framebuffer);
    uint8_t *data_start = &(framebuffer[0]);
    const unsigned int r = 10;
    uint8_t *packet_buffer = data_start + r * PACKET_SIZE;
    packet_buffer[1] = 0; // packet number

    std::lock_guard<std::mutex> lk(_mutex);
    _data.insert(_data.end(), framebuffer.begin(), framebuffer.end());
    _cv.notify_one();
}

void
LeptonTestImpl::spiRead(void *buf, size_t len)
{
    std::unique_lock<std::mutex> lk(_mutex);
    _cv.wait(lk, [this, len] { return (_offset + len) <= _data.size() ||
                                      _trigger_eof.load(); });
    if (_trigger_eof.load() && _offset == _data.size()) {
        _at_eof.store(true);
        BAIL_WITH_ERROR(LeptonDriver::eof_error, "EOF has been reached");
    }
    if ((_offset + len) > _data.size())
        BAIL("Uh oh, somehow there's not enough data left to return");

    memcpy(buf, &(_data[_offset]), len);
    _offset += len;
}

void
LeptonTestImpl::finalize()
{
    _trigger_eof.store(true);
    _cv.notify_one();
    while (!_at_eof.load())
        usleep(1000);
}

void
LeptonTestImpl::_buildFrame(uint16_t value, std::vector<uint8_t> &frameBuffer)
{
    const size_t frameSize = PACKET_SIZE * FRAME_HEIGHT;
    frameBuffer.resize(frameSize);
    uint8_t *data_start = &(frameBuffer[0]);
    for (int r = 0; r < FRAME_HEIGHT; r++) {
        uint8_t *packet_buffer = data_start + r * PACKET_SIZE;
        packet_buffer[0] = 0; // packet header
        packet_buffer[1] = r; // packet number
        uint16_t *short_buffer = (uint16_t *) (packet_buffer + 4);
        for (int c = 0; c < FRAME_WIDTH; ++c)
            short_buffer[c] = value;
    }
}

/*********************************************************************
 * GetFrameInfo - retrieve information about the frame
 *********************************************************************/
TEST(Lepton, GetFrameInfo)
{
    strikepoint::Logger logger("stdout");
    LeptonTestImpl leptonTest;
    strikepoint::LeptonDriver leptonDriver(logger, leptonTest);

    SPLIB_DriverInfo driverInfo;
    leptonDriver.getDriverInfo(&driverInfo);
    leptonTest.finalize();
    EXPECT_EQ(driverInfo.frameWidth, FRAME_WIDTH);
    EXPECT_EQ(driverInfo.frameHeight, FRAME_HEIGHT);
}

/*********************************************************************
 * GetFrameNormal - normal sequence
 *********************************************************************/
TEST(Lepton, GetFrameNormal)
{
    strikepoint::Logger logger("stdout");
    LeptonTestImpl leptonTest;
    strikepoint::LeptonDriver leptonDriver(logger, leptonTest);
    strikepoint::LeptonDriver::frameInfo frame_info;

    leptonTest.appendGoodFrame(0);
    leptonTest.appendGoodFrame(0);
    leptonTest.appendGoodFrame(0);
    for (int i = 0; i < 50; i++) {
        leptonDriver.getFrame(frame_info);
        EXPECT_EQ(3 * i, frame_info.frame_seq);
        leptonTest.appendGoodFrame(i + 1);
        leptonTest.appendGoodFrame(i + 1);
        leptonTest.appendGoodFrame(i + 1);
    }
    leptonTest.finalize();
}

/*********************************************************************
 * GetFrameEveryFrameChanges - Check whether a frame changing every
 * capture is okay or fails
 *********************************************************************/
TEST(Lepton, GetFrameEveryFrameChanges)
{
    strikepoint::Logger logger("stdout");
    LeptonTestImpl leptonTest;
    strikepoint::LeptonDriver leptonDriver(logger, leptonTest);
    strikepoint::LeptonDriver::frameInfo frame_info;

    leptonTest.appendGoodFrame(0);
    for (int i = 0; i < 50; i++) {
        leptonDriver.getFrame(frame_info);
        EXPECT_EQ(i, frame_info.frame_seq);
        leptonTest.appendGoodFrame(i + 1);
    }
    leptonTest.finalize();
}

/*********************************************************************
 * CheckStaleFrames - Do we reboot if we see stale frames
 *********************************************************************/
TEST(Lepton, CheckStaleFrames)
{
    strikepoint::Logger logger("stdout");
    LeptonTestImpl leptonTest;
    strikepoint::LeptonDriver leptonDriver(logger, leptonTest);
    strikepoint::LeptonDriver::frameInfo frame_info;

    for (int i = 0; i < 50; i++)
        leptonTest.appendGoodFrame(50);
    leptonDriver.getFrame(frame_info);
    leptonTest.finalize();
    EXPECT_EQ(1, leptonTest.cameraEnabledCount());
}

/*********************************************************************
 * BadFrameAllRows - Start with a bad frame, do we recover?
 *********************************************************************/
TEST(Lepton, BadFrameAllRows)
{
    strikepoint::Logger logger("stdout");
    LeptonTestImpl leptonTest;
    strikepoint::LeptonDriver leptonDriver(logger, leptonTest);
    strikepoint::LeptonDriver::frameInfo frame_info;

    leptonTest.appendBadFrameAllRows(7);
    for (int i = 0; i < 50; i++) {
        usleep(1000);
        leptonTest.appendGoodFrame(i + 1);
        leptonDriver.getFrame(frame_info);
        EXPECT_EQ(i, frame_info.frame_seq);
    }
    leptonTest.finalize();
}

/*********************************************************************
 * BadFrameOneRow - Start with a bad frame, do we recover?
 *********************************************************************/
TEST(Lepton, BadFrameOneRow)
{
    strikepoint::Logger logger("stdout");
    LeptonTestImpl leptonTest;
    strikepoint::LeptonDriver leptonDriver(logger, leptonTest);
    strikepoint::LeptonDriver::frameInfo frame_info;

    leptonTest.appendBadFrameOneRow(7);
    for (int i = 0; i < 50; i++) {
        usleep(1000);
        leptonTest.appendGoodFrame(i + 1);
        leptonDriver.getFrame(frame_info);
        EXPECT_EQ(i, frame_info.frame_seq);
    }
    leptonTest.finalize();
}

// TEST a single bad frame
// TEST a bunch of bad frames in a row
// TEST stale frames
