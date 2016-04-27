# TODO
#   - Reimplement sox
#   - Reporting (return meta dict)
#   - Reclock encoder error handling
#   - Move matching files

from __future__ import print_function

import os
import sys
import time

from nxtools import *

# Trancoding methods

from .reclock import *
from .audio import *
from .direct import *

__all__ = ["Themis"]


class AudioTrack():
    def __init__(self, **kwargs):
        self.data = kwargs

    def __getitem__(self, key):
        return self.data[key]

    @property
    def id(self):
        return self["index"]


class Themis():
    def __init__(self, input_path, **kwargs):
        self.input_path = input_path
        self.settings = self.defaults
        self.settings.update(kwargs)
        self.temp_files = []
        self.filters = []
        self.probe_result = {}
        self.analyse_result = {}
        self.meta = {
                "container" : os.path.splitext(self.input_path)[1].lstrip(".")
                }
        self.status = "Starting conversion"

    @property
    def defaults(self):
        settings = {
            "frame_rate" : 25,
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
        return settings

    ##
    # Temporary files handling
    ##

    def get_temp(self, extension=False):
        filename = get_temp(extension)
        self.temp_files.append(filename)
        return filename

    def clean_up(self):
        if self.temp_files:
            logging.debug("Cleaning-up temporary files")
        for f in self.temp_files:
            if not os.path.exists(f):
                continue
            try:
                os.remove(f)
            except:
                logging.warning("Unable to remove temporary file {}".format(f))

    def __del__(self):
        self.clean_up()

    ##
    # Paths and names
    ##

    @property
    def base_name(self):
        return self.settings.get("base_name", False) or get_base_name(self.input_path)

    @property
    def friendly_name(self):
        return self.settings.get("friendly_name", False) or self.base_name

    @property
    def output_path(self):
        return self.settings.get("output_path", False) or  os.path.join(
                self.settings["output_dir"],
                "{}.{}".format(self.base_name, self.settings["container"])
                )

    ##
    # Logging
    ##

    def set_status(self, message, level="debug"):
        self.status = message
        {
            False : lambda x: x,
            "debug" : logging.debug,
            "info" : logging.info,
            "warning" : logging.warning,
            "error" : logging.error,
            "good_news" : logging.goodnews
        }.get(level, False)(message)

    def progress_handler(self, progress):
        pass

    def frame_progress(self, at_frame):
        progress = min(99.99, (at_frame / self.num_frames) * 100)
        self.progress_handler(progress)

    ##
    # Source metadata extraction
    ##

    def analyse(self, video=True, audio=True):
        self.current_phase = 1
        self.set_status("Analysing {}".format(self.friendly_name))
        self.analyse_result = ffanalyse(self.input_path, progress_handler=self.frame_progress, video=video, audio=audio)

    def probe(self):
        self.set_status("Probing {}".format(self.friendly_name))
        self.probe_result = ffprobe(self.input_path)
        self.audio_tracks = []

        format_info = self.probe_result["format"]

        for stream in self.probe_result["streams"]:
            if stream["codec_type"] == "video":
                # Frame rate detection
                fps_n, fps_d = [float(e) for e in stream["r_frame_rate"].split("/")]
                self.meta["frame_rate"] = fps_n / fps_d

                # Aspect ratio detection
                try:
                    dar_n, dar_d = [float(e) for e in stream["display_aspect_ratio"].split(":")]
                    if not (dar_n and dar_d):
                        raise Exception
                except:
                    dar_n, dar_d = float(stream["width"]), float(stream["height"])
                self.meta["aspect_ratio"] = dar_n / dar_d

                # Video track duration
                try:
                    source_vdur = float(stream["duration"])
                except:
                    source_vdur = False

                self.meta["video_codec"] = stream["codec_name"]
                self.meta["pixel_format"] = stream["pix_fmt"]
                self.meta["width"] = stream["width"]
                self.meta["height"] = stream["height"]
                self.meta["video_index"] = stream["index"]

            elif stream["codec_type"] == "audio":
                self.audio_tracks.append(AudioTrack(**stream))

        self.meta["duration"] = float(format_info["duration"]) or source_vdur
        self.meta["num_frames"] = self.meta["duration"] * self.meta["frame_rate"]


    @property
    def loudness(self):
        key = "audio/r128/i"
        if not key in self.analyse_result:
            self.analyse(video=False)
        return self.analyse_result.get(key, self.settings["loudness"])

    @property
    def is_interlaced(self):
        key = "video/is_interlaced"
        if not key in self.analyse_result:
            self.analyse()
        return self.analyse_result.get(key, False)

    @property
    def gain_change(self):
        gain_change = self.settings.get("loudness", -23) - self.loudness
        return gain_change if (self.loudness and abs(gain_change) > 0.5) else 0

    @property
    def duration(self):
        return self.meta["duration"]

    @property
    def num_frames(self):
        return self.meta["num_frames"]

    ##
    # Main process
    ##

    def process(self, **kwargs):
        start_time = time.time()
        logging.debug("Updating settings:", str(kwargs))
        self.settings.update(kwargs)
        self.set_status("Transcoding {}".format(self.friendly_name), level="info")
        try:
            result = self._process()
        except KeyboardInterrupt:
            print ()
            logging.warning("Transcoding aborted", level="warning")
            result = False
        if not result:
            self.fail_clean_up()
            self.set_status("Transcoding failed", level="error")
            return False
        end_time = time.time()
        proc_time = end_time - start_time
        speed = self.duration / proc_time
        self.set_status(
            "Transcoding {:.2f}s long video finished in {} ({:.2f}x realtime)".format(
                self.duration,
                s2words(proc_time),
                speed
                ),
            level="good_news"
            )
        return True

    def fail_clean_up(self):
        if os.path.exists(self.output_path):
            os.remove(self.output_path)

    def _process(self):
        if not self.probe_result:
            self.probe()
        ##
        # Check, which streams must be re-encoded
        ##

        compare_v = [
            "container",
            "frame_rate",
            "video_codec",
            "pixel_format",
            "width",
            "height",
            ]

        for key in compare_v:
            if self.settings[key] != self.meta[key]:
                logging.debug(
                    "Source {} does not match target format. IS: {} SHOULD BE: {}".format(
                        key,
                        self.meta[key],
                        self.settings[key]
                        )
                    )
                encode_video = True
                break
        else:
            encode_video = False

        ##
        # Decide, which method will be used and execute!
        ##

        if encode_video:
            # Create video filter chain
            if self.settings["deinterlace"] and self.is_interlaced:
                logging.debug("Video will be deinterlaced")
                self.filters.append(filter_deinterlace())
            self.filters.append(
                filter_arc(self.settings["width"],
                    self.settings["height"],
                    self.meta["aspect_ratio"]
                    )
                )

            source_fps = self.meta.get("frame_rate", 25)
            profile_fps = self.settings.get("frame_rate", 25)
            if source_fps >= profile_fps or profile_fps - source_fps > 3:
                encode_method = encode_direct
            else:
                encode_method = encode_reclock
        else:
            encode_method =  encode_audio_only
        return encode_method(self)
