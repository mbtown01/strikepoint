import os
import json
import numpy as np

from sqlalchemy import create_engine, text


class Database:
    """Simple helper to init DB and persist/load calibration transforms."""

    def __init__(self, db_uri: str = None):
        uri = db_uri or os.environ.get(
            "STRIKEPOINT_DB_URI",
            f"sqlite:///{os.path.abspath('strikepoint.db')}")
        self.engine = create_engine(uri, future=True)

        stmt = """
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            matrix TEXT NOT NULL
        );
        """
        with self.engine.begin() as conn:
            conn.execute(text(stmt))

    def saveTransform(self, transform: np.ndarray):
        """Persist the affine transform (2x3 numpy array) as JSON to the DB."""
        matrix_json = json.dumps(np.asarray(transform).tolist())
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO calibrations (matrix) VALUES (:matrix)"),
                {"matrix": matrix_json},
            )

    def loadLatestTransform(self):
        """Load the most recent transform from the DB, returns numpy array or None."""
        with self.engine.connect() as conn:
            stmt = """
            SELECT matrix FROM calibrations ORDER BY id DESC LIMIT 1
            """
            result = conn.execute(text(stmt)).fetchone()
            if result is None:
                return None
            matrix_list = json.loads(result[0])
            return np.array(matrix_list, dtype=np.float32)
