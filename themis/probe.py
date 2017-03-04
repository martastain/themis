from nxtools import *
from nxtools.media import *

__all__ = ["probe"]


class AudioTrack():
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
