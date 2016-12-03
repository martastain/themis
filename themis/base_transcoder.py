from __future__ import print_function

import time

from nxtools import *

#
# Metadata extraction helpers
#

def guess_aspect (w, h):
    if 0 in [w, h]:
        return 0
    valid_aspects = [(16, 9), (4, 3), (2.35, 1)]
    ratio = float(w) / float(h)
    return "{}:{}".format(*min(valid_aspects, key=lambda x:abs((float(x[0])/x[1])-ratio)))


def find_start_timecode(probe_result):
    tc_places = [
            probe_result["format"].get("tags", {}).get("timecode", "00:00:00:00"),
            probe_result["format"].get("timecode", "00:00:00:00"),
        ]
    tc = "00:00:00:00"
    for i, tcp in enumerate(tc_places):
        if tcp != "00:00:00:00":
            tc = tcp
            break
    return tc


def probe(source_path, progress_handler=False):
    probe_result = ffprobe(source_path)

    if not probe_result:
        return False

    meta = {
            "audio_tracks" : []
        }

    format_info = probe_result["format"]

    for stream in probe_result["streams"]:
        if stream["codec_type"] == "video":
            # Frame rate detection
            fps_n, fps_d = [float(e) for e in stream["r_frame_rate"].split("/")]
            meta["frame_rate"] = fps_n / fps_d

            # Aspect ratio detection
            try:
                dar_n, dar_d = [float(e) for e in stream["display_aspect_ratio"].split(":")]
                if not (dar_n and dar_d):
                    raise Exception
            except:
                dar_n, dar_d = float(stream["width"]), float(stream["height"])

            meta["aspect_ratio"] = dar_n / dar_d
            meta["guess_aspect_ratio"] = guess_aspect(dar_n, dar_d)

            try:
                source_vdur = float(stream["duration"])
            except:
                source_vdur = False

            meta["video_codec"] = stream["codec_name"]
            meta["pixel_format"] = stream["pix_fmt"]
            meta["width"] = stream["width"]
            meta["height"] = stream["height"]
            meta["video_index"] = stream["index"]

            for key in ["color_range"]:
                if key in stream:
                    meta[key] = stream[key]

        elif stream["codec_type"] == "audio":
            meta["audio_tracks"].append(AudioTrack(**stream))

    meta["duration"] = float(format_info["duration"]) or source_vdur
    meta["num_frames"] = meta["duration"] * meta["frame_rate"]

    tc = find_start_timecode(probe_result)
    if tc != "00:00:00:00":
        meta["timecode"] = tc
    return meta


#
# Helper classes
#


class AudioTrack(object):
    def __init__(self, **kwargs):
        self.data = kwargs

    def __getitem__(self, key):
        return self.data[key]

    def __repr__(self):
        return "Audio track ({})".format(self.data["channel_layout"])

    def get(self, key, default=False):
        return self.data.get(key, default)

    @property
    def id(self):
        return self["index"]


class ProcessResult(object):
    def __init__(self, is_success, **kwargs):
        self.is_success = is_success
        self.data = {}
        self.data.update(kwargs)

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return self.is_success

    def get(self, key, default=False):
        return self.data.get(key, default)

    @property
    def message(self):
        return self.get("message", "Invalid data")

    @property
    def is_error(self):
        return not self.is_success


#
# Main class
#


class BaseTranscoder(object):
    def __init__(self, input_path, **kwargs):
        self.input_path = input_path
        self.settings = self.defaults
        self.settings.update(kwargs)
        self.meta = probe(input_path)
        self.last_progress_time = time.time()
        if self.meta:
            self.is_ok = True
        else:
            self.set_status("Unable to open file", level="error")
            self.is_ok = False

    def __getitem__(self, key):
        return self.settings[key]

    def __len__(self):
        return self.is_ok

    @property
    def defaults(self):
        return {}

    ##
    # Clean-up
    ##

    def clean_up(self):
        pass

    def fail_clean_up(self):
        self.clean_up()

    #
    # Source metadata
    #

    @property
    def audio_tracks(self):
        return self.meta.get("audio_tracks", [])

    @property
    def duration(self):
        #TODO: mark-in / out
        return self.meta["duration"]

    #
    # Paths and names
    #

    @property
    def container(self):
        return os.path.splitext(self.input_path)[1].lstrip(".")

    @property
    def base_name(self):
        return self.settings.get("base_name", False) or get_base_name(self.input_path)

    @property
    def friendly_name(self):
        return self.settings.get("friendly_name", False) or self.base_name

    @property
    def profile_name(self):
        return self.settings.get("profile_name", self.settings["video_bitrate"])

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

    #
    # Processing
    #

    def set_status(self, message, level="debug"):
        self.status = message
        {
            False : lambda x: x,
            "debug" : logging.debug,
            "info" : logging.info,
            "warning" : logging.warning,
            "error" : logging.error,
            "good_news" : logging.goodnews
        }.get(level, False)("{}: {}".format(self.friendly_name, message))


    def progress_handler(self, progress):
        if time.time() - self.last_progress_time > 3:
            logging.debug("{}: {} ({:.02f}% done)".format(
                    self.friendly_name,
                    self.status,
                    progress
                ))
            self.last_progress_time = time.time()


    def process(self):
        logging.warning("Nothing to do. You must override process method")


    def start(self, **kwargs):
        self.set_status("Starting {} transcoder".format(self.__class__.__name__), level="info")
        start_time = time.time()
        self.settings.update(kwargs)
        try:
            result = self.process()
        except KeyboardInterrupt:
            print ()
            self.set_status("Aborted", level="warning")
            self.fail_clean_up()
            return False

        except Exception:
            log_traceback("Unhandled exception occured during transcoding")
            result = False

        if not result:
            self.fail_clean_up()
            self.set_status("Failed", level="error")
            return False

        # Final report

        end_time = time.time()
        proc_time = end_time - start_time
        speed = self.duration / proc_time
        logging.info(
            "{}: transcoding {:.2f}s long video finished in {} ({:.2f}x realtime)".format(
                self.friendly_name,
                self.duration,
                s2words(proc_time),
                speed
                ),
            )
        self.set_status("Completed", level="good_news")
        return True


