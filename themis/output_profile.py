from nxtools import *

__all__ = ["get_output_profile"]


default_bitrates = {
        "dnxhd" : "120M",
        "mjpeg" :  False,
        "mpeg2video" : "50M",
        "libx264" : "6M",
        "libx265" : "4M",
        "libfdk_aac" : "128k",
        "mp2" : "128k"
    }

default_audio_codecs = {
        "dnxhd" : "pcm_s16le",
        "mjpeg" : "pcm_s16le",
        "mpeg2video" : "mp2",
        "libx264" : "libfdk_aac",
        "libx265" : "libfdk_aac"
    }


def get_output_profile(**kwargs):

    #
    # Video
    #

    result = [
            ["r", kwargs["frame_rate"]],
            ["pix_fmt", kwargs.get("pixel_format", "yuv422p")],
            ["c:v", kwargs["video_codec"]]
        ]

    video_bitrate = kwargs.get("video_bitrate", False) or default_bitrates.get(kwargs["video_codec"], False)
    if video_bitrate:
        result.append(["b:v", video_bitrate])

    if kwargs["qscale"]:
        result.append(["q:v", kwargs["qscale"]])

    if kwargs["gop_size"]:
        gop_size = kwargs["gop_size"]
        result.extend([
                ["g", gop_size],
                ["keyint_min", gop_size],
            ])
        if kwargs["video_codec"] == "libx264":
            result.append(["x264opts", "keyint={g}:min-keyint={g}:no-scenecut".format(g=gop_size)])

    #
    # Audio
    #

    audio_codec = kwargs.get("audio_codec", default_audio_codecs.get("video_codec", False))
    if not audio_codec:
        audio_codec = "pcm_s16le"
    result.append(["c:a", audio_codec])

    audio_bitrate = kwargs.get("audio_bitrate", default_bitrates.get(audio_codec, False))
    if audio_bitrate:
        result.append(["b:a", audio_bitrate])

    #
    # Container
    #

    result.append(["map_metadata", "-1"])

    if kwargs["container"] == "mov" and kwargs["frame_rate"] == 25:
        result.append(["video_track_timescale", 25])

    return result
