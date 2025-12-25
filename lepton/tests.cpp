#include <gtest/gtest.h>

extern "C" {
#include "driver.h"
}

#define FRAME_WIDTH 80
#define FRAME_HEIGHT 60

// The original C tests asserted error return (-1) for NULL/invalid args.
// Here we follow the same expectations; if your driver returns a different
// error code change EXPECT_EQ(..., -1) -> EXPECT_NE(..., 0) as appropriate.

TEST(DriverApi, InitNullArgs) {
    // original C test called LEPDRV_Init(NULL, NULL, NULL)
    // keep the same call - adjust if your header has different signature.
    int rc = LEPDRV_Init(NULL, NULL, NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, GetFrameNull) {
    float buf[FRAME_WIDTH * FRAME_HEIGHT];
    // original test calls two-arg GetFrame(NULL, buf)
    int rc = LEPDRV_GetFrame(NULL, buf);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, ShutdownNull) {
    int rc = LEPDRV_Shutdown(NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, CameraEnableDisableNull) {
    int rc = LEPDRV_CameraDisable(NULL);
    EXPECT_EQ(rc, -1);
    rc = LEPDRV_CameraEnable(NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, SimpleFramePoll) {
    LEPDRV_SessionHandle hndl;
    LEPDRV_DriverInfo info;
    float buffer[FRAME_HEIGHT*FRAME_WIDTH];
    int rc;

    rc = LEPDRV_Init(&hndl, &info, "stdout");
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_StartPolling(hndl);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_GetFrame(hndl, buffer);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

TEST(DriverApi, RecoveryFramePoll) {
    LEPDRV_SessionHandle hndl;
    LEPDRV_DriverInfo info;
    float buffer[FRAME_HEIGHT*FRAME_WIDTH];
    int rc;

    rc = LEPDRV_Init(&hndl, &info, "stdout");
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_CameraDisable(hndl);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_StartPolling(hndl);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_GetFrame(hndl, buffer);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}