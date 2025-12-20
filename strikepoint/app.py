import dash_bootstrap_components as dbc
import numpy as np
import cv2

from flask import Response, stream_with_context
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
from strikepoint.producer import FrameProducer
from strikepoint.frames import FrameInfoWriter, FrameInfo
from threading import Lock


class StrikePointDashApp:

    def __init__(self, producer: FrameProducer):
        self.app = Dash(__name__, external_stylesheets=[dbc.themes.SLATE])

        self.server = self.app.server  # Flask server used for the stream route
        self.producer = producer
        self.frameWriter = None
        self.frameWriterLock = Lock()

        def hstackGenerator():
            while True:
                frameInfo = self.producer.getFrameInfo()
                frame = np.hstack((frameInfo.rgbFrames['visual'], 
                                   frameInfo.rgbFrames['thermal']))
                with self.frameWriterLock:
                    if self.frameWriter is not None:
                        self.frameWriter.writeFrameInfo(frameInfo)
                yield self.encodeFrame(frame)

        # add the route to the Flask server
        @self.server.route("/hstack")
        def stream_mjpg_route():
            return Response(
                hstackGenerator(), mimetype="multipart/x-mixed-replace; boundary=frame")

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

        self.app.layout = html.Div(
            [
                navbar,
                html.H3("Lepton Live (thermal)"),
                html.Div(
                    [
                        html.Button("Start Recording",
                                    id="start-rec-btn", n_clicks=0),
                    ],
                    style={"marginBottom": "8px"}
                ),
                html.Img(id="frame", src="/hstack",
                         style={"width": "960", "height": "240"}),
            ],
            style={"textAlign": "center"},
        )

        # Dash callback to start recording when button pressed
        @self.app.callback(Output("start-rec-btn", "children"),
                           Input("start-rec-btn", "n_clicks"))
        def on_start_record(n_clicks):
            if not n_clicks:
                return "Start Recording"
            try:
                with self.frameWriterLock:
                    if self.frameWriter is None:
                        self.frameWriter = FrameInfoWriter("recording.bin")
                        return "Stop Recording"
                    else:
                        self.frameWriter.close()
                        self.frameWriter = None
                        return "Start Recording"
            except Exception as ex:
                return "Start Recording"

    def encodeFrame(self, frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to encode frame")
        return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + \
            encoded.tobytes() + b"\r\n"


    def shutdown(self):
        try:
            self.producer.stop()
        except Exception:
            pass
        return

    def run(self, host="0.0.0.0", port=8050, debug=False, threaded=True):
        # threaded=True helps keep the MJPEG stream and Dash callbacks responsive
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)


if __name__ == "__main__":
    app_instance = StrikePointDashApp()
    app_instance.run()
