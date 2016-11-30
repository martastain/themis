import os
import time

from nxtools import *

from .output_profile import *
from .probe import *
from .extract import extract
from .encode  import encode

__all__ = ["Themis"]

default_settings = {
        "container" : "mov",
        "output_dir" : "output",

        "width" : 1920,
        "height" : 1080,
        "frame_rate" : 25,
        "pixel_format" : "yuv422p",
        "video_codec" : "dnxhd",

        # optional

        "video_bitrate" : False,
        "qscale"        : False,
        "gop_size"      : False,
        "audio_codec"   : False,
        "audio_bitrate" : False,

        #x264/x265 settings
        "level"         : False,
        "preset"        : False,
        "profile"       : False,

        # Helpers
        "expand_levels" : False, # Expand tv color levels to full
        "deinterlace"   : True,  # Enable smart deinterlace (slower)
        "crop_detect"   : False,  # Enable smart crop detection (slower)
        "loudness"      : -23,
        "logo"          : False,

        "strip_tracks"   : 2,    # 0 - keep all audio tracks, 1 - Keep only first track, 2 - Keep only first track or keep all if they are mono
        "to_stereo"      : True, # Mixdown multichannel audio tracks to stereo
    }


class Themis(object):
    def __init__(self, source_path, **kwargs):
        self.source_path = source_path
        self.settings = default_settings
        self.settings.update(kwargs)
        logging.debug("Probing {}".format(self.friendly_name))
        self.meta = probe(source_path)
        self.last_progress_time = time.time()
        self.progress = 0
        self.status = "Pending ingest {}".format(self.friendly_name)


    def __getitem__(self, key):
        return self.settings[key]


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


    @property
    def base_name(self):
        return self.settings.get(
                "base_name",
                get_base_name(self.source_path)
            )


    @property
    def friendly_name(self):
        return self.settings.get("friendly_name", False) or self.base_name


    @property
    def output_path(self):
        if "output_path" in self.settings:
            return self.settings["output_path"]
        if "output_dir" in self.settings:
            return os.path.join(
                self.settings["output_dir"], "{}.{}".format(
                        self.settings["output_dir"],
                        self.settings["container"]
                    )
                )


    @property
    def audio_tracks(self):
        return self.meta.get("audio_tracks", [])


    @property
    def strip_tracks(self):
        if not self["strip_tracks"]:
            return False
        strip_tracks = self["strip_tracks"]
        if list(set([ track["channels"] for track in self.audio_tracks])) == 1:
            if strip_tracks == 2 and self.audio_tracks[0]["channels"] == 1:
                return False
        return strip_tracks


    @property
    def filters(self):
        filters = []
        if self.settings["deinterlace"] and self.meta["is_interlaced"]:
            logging.debug("Video will be deinterlaced")
            filters.append(filter_deinterlace())

        filters.append(
            filter_arc(self.settings["width"],
                self.settings["height"],
                self.meta["aspect_ratio"]
                )
            )
        return join_filters(*filters)


    def progress_handler(self, progress):
        if time.time() - self.last_progress_time > 3:
            logging.debug("{} {} ({:.02f}% done)".format(
                    self.status,
                    self.friendly_name,
                    progress
                ))
            self.last_progress_time = time.time()


    def process(self, **kwargs):
        """v1 compatibility"""
        self.start(**kwargs)


    def start(self, **kwargs):
        self.settings.update(kwargs)
        start_time = time.time()

        logging.debug("There are {} audio tracks".format(len(self.audio_tracks)))
        if self.audio_tracks and self.strip_tracks:
            logging.debug("Strip audio tracks")
            self.meta["audio_tracks"] = [self.audio_tracks[0]]

        self.set_status("Extracting tracks")
        self.meta.update(extract(self))

        success = encode(self)

        # temp file clean-up
        for atrack in self.audio_tracks:
            for l in [
                    atrack.source_audio_path,
                    atrack.final_audio_path
                    ]:
                if os.path.exists(l):
                    logging.debug("removing {}".format(l))
                    os.remove(l)


        if not success:
            try:
                os.remove(self.output_path)
            except:
                pass


        # final report
        total_duration = self.meta["num_frames"] / self.meta["frame_rate"]
        end_time = time.time()
        proc_time = end_time - start_time
        speed = total_duration / proc_time
        self.set_status(
            "Transcoding {:.2f}s long video finished in {} ({:.2f}x realtime)".format(
                total_duration,
                s2words(proc_time),
                speed
                ),
            level="good_news"
            )
        return True
