#ifndef __LEPTON_H__
#define __LEPTON_H__

#include <stdint.h>


int LEPSDK_Init();
int LEPSDK_GetFrame(uint16_t *frameBuffer);
int LEPSDK_Shutdown();

#endif