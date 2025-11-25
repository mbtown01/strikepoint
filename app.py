import time
import threading
import atexit

import cv2
import numpy as np
from flask import Response

import dash
from dash import html, dcc
from dash.dependencies import Input, Output

from lepton import Lepton


class FrameProducer:
    """Background thread capturing frames and keeping the latest PNG bytes
    and min/max temperatures in Fahrenheit.
    """

    def __init__(self, interval=0.1):
        self.lepton = Lepton()
        self.interval = interval
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
                frame = self.lepton.capture()  # expected: raw 16-bit frame (centi-Kelvin)
                if frame is None:
                    continue

                frame = Lepton.to_fahrenheit(frame)
                frameMin = float(np.nanmin(frame))
                frameMax = float(np.nanmax(frame))

                frame = cv2.resize(frame, (frame.shape[1]*4, frame.shape[0]*4),
                                   interpolation=cv2.INTER_NEAREST)
                frame = cv2.GaussianBlur(frame, (13, 13), 0)
                frame = cv2.normalize(
                    frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

                # Step 4: Find contours
                # First, threshold or normalize the image to get binary values
                _, thresh = cv2.threshold(frame, 220, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(
                    thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                frame = cv2.normalize(
                    frame, None, 50, 200, cv2.NORM_MINMAX).astype(np.uint8)
                frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
                cv2.drawContours(frame, contours, -1, (0, 255, 0), 2)

                ok, buf = cv2.imencode('.png', frame)
                if ok:
                    with self.lock:
                        self.png_bytes = buf.tobytes()
                        self.min_f = frameMin
                        self.max_f = frameMax
                    time.sleep(self.interval)

            except Exception:
                pass

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
        html.Img(id="frame", src="/frame.png",
                 style={"width": "640px", "height": "480px"}),
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
