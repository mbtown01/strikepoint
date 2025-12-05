
## Steps

``` bash
sudo apt update
sudo apt install python3-dev python3-pip build-essential cmake git libusb-1.0-0-dev
sudo apt-get install libgtk2.0-dev pkg-config
```

## Resource links

https://flir.netx.net/file/asset/13333/original/attachment

### Sparkfun setup and initial project
https://learn.sparkfun.com/tutorials/flir-lepton-hookup-guide/all
https://cdn.sparkfun.com/assets/8/0/d/b/3/DS-16912-FLiR_Lepton_-_Breakout_Board_V2.pdf
https://groupgets-files.s3.amazonaws.com/lepton/Resources/Getting%20Started%20with%20the%20Raspberry%20Pi%20and%20Breakout%20Board%20V2.0.pdf

### Simple camera wiring

|RPI |FLIR|
|---|---|
| SDA(3) | SDA(5) |
| 5V(4) | 5V(2) |
| SCL(5) | SCL(8) |
| GND(6) | GND(1) |
| GPIO17(11) | GPIO3(15) |
| MSIO(21) | SPI_MSIO(12) |
| SCLK(23) | SPI_CLK(7) |
| CEO(24) | SPI_CS(10) |

### Reference documents

https://www.digikey.tw/htmldatasheets/production/1752535/0/0/1/500-0643-00.pdf