#!/usr/bin/env python

#
# This is Themis example script.
# It converts files from desired watchfolder to production format.
# All setting can be set using transcode.json configuration file
#

import os
import sys
import time
import json
import sets

from themis import Themis
from themis import Log

from nxtools import *


##
# Simple watchfolder class
# 
# Requires
#     - nxtools.*
#     - os
#     - time
#     - sets
##

class WatchFolder():
    def __init__(self, input_dir, **kwargs):
        self.input_dir = input_dir
        self.settings = self.defaults
        self.settings.update(**kwargs)
        self.file_sizes = {}
        self.ignore_files = sets.Set()

    @property
    def defaults(self):
        settings = {
            "iter_delay" : 5,
            "recursive" : True,
            "valid_exts" : []
            }
        return settings

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
            try:
                f = open(input_path, "rb")
            except:
                logging.debug("File creation in progress. {}".format(os.path.basename(input_path)))
                continue

            f.seek(0, 2)
            file_size = f.tell()
            f.close()

            if file_size == 0:
                continue

            if not (input_path in self.file_sizes.keys() and self.file_sizes[input_path] == file_size):
                self.file_sizes[input_path] = file_size
                logging.debug("New file {} detected (or file has been changed)".format(input_path))
                continue
            self.process(input_path)

    def process(self, input_path):
        pass





class ThemisWatchFolder(WatchFolder):
    def process(self, input_path):
        input_rel_path = input_path.replace(self.input_dir, "", 1).lstrip("/")
        input_base_name = get_base_name(input_rel_path)

        output_rel_dir = os.path.split(input_rel_path)[0]
        output_dir = os.path.join(self.settings["output_dir"], output_rel_dir)
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except:
                logging.error("Unable to create output directory {}".format(output_rel_dir))
                self.ignore_files.add(input_path)
                continue

        output_path = os.path.join(output_dir, "{}.{}".format(input_base_name, self.profile.get("container", "mov")))
        
        if os.path.exists(output_path): #TODO: If not overwrite
            continue

        themis = Themis(input_path)

        if not themis.process(output_path, self.profile):
            logging.error("Encoding failed")
            self.ignore_files.add(input_path)

        ##
        # Move source file to "done" directory
        ##

        if self.done_dir:
            done_dir = os.path.join(self.done_dir, output_rel_dir)
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except:
                    logging.error("Unable to create backup directory {}".format(output_rel_dir))
            
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

    valid_exts = ["mov", "mp4", "avi", "flv", "mpg", "mpeg", "mp4", "video", "m4v"]
    
    input_dir = cfg.get("input_dir", "input")
    output_dir = cfg.get("output_dir", "output")

    watch = ThemisWatchFolder(
        input_dir=input_dir, 
        output_dir=output_dir,
        valid_exts=valid_exts
        )

    watch.start()


