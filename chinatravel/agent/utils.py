import sys
from numpy import ndarray, integer, floating
import numpy as np
import json
import os


def _safe_open_path(path):
    """Return a path that is safe to open on the current OS.

    - Ensures the parent directory exists (Windows won't create it implicitly,
      and `open()` fails if it's missing).
    - On Windows, applies the `\\\\?\\` extended-length prefix so paths longer
      than the ~260-char MAX_PATH limit still work. No-op on macOS and Linux.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.name == "nt":
        abs_path = os.path.abspath(path)
        if not abs_path.startswith("\\\\?\\"):
            abs_path = "\\\\?\\" + abs_path
        return abs_path
    return path


def decode_numpy_dict(d):
    if isinstance(d, dict):
        return {decode_numpy_dict(k): decode_numpy_dict(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [decode_numpy_dict(i) for i in d]
    elif isinstance(d, integer):
        return int(d)
    elif isinstance(d, floating):
        return float(d)
    elif isinstance(d, ndarray):
        return decode_numpy_dict(d.tolist())
    else:
        return d


class Logger(object):
    def __init__(self, filename="default.log", stream=sys.stdout, debug_mode=False):

        self.debug_mode = debug_mode

        ## Create parent dirs and handle Windows long paths before opening.
        self.log = open(_safe_open_path(filename), "a", encoding="utf-8")

        if self.debug_mode:
            self.terminal = stream

    def write(self, message):
        self.log.write(message)

        if self.debug_mode:
            self.terminal.write(message)

    def flush(self):
        if hasattr(self, "log") and not self.log.closed:
            self.log.flush()
        if self.debug_mode:
            self.terminal.flush()

    def __del__(self):
        if hasattr(self, "log") and not self.log.closed:
            self.log.close()


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


def load_json_file(file_path):
    with open(_safe_open_path(file_path), "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(json_data, file_path):
    with open(_safe_open_path(file_path), "w", encoding="utf8") as dump_f:
        json.dump(json_data, dump_f, ensure_ascii=False, indent=4, cls=NpEncoder)
