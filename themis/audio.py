from __future__ import print_function

from nxtools import *

__all__ = ["encode_audio_only"]

def encode_audio_only(parent):
    parent.set_status("Transcoding file (audio only)")
    cmd = [
            ["map", "0:{}".format(parent.meta["video_index"])],
        ]

    for audio_track in parent.audio_tracks:
        cmd.append(["map", "0:{}".format(audio_track.id)])

    if parent.gain_change:
        cmd.append(["filter:a", "volume={}dB".format(parent.gain_change)])

    cmd.extend([
            ["c:v", "copy"],
            ["c:a", parent.settings.get("audio_codec", "pcm_s16le")],
            ["ar", parent.settings.get("audio_sample_rate", 48000)],
        ])

    if parent.settings.get("audio_bitrate", False):
        cmd.append(["b:a", parent.settings["audio_bitrate"]])

    cmd.append(["map_metadata", "-1"])
    cmd.append(["video_track_timescale", parent.settings["frame_rate"]])

    return ffmpeg(parent.input_path, parent.output_path, output_format=cmd, progress_handler=parent.frame_progress)
