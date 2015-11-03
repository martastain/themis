#!/usr/bin/env python

#
# This is Themis example script.
# It converts files from desired watchfolder to production format.
# All setting can be set using transcode.json configuration file
#

from __future__ import print_function

import os
import sys
import time
import json
import stat
import sets

from themis import Themis
from themis import Log


#
# Default encoding profile (nxtv production format)
#

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

#
# get_files helper function from nxtools.files
#

def get_files(base_path, **kwargs):
    recursive = kwargs.get("recursive", False)
    hidden = kwargs.get("hidden", False)
    relative_path = kwargs.get("relative_path", False)
    exts = kwargs.get("exts", [])
    strip_path=kwargs.get("strip_path", base_path)
    if os.path.exists(base_path):
        for file_name in os.listdir(base_path):
            if not hidden and file_name.startswith("."):
                continue
            file_path = os.path.join(base_path, file_name) 
            if S_ISREG(os.stat(file_path)[ST_MODE]): 
                if exts and os.path.splitext(file_name)[1].lstrip(".") not in exts:
                    continue
                if relative_path:
                    yield file_path.replace(strip_path, "", 1).lstrip(os.path.sep)
                else:
                    yield file_path
            elif S_ISDIR(os.stat(file_path)[ST_MODE]) and recursive: 
                for file_path in get_files(file_path, recursive=recursive, hidden=hidden, exts=exts, relative_path=relative_path, strip_path=strip_path): 
                    yield file_path


#
# base_name helper function from nxtools.files
#

def base_name(fname): 
    return os.path.splitext(os.path.basename(fname))[0] 

#
# Simple watchfolder class
#

class WatchFolder():
    def __init__(self, input_dir, output_dir, **kwargs):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.done_dir = kwargs.get("done_dir", False)
        self.profile = kwargs.get("profile", DEFAULT_PROFILE)
        self.logging = kwargs.get("logging", Log("Themis"))
        self.iter_delay = kwargs.get("iter_delay", 5)
        self.recursive = kwargs.get("recursive", True)
        
        self.valid_exts = ["mov", "mp4", "avi", "flv", "mpg", "mpeg", "mp4", "video", "m4v"] #TODO: Add common video files
        self.file_sizes = {}
        self.ignore_files = sets.Set()

    def start(self):
        while True:
            self.main()
            self.clean_filesizes()
            time.sleep(self.iter_delay)

    def clean_filesizes(self):
        keys = self.file_sizes.keys()
        for file_path in keys:
            if not os.path.exists(file_path):
                del(self.file_sizes[file_path])

    def main(self):
        for input_path in get_files(self.input_dir, recursive=self.recursive, exts=self.valid_exts):
            
            if input_path in self.ignore_files:
                continue

            input_rel_path = input_path.replace(self.input_dir, "", 1).lstrip("/")
            input_base_name = base_name(input_rel_path)
            
            #
            # Check file completion
            #

            try:
                f = open(input_path, "rb")
            except:
                self.logging.debug("File creation in progress. {}".format(os.path.basename(input_path)))
                continue

            f.seek(0, 2)
            file_size = f.tell()
            f.close()

            if file_size == 0:
                continue

            if not (input_path in self.file_sizes.keys() and self.file_sizes[input_path] == file_size):
                self.file_sizes[input_path] = file_size
                self.logging.debug("New file {} detected (or file has been changed)".format(input_rel_path))
                continue

            #
            # Transcode file
            #

            output_rel_dir = os.path.split(input_rel_path)[0]
            output_dir = os.path.join(self.output_dir, output_rel_dir)
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except:
                    self.logging.error("Unable to create output directory {}".format(output_rel_dir))
                    self.ignore_files.add(input_path)
                    continue

            output_path = os.path.join(output_dir, "{}.{}".format(input_base_name, self.profile.get("container", "mov")))
            
            if os.path.exists(output_path): #TODO: If not overwrite
                continue

            themis = Themis(input_path, logging=self.logging)
            themis.analyze()

            if not themis.process(output_path, self.profile):
                self.logging.error("Encoding failed")
                self.ignore_files.add(input_path)

            #
            # Move source file to "done" directory
            #

            if self.done_dir:
                done_dir = os.path.join(self.done_dir, output_rel_dir)
                if not os.path.exists(output_dir):
                    try:
                        os.makedirs(output_dir)
                    except:
                        self.logging.error("Unable to create backup directory {}".format(output_rel_dir))
                
                if os.path.exist(output_dir):
                    done_path = os.path.join(self.done_dir, input_rel_path)
                    
                    try:
                        os.rename(fpath, dpath)
                    except:
                        logging.error("Unable to move source file to done")

            



if __name__ == "__main__":
    try:
        cfg = json.load(open("transcode.json"))
    except:
        cfg = {}

    input_dir = cfg.get("input_dir", "input")
    output_dir = cfg.get("output_dir", "output")

    watch = WatchFolder(
        input_dir=input_dir, 
        output_dir=output_dir, 
        ) #TODO: kwargs

    watch.start()
