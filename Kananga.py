#!/usr/bin/env python

import os
import time
import math

from Cheetah.Template import Template
import cherrypy
from cherrypy.lib.static import serve_file

import pygst
import gst


program_dir = os.path.dirname(os.path.abspath(__file__))
video_dir = '/home/dhayes/Downloads'
ACCEPTED_EXTENSIONS = ['avi', 'mp4', 'm4v', 'mpeg', 'mpg', 'mp2', 'flv', 'mkv', 'wmv', 'mov']

class Kananga:
    def __init__(self):
        self._path = os.path.dirname(os.path.abspath(__file__))
        print "Loading %s..." % video_dir
        self.videos = []
        for root, dirs, files in os.walk(video_dir):
            for item in files:
                # Get the file extension, e.g. 'mp3' or 'flac', and see if it's in
                # the list of extensions we're supposed to look for.
                extension = os.path.splitext(item)[1].lower()[1:]
                if extension in ACCEPTED_EXTENSIONS:
                    self.videos.append({
                        'name': item,
                        'path': os.path.join(root, item),
                        'resolution': get_resolution(os.path.join(root, item))
                        })
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
        return template.respond()
    player.exposed = True

    def video(self, index, width=None, height=None):
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
        resolution = {'width': width, 'height': height}
        scale = "! videoscale ! video/x-raw-yuv, width=%(width)s, height=%(height)s " % resolution
    else:
        scale = ''
    print "Transcoding", path
    transcoder = gst.parse_launch("filesrc name=source ! decodebin2 name=decoder ! audioconvert ! faac ! flvmux name=muxer ! appsink name=output decoder. ! ffmpegcolorspace %s! x264enc ! muxer." % scale)
    source = transcoder.get_by_name('source')
    source.set_property("location", path)
    output = transcoder.get_by_name('output')
    output.set_property("sync", False)
    transcoder.set_state(gst.STATE_PLAYING)
    try:
        while not output.get_property("eos"):
            yield str(output.emit('pull-buffer'))
    except:
        print "Something broke..."
    transcoder.set_state(gst.STATE_NULL)


def get_resolution(path):
    player = gst.parse_launch("filesrc name=source ! decodebin name=decoder ! fakesink decoder. ! fakesink")
    player.set_state(gst.STATE_NULL)
    player.get_by_name("source").set_property("location", path)
    player.set_state(gst.STATE_PAUSED)
    while gst.element_state_get_name(player.get_state()[1]) != "PAUSED":
        time.sleep(0.01)
    for i in player.get_by_name("decoder").src_pads():
        structure_name = i.get_caps()[0].get_name()
        if structure_name.startswith("video") and len(str(i.get_caps()[0]["width"])) < 6:
            return (i.get_caps()[0]["width"], i.get_caps()[0]["height"])
            player.set_state(gst.STATE_NULL)
            break


#decodebin2 name=decoder ! audioconvert ! faac ! flvmux name=muxer ! filesink location=test.flv decoder. ! ffmpegcolorspace ! x264enc ! muxer.

#decodebin2 name=decoder ! audioconvert ! vorbisenc ! oggmux name=muxer ! appsink name=output decoder. ! theoraenc ! muxer.
pipeline = {
    'mp3': "filesrc name=source ! decodebin ! audioconvert ! lamemp3enc name=encoder ! id3v2mux ! appsink name=output",
    'ogg': "filesrc name=source ! decodebin ! audioconvert ! vorbisenc name=encoder ! oggmux ! appsink name=output"
}

if __name__ == '__main__':

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


