import re
import os
import subprocess

from nxtools import *
from nxtools.media import *

from .sox import Sox
from .output_profile import get_output_profile

__all__ = ["encode"]

def encode(parent):
    if parent.reclock_ratio:
        encode_method = "reclock"
        source_format = [
                    ["an"],
                    ["map", "0:{}".format(parent.meta["video_index"])],
                    ["filter:v", parent.filters],
                    ["pix_fmt", parent.settings["pixel_format"]],
                    ["f", "rawvideo"],
                ]
        input_format = [
                    ["f", "rawvideo"],
                    ["pix_fmt", parent.settings["pixel_format"]],
                    ["s", "{}x{}".format(parent.settings["width"], parent.settings["height"])],
                ]
        output_format = []
        track_mapping = [["map", "0:0"]]

    else:
        encode_method = "direct"
        input_format = []
        output_format = [
                ]
        track_mapping = [["map", "0:{}".format(parent.meta["video_index"])]]



    for i, track in enumerate(parent.audio_tracks):
        if encode_method == "reclock":
            parent.set_status("Reclocking audio {} of {}".format(
                i+1,
                len(parent.audio_tracks),
                ))
            f_in = track.source_audio_path
            f_out = track.final_audio_path = get_temp("wav")
            cmd = [
                    f_in,
                    "-r", parent.settings.get("audio_sample_rate", 48000),
                    f_out
                ]
            cmd.extend(["tempo", parent.reclock_ratio])
            sox = Sox(*cmd)
            result = sox.start(handler=parent.progress_handler)

        track_mapping.append(["map", "{}:{}".format(i+1, 0)])
        if track.get("tags", {}).get("language", False):
            track_mapping.append(["metadata:s:{}".format(i+1), "language={}".format(track["tags"]["language"])])
        output_format.append(["i", track.final_audio_path])


    parent.set_status("Transcoding")

    output_format.extend(track_mapping)

    if encode_method == "direct":
        output_format.append(["filter:v", parent.filters])

    output_format.extend(get_output_profile(**parent.settings))

    if encode_method == "reclock":
        dec = FFMPEG(parent.input_path, "-", source_format)
        dec.start(stdout=subprocess.PIPE)
        enc_input = "-"
        enc_stdin = dec.stdout
        enc_stderr = open(os.devnull, "w")
    else:
        enc_input = parent.input_path
        enc_stdin = None
        enc_stderr = subprocess.PIPE


    enc = FFMPEG(enc_input, parent.output_path, output_format, input_format)
    enc.start(stdin=enc_stdin, stderr=enc_stderr)

    if encode_method == "reclock":
        dec.stdout.close()
        while dec.is_running or enc.is_running:
            if dec.is_running:
                dec.process(progress_handler=lambda x: parent.progress_handler(float(x) / parent.meta["num_frames"] * 100))
            if enc.is_running:
                enc.process()

        if dec.return_code or enc.return_code:
                logging.error("Decoding failed with following error:\n\n{}\n\n".format(indent(dec.error_log)))
                logging.error("Encoding failed with following error:\n\n{}\n\n".format(indent(enc.error_log)))

    else:
        while enc.is_running:
            enc.process(progress_handler=lambda x: parent.progress_handler(float(x) / parent.meta["num_frames"] * 100))

    return True




