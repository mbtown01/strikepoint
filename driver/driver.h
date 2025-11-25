#ifndef __LEPTON_H__
#define __LEPTON_H__

#include <stdint.h>
#include <stdbool.h>


int LEPSDK_Init();
int LEPSDK_GetFrame(float *frameBuffer, bool asFahrenheit);
int LEPSDK_Shutdown();

#endif