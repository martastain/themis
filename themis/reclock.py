from __future__ import print_function

import os
import subprocess
from nxtools import *
from processors import Sox

__all__ = ["encode_reclock"]


def reclock_audio_tracks(parent):
    parent.set_status("Extracting audio track(s)")
    cmd = []
    for i, track in enumerate(parent.audio_tracks):
        track.reclock_input_path = parent.get_temp("wav")
        cmd.extend([
                ["map", "0:{}".format(track.id)],
                ["c:a", "pcm_s16le"],
                ["vn", track.reclock_input_path]
            ])

    cmd.append(["f", "null"])

    if not ffmpeg(parent.input_path, os.devnull, output_format=cmd, progress_handler=parent.frame_progress):
        return False

    ##
    # Audio reclock
    ##

    parent.set_status("Resampling audio")
    sox_tempo = float(parent.settings["frame_rate"]) / parent.meta["frame_rate"]

    for i, track in enumerate(parent.audio_tracks):
        f_in = track.reclock_input_path
        f_out = track.reclock_output_path = parent.get_temp("wav")

        cmd = [
                f_in,
                "-r", parent.settings.get("audio_sample_rate", 48000),
                f_out
                ]

        if sox_tempo:
            logging.debug("SOX Tempo: {}".format(sox_tempo))
            cmd.extend(["tempo", sox_tempo])

        if parent.gain_change:
            cmd.extend(["gain", parent.gain_change])

        sox = Sox(*cmd)
        result = sox.start(handler=parent.progress_handler)

        if result:
            logging.error("SOX Failed: {}".format(sox.error))
            return False






def encode_reclock(parent):
    source_format = [
                ["an"],
                ["map", "0:{}".format(parent.meta["video_index"])],
                ["filter:v", join_filters(*parent.filters)],
                ["pix_fmt", parent.settings["pixel_format"]],
                ["f", "rawvideo"],
            ]

    input_format = [
                ["f", "rawvideo"],
                ["pix_fmt", parent.settings["pixel_format"]],
                ["s", "{}x{}".format(parent.settings["width"], parent.settings["height"])],
            ]

    output_format = []

    if parent.audio_tracks:
        reclock_audio_tracks(parent)
        track_mapping = [["map", "0:{}".format(parent.meta["video_index"])]]

        for i, track in enumerate(parent.audio_tracks):
            output_format.append(["i", track.reclock_output_path])
            track_mapping.append(["map", "{}:{}".format(i+1, 0)])

        output_format.extend(track_mapping)
        output_format.extend([
                ["c:a", parent.settings.get("audio_codec", "pcm_s16le")],
                ["ar", parent.settings.get("audio_sample_rate", 48000)],
            ])

    else:
        output_format.append(["an"])

    output_format.extend([
                ["r", parent.settings["frame_rate"]],
                ["c:v", parent.settings["video_codec"]],
                ["b:v", parent.settings["video_bitrate"]],
                ["map_metadata", -1],
                ["video_track_timescale", parent.settings["frame_rate"]],
            ])

    parent.set_status("Transcoding file (reclock)")

    dec = FFMPEG(parent.input_path, "-", source_format)
    dec.start(stdout=subprocess.PIPE)

    enc = FFMPEG("-", parent.output_path, output_format, input_format)
    enc.start(stdin=dec.stdout, stderr=open(os.devnull, "w"))

    dec.stdout.close()

    while dec.is_running or enc.is_running:
        if dec.is_running:
            dec.process(progress_handler=parent.frame_progress)
        if enc.is_running:
            enc.process()

    if dec.return_code or enc.return_code:
        if dec.return_code:
            logging.error("Decoding failed with following error:\n\n{}\n\n".format(indent(dec.error_log)))
        if enc.return_code:
            logging.error("Encoding failed with following error:\n\n{}\n\n".format(indent(dec.error_log)))
        return False

    return True
