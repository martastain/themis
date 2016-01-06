themis
======

ffmpeg based file ingest server

Prerequisites
-------------

Themis requires ffmpeg and sox to be installed.
Use [inst.ffmpeg.sh](https://github.com/immstudios/installers/blob/master/install.ffmpeg.sh)
to install latest tested version on Debian/Ubuntu machine.

transcode.py
------------

Example script.

### Configuration

transcode.json
```json
{
    "input_dir" : "input",
    "output_dir" : "output",
    "done_dir" : "done",
    "recursive" : true
}
```
