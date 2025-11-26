#include "driver.h"
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>


void createDummyData(int frameCount)
{
    const int frameSize = FRAME_HEIGHT*FRAME_WIDTH;
    float buffer[80 * 60];
    LEPSDK_Init();

    int fd = open("output.bin", O_CREAT | O_WRONLY);
    for (int i = 0; i < frameCount; i++)
    {
        LEPSDK_GetFrame(buffer, true);
        write(fd, buffer, frameSize*sizeof(float));
        printf("Frame %d\n", i);
    }

    close(fd);
    LEPSDK_Shutdown();

    return (0);

}

int main(int argc, char *argv[])
{
    createDummyData(256);    
}
