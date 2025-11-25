#include "driver.h"

int main(int argc, char *argv[])
{
    float buffer[80*60];
    LEPSDK_Init();

    while(1)
    {   
        LEPSDK_GetFrame(buffer, true);
        printf("Frame\n");
    }
        

    LEPSDK_Shutdown();

    return(0);

}