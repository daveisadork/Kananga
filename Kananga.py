#/usr/bin/env python

import os
import time
import math
import thread
from operator import itemgetter
import re
from fractions import Fraction

from Cheetah.Template import Template
import cherrypy
from cherrypy.lib.static import serve_file

import gobject
gobject.threads_init ()
import pygst
pygst.require ("0.10")
import gst


program_dir = os.path.dirname(os.path.abspath(__file__))
video_dirs = [
    '/home/dave/Downloads',
    '/media/Movies/Videos/Movies',
    '/media/WinXP/Downloads',
    '/media/Music',
    '/media/MMA/MMA'
    ]
ignore = [
    'ufc.uu.1995.xvid.cd1-koenig.avi',
    'aaf-d5lgpf.cd1.avi',
    'aaf-d5lgpf.cd2.avi',
    'aaf-d5lgpf.cd3.avi',
    'aaf-dream.10.hdtv.xvid.cd3.avi',
    'aaf-dream.10.hdtv.xvid.cd1.avi',
    'aaf-dream.10.hdtv.xvid.cd2.avi',
    'The Ultimate Fighter - 4x13 - The Ultimate Fighter 4 Finale.avi',
    'Star.Wars.Episode.VI.Return.Of.The.Jedi.1983.720p.HDTV.x264.INTERNAL-hV.mkv'
    ]
ACCEPTED_EXTENSIONS = ['avi', 'mp4', 'm4v', 'mpeg', 'mpg', 'flv', 'mkv', 'wmv', 'mov']

class Kananga:
    def __init__(self):
        self._path = os.path.dirname(os.path.abspath(__file__))
        self.videos = []
        for path in video_dirs:
            print "Loading {0}...".format(path)
#            self._load_videos(path)
            thread.start_new_thread(self._load_videos, (path,))

    def _load_videos(self, path):
        for root, dirs, files in os.walk(path):
            for item in files:
                item_path = os.path.abspath(os.path.join(root, item))
                if not re.match("^.* - ([0-9]+)x([0-9]+) - .*$", item):
                    item_name = os.path.basename(os.path.dirname(item_path))
                else:
                    item_name = os.path.splitext(item)[0]
                # Get the file extension, e.g. 'mp3' or 'flac', and see if it's in
                # the list of extensions we're supposed to look for.
                extension = os.path.splitext(item)[1].lower()[1:]
                if extension in ACCEPTED_EXTENSIONS and item not in ignore:
                    print "\n{0}".format(item_name[0:78])
                    props = get_props(item_path)
                    if props:
                        width = props['resolution'][0]
                        if width < 720:
                            quality = "SD"
                        elif width < 1280:
                            quality = "480p"
                        elif width < 1920:
                            quality = "720p"
                        else:
                            quality = "1080i"
                        aspect_ratio = props['aspect-ratio']
                        if aspect_ratio <= 1.495:
                            aspect_ratio = "4:3"
                        elif aspect_ratio > 1.5 and aspect_ratio <= 1.72:
                            aspect_ratio = "1.66"
                        elif aspect_ratio > 1.72 and aspect_ratio <= 1.815:
                            aspect_ratio = "16:9"
                        elif aspect_ratio > 1.815 and aspect_ratio <= 2.12:
                            aspect_ratio = "1.85"
                        elif aspect_ratio > 2.12 and aspect_ratio <= 2.57:
                            aspect_ratio = "2.39"
                        elif aspect_ratio > 2.57 and aspect_ratio <= 3:
                            aspect_ratio = "2.75"
                        else:
                            aspect_ratio = "4.00"
                        print "--Resolution:\t{0[0]!s}x{0[1]!s}".format(props['resolution'])
                        print "--Aspect Ratio:\t{0}".format(aspect_ratio)
                        print "--Frame Rate:\t{0} FPS".format(props['framerate'])
                        self.videos.append({
                            'name': item_name,
                            'path': item_path,
                            'extension': extension,
                            'quality': quality,
                            'aspect': aspect_ratio,
                            'resolution': props['resolution'],
                            'framerate': props['framerate']
                        })
                        self.videos = sorted(self.videos, key=itemgetter('name'))
                    else:
                        print "Failed\n"
        print "done"

    def index(self):
        template = Template(file=os.path.join(self._path, 'templates/index.tmpl'))
        template.videos = self.videos
        return template.respond()
    index.exposed = True


    def player(self, index, quality='low'):
        index = int(index)
        if quality == 'low':
            width = 320
        elif quality == 'hi':
            width = 720
        elif quality == 'hd':
            width = 1280
        else:
            width = 480
        resolution = self.videos[index]['resolution']
        scale = float(width) / resolution[0]
        resolution = (width, int(resolution[1] * scale))
        template = Template(file=os.path.join(self._path, 'templates/player.tmpl'))
        template.index = index
        template.meta = self.videos[index]
        template.quality = quality
        template.width = resolution[0]
        template.height = resolution[1]
        template.player_h = template.height + 24
        return template.respond()
    player.exposed = True

    def video(self, index, width=None, height=None, quality=None):
        cherrypy.response.headers['Content-Type'] = 'video/x-flv'
        index = int(index)
        if quality == "low":
            width = 320
            vbitrate = 480
            abitrate = 64000
            arate = 22050
            achan = 1
        elif quality == "hi":
            width = 720
            vbitrate = 1536
            abitrate = 192000
            arate = 44100
            achan = 2
        elif quality == "hd":
            width = 1280
            vbitrate = 2560
            abitrate = 256000
            arate = 48000
            achan = 2
        else:
            width = 480
            vbitrate = 1152
            abitrate = 128000
            arate = 44100
            achan = 1
        if width and not height:
            try:
                width = int(width)
                scale = width / self.videos[index]['resolution'][0]
                height = int(scale * self.videos[index]['resolution'][1])
            except:
                width = height = None
        elif height and not width:
            try:
                height = int(height)
                scale = height / self.videos[index]['resolution'][1]
                width = int(scale * self.videos[index]['resolution'][0])
            except:
                width = height = None
        if width >= self.videos[index]['resolution'][0] or height >= self.videos[index]['resolution'][1]:
            width = height = None
        return transcode(self.videos[index]['path'], width, height, vbitrate, abitrate, arate, achan)
    video._cp_config = {'response.stream': True}
    video.exposed = True

def transcode(path, width=None, height=None, vbitrate=480, abitrate=64000, arate=22050, achan=1):
    vbitrate = int(vbitrate)
    abitrate = int(abitrate)
    arate = int(arate)
    achan = int(achan)
    if width and height:
        if int(height) % 2 != 0:
            height = int(height) + 1
        resolution = {'width': width, 'height': height}
        scale = "! ffvideoscale name=scaler ! video/x-raw-yuv, width={0['width']}, height={0['height']} ".format(resolution)
    else:
        scale = ''
    print "Transcoding", path
    tstring = 'filesrc name=source ! decodebin2 name=decoder ! audioconvert ! audioresample ! audio/x-raw-int, channels={1}, rate={2} ! audiorate ! faac name=aenc ! flvmux name=muxer ! queue ! appsink name=output decoder. ! ffmpegcolorspace {0}! x264enc name=venc ! muxer.'.format(scale, achan, arate)
    print tstring
    transcoder = gst.parse_launch(tstring)
    source = transcoder.get_by_name('source')
    source.set_property("location", path)
    output = transcoder.get_by_name('output')
    output.set_property("sync", False)
    aenc = transcoder.get_by_name('aenc')
    aenc.set_property("bitrate", abitrate)
    venc = transcoder.get_by_name('venc')
    venc.set_property("threads", 0)
    venc.set_property("pass", 17)
    venc.set_property("bitrate", vbitrate)
    try:
        scaler = transcoder.get_by_name('scaler')
        scaler.set_property("method", 9)
    except:
        pass
    gobject.idle_add(transcoder.elements)
#    transcoder.set_state(gst.STATE_PAUSED)
#    print gst.element_state_get_name(transcoder.get_state()[1])
#    gobject.MainLoop().get_context().iteration(True)
    print transcoder.set_state(gst.STATE_PLAYING)
    
    if transcoder.get_state()[1] == gst.STATE_PLAYING:
        try:
            while not output.get_property("eos"):
                yield str(output.emit("pull-buffer"))
        except:
            print "Something broke..."
        finally:
            transcoder.set_state(gst.STATE_NULL)
    else:
        transcoder.set_state(gst.STATE_NULL)
        print "couldn't set state"


def get_props(path):
    props = {}
    player = gst.parse_launch("filesrc name=source ! decodebin name=decoder ! queue ! fakesink decoder. ! queue ! fakesink")
    player.get_by_name("source").set_property("location", path)
    try:
        player.set_state(gst.STATE_PAUSED)
        while gst.element_state_get_name(player.get_state()[1]) != "PAUSED":
            time.sleep(0.01)
        for i in player.get_by_name("decoder").src_pads():
            structure_name = i.get_caps()[0].get_name()
            if structure_name.startswith("video") and len(str(i.get_caps()[0]["width"])) < 6:
                props['framerate'] = "{0:.2f}".format(i.get_caps()[0]["framerate"].__float__())
                props['pixel-aspect-ratio'] = i.get_caps()[0]["pixel-aspect-ratio"].__float__()
                props['resolution'] = (i.get_caps()[0]["width"], i.get_caps()[0]["height"])
                props['aspect-ratio'] = float(i.get_caps()[0]["width"]) / i.get_caps()[0]["height"] * i.get_caps()[0]["pixel-aspect-ratio"].__float__()
                break
    except:
        props = None
    finally:
        player.set_state(gst.STATE_NULL)
        return props


def start():
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8082,
        'tools.encode.on':True,
        'tools.encode.encoding':'utf-8'
        })

    conf = {
        '/assets': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.join(program_dir, 'assets')}
        }
    if not os.path.isdir(os.path.join(program_dir, 'cache')):
        os.mkdir(os.path.join(program_dir, 'cache'))
    cherrypy.quickstart(Kananga(), '', config=conf)


if __name__ == '__main__':
    start()
