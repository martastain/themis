#!/usr/bin/env python

import os
import sys
import time
import json

from themis import Themis

try:
    cfg = json.load(open("config.json"))
except:
    cfg = {}

SRC_DIR = cfg.get("src_dir", "input")
TGT_DIR = cfg.get("tgt_dir", "output")
DONE_DIR = cfg.get("done_dir", "done")


PROFILE = {
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



for fname in os.listdir(SRC_DIR):
    fpath = os.path.join(SRC_DIR, fname)

    tname = os.path.splitext(fname)[0]
    tpath = os.path.join(TGT_DIR, tname + "." + PROFILE["container"])

    themis = Themis(fpath)
    themis.analyze()

    themis.process(tpath, PROFILE)


