import cv2
import numpy as np
import dash_bootstrap_components as dbc

from struct import pack
from flask import Response, stream_with_context
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
from strikepoint.producer import FrameProducer
from strikepoint.driver import LeptonDriver
from picamera2 import Picamera2
from threading import Lock


class StrikePointDashApp:

    def __init__(self, interval=0.1):
        self.app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

        self.server = self.app.server  # Flask server used for the stream route
        self.driver = LeptonDriver()
        self.driver.setLogFile('dashApp.log')
        self.driver.startPolling()
        self.picam = Picamera2()

        self.producer = FrameProducer(self.driver, self.picam)
        self.isRecording = False
        self.recStream = None
        self.recLock = Lock()

        self.register_callbacks()

    def register_callbacks(self):

        def hstackGenerator():
            while True:
                frame = self.producer.getFrame()
                with self.recLock:
                    if self.recStream is not None:
                        success, encoded = cv2.imencode(".png", frame)
                        if not success:
                            raise RuntimeError("Image encoding failed")

                        data = encoded.tobytes()
                        self.recStream.write(pack(">I", len(data)))
                        self.recStream.write(data)
                encoded = self.producer.encodeFrame(frame)
                yield self.producer.encodeFrame(frame)

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
                with self.recLock:
                    if not self.isRecording:
                        self.isRecording = True
                        self.recStream = open("recording.bin", "wb")
                        return "Stop Recording"
                    else:
                        self.isRecording = False
                        self.recStream.close()
                        self.recStream = None
                        return "Start Recording"
            except Exception as ex:
                return "Start Recording"

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
    app_instance = StrikePointDashApp(interval=0.1)
    app_instance.run()
