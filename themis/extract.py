import re
import subprocess
import time

from nxtools import *

def extract(parent):
    """
    This function:
        - extracts audio tracks
        - detects crop
        - detects interlaced content

    It does not:
        - analyze loudness (audio tracks may be time-stretched later)
    """

    filters = []
    if parent["deinterlace"] and parent.meta["frame_rate"] >= 25:
        filters.append("idet")
    if parent["crop_detect"]:
        filters.append("cropdetect")

    cmd = [
            "ffmpeg",
            "-i", parent.source_path,
        ]
    if filters:
        cmd.extend([
            "-map", "0:{}".format(parent.meta["video_index"]),
            "-filter:v", ",".join(filters), "-f", "null", "-",
        ])

    for i, track in enumerate(parent.audio_tracks):
        track.source_audio_path = track.final_audio_path = get_temp("wav")
        cmd.extend(["-map", "0:{}".format(track.id)])
        cmd.extend(["-c:a", "pcm_s16le"])
        if parent["to_stereo"]:
            cmd.extend(["-ac", "2"])
        cmd.append(track.source_audio_path)


    result = {
            "is_interlaced" : False
        }
    last_idet = buff = ""
    at_frame = 0

    st = time.time()
    logging.debug("Executing: {}".format(" ".join(cmd)))
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    while proc.poll() == None:
        try:
            ch = decode_if_py3(proc.stderr.read(1))
        except:
            continue
        if ch in ["\n", "\r"]:
            line = buff.strip()
            if line.startswith("frame="):
                m = re.match(r".*frame=\s*(\d+)\s*fps.*", line)
                if m:
                    at_frame = int(m.group(1))
                    parent.progress_handler(float(at_frame) / parent.meta["num_frames"] * 100)

            elif line.find("Repeated Fields") > -1:
                last_idet = line
            buff = ""
        else:
            buff += ch

    if last_idet:
        exp = r".*Repeated Fields: Neither:\s*(\d+)\s*Top:\s*(\d+)\s*Bottom:\s*(\d+).*"
        m = re.match(exp, last_idet)
        if m:
            n = int(m.group(1))
            t = int(m.group(2))
            b = int(m.group(3))
            tot = n + t + b
            if n / float(tot) < .9:
                result["is_interlaced"] = True

    if at_frame:
        result["num_frames"] = at_frame
    return result

