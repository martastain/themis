#!/usr/bin/env python

import os
import sys
import time
import json

from themis import Themis
from themis import Log


DEFAULT_PROFILE = {
    "name" : "DNxHD 1080p25 36Mbps",
    "fps" : 25,
    "loudness" : -23.0,
    "deinterlace" : True,
    "container" : "mov",

    "width" : 1920,
    "height" : 1080,
    "pixel_format" : "yuv422p",
    "video_codec" : "dnxhd",
    "video_bitrate" : "36M",
    "audio_codec" : "pcm_s16le",
    "audio_sample_rate" : 48000
    }


class WatchFolder():
    def __init__(self, src_dir="input", tgt_dir="output", done_dir="done", profile=False, logging=False):
        self.src_dir = src_dir
        self.tgt_dir = tgt_dir
        self.done_dir = done_dir
        self.profile = profile or DEFAULT_PROFILE
        self.logging = logging or Log("ThemisDemo")

        self.filesizes = {}


    def start(self):
        while True:
            self.main()
            time.sleep(5)


    def clean_filesizes(self):
        keys = self.filesizes.keys()
        for f in keys:
            if not os.path.exists(f):
                del(self.filesizes[f])

    def main(self):
        for fname in os.listdir(self.src_dir):
            fpath = os.path.join(self.src_dir, fname)
            try:
                 f = open(fpath,"rb")
            except:
                 self.logging.debug("File creation in progress. {}".format(fname))
                 continue

            f.seek(0,2)
            fsize = f.tell()
            f.close()

            if not (fpath in self.filesizes.keys() and self.filesizes[fpath] == fsize):
                self.filesizes[fpath] = fsize
                self.logging.debug("New file {} detected (or file has been changed)".format(fname))
                continue

            self.process(fname)

        self.clean_filesizes()


    def process(self, fname):
        fpath = os.path.join(self.src_dir, fname)

        tname = os.path.splitext(fname)[0]
        tpath = os.path.join(self.tgt_dir, tname + "." + self.profile["container"])
        dpath = os.path.join(self.done_dir, fname)

        themis = Themis(fpath, logging=self.logging)
        themis.analyze()

        if not themis.process(tpath, self.profile):
            self.logging.error("Encoding failed")
            return False

        try:
            os.rename(fpath, dpath)
        except:
            logging.error("Unable to move source file to done")
            return False

        return True



if __name__ == "__main__":
    try:
        cfg = json.load(open("config.json"))
    except:
        cfg = {}

    src_dir = cfg.get("src_dir", "input")
    tgt_dir = cfg.get("tgt_dir", "output")
    done_dir = cfg.get("done_dir", "done")

    watch = WatchFolder(
        src_dir=src_dir, 
        tgt_dir=tgt_dir, 
        done_dir=done_dir
        )

    watch.start()
