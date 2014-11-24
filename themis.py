#!/usr/bin/env python

import os
import sys
import time
import uuid
import json
import tempfile
import subprocess


if sys.version_info[:2] >= (3, 0):
    decode_if_py3 = lambda x: x.decode("utf8")
else:
    decode_if_py3 = lambda x: x


class Log():
    def debug(self, *args):
        print ("DEBUG", *args)

    def info(self, *args):
        print ("INFO", *args)

    def warning(self, *args):
        print ("WARNING", *args)

    def error(self, *args):
        print ("ERROR", *args)  


####################################
## FFMPEG Filters

def join_filters(*filters):
    """Joins multiple filters"""
    return "[in]{}[out]".format("[out];[out]".join(i for i in filters if i))

def filter_deinterlace():
    """Yadif deinterlace"""
    return "yadif=0:-1:0"

def filter_arc(w, h, aspect):
    """Aspect ratio convertor. you must specify output size and source aspect ratio (as float)"""
    taspect = float(w)/h
    if abs(taspect - aspect) < 0.01:
        return "scale=%s:%s"%(w,h)
    if taspect > aspect: # pillarbox
        pt = 0
        ph = h
        pw = int (h*aspect)
        pl = int((w - pw)/2.0)
    else: # letterbox
        pl = 0
        pw = w
        ph = int(w * (1/aspect))
        pt = int((h - ph)/2.0)
    return "scale=%s:%s[out];[out]pad=%s:%s:%s:%s:black" % (pw,ph,w,h,pl,pt)

## FFMPEG Filters
##############################
## Processing

class BaseProcessor():
    default_args = []
    
    def __init__(self, *args):
        self.args = []
        for arg in self.default_args:
            self.args.append(str(arg))
        for arg in args:
            self.args.append(str(arg))
        self.proc = None    
        self.err = ""    
        self.buff = ""    
    
    def start(self, **kwargs):
        self.proc = subprocess.Popen(
            self.args, 
            stdin=kwargs.get("stdin", None), 
            stdout=kwargs.get("stdout", subprocess.PIPE),
            stderr=kwargs.get("stderr", subprocess.PIPE)
            )
        if kwargs.get("check_output", True):
            self.check_output(handler=kwargs.get("handler", False))

    @property 
    def error(self):
        return self.err + self.buff + decode_if_py3(self.proc.stderr.read())


class FFMpeg(BaseProcessor):
    default_args = ["ffmpeg", "-y"]

    def check_output(self, handler=False):
        self.buff = ""
        while self.proc.poll() == None:
            ch = decode_if_py3(self.proc.stderr.read(1))
            if ch in ["\n", "\r"]:
                if self.buff.startswith("frame="):
                    at_frame = self.buff.split("fps")[0].split("=")[1].strip()
                    if handler:
                        handler(at_frame)
                self.err += self.buff + "\n"
                self.buff = ""
            else:
                self.buff += ch
        return self.proc.returncode


class Sox(BaseProcessor):
    default_args = ["sox", "-S"]

    def check_output(self, handler=False):
        self.buff = ""
        while self.proc.poll() == None:
            ch = decode_if_py3(self.proc.stderr.read(1))
            if ch in ["\n", "\r"]:
                if self.buff.startswith("In:"):
                    at_frame = self.buff.split("%")[0].split(":")[1].strip()
                    if handler:
                        handler(at_frame)
                self.err += self.buff + "\n"
                self.buff = ""
            else:
                self.buff += ch
        return self.proc.returncode

## Processing
##############################



class Themis():
    def __init__(self, fname, **kwargs):
        self.logging = kwargs.get("logging", Log())

        self.fname = fname
        self.kwargs = kwargs
        
        self.loudness = False
        self.probe_result = {}
        self.tempfiles = []
        self.status = "(no result)"


    def get_temp(self, container=False):
        dr = tempfile.gettempdir()
        fn = uuid.uuid1() 
        filename =  os.path.join(dr, str(fn))
        if container:
            filename += "." + container
        self.tempfiles.append(filename)
        return filename


    def clean_temp(self):
        if self.tempfiles:
            self.logging.debug("Cleaning-up temporary files")
            for f in self.tempfiles:
                if os.path.exists(f):
                    #try:
                        os.remove(f)
                    #except:
                    #    pass

    def __del__(self):
        self.clean_temp()


    def set_status(self, message, level="debug"):
        self.status = message
        {
        False : lambda x: x,
        "debug" : self.logging.debug,
        "info" : self.logging.info,
        "warning" : self.logging.warning,
        "error" : self.logging.error
        }[level](message)


    def probe(self):
        cmd = [
            "ffprobe",
            "-show_format",
            "-show_streams",
            "-print_format", "json",
            self.fname
            ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while proc.poll() == None:
            time.sleep(.1)

        if proc.returncode:
            logging.error("Unable to ffprobe")
            return False

        self.probe_result = json.loads(decode_if_py3(proc.stdout.read()))
#        from pprint import pprint
#        pprint(self.probe_result)
#        sys.exit(0)
#        return self.probe_result


    def r128(self):
        cmd = [
            "ffmpeg",
            "-i", self.fname,
            "-filter_complex", "ebur128",
            "-vn",
            "-f", "null",
            os.devnull
            ]

        self.loudness = False

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while proc.poll() == None:
            line = decode_if_py3(proc.stderr.readline())
            if line.strip().startswith("I:"):
                self.loudness = float(line.split("I:")[-1].strip().rstrip(" LUFS"))

        if proc.returncode:
            return False

        if self.loudness == -70.0:
            self.loudness = False

        return self.loudness


    def analyze(self):
        self.logging.debug("FFProbing")
        self.probe()
        self.logging.debug("Loudness metering")
        self.r128()
        self.logging.debug("Source loudness:", self.loudness, "LUFS")


    def process(self, output, profile):
        if not self.probe_result:
            self.set_status("Unable to open source file metadata", "error")
            return False

        ###################################################################
        ## Extract streams information

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
                source_width = stream["width"]
                source_height = stream["height"]
                video_index = stream["index"]


            elif stream["codec_type"] == "audio":
                atracks[int(stream["index"])] = stream 

        track_indices = atracks.keys()
        atrack = {}
        try:
            atrack = atracks[min(track_indices)]
            has_audio = True
        except IndexError:
            has_audio = False

        duration = source_vdur or float(format_info["duration"])

        ## Extract streams information
        ###################################################################
        ## Check, which streams must be re-encoded

        compare_v = [
            ["container", os.path.splitext(self.fname)[1][1:]],
            ["fps", source_fps],
            ["video_codec",  source_vcodec],
            ["width",  source_width],
            ["height", source_height]
            ]


        for key, val in compare_v:
            if profile[key] != val:
                self.logging.debug("Source", key, "does not match target format. IS:", val, "SHOULD BE:", profile[key])
                encode_video = True
                break
        else:
            encode_video = False


        ## Check, which streams must be re-encoded
        ###################################################################
       
        profile_fps = profile.get("fps", 25)

        if self.loudness:
            gain = self.kwargs.get("target_loudness", -23) - self.loudness
            if abs(gain) < 0.5:
                gain = 0
        else:
            gain = 0



        
        if encode_video:

            filters = []
            if profile.get("deinterlace", False):
                filters.append(filter_deinterlace())

            filters.append(filter_arc(profile["width"], profile["height"], source_dar) )

            if source_fps >= profile_fps or profile_fps - source_fps > 4:
                self.logging.debug("Source FPS:", source_fps)
                self.logging.debug("Target FPS:", profile_fps)

                cmd = [
                    "-i", self.fname,
                    "-r", profile_fps,
                    "-filter:v", join_filters(*filters),
                    "-pix_fmt", profile.get("pixel_format", "yuv422p"),
                    "-c:v", profile["video_codec"],
                    "-b:v", profile["video_bitrate"],
                    "-map", "0:{}".format(video_index),
                ]

                if has_audio:
                    self.logging.debug("Source has audio")
                    cmd.append("-map")
                    cmd.append("0:{}".format(atrack["index"]))

                    cmd.append("-c:a")
                    cmd.append(profile.get("audio_codec", "pcm_s16le"))

                    cmd.append("-ar")
                    cmd.append(profile.get("audio_sample_rate", 48000))

                    if profile.get("audio_bitrate", False):
                        cmd.append("-b:a")
                        cmd.append(profile["audio_bitrate"])

                    if gain:
                        self.logging.debug("Adjusting gain by", gain, "dB")
                        cmd.append("-filter:a")
                        cmd.append("volume={}dB".format(gain))

                cmd.append(output)

                self.set_status("Encoding video (straight from {} to {})".format(source_fps, profile_fps), "info")
                ffmpeg = FFMpeg(*cmd)
                result = ffmpeg.start(handler=lambda x: sys.stdout.write("\r{} of {}".format(x, int(duration*source_fps))))

                if result:
                    logging.error("Encoding failed:", ffmpeg.error)
                    return False

            else:

                if has_audio:
                    sox_tempo = float(profile_fps) / source_fps

                    self.logging.debug ("Extracting audio track")

                    audio_temp_name = self.get_temp("wav")
                    audio_temp_name2 = self.get_temp("wav")

                    cmd = [
                            "-i", self.fname,
                            "-vn",
                            "-map", "0:{}".format(atrack["index"]),
                            "-c:a", "pcm_s16le",
                            audio_temp_name
                        ]

                    ffmpeg = FFMpeg(*cmd)
                    result = ffmpeg.start()
                    if result:
                        logging.error("Audio extraction failed:", ffmpeg.error)
                        return False


                    cmd = [
                            audio_temp_name,
                            "-r", profile.get("audio_sample_rate", 48000),
                            audio_temp_name2
                        ]

                    if sox_tempo:
                        self.logging.debug("SOX Tempo:", sox_tempo)
                        cmd.append("tempo")
                        cmd.append(sox_tempo)

                    if gain:
                        self.logging.debug("SOX Gain:", gain)
                        cmd.append("gain")
                        cmd.append(gain)

                    self.logging.debug("Processing audio")
                    sox = Sox(*cmd)
                    result = sox.start()

                    if result:
                        logging.error("SOX Failed:", sox.error)
                        return False


                self.set_status("Encoding video (reclock from {} to {})".format(source_fps, profile_fps), "info")

                cmd1 = [
                    "-i", self.fname,
                    "-an",
                    "-filter:v", join_filters(*filters),
                    "-pix_fmt", "yuv422p",
                    "-f", "rawvideo",
                    "-"
                    ]

                cmd2 = [
                    "-f", "rawvideo",
                    "-pix_fmt", "yuv422p",
                    "-s", "{}x{}".format(profile["width"], profile["height"]),
                    "-i", "-",
                    ]

                if has_audio:
                    cmd2.append("-i")
                    cmd2.append(audio_temp_name2)
                    
                    cmd2.append("-c:a")
                    cmd2.append(profile.get("audio_codec", "pcm_s16le"))

                    cmd2.append("-ar")
                    cmd2.append(profile.get("audio_sample_rate", 48000))

                    if profile.get("audio_bitrate", False):
                        cmd2.append("-b:a")
                        cmd2.append(profile["audio_bitrate"])


                cmd2.append("-r")
                cmd2.append(profile_fps)
                    
                cmd2.append("-c:v")
                cmd2.append(profile["video_codec"])
                cmd2.append("-b:v")
                cmd2.append(profile["video_bitrate"])

                cmd2.append(output)



                handler=lambda x: sys.stdout.write("\r{} of {}".format(x, int(duration*profile_fps)))

                p1 = FFMpeg(*cmd1)
                p1.start(check_output=False)

                p2 = FFMpeg(*cmd2)
                p2.start(check_output=False, stdin=p1.proc.stdout)

                p1.proc.stdout.close()


                p2.check_output(handler=handler)


            


        # Just change audio gain
        elif gain:
            self.logging.debug("Adjusting gain by", gain, "dB")
            cmd = [
                    "-i", self.fname,

                    "-map", "0:{}".format(video_index),
                    "-map", "0:{}".format(atrack["index"]),

                    "-c:v", "copy",
                    "-c:a", profile.get("audio_codec", "pcm_s16le"),
                    "-ar", profile.get("audio_sample_rate", 48000),
                    "-filter:a", "volume={}dB".format(gain)
                ]


            if profile.get("audio_bitrate", False):
                cmd.append("-b:a")
                cmd.append(profile["audio_bitrate"])

            cmd.append(output)

            ffmpeg = FFMpeg(*cmd)
            ffmpeg.start()
 

            


        else:
            pass
            #just move


        self.set_status("Import completed")










if __name__ == "__main__":
    profile = json.load(open("profiles/dnxhd36_25.json"))
    IN = "c:\\TEMP\\input"
    OUT = "c:\\TEMP\\output"

    for fname in os.listdir(IN):
        fpath = os.path.join(IN, fname)
        opath = os.path.join(OUT, os.path.splitext(fname)[0]+".mov")

        if not os.path.exists(opath):
            themis = Themis(fpath)
            themis.analyze()
            themis.process(opath, profile)
