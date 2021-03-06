import time
import subprocess

from nxtools import logging, decode_if_py3

class BaseProcessor():
    default_args = []


class Sox(BaseProcessor):
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.args = ["sox", "-S"]
        for arg in args:
            self.args.append(str(arg))
        self.proc = None
        self.err = ""
        self.buff = ""


    def start(self, **kwargs):
        message = "Executing: " + " ".join(self.args)
        logging.debug(message)
        self.proc = subprocess.Popen(
            self.args,
            stdin=kwargs.get("stdin", None),
            stdout=kwargs.get("stdout", subprocess.PIPE),
            stderr=kwargs.get("stderr", subprocess.PIPE),
            close_fds=True
            )
        if kwargs.get("check_output", True):
            self.check_output(handler=kwargs.get("handler", False))

    @property
    def error(self):
        return self.err + self.buff + decode_if_py3(self.proc.stderr.read())

    def check_output(self, handler=False):
        self.buff = ""
        while self.proc.poll() == None:
            ch = decode_if_py3(self.proc.stderr.read(1))
            if ch in ["\n", "\r"]:
                line = self.buff.strip()
                if line.startswith("In:"):
                    at_frame = line.split("%")[0].split(":")[1].strip()
                    at_frame = float(at_frame)
                    if handler:
                        handler(at_frame)
                self.err += self.buff + "\n"
                self.buff = ""
            else:
                self.buff += ch
        return self.proc.returncode
