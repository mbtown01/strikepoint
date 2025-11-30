import time
import atexit
import cv2
import numpy as np

from flask import Response, stream_with_context
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
from strikepoint.producer import FrameProducer
import dash_bootstrap_components as dbc


class StrikePointDashApp:

    def __init__(self, interval=0.1):
        self.app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

        self.server = self.app.server  # Flask server used for the stream route
        self.producer = FrameProducer(interval=interval)
        self.register_callbacks()

    def register_callbacks(self):
        # add the route to the Flask server
        @self.server.route("/stream.mjpg")
        def stream_mjpg_route():
            return self.stream_mjpg()

        navbar = dbc.NavbarSimple(
            children=[
                dbc.NavItem(dbc.NavLink("Page 1", href="#")),
                dbc.DropdownMenu(
                    children=[
                        dbc.DropdownMenuItem("More pages", header=True),
                        dbc.DropdownMenuItem("Page 2", href="#"),
                        dbc.DropdownMenuItem("Page 3", href="#"),
                    ],
                    nav=True,
                    in_navbar=True,
                    label="More",
                ),
            ],
            brand="StrikePoint",
            brand_href="#",
            color="primary",
            dark=True,
        )

        # layout: keep MJPEG src static, update stats with dcc.Interval
        self.app.layout = html.Div(
            [
                navbar,
                html.H3("Lepton Live (thermal)"),
                html.Img(id="frame", src="/stream.mjpg",
                         style={"width": "320", "height": "240"}),
                dcc.Interval(id="interval", interval=200,
                             n_intervals=0),  # 200 ms
                html.Div(id="stats", style={
                         "marginTop": "8px", "fontSize": "16px"})
            ],
            style={"textAlign": "center"},
        )

        # callback to update only the stats text (closure captures self.producer)
        @self.app.callback(
            Output("stats", "children"),
            Input("interval", "n_intervals")
        )
        def update_stats(n):
            return self.update_stats(n)

        # clean shutdown registration
        atexit.register(self.shutdown)

    def update_stats(self, n):
        frame = self.producer.getLatestFrame()
        if frame is None:
            return "No frame yet"
        return f"Min: {frame.min():.1f} °F   Max: {frame.max():.1f} °F"

    # register MJPEG stream endpoint using a closure so it captures self.producer
    def stream_mjpg(self):

        def gen():
            while True:
                try:
                    frame = self.producer.getLatestFrame()
                    if frame is None:
                        time.sleep(0.05)
                        continue

                    frame = cv2.normalize(
                        frame, None, 50, 200, cv2.NORM_MINMAX).astype(np.uint8)
                    frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)

                    ok, buf = cv2.imencode('.png', frame)
                    if not ok:
                        raise RuntimeError("Could not encode frame to PNG")

                    part = (
                        b"--frame\r\n"
                        + b"Content-Type: image/png\r\n"
                        + b"Content-Length: " +
                        str(len(buf)).encode() + b"\r\n\r\n" +
                        buf.tobytes() + b"\r\n"
                    )
                    yield part
                    time.sleep(self.producer.interval)
                except GeneratorExit:
                    break
                except Exception as ex:
                    # log and keep trying; prevents the stream from dying silently
                    print("stream_mjpg exception:", ex)
                    time.sleep(0.5)

        return Response(stream_with_context(gen()),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    def shutdown(self):
        try:
            self.producer.stop()
        except Exception:
            pass
    def run(self, host="0.0.0.0", port=8050, debug=False, threaded=True):
        # threaded=True helps keep the MJPEG stream and Dash callbacks responsive
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)


if __name__ == "__main__":
    app_instance = StrikePointDashApp(interval=0.1)
    app_instance.run()
