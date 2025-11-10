import time
import threading
import atexit

import cv2
import numpy as np
from flask import Response

import dash
from dash import html, dcc
from dash.dependencies import Input, Output

from lepton import Lepton  # updated: use refactored lepton.py


class FrameProducer:
    """Background thread capturing frames and keeping the latest PNG bytes
    and min/max temperatures in Fahrenheit.
    """
    def __init__(self, spi_bus=0, spi_device=0, speed_hz=18000000, interval_s=0.1):
        self.lepton = Lepton(spi_bus, spi_device, speed_hz)
        self.interval = interval_s
        self.lock = threading.Lock()
        self.png_bytes = None
        self.min_f = None
        self.max_f = None
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                frame16 = self.lepton.capture()  # expected: raw 16-bit frame (centi-Kelvin)
                if frame16 is not None:
                    # compute temperatures in Fahrenheit using Lepton helper
                    try:
                        temps_f = Lepton.to_fahrenheit(frame16)
                    except Exception:
                        # if capture already returned temps, fall back to using the array as-is
                        temps_f = frame16.astype(np.float32)

                    with self.lock:
                        self.min_f = float(np.nanmin(temps_f))
                        self.max_f = float(np.nanmax(temps_f))

                    # prepare PNG for serving (use the raw 16-bit image for normalization)
                    frame8 = cv2.normalize(frame16, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                    colored = cv2.applyColorMap(frame8, cv2.COLORMAP_INFERNO)
                    ok, buf = cv2.imencode('.png', colored)
                    if ok:
                        with self.lock:
                            self.png_bytes = buf.tobytes()
            except Exception:
                # keep running on capture errors; could log if desired
                pass
            time.sleep(self.interval)

    def get_png(self):
        with self.lock:
            return self.png_bytes

    def get_stats(self):
        with self.lock:
            if self.min_f is None or self.max_f is None:
                return None
            return (self.min_f, self.max_f)

    def stop(self):
        self.running = False
        try:
            self.thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self.lepton.close()
        except Exception:
            pass


# create producer
producer = FrameProducer()

# create Dash app
app = dash.Dash(__name__)
server = app.server  # Flask server used for route below

# a simple endpoint that returns latest PNG
@server.route("/frame.png")
def frame_png():
    png = producer.get_png()
    if png is None:
        # return a 1x1 transparent PNG until first frame arrives
        empty = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\xdac\xf8\x0f\x00\x01\x01\x01\x00;\x82\x05\x1d\x00\x00\x00\x00IEND\xaeB`\x82'
        return Response(empty, mimetype='image/png')
    return Response(png, mimetype='image/png')


app.layout = html.Div(
    [
        html.H3("Lepton Live (thermal)"),
        html.Img(id="frame", src="/frame.png", style={"width": "640px", "height": "480px"}),
        dcc.Interval(id="interval", interval=200, n_intervals=0),  # 200 ms
        html.Div(id="stats", style={"marginTop": "8px", "fontSize": "16px"})
    ],
    style={"textAlign": "center"},
)


# callback returns both the image src (cache-busted) and stats text
@app.callback(
    [Output("frame", "src"), Output("stats", "children")],
    [Input("interval", "n_intervals")]
)
def update_frame_and_stats(n):
    src = f"/frame.png?ts={int(time.time() * 1000)}"
    stats = producer.get_stats()
    if stats is None:
        stats_text = "No frame yet"
    else:
        min_f, max_f = stats
        stats_text = f"Min: {min_f:.1f} °F   Max: {max_f:.1f} °F"
    return src, stats_text


# clean shutdown
def _shutdown():
    producer.stop()


atexit.register(_shutdown)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)