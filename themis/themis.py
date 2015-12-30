#!/usr/bin/env python
from __future__ import print_function

import os
import sys
import time

from nxtools import *

from .processors import *


# TODO
#   - Replace local implementation of FFMpeg class with nxtools.ffmpeg.ffmpeg
#   - Multichannel audio
#   - Progress handling
#   - Reporting (return meta dict)


class Themis():
    def __init__(self, input_path, **kwargs):
        self.input_path = input_path
        self.settings = self.defaults
        self.settings.update(kwargs)

        self.temp_files = []
        self.status = "(no result)"

        # Source file analysis
        logging.debug("Analysing file {}".format(self.input_path))
        self.probe_result = ffprobe(self.input_path)
        self.analyser_result = ffanalyse(self.input_path)
        logging.debug("Analysis finished")

    def __del__(self):
        self.clean_up()

    def clean_up(self):
        if self.temp_files:
            logging.debug("Cleaning-up temporary files")
        for f in self.temp_files:
            if not os.path.exists(f):
                continue
            try:
                os.remove(f)
            except:
                logging.warning("Unable to remove temporary file {}".format(f))

    @property
    def defaults(self):
        settings = {
            "frame_rate" : 25,
            "loudness" : -23.0,
            "deinterlace" : True,
            "container" : "mov",
            "width" : 1920,
            "height" : 1080,
            "pixel_format" : "yuv422p",
            "video_codec" : "dnxhd",
            "video_bitrate" : "36M",
            "audio_codec" : "pcm_s16le",
            "audio_sample_rate" : 48000
            }
        return settings


    def get_temp(self, extension=False):
        filename = get_temp(extension)
        self.temp_files.append(filename)
        return filename


    def set_status(self, message, level="debug"):
        self.status = message
        {
            False : lambda x: x,
            "debug" : logging.debug,
            "info" : logging.info,
            "warning" : logging.warning,
            "error" : logging.error
        }.get(level, False)(message)

    
    def progress_handler(self, progress):
        print (progress)

    
    @property
    def loudness(self):
        return self.analyser_result.get("audio/r128/i", False)


    def process(self, **kwargs):
        self.settings.update(kwargs)
        base_name = self.settings.get("base_name", False) or get_base_name(self.input_path)
        friendly_name = self.settings.get("friendly_name", False) or base_name

        output_path = os.path.join(
                self.settings["output_dir"], 
                "{}.{}".format(base_name, self.settings["container"]) 
                )

        if os.path.exists(output_path): #TODO : cond
            return

        if not self.probe_result:
            self.set_status("Unable to open source file metadata", "error")
            return False

        logging.info("Normalising {}".format(self.input_path))
       
        ##
        # Streams information
        ##

        atracks = {}
        format_info = self.probe_result["format"]

        for stream in self.probe_result["streams"]:
            if stream["codec_type"] == "video":

                # Frame rate detection
                fps_n, fps_d = [float(e) for e in stream["r_frame_rate"].split("/")]
                source_fps = fps_n / fps_d

                # Aspect ratio detection
                try:
                    dar_n, dar_d = [float(e) for e in stream["display_aspect_ratio"].split(":")]
                    if not (dar_n and dar_d):
                        raise Exception
                except:
                    dar_n, dar_d = float(stream["width"]), float(stream["height"])
                source_dar = dar_n / dar_d

                # Video track duration
                try:
                    source_vdur = float(stream["duration"])
                except: 
                    source_vdur = False

                source_vcodec = stream["codec_name"]
                source_pix_fmt = stream["pix_fmt"]
                source_width = stream["width"]
                source_height = stream["height"]
                video_index = stream["index"]


            elif stream["codec_type"] == "audio":
                atracks[int(stream["index"])] = stream 

        track_indices = atracks.keys()
        atrack = {}

        if track_indices:
            atrack = atracks[min(track_indices)]
            has_audio = True
        else:
            has_audio = False

        duration = source_vdur or float(format_info["duration"])

        ## Extract streams information
        ###################################################################
        ## Check, which streams must be re-encoded

        compare_v = [
            ["container", os.path.splitext(self.input_path)[1][1:]],
            ["frame_rate", source_fps],
            ["video_codec",  source_vcodec],
            ["pixel_format", source_pix_fmt],
            ["width",  source_width],
            ["height", source_height]
            ]


        for key, val in compare_v:
            if self.settings[key] != val:
                logging.debug("Source {} does not match target format. IS: {} SHOULD BE: {}".format(key, val, self.settings[key]) )
                encode_video = True
                break
        else:
            encode_video = False


        ## Check, which streams must be re-encoded
        ###################################################################

        profile_fps = self.settings.get("frame_rate", 25)

        if self.loudness:
            gain = self.settings.get("target_loudness", -23) - self.loudness
            if abs(gain) < 0.5:
                gain = 0
        else:
            gain = 0



        if encode_video:

            filters = []
            if self.settings.get("deinterlace", False):
                filters.append(filter_deinterlace())

            filters.append(filter_arc(self.settings["width"], self.settings["height"], source_dar))

            if source_fps >= profile_fps or profile_fps - source_fps > 4:
                logging.debug("Source FPS: {}".format(source_fps))
                logging.debug("Target FPS: {}".format(profile_fps))

                cmd = [
                    "-i", self.input_path,
                    "-r", profile_fps,
                    "-filter:v", join_filters(*filters),
                    "-pix_fmt", self.settings.get("pixel_format", "yuv422p"),
                    "-c:v", self.settings["video_codec"],
                    "-b:v", self.settings["video_bitrate"],
                    "-map", "0:{}".format(video_index),
                ]

                if has_audio:
                    logging.debug("Source has audio")
                    cmd.append("-map")
                    cmd.append("0:{}".format(atrack["index"]))

                    cmd.append("-c:a")
                    cmd.append(self.settings.get("audio_codec", "pcm_s16le"))

                    cmd.append("-ar")
                    cmd.append(self.settings.get("audio_sample_rate", 48000))

                    if self.settings.get("audio_bitrate", False):
                        cmd.append("-b:a")
                        cmd.append(self.settings["audio_bitrate"])

                    if gain:
                        logging.debug("Adjusting gain by {} dB".format(gain))
                        cmd.append("-filter:a")
                        cmd.append("volume={}dB".format(gain))


                cmd.append("-map_metadata")
                cmd.append("-1")

                cmd.append("-video_track_timescale")
                cmd.append(profile_fps)

                cmd.append(output_path)

                self.set_status("Encoding video (straight from {} to {})".format(source_fps, profile_fps), "info")
                ffmpeg = FFMpeg(*cmd)
                result = ffmpeg.start()

                if result:
                    logging.error("Encoding failed: {}".format(ffmpeg.error))
                    return False

            else:

                if has_audio:
                    sox_tempo = float(profile_fps) / source_fps

                    logging.debug ("Extracting audio track")

                    audio_temp_name = self.get_temp("wav")
                    audio_temp_name2 = self.get_temp("wav")

                    cmd = [
                            "-i", self.input_path,
                            "-vn",
                            "-map", "0:{}".format(atrack["index"]),
                            "-c:a", "pcm_s16le",
                            audio_temp_name
                        ]

                    ffmpeg = FFMpeg(*cmd)
                    result = ffmpeg.start()
                    if result:
                        logging.error("Audio extraction failed: {}".format(ffmpeg.error))
                        return False


                    cmd = [
                            audio_temp_name,
                            "-r", self.settings.get("audio_sample_rate", 48000),
                            audio_temp_name2
                        ]

                    if sox_tempo:
                        logging.debug("SOX Tempo: {}".format(sox_tempo))
                        cmd.append("tempo")
                        cmd.append(sox_tempo)

                    if gain:
                        logging.debug("SOX Gain: {}".format(gain))
                        cmd.append("gain")
                        cmd.append(gain)

                    logging.debug("Processing audio")
                    sox = Sox(*cmd)
                    result = sox.start()

                    if result:
                        logging.error("SOX Failed: {}".format(sox.error))
                        return False


                self.set_status("Encoding video (reclock from {} to {})".format(source_fps, profile_fps), "info")

                cmd1 = [
                    "-i", self.input_path,
                    "-an",
                    "-filter:v", join_filters(*filters),
                    "-pix_fmt", "yuv422p",
                    "-f", "rawvideo",
                    "-"
                    ]

                cmd2 = [
                    "-f", "rawvideo",
                    "-pix_fmt", "yuv422p",
                    "-s", "{}x{}".format(self.settings["width"], self.settings["height"]),
                    "-i", "-",
                    ]

                if has_audio:
                    cmd2.append("-i")
                    cmd2.append(audio_temp_name2)

                    cmd2.append("-c:a")
                    cmd2.append(self.settings.get("audio_codec", "pcm_s16le"))

                    cmd2.append("-ar")
                    cmd2.append(self.settings.get("audio_sample_rate", 48000))

                    if self.settings.get("audio_bitrate", False):
                        cmd2.append("-b:a")
                        cmd2.append(self.settings["audio_bitrate"])


                cmd2.append("-r")
                cmd2.append(profile_fps)

                cmd2.append("-c:v")
                cmd2.append(self.settings["video_codec"])
                cmd2.append("-b:v")
                cmd2.append(self.settings["video_bitrate"])


                cmd2.append("-map_metadata")
                cmd2.append("-1")

                cmd2.append("-video_track_timescale")
                cmd2.append(profile_fps)

                cmd2.append(output_path)



                p1 = FFMpeg(*cmd1)
                p1.start(check_output=False)

                p2 = FFMpeg(*cmd2)
                p2.start(check_output=False, stdin=p1.proc.stdout)

                p1.proc.stdout.close()


                while True:
                    if p1.proc.poll() != None:
                        logging.debug("Proc 1 ended")
                    elif p2.proc.poll() != None:
                        logging.debug("Proc 2 ended")
                    else:
                        try:
                            time.sleep(.001)
                            continue
                        except KeyboardInterrupt:
                            logging.error("PROC1:\n", p1.error, "\n")
                            logging.error("PROC2:\n", p2.error, "\n")
                            break

                    break


        # Just change audio gain
        elif gain:
            logging.debug("Adjusting gain by {} dB".format(gain))
            cmd = [
                    "-i", self.input_path,

                    "-map", "0:{}".format(video_index),
                    "-map", "0:{}".format(atrack["index"]),

                    "-c:v", "copy",
                    "-c:a", self.settings.get("audio_codec", "pcm_s16le"),
                    "-ar", self.settings.get("audio_sample_rate", 48000),
                    "-filter:a", "volume={}dB".format(gain)
                ]


            if self.settings.get("audio_bitrate", False):
                cmd.append("-b:a")
                cmd.append(self.settings["audio_bitrate"])

            cmd.append("-map_metadata")
            cmd.append("-1")

            cmd.append("-video_track_timescale")
            cmd.append(profile_fps)

            cmd.append(output_path)

            ffmpeg = FFMpeg(*cmd)
            ffmpeg.start()

        else:
            logging.info("Moving file".format(gain))
            os.rename(self.input_path, output_path)


        logging.goodnews("Encoding completed")
        return True
