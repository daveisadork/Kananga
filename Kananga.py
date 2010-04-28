#/usr/bin/env python

import os
import time
import math
import thread
from operator import itemgetter

from Cheetah.Template import Template
import cherrypy
from cherrypy.lib.static import serve_file

import gobject
gobject.threads_init ()
import pygst
pygst.require ("0.10")
import gst


program_dir = os.path.dirname(os.path.abspath(__file__))
video_dir = ['/home/dhayes/Downloads']
ACCEPTED_EXTENSIONS = ['avi', 'mp4', 'm4v', 'mpeg', 'mpg', 'mp2', 'flv', 'mkv', 'wmv', 'mov']

class Kananga:
    def __init__(self):
        self._path = os.path.dirname(os.path.abspath(__file__))
        print "Loading %s..." % video_dir
        self.videos = []
        for path in video_dir:
            thread.start_new_thread(self._load_videos, (path,))

    def _load_videos(self, path):
        for root, dirs, files in os.walk(path):
            for item in files:
                # Get the file extension, e.g. 'mp3' or 'flac', and see if it's in
                # the list of extensions we're supposed to look for.
                extension = os.path.splitext(item)[1].lower()[1:]
                if extension in ACCEPTED_EXTENSIONS:
                    resolution = get_resolution(os.path.join(root, item))
                    if resolution:
                        print item, str(resolution)
                        self.videos.append({
                            'name': item,
                            'path': os.path.join(root, item),
                            'resolution': resolution
                        })
                        self.videos = sorted(self.videos, key=itemgetter('name'))
                    else:
                        print "Couldn't get resolution for %s" % item
        print "done"

    def index(self):
        template = Template(file=os.path.join(self._path, 'templates/index.tmpl'))
        template.videos = self.videos
        return template.respond()
    index.exposed = True


    def player(self, index, width='480', height=None):
        index = int(index)
        template = Template(file=os.path.join(self._path, 'templates/player.tmpl'))
        resolution = self.videos[index]['resolution']
        scale = 480.0 / resolution[0]
        resolution = (480, int(resolution[1] * scale))
        template.index = index
        template.width = resolution[0]
        template.height = resolution[1]
        template.player_h = template.height + 24
        return template.respond()
    player.exposed = True

    def video(self, index, width=None, height=None, ext=None):
        cherrypy.response.headers['Content-Type'] = 'video/x-flv'
        index = int(index)
        if width and not height:
            try:
                width = int(width)
                scale = width / self.videos[index]['resolution'][0]
                height = int(scale * self.videos[index]['resolution'][1])
            except:
                width, height = None
        elif height and not width:
            try:
                height = int(height)
                scale = height / self.videos[index]['resolution'][1]
                width = int(scale * self.videos[index]['resolution'][0])
            except:
                width, height = None
        return transcode(self.videos[index]['path'], width, height)
    video._cp_config = {'response.stream': True}
    video.exposed = True

def transcode(path, width=None, height=None):
    if width and height:
        if int(height) % 2 != 0:
            height = int(height) + 1
        resolution = {'width': width, 'height': height}
        scale = "! ffvideoscale name=scaler ! video/x-raw-yuv, width=%(width)s, height=%(height)s " % resolution
    else:
        scale = ''
    print "Transcoding", path
    tstring = 'filesrc name=source ! decodebin2 name=decoder ! audioconvert ! audioresample ! audio/x-raw-int, channels=2, rate=44100 ! audiorate ! faac name=aenc ! flvmux name=muxer ! queue ! appsink name=output decoder. ! ffmpegcolorspace %s! x264enc name=venc ! muxer.' % scale
    print tstring
    transcoder = gst.parse_launch(tstring)
    source = transcoder.get_by_name('source')
    source.set_property("location", path)
    output = transcoder.get_by_name('output')
    output.set_property("sync", False)
    aenc = transcoder.get_by_name('aenc')
    aenc.set_property("bitrate", 96000)
    venc = transcoder.get_by_name('venc')
    venc.set_property("threads", 0)
    venc.set_property("pass", 17)
    venc.set_property("bitrate", 480)
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


def get_resolution(path):
    resolution = False
    player = gst.parse_launch("filesrc name=source ! decodebin name=decoder ! queue ! fakesink decoder. ! queue ! fakesink")
    player.set_state(gst.STATE_NULL)
    player.get_by_name("source").set_property("location", path)
    try:
        player.set_state(gst.STATE_PAUSED)
        while gst.element_state_get_name(player.get_state()[1]) != "PAUSED":
            time.sleep(0.1)
        for i in player.get_by_name("decoder").src_pads():
            structure_name = i.get_caps()[0].get_name()
            if structure_name.startswith("video") and len(str(i.get_caps()[0]["width"])) < 6:
                resolution = (i.get_caps()[0]["width"], i.get_caps()[0]["height"])
                break
    except:
        pass
    finally:
        player.set_state(gst.STATE_NULL)
        #print gst.element_state_get_name(player.get_state()[1])
        return resolution


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
