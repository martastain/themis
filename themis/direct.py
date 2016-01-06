from __future__ import print_function

from nxtools import *

__all__ = ["encode_direct"]

def encode_direct(parent):
    parent.set_status("Transcoding file (direct)")
    cmd = [
        ["r", parent.settings["frame_rate"]],
        ["filter:v", join_filters(*parent.filters)],
        ["pix_fmt", parent.settings.get("pixel_format", "yuv422p")],
        ["c:v", parent.settings["video_codec"]],
        ["b:v", parent.settings["video_bitrate"]],
        ["map", "0:{}".format(parent.meta["video_index"])],
    ]

    if parent.audio_tracks:
        for audio_track in parent.audio_tracks:
            cmd.append(["map", "0:{}".format(audio_track.id)])
        cmd.append(["c:a", parent.settings.get("audio_codec", "pcm_s16le")])
        cmd.append(["ar", parent.settings.get("audio_sample_rate", 48000)])

        if parent.settings.get("audio_bitrate", False):
            cmd.append(["b:a", parent.settings["audio_bitrate"]])

        if parent.gain_change:
            cmd.append(["filter:a", "volume={}dB".format(parent.gain_change)])

    cmd.append(["map_metadata", "-1"])
    cmd.append(["video_track_timescale", parent.settings["frame_rate"]])

    if not ffmpeg(parent.input_path, parent.output_path, output_format=cmd, progress_handler=parent.frame_progress):
        return False

    return True
