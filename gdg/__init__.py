import os
import re
import cherrypy
import gdg
from urlparse import urljoin
from mako.template import Template
from mako.lookup import TemplateLookup
from gdg.data import *

# Content is relative to the base directory, not the module directory.
current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

templates = TemplateLookup(directories=['html'], strict_undefined=True)

application = None

class ImageModel(object):
    def __init__(self, **entries):
        self.__dict__.update(entries)

def get_relative_path(base, path):
    if path == None:
        return None
    if not path == "":
        path = os.path.relpath(path, current_dir)
    return urljoin(base, path.replace('\\', '/'))

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

    baseurl = urljoin(cherrypy.request.base, cherrypy.request.script_name + '/')
    
    model = {
        'path': get_relative_path(baseurl, img.path),
        'file': filename,
        'thumb': get_relative_path(baseurl, img.thumb),
        'average_color': color,
        'size_x': img.x,
        'size_y': img.y,
        'filesize': size,
        'grey': grey
    }
    
    return ImageModel(**model)
    
def get_viewmodel():
    return { 'title': '', 'message': '', 'images': [], 'page': 1, 'total_images': 0, 'total_pages': 1, 'baseurl': '', 'gallery_url': '', 'gallery': '', 'parent_gallery': '', 'children': [] }

def get_images(dbpath, model=None, page=1, page_size=20, gallery=""):
    if model == None:
        model = get_viewmodel()

    while gallery.startswith('/'): gallery = gallery[1:]
    while gallery.endswith('/'): gallery = gallery[:-1]

    baseurl = urljoin(cherrypy.request.base, cherrypy.request.script_name + '/')
    model['gallery'] = gallery

    if not gallery == "":
        gallery_url = urljoin(baseurl, gallery)
        parent_gallery = os.path.dirname(gallery)
    else:
        gallery_url = baseurl
        parent_gallery = ""
    
    if not gallery_url.endswith('/'):
        gallery_url += '/'

    model['baseurl'] = baseurl
    model['gallery_url'] = gallery_url
    model['parent_gallery'] = parent_gallery
    
    with GoddamnDatabase(dbpath):
        q = Image.select().where(Image.gallery == gallery)
        
        count = q.count()
        if count == 0:
            return model

        model['total_images'] = count
        
        q = q.order_by(Image.path)
        
        model['total_pages'] = int((count - 1) / page_size) + 1
        model['page'] = page
        q = q.paginate(page, page_size)
        
        model['images'] = [get_model(i) for i in q]

        model['children'] = [i.gallery for i in Image.select().group_by(Image.gallery).having(Image.parent == gallery)]
        
    return model
    
def find_image(name):
    if name == None or name == "":
        return [];
        
    baseurl = urljoin(cherrypy.request.base, cherrypy.request.script_name + '/')
    dbpath = cherrypy.request.app.config['database']['path']
    pattern = "[\\\/]" + re.escape(name) + "\..{2,}$"
    
    with GoddamnDatabase(dbpath):
        return [get_relative_path(baseurl, i.path) for i in Image.select().where(Image.path.regexp(pattern))]

class GalleryController(object):
    @cherrypy.expose
    def index(self, gallery="", page="1"):
        tmp = templates.get_template("index.html")
        model = get_viewmodel()
        
        dbpath = cherrypy.request.app.config['database']['path']
        
        if not os.path.isfile(os.path.join(dbpath, 'gallery.db')):
            model['title'] = 'Goddamnit'
            model['message'] = 'Your database is not initialized.  Please run the scraper so you can see your images here.'
        else:
            model['title'] = 'Some Images'
            pagesize = cherrypy.request.app.config['gallery']['images_per_page']
            
            get_images(dbpath, model, page=int(page), page_size=pagesize, gallery=gallery)
        
        model['urljoin'] = urljoin
        return tmp.render(**model)
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def search(self, image=""):
        return find_image(image)

def configure_routes(script_name=''):
    cherrypy.config.update('gdg.conf')

    dispatch = cherrypy.dispatch.RoutesDispatcher()
    dispatch.connect("search", "/search/{image:.*?}", GalleryController(), action="search")
    dispatch.connect("primary", "{gallery:.*?}/page/:page", GalleryController(), action='index')
    dispatch.connect("primary", "{gallery:.*?}", GalleryController(), action='index')
    route_config = { '/': { 'request.dispatch': dispatch } }

    application = cherrypy.tree.mount(root=None, script_name=script_name, config='gdg.conf')
    application.merge(route_config)

def main():
    configure_routes()
    cherrypy.engine.start()
    cherrypy.engine.block()

def wsgi(env, start_response, script_name=''):
    configure_routes(script_name)
    return cherrypy.tree(env, start_response)
