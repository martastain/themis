from __future__ import print_function

import os
import sys
import time

from nxtools import *

from .processors import *


# TODO
#   - Reimplement sox
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

        ##
        # Check, which streams must be re-encoded
        ##

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

                ##
                # Direct encoding
                ##

                logging.debug("Source FPS: {}".format(source_fps))
                logging.debug("Target FPS: {}".format(profile_fps))

                cmd = [
                    ["r", profile_fps],
                    ["filter:v", join_filters(*filters)],
                    ["pix_fmt", self.settings.get("pixel_format", "yuv422p")],
                    ["c:v", self.settings["video_codec"]],
                    ["b:v", self.settings["video_bitrate"]],
                    ["map", "0:{}".format(video_index)],
                ]

                if has_audio:
                    logging.debug("Source has audio")
                    cmd.append(["-map", "0:{}".format(atrack["index"])])
                    cmd.append(["c:a", self.settings.get("audio_codec", "pcm_s16le")])
                    cmd.append(["ar", self.settings.get("audio_sample_rate", 48000)])

                    if self.settings.get("audio_bitrate", False):
                        cmd.append(["b:a", self.settings["audio_bitrate"]])

                    if gain:
                        logging.debug("Adjusting gain by {} dB".format(gain))
                        cmd.append(["filter:a", "volume={}dB".format(gain)])

                cmd.append(["map_metadata", "-1"])
                cmd.append(["video_track_timescale", profile_fps])

                self.set_status("Encoding video (straight from {} to {})".format(source_fps, profile_fps), "info")
                if not ffmpeg(self.input_path, output_path, output_format=cmd):
                    return False

            else:

                ##
                # Reclock
                ##

                if has_audio:
                    sox_tempo = float(profile_fps) / source_fps

                    ##
                    # Extract audio track
                    ##

                    logging.debug ("Extracting audio track")
                    audio_temp_name = self.get_temp("wav")
                    audio_temp_name2 = self.get_temp("wav")

                    cmd = [
                            "vn",
                            ["map", "0:{}".format(atrack["index"])],
                            ["c:a", "pcm_s16le"],
                        ]

                    if not ffmpeg(self.input_path, audio_temp_name, output_format=cmd):
                        return False

                    ##
                    # Audio reclock
                    ##

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

                    # Reclocked audio is ready


                self.set_status("Encoding video (reclock from {} to {})".format(source_fps, profile_fps), "info")

                cmd1 = [
                    ["an", False],
                    ["filter:v", join_filters(*filters)],
                    ["pix_fmt", "yuv422p"],
                    ["f", "rawvideo"],
                    ]

                cmd2_input = [
                    ["f", "rawvideo"],
                    ["pix_fmt", "yuv422p"],
                    ["s", "{}x{}".format(self.settings["width"], self.settings["height"])],
                    ]

                cmd2 = []

                if has_audio:
                    cmd2.append(["i", audio_temp_name2])
                    cmd2.append(["c:a", self.settings.get("audio_codec", "pcm_s16le")])
                    cmd2.append(["ar", self.settings.get("audio_sample_rate", 48000)])

                    if self.settings.get("audio_bitrate", False):
                        cmd2.append(["b:a", self.settings["audio_bitrate"]])

                cmd2.append(["r", profile_fps])
                cmd2.append(["c:v", self.settings["video_codec"]])
                cmd2.append(["b:v", self.settings["video_bitrate"]])
                cmd2.append(["map_metadata", "-1"])
                cmd2.append(["video_track_timescale", profile_fps])

                p1 = FFMPEG(self.input_path, "-", output_format=cmd1)
                p1.start(stdout=subprocess.PIPE)

                p2 = FFMPEG("-", output_path, output_format=cmd2, input_format=cmd2_input)
                p2.start(stdin=p1.stdout)

                p1.stdout.close()

                while p1.is_running or p2.is_running:
                    try:
                        if p1.is_running:
                            p1.process(progress_handler=lambda x: print("PROC1", x))
                        if p2.is_running:
                            p2.process()
                        time.sleep(.001)
                    except KeyboardInterrupt:
                        logging.error("PROC1:\n", p1.error_log, "\n")
                        logging.error("PROC2:\n", p2.error_log, "\n")
                        break

                if p1.return_code:
                    logging.error(p1.error_log)
                    return False

                if p2.return_code:
                    logging.error(p2.error_log)
                    return False

        elif gain:

            ##
            # change audio gain only
            ##

            logging.debug("Adjusting gain by {} dB".format(gain))
            cmd = [
                    ["map", "0:{}".format(video_index)],
                    ["map", "0:{}".format(atrack["index"])],
                    ["c:v", "copy"],
                    ["c:a", self.settings.get("audio_codec", "pcm_s16le")],
                    ["ar", self.settings.get("audio_sample_rate", 48000)],
                    ["filter:a", "volume={}dB".format(gain)]
                ]


            if self.settings.get("audio_bitrate", False):
                cmd.append(["b:a", self.settings["audio_bitrate"]])

            cmd.append(["map_metadata", "-1"])
            cmd.append(["video_track_timescale", profile_fps])

            ff = FFMPEG(self.input_path, output_path, output_format=cmd)
            ff.start()

            if ff.return_code:
                logging.error(ff.error_log)
                return False

        else:

            ##
            # Source match target profile. Move to target
            ##

            logging.info("Moving file".format(gain))
            try:
                os.rename(self.input_path, output_path)
            except:
                log_traceback()
                return False

        ##
        # Finish
        ##

        logging.goodnews("Encoding completed")
        return True







    ##############################################################
    ## Future

    @property
    def base_name(self):
        return self.settings.get("base_name", False) or get_base_name(self.input_path)

    @property
    def friendly_name(self):
        return self.settings.get("friendly_name", False) or base_name

    @property
    def output_path(self)
        return os.path.join(
                self.settings["output_dir"],
                "{}.{}".format(base_name, self.settings["container"])
                )

    @property
    def meta(self):
        """Source file properties"""
        if hasattr(self._meta):
            return self._meta
        self._meta = {
                "loudness" : "",
                "frame_rate" : "",
                "aspect_ratio" : "",
                "width" : "",
                "height" : "",
            }
        return self._meta


    def process_1(self):
        pass

    def process_2(self):
        pass

    def process_3(self):
        #TODO: Future, refactored version of above

        input_format = [
                    ["f", "rawvideo"],
                    ["pix_fmt", self.settings["pixel_format"]],
                    ["s", "{}x{}".format(self.settings["width"], self.settings["height"])],
                ]

        output_format = [
                    ["r", profile_fps],
                    ["c:v", self.settings["video_codec"]],
                    ;["b:v", self.settings["video_bitrate"]],
                ]


        if has_audio:

            #TODO: Audio tracks mapping

            output_format.extend([
                    ["c:a", self.settings.get("audio_codec", "pcm_s16le")],
                    ["ar", self.settings.get("audio_sample_rate", 48000)],
                    ["filter:a", "volume={}dB".format(gain)]
                ])
        else:
            output_format.append("vn")

        output_format.extend([
                    ["map_metadata", -1],
                    ["video_track_timescale", profile_fps]
                ])

        dec = FFMPEG(input_path, "-")
        dec.start(stdout=subprocess.PIPE)

        enc = FFMPEG("-", output_path, output_format, input_format)
        enc.start(stdin=dec.stdout)

        dec.stdout.close()

        while dec.is_running or enc.is_running:
            if dec.is_running:
                dec.process(progress_handler=lambda x: print("PROC1", x))
            if enc.is_running:
                enc.process()
            time.sleep(.001)

        if p1.return_code:
            logging.error(p1.error_log)
            return False

        if p2.return_code:
            logging.error(p2.error_log)
            return False

        return True
