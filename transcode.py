#!/usr/bin/env python

#
# This is Themis example script.
# It converts files from desired watchfolder to production format.
# All setting can be set using transcode.json configuration file
#

import os
import sys
import json

from nxtools import *

from themis import Themis


class ThemisWatchFolder(WatchFolder):
    def process(self, input_path):
        print input_path
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
                return False

        output_path = os.path.join(output_dir, "{}.{}".format(input_base_name, "mov"))
        if os.path.exists(output_path):
            return False

        themis = Themis(input_path)
        themis.process(
                output_path=output_path,
                video_bitrate="36M"
            )

#            logging.error("Encoding failed")
#            self.ignore_files.add(input_path)





if __name__ == "__main__":
    settings_file = "settings.json"

    if os.path.exists(settings_file):
        try:
            cfg = json.load(open(settings_file))
        except:
            log_traceback()
            cfg = {}

    valid_exts = ["mov", "mp4", "avi", "flv", "mpg", "mpeg", "mp4", "video", "m4v", "mts", "MTS", "MP4"]

    input_dir = cfg.get("input_dir", "input")
    output_dir = cfg.get("output_dir", "output")

    watch = ThemisWatchFolder(
        input_dir=input_dir,
        output_dir=output_dir,
        valid_exts=valid_exts
        )

    watch.start()


