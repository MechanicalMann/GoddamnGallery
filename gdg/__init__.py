import os
import re
import httplib
import json
import cherrypy
import gdg
from urlparse import urljoin, urlparse
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
        
        if not page_size == None:
            model['total_pages'] = int((count - 1) / page_size) + 1
            model['page'] = page
            q = q.paginate(page, page_size)
        
        model['images'] = [get_model(i) for i in q]

        model['children'] = [i.gallery for i in Image.select().group_by(Image.gallery).having(Image.parent == gallery)]
        
    return model

# Levenshtein Distance implementation by Magnus Lie Hetland
# http://hetland.org/coding/python/levenshtein.py
def levenshtein(a, b):
    m, n = len(a), len(b)
    if m > n:
        a, b = b, a
        m, n = n, m
    
    current = range(m + 1)
    for i in range(1, n + 1):
        previous, current = current, [i] + [0] * m
        for j in range(1, m + 1):
            add, delete = previous[j] + 1, current[j - 1] + 1
            change = previous[j - 1]
            if not a[j - 1] == b[i - 1]:
                change = change + 1
            current[j] = min(add, delete, change)
    return current[m]

ext = "\.\w{2,}$"
extension = re.compile(ext)
spaces = re.compile("[\\\]*\s+")
filename = re.compile("/([^\\/]+)" + ext)

def filename_lev(a, f):
    fn = filename.search(f)
    if fn == None:
        return levenshtein(a, f)
    else:
        return levenshtein(a, fn.group(1))

def find_image(name):
    if name == None or name == "":
        return [];
        
    baseurl = urljoin(cherrypy.request.base, cherrypy.request.script_name + '/')
    dbpath = cherrypy.request.app.config['database']['path']
    
    pattern = re.escape(name)
    pattern = spaces.sub("[\s\-_\.]*", pattern)
    
    # If they include an extension in their search, search for their input exactly.
    # If they did not include an extension, search for images with any extension.
    # This is mostly to prevent people from entering "jpg" and getting everything.
    if extension.search(name) == None:
        pattern += ".*" + ext
    else:
        pattern += "$"
    
    with GoddamnDatabase(dbpath):
        images = [get_relative_path(baseurl, i.path) for i in Image.select().where(Image.path.regexp(pattern)).order_by(SQL('path collate nocase'))]
    
    if len(images) > 1:
        images.sort(key=lambda x: filename_lev(name, x))
    
    return images

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

class ApiController(object):
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def search(self, q=""):
        cherrypy.log("Executing search for \"{}\"".format(q))
        return { "query" : q, "results" : find_image(q) }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def list(self, gallery=""):
        model = get_viewmodel()
        dbpath = cherrypy.request.app.config['database']['path']
        baseurl = urljoin(cherrypy.request.base, cherrypy.request.script_name + '/')
        result = {}
        with GoddamnDatabase(dbpath):
            images = Image.select()
            if not gallery == "" and not gallery == None:
                images = images.where(Image.gallery == gallery)
                result["gallery"] = gallery
                
            images = images.order_by(SQL('path collate nocase'))
            result["images"] = [get_relative_path(baseurl, i.path) for i in images]
        return result
    
    @cherrypy.expose
    def slack(self, **kwargs):
        if not 'slack' in cherrypy.request.app.config:
            return "You haven't configured your goddamn Slack integration at all."
        
        text = kwargs.get('text', '')
        if text == None or text == '':
            return "You need to enter an image name to search for."
            
        result = find_image(text)
        if len(result) == 0:
            return "No images were found that matched \"{}.\"".format(text)
            
        url = cherrypy.request.app.config['slack']['webhook_url']
        if url == None or url == '':
            return "You haven't configured the goddamn web hook."
        
        try:
            cherrypy.log("User {} ({}) in channel {} ({}) requests image {}".format(kwargs['user_name'], kwargs['team_domain'], kwargs['channel_name'], kwargs['channel_id'], result[0]))

            message = { "channel": kwargs['channel_id'] }
            
            # Send the image as an attachment because it looks more like a real Slack integration
            attachment = { "text": "<{}>".format(result[0]), "author_name": "<@{}>".format(kwargs['user_name']), "image_url": result[0], "fallback": result[0] }
            message['attachments'] = [attachment]
            
            icon = cherrypy.request.app.config['slack']['icon_url']
            emoji = cherrypy.request.app.config['slack']['icon_emoji']
            username = cherrypy.request.app.config['slack']['username']
            
            if not icon == None and not icon == "":
                message['icon_url'] = icon
            elif not emoji == None and not icon == "":
                message['icon_emoji'] = emoji
            if not username == None and not username == "":
                message['username'] = username
            
            p = urlparse(url)
            con = httplib.HTTPSConnection(p.netloc)
            con.request("POST", p.path, json.dumps(message))
            
            return ""
        except:
            cherrypy.log("An error occurred while attempting to send an image to Slack.", traceback=True)
            return "Something has gone horribly wrong."

def configure_routes(script_name=''):
    cherrypy.config.update('gdg.conf')

    dispatch = cherrypy.dispatch.RoutesDispatcher()
    dispatch.connect("api", "/api/list/{gallery:.*}", ApiController(), action='list')
    dispatch.connect("api", "/api/{action}/{id}", ApiController())
    dispatch.connect("api", "/api/{action}", ApiController())
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
