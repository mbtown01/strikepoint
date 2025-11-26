import time
import atexit

from flask import Response, stream_with_context
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
from strikepoint.producer import FrameProducer



class StrikePointDashApp:

    def __init__(self, interval=0.1):
        self.app = Dash(__name__)
        self.server = self.app.server  # Flask server used for the stream route
        self.producer = FrameProducer(interval=interval)
        self.register_callbacks()

    def register_callbacks(self):
        # add the route to the Flask server
        @self.server.route("/stream.mjpg")
        def stream_mjpg_route():
            return self.stream_mjpg()

        # layout: keep MJPEG src static, update stats with dcc.Interval
        self.app.layout = html.Div(
            [
                html.H3("Lepton Live (thermal)"),
                html.Img(id="frame", src="/stream.mjpg",
                         style={"width": "640px", "height": "480px"}),
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
        frameInfo = self.producer.getLatestFrameInfo()
        if frameInfo is None:
            return "No frame yet"
        return f"Min: {frameInfo.minValue:.1f} °F   Max: {frameInfo.maxValue:.1f} °F"

    # register MJPEG stream endpoint using a closure so it captures self.producer
    def stream_mjpg(self):
        def gen():
            while True:
                frameInfo = self.producer.getLatestFrameInfo()
                if frameInfo is None:
                    time.sleep(0.05)
                    continue
                part = (
                    b"--frame\r\n"
                    + b"Content-Type: image/png\r\n"
                    + b"Content-Length: " +
                    str(len(frameInfo.pngBytes)).encode() + b"\r\n\r\n"
                    + frameInfo.pngBytes + b"\r\n"
                )
                yield part
                time.sleep(self.producer.interval)
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
