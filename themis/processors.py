import subprocess

from nxtools import logging, decode_if_py3

class BaseProcessor():
    default_args = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.args = []
        for arg in self.default_args:
            self.args.append(str(arg))
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
            stderr=kwargs.get("stderr", subprocess.PIPE)
            )
        if kwargs.get("check_output", True):
            self.check_output(handler=kwargs.get("handler", False))

    @property 
    def error(self):
        return self.err + self.buff + decode_if_py3(self.proc.stderr.read())


class FFMpeg(BaseProcessor):
    default_args = ["ffmpeg", "-y"]

    def check_output(self, handler=False):
        self.buff = ""
        while self.proc.poll() == None:
            ch = decode_if_py3(self.proc.stderr.read(1))
            if ch in ["\n", "\r"]:
                if self.buff.startswith("frame="):
                    at_frame = self.buff.split("fps")[0].split("=")[1].strip()
                    if handler:
                        handler(at_frame)
                self.err += self.buff + "\n"
                self.buff = ""
            else:
                self.buff += ch
        return self.proc.returncode


class Sox(BaseProcessor):
    default_args = ["sox", "-S"]

    def check_output(self, handler=False):
        self.buff = ""
        while self.proc.poll() == None:
            ch = decode_if_py3(self.proc.stderr.read(1))
            if ch in ["\n", "\r"]:
                if self.buff.startswith("In:"):
                    at_frame = self.buff.split("%")[0].split(":")[1].strip()
                    if handler:
                        handler(at_frame)
                self.err += self.buff + "\n"
                self.buff = ""
            else:
                self.buff += ch
        return self.proc.returncode

