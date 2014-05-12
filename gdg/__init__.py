import os
import cherrypy
import gdg
from gdg.data import *
from mako.template import Template
from mako.lookup import TemplateLookup

# Content is relative to the base directory, not the module directory.
current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

templates = TemplateLookup(directories=['html'])

class ImageModel(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)

def get_relative_path(path):
    if path == None:
        return None
    return path.replace(current_dir, "")

def filesize(num):
    for x in ['bytes','KB','MB','GB']:
        if num < 1024.0 and num > -1024.0:
            return "%3.1f%s" % (num, x)
        num /= 1024.0
    return "%3.1f%s" % (num, 'TB')

def get_model(img):
    p = os.path.abspath(img.path)
    if not os.path.exists(p):
        return None
    
    filename = os.path.basename(p)
    size = filesize(os.path.getsize(p))
    color = "#%02X%02X%02X" % (img.r, img.g, img.b)
    grey = int((img.r * 0.299) + (img.g * 0.587) + (img.b * 0.114))
    
    model = {
        'path': get_relative_path(img.path),
        'file': filename,
        'thumb': get_relative_path(img.thumb),
        'average_color': color,
        'size_x': img.x,
        'size_y': img.y,
        'filesize': size,
        'grey': grey
    }
    
    return ImageModel(**model)

class Gallery(object):
    @cherrypy.expose
    def index(self):
        with GoddamnDatabase(cherrypy.request.app.config['database']['path']):
            images = [get_model(i) for i in Image.select().order_by(Image.path)]
            tmp = templates.get_template("index.html")
            return tmp.render(**{ 'title': "Some Pictures", 'images': images })

def main():
    cherrypy.quickstart(Gallery(), config='gdg.conf')