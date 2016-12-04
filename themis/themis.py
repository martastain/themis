import os
import time

from nxtools import *

from .base_transcoder import *
from .output_profile import *
from .extract import extract
from .encode  import encode

__all__ = ["Themis"]


class Themis(BaseTranscoder):
    @property
    def defaults(self):
        return {
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
            "expand_levels" : False,  # Expand tv color levels to full
            "deinterlace"   : True,   # Enable smart deinterlace (slower)
            "crop_detect"   : False,  # Enable smart crop detection (slower)
            "loudness"      : False,  # Normalize audio (LUFS)
            "logo"          : False,  # Path to logo to burn in

            "strip_tracks"   : 2,    # 0 - keep all audio tracks, 1 - Keep only first track, 2 - Keep only first track or keep all if they are mono
            "to_stereo"      : True, # Mixdown multichannel audio tracks to stereo
        }


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
            logging.debug("{}: Using deinterlace filter".format(self.friendly_name))
            filters.append(filter_deinterlace())

        filters.append(
            filter_arc(self.settings["width"],
                self.settings["height"],
                self.meta["aspect_ratio"]
                )
            )
        return join_filters(*filters)



    def process(self):
        logging.debug("{}: Has {} audio track(s)".format(self.friendly_name, len(self.audio_tracks)))
        if self.audio_tracks and self.strip_tracks:
            logging.debug("{}: Stripping audio tracks".format(self.friendly_name))
            self.meta["audio_tracks"] = [self.audio_tracks[0]]

        self.meta.update(extract(self))

        success = encode(self)

        if not success:
            try:
                os.remove(self.output_path)
            except:
                pass
            return False

        return True



    def clean_up(self):
        return
        for atrack in self.audio_tracks:
            for l in [
                    atrack.source_audio_path,
                    atrack.final_audio_path
                    ]:
                if os.path.exists(l):
                    logging.debug("Removing {}".format(l))
                    os.remove(l)



