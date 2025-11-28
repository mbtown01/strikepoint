#include "driver.h"
#include <stdio.h>
#include <errno.h>
#include <stdlib.h>
#include <fcntl.h>
#include <string.h>
#include <unistd.h>
#include <getopt.h>
#include <stdbool.h>
#include <sys/types.h>
#include <sys/stat.h>

/*
Simple utility to create dummy data file for testing
*/

static void usage(const char *prog)
{
    fprintf(stderr, "Usage: %s [--frames N] [-f N] [--output FILE] [-o FILE]\n", prog);
    fprintf(stderr, "  --frames N, -f N         Number of frames to capture (default 256)\n");
    fprintf(stderr, "  --delay N, -d N          Microseconds of delay between captures (default 100000)\n");
    fprintf(stderr, "  --output FILE, -o FILE   Output filename (default \"output.bin\")\n");
    exit(1);
}

int main(int argc, char *argv[])
{
    int frames = 256;                   // default
    int delay = 100000;                 // default
    const char *outfile = "output.bin"; // default

    static struct option long_options[] = {
        {"frames", required_argument, 0, 'f'},
        {"delay", required_argument, 0, 'd'},
        {"output", required_argument, 0, 'o'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}};

    int opt, option_index = 0;
    char *endptr = NULL;
    while ((opt = getopt_long(argc, argv, "f:o:d:h", long_options, &option_index)) != -1)
    {
        switch (opt)
        {
        case 'f':
        {
            frames = strtol(optarg, &endptr, 10);
            if (endptr == optarg || *endptr != '\0' || frames <= 0)
                fprintf(stderr, "Invalid frames value: %s\n", optarg);
            break;
        }
        case 'd':
        {
            delay = strtol(optarg, &endptr, 10);
            if (endptr == optarg || *endptr != '\0' || delay <= 0)
                fprintf(stderr, "Invalid delay value: %s\n", optarg);
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

    LEPSDK_DriverInfo driverInfo;
    LEPSDK_Init(&driverInfo);
    const int frameSize = driverInfo.frameHeight * driverInfo.frameWidth;
    float *buffer = (float *)malloc(frameSize);

    int fd = open(outfile, O_CREAT | O_WRONLY | O_TRUNC, 0664);
    if (fd < 0)
    {
        perror("open(output.bin)");
        LEPSDK_Shutdown();
        exit(1);
    }

    for (int i = 0; i < frames; i++)
    {
        if (0 != LEPSDK_GetFrame(buffer, true))
        {
            fprintf(stderr, "Error capturing frame %d\n", i);
            break;
        }

        ssize_t wrote = write(fd, buffer, frameSize * sizeof(float));
        if (wrote != (ssize_t)(frameSize * sizeof(float)))
        {
            fprintf(stderr, "Error writing frame %d: %s\n", i, strerror(errno));
            break;
        }
        printf("Frame %d\n", i);
        usleep(delay);
    }

    close(fd);
    LEPSDK_Shutdown();

    return 0;
}
// ...existing code...