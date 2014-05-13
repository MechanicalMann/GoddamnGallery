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
    if not img.r == None:
        color = "#%02X%02X%02X" % (img.r, img.g, img.b)
        grey = int((img.r * 0.299) + (img.g * 0.587) + (img.b * 0.114))
    else:
        color = "#FFFFFF"
        grey = 255
    
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
    
def get_viewmodel():
    return { 'title': '', 'message': '', 'images': [], 'page': 1, 'total_images': 0, 'total_pages': 1 }

def get_images(dbpath, model=None, page=1):
    if model == None:
        model = get_viewmodel()
    
    with GoddamnDatabase(cherrypy.request.app.config['database']['path']):
        q = Image.select()
        
        count = q.count()
        model['total_images'] = count
        
        q = q.order_by(Image.path)
        
        # TODO make total images per page a config variable
        model['total_pages'] = int((count - 1) / 20) + 1
        model['page'] = page
        q = q.paginate(page, 20)
        
        model['images'] = [get_model(i) for i in q]
        
    return model

class GalleryController(object):
    @cherrypy.expose
    def index(self):
        tmp = templates.get_template("index.html")
        model = get_viewmodel()
        
        dbpath = cherrypy.request.app.config['database']['path']
        
        if not os.path.isfile(os.path.join(dbpath, 'gallery.db')):
            model['title'] = 'Goddamnit'
            model['message'] = 'Your database is not initialized.  Please run the scraper so you can see your images here.'
        else:
            model['title'] = 'Some Images'
            get_images(dbpath, model)
        
        return tmp.render(**model)
    
    @cherrypy.expose
    def page(self, page=1):
        tmp = templates.get_template("index.html")
        dbpath = cherrypy.request.app.config['database']['path']
        
        model = get_images(dbpath, page=int(page))
        model['title'] = 'Some Images'
        
        return tmp.render(**model)

def main():
    cherrypy.quickstart(GalleryController(), config='gdg.conf')