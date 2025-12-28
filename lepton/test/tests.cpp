#include <gtest/gtest.h>

extern "C" {
#include "driver.h"
}

TEST(DriverApi, InitNullArgs) {
    int rc = LEPDRV_Init(NULL, NULL, NULL);
    EXPECT_EQ(rc, -1);
}

TEST(DriverApi, GetFrameNull) {
    float buf[1024];
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

TEST(DriverApi, FillMemoryLogBuffer) {
    LEPDRV_SessionHandle hndl;
    LEPDRV_DriverInfo info;
    LEPDRV_LogLevel level;
    char buffer[256];
    int rc;

    rc = LEPDRV_Init(&hndl, &info, NULL);
    EXPECT_EQ(rc, 0);

    const int logEntriesToAdd = info.maxLogEntries + 10;
    for (int i = 0; i < logEntriesToAdd; i++) {
        rc = LEPDRV_SetTemperatureUnits(
            hndl, LEPDRV_TEMP_UNITS_CELCIUS);
        EXPECT_EQ(rc, 0);
    }

    // Now read back log entries until none remain
    uint32_t entriesRead = 0;
    while (0 == LEPDRV_GetNextLogEntry(hndl, &level, buffer, sizeof(buffer)))
        entriesRead++;

    // Should have maxLogEntries entries, since the log buffer
    // should have overwritten the first few entries
    EXPECT_EQ(entriesRead, info.maxLogEntries);

    for (int i = 0; i < 5; i++) {
        rc = LEPDRV_SetTemperatureUnits(
            hndl, LEPDRV_TEMP_UNITS_CELCIUS);
        EXPECT_EQ(rc, 0);
    }

    entriesRead = 0;
    while (0 == LEPDRV_GetNextLogEntry(hndl, &level, buffer, sizeof(buffer)))
        entriesRead++;

    EXPECT_EQ(entriesRead, 5);

    rc = LEPDRV_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

TEST(DriverApi, SimpleFramePoll) {
    LEPDRV_SessionHandle hndl;
    LEPDRV_DriverInfo info;
    int rc;

    rc = LEPDRV_Init(&hndl, &info, NULL);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_StartPolling(hndl);
    EXPECT_EQ(rc, 0);

    float buffer[info.frameWidth * info.frameHeight];
    rc = LEPDRV_GetFrame(hndl, buffer);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

TEST(DriverApi, RecoveryFramePollOnStartup) {
    LEPDRV_SessionHandle hndl;
    LEPDRV_DriverInfo info;
    int rc;

    rc = LEPDRV_Init(&hndl, &info, NULL);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_CameraDisable(hndl);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_StartPolling(hndl);
    EXPECT_EQ(rc, 0);

    float buffer[info.frameWidth * info.frameHeight];
    rc = LEPDRV_GetFrame(hndl, buffer);
    EXPECT_EQ(rc, 0);

    rc = LEPDRV_Shutdown(hndl);
    EXPECT_EQ(rc, 0);
}

int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}