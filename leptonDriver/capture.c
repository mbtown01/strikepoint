#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif

#include "driver.h"
#include "crc16.h"
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

/*
Simple utility to create dummy data file for testing
*/

static void usage(const char *prog) {
    fprintf(stderr, "Usage: %s [--frames N] [-f N] [--output FILE] [-o FILE]\n", prog);
    fprintf(stderr, "  --frames N, -f N         Number of frames to capture (default 256)\n");
    fprintf(stderr, "  --fps N, -d N            Frame per second to capture (default 27)\n");
    fprintf(stderr, "  --output FILE, -o FILE   Output filename (default \"output.bin\")\n");
    exit(1);
}

double get_time_sec() {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return now.tv_sec + now.tv_nsec / 1e9;
}

int main(int argc, char *argv[]) {
    int frames = 256;
    int fps = 27;
    const char *outfile = "output.bin";

    static struct option long_options[] = {
        {"frames", required_argument, 0, 'f'},
        {"fps", required_argument, 0, 'p'},
        {"output", required_argument, 0, 'o'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}};

    int opt, option_index = 0;
    char *endptr = NULL;
    while ((opt = getopt_long(argc, argv, "f:o:d:h", long_options,
                              &option_index)) != -1) {
        switch (opt) {
        case 'f': {
            frames = strtol(optarg, &endptr, 10);
            if (endptr == optarg || *endptr != '\0' || frames <= 0)
                fprintf(stderr, "Invalid frames value: %s\n", optarg);
            break;
        }
        case 'p': {
            fps = strtol(optarg, &endptr, 10);
            if (endptr == optarg || *endptr != '\0' || fps <= 0)
                fprintf(stderr, "Invalid fps value: %s\n", optarg);
            break;
        }
        case 'o':
            outfile = optarg;
            break;
        case 'h':
            usage(argv[0]);
            break;
        default:
            usage(argv[0]);
            break;
        }
    }

    LEPDRV_DriverInfo driverInfo;
    LEPDRV_SessionHandle hndl;
    if (0 != LEPDRV_Init(&hndl, &driverInfo)) {
        fprintf(stderr, "Error initializing Lepton driver\n");
        exit(1);
    }

    const int frameSize = driverInfo.frameHeight * driverInfo.frameWidth;
    float *buffer = (float *) malloc(frameSize);

    int fd = open(outfile, O_CREAT | O_WRONLY | O_TRUNC, 0664);
    if (fd < 0) {
        perror("open(output.bin)");
        LEPDRV_Shutdown(hndl);
        exit(1);
    }

    CRC16 crcOld=0;
    for (int i = 0; i < frames; i++) {
        double start = get_time_sec();
        if (0 != LEPDRV_GetFrame(hndl, buffer, true)) {
            fprintf(stderr, "Error capturing frame %d\n", i);
            break;
        }

        CRC16 crcNew = CalcCRC16Bytes(sizeof(float)*frameSize, (char *)buffer);

        ssize_t wrote = write(fd, buffer, frameSize * sizeof(float));
        if (wrote != (ssize_t) (frameSize * sizeof(float))) {
            fprintf(stderr, "Error writing frame %d: %s\n", i, strerror(errno));
            break;
        }

        double elapsed = get_time_sec() - start;
        double delay = (1.0 / fps) - elapsed;
        printf("Frame %d crc=%x elapsed=%lf delay=%lf\n", i, crcNew, elapsed, delay);
        if (delay > 0)
            usleep(delay * 1e6);
    }

    close(fd);
    LEPDRV_Shutdown(hndl);

    return 0;
}