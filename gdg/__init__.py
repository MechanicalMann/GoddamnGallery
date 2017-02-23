import os
import random
import re
import httplib
import json
import cherrypy
import gdg
import bcrypt
from urlparse import urljoin, urlparse
from mako.template import Template
from mako.lookup import TemplateLookup
from gdg.data import *

# Content is relative to the base directory, not the module directory.
current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
virtual_dir = ''

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

def get_base_url():
    return urljoin(cherrypy.request.base, virtual_dir + '/')

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

    baseurl = get_base_url()

    tags = [t.name for t in [ti.tag for ti in img.tagimage_set_prefetch]] if hasattr(img, 'tagimage_set_prefetch') else []
    
    model = {
        'path': get_relative_path(baseurl, img.path),
        'file': filename,
        'thumb': get_relative_path(baseurl, img.thumb),
        'average_color': color,
        'size_x': img.x,
        'size_y': img.y,
        'filesize': size,
        'grey': grey,
        'tags': tags
    }
    
    return ImageModel(**model)
    
def get_viewmodel():
    return { 'message': '', 'images': [], 'page': 1, 'total_images': 0, 'total_pages': 1, 'gallery_url': '', 'gallery': '', 'parent_gallery': '', 'children': [] }

def get_images(dbpath, model=None, page=1, page_size=20, gallery="", tag=""):
    if model == None:
        model = get_viewmodel()

    while gallery.startswith('/'): gallery = gallery[1:]
    while gallery.endswith('/'): gallery = gallery[:-1]

    baseurl = get_base_url()
    model['gallery'] = gallery

    if not gallery == "":
        gallery_url = urljoin(baseurl, gallery)
        parent_gallery = os.path.dirname(gallery)
    else:
        gallery_url = baseurl
        parent_gallery = ""
    
    if not gallery_url.endswith('/'):
        gallery_url += '/'

    model['gallery_url'] = gallery_url
    model['parent_gallery'] = parent_gallery
    
    with GoddamnDatabase(dbpath):
        q = Image.select().where(Image.gallery == gallery)
        
        if not tag == "":
            model['tagged'] = tag
            q = q.join(TagImage).join(Tag).where(Tag.name == tag)
        else:
            model['tagged'] = None
        
        count = q.count()
        if count == 0:
            return model

        model['total_images'] = count
        
        q = q.order_by(Image.path)
        
        if not page_size == None:
            model['total_pages'] = int((count - 1) / page_size) + 1
            model['page'] = page
            q = q.paginate(page, page_size)

        tags = TagImage.select(TagImage, Tag).join(Tag)
        image_tags = prefetch(q, tags)
        
        model['images'] = [get_model(i) for i in image_tags]

        model['children'] = [i.gallery for i in Image.select().group_by(Image.gallery).having(Image.parent == gallery)]
        
    return model

def get_image_details(p):
    if p == None or p == "":
        return None
    p = os.path.normpath(p.replace(get_base_url(), current_dir + '/'))
    dbpath = cherrypy.request.app.config['database']['path']
    with GoddamnDatabase(dbpath):
        return get_model(Image.get(Image.path == p))

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
symbols = re.compile("([^\w\s\.]+)")
filename = re.compile("/([^\\/]+)" + ext)

def filename_lev(a, f):
    fn = filename.search(f)
    if fn == None:
        return levenshtein(a, f)
    else:
        return levenshtein(a, fn.group(1))

# Returns a list of key-value pairs {image, distance}
def filter_images_by_lev(name, image_list, max_dist):
    for filename in image_list:
        lev_dist = 0 if max_dist < 0 else filename_lev(name.lower(), filename.lower())
        if max_dist >= 0 and lev_dist > max_dist:
            continue
        yield { 'image': filename, 'distance': lev_dist }

def find_images_by_name(name):
    if name == None or name == "":
        return []
        
    baseurl = get_base_url()
    dbpath = cherrypy.request.app.config['database']['path']
    
    pattern = symbols.sub("[\W_]*?", name)
    pattern = spaces.sub("[\s\-_\.]*?", pattern)
    
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
        if not 'api' in cherrypy.request.app.config:
            return "You haven't configured the goddamn API."

        max_dist = cherrypy.request.app.config['api']['max_lev_distance']
        max_dist = -1 if max_dist is None else max_dist

        # Filter and then sort the images by their levenshtein distance
        filtered_images = sorted(filter_images_by_lev(name, images, max_dist), key=lambda kvp: kvp['distance'])
        images = [kvp['image'] for kvp in filtered_images]
    return images

def find_images_by_tags(tags):
    if tags is None or tags == []:
        return []

    baseurl = get_base_url()
    dbpath = cherrypy.request.app.config['database']['path']

    with GoddamnDatabase(dbpath):
        return [get_relative_path(baseurl, i.path) for i in Image.select().join(TagImage).join(Tag).where(Tag.name << tags)]

def find_image(text):
    if not text:
        return None
    if text.startswith('#'):
        tags = [tag.strip() for tag in text.split('#') if tag and not tag.isspace()]
        images = find_images_by_tags(tags)
        return random.choice(images) if len(images) else None
    else:
        images = find_images_by_name(text)
        return images[0] if len(images) else None

def verify_key(key):
    # TODO not this
    real_key = cherrypy.request.app.config['api'].get('key', None)
    if not real_key:
        return True
    return real_key == key

def set_user_info(model):
    if 'user' in cherrypy.session:
        model['logged_in'] = True
        model['user'] = cherrypy.session['user']
    else:
        model['logged_in'] = False
        model['user'] = None

class BaseController(object):
    def render_page(self, template, model=None):
        tmp = templates.get_template(template)
        baseurl = get_base_url()

        base_model = { 'title': "Goddamn Gallery", 'baseurl': baseurl, 'urljoin': urljoin }

        if 'user' in cherrypy.session:
            base_model['logged_in'] = True
            base_model['user'] = cherrypy.session['user']
        else:
            base_model['logged_in'] = False
            base_model['user'] = None
        
        if model:
            base_model.update(model)
        return tmp.render(**base_model)

class GalleryController(BaseController):
    @cherrypy.expose
    def index(self, gallery="", page="1", **kwargs):
        model = get_viewmodel()
        
        dbpath = cherrypy.request.app.config['database']['path']
        
        if not os.path.isfile(os.path.join(dbpath, 'gallery.db')):
            model['title'] = 'Goddamnit'
            model['message'] = 'Your database is not initialized.  Please run the scraper so you can see your images here.'
        else:
            model['title'] = 'Some Images'
            pagesize = cherrypy.request.app.config['gallery']['images_per_page']
            tag = kwargs['tagged'] if 'tagged' in kwargs else ""
            
            get_images(dbpath, model, page=int(page), page_size=pagesize, gallery=gallery, tag=tag)
        
        return self.render_page("index.html", model)

class AccountController(BaseController):
    def show_login(self, error=False):
        tmp = templates.get_template("login.html")
        model = { "title": "Sign in", "error": error }
        return self.render_page("login.html", model)

    @cherrypy.expose
    def index(self):
        if 'user' not in cherrypy.session:
            self.show_login()
        raise cherrypy.HTTPRedirect("/")
    
    @cherrypy.expose
    def login(self):
        return self.show_login()
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def handle_login(self, username="", password=""):
        dbpath = cherrypy.request.app.config['database']['path']
        try:
            with GoddamnDatabase(dbpath):
                user = User.get(User.email == username)
                p = bcrypt.hashpw(password.encode('utf-8'), user.hash.encode('utf-8')) #bcrypt is very particular about string encodings
                if p == user.hash:
                    cherrypy.session['user'] = { 'name': user.name, 'email': user.email }
                    baseurl = get_base_url()
                    raise cherrypy.HTTPRedirect(baseurl)
        except cherrypy.HTTPRedirect:
            raise
        except:
            pass # Swallow all exceptions
        return self.show_login(True)
    
    def logout(self):
        cherrypy.session.pop('user', None)
        baseurl = get_base_url()
        raise cherrypy.HTTPRedirect(baseurl)

class TagController(object):
    def __init__(self):
        pass

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def list(self, image=""):
        cherrypy.log(cherrypy.request.method)
        dbpath = cherrypy.request.app.config['database']['path']
        if not image:
            with GoddamnDatabase(dbpath):
                return [t.slug for t in Tag.select()]
        image_folder = cherrypy.request.app.config['images']['path']
        full_path = os.path.join(current_dir, image_folder, image)
        with GoddamnDatabase(dbpath):
            return [t.slug for t in Tag.select().join(TagImage).join(Image).where(Image.path == full_path)]
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST', 'PUT', 'PATCH'])
    def add_tag(self, image="", **kwargs):
        if 'user' not in cherrypy.session and not verify_key(kwargs.get('key', '')):
            raise cherrypy.HTTPError(401, "What's the magic word?")
        tag_name = kwargs.get('tag', '')
        if not tag_name:
            raise cherrypy.HTTPError(400, "You need to specify a tag name.")
        if not image:
            raise cherrypy.HTTPError(400, "You need to specify an image to tag.")
        image_folder = cherrypy.request.app.config['images']['path']
        full_path = os.path.join(current_dir, image_folder, image)

        dbpath = cherrypy.request.app.config['database']['path']
        with GoddamnDatabase(dbpath) as db:
            with db.transaction():
                images = list(Image.select().where(Image.path == full_path))
                if len(images) == 0:
                    raise cherrypy.HTTPError(404, "Image \"{}\" does not exist".format(image))
                image = images[0]
                tag, _ = Tag.get_or_create(name=tag_name, slug=tag_name)
                _, created = TagImage.get_or_create(image=image, tag=tag)
                if created:
                    return "Image has been successfully tagged"
                else:
                    return "Image was already tagged"
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['DELETE'])
    def remove_tag(self, image="", tag=""):
        if 'user' not in cherrypy.session and not verify_key(kwargs.get('key', '')):
            raise cherrypy.HTTPError(401, "What's the magic word?")
        if not tag:
            raise cherrypy.HTTPError(400, "You need to specify a tag name.")
        if not image:
            raise cherrypy.HTTPError(400, "You need to specify an image to tag.")
        image_folder = cherrypy.request.app.config['images']['path']
        full_path = os.path.join(current_dir, image_folder, image)

        dbpath = cherrypy.request.app.config['database']['path']
        with GoddamnDatabase(dbpath) as db:
            with db.transaction():
                images = list(Image.select().where(Image.path == full_path))
                if len(images) == 0:
                    raise cherrypy.HTTPError(404, "Image \"{}\" does not exist".format(image))
                i = images[0]
                tags = list(Tag.select().where(Tag.slug == tag))
                if len(tags) == 0:
                    raise cherrypy.HTTPError(404, "Tag \"{}\" does not exist".format(tag))
                t = tags[0]
                n = TagImage.delete().where(TagImage.tag == t, TagImage.image == i).execute()
                if n > 0:
                    return "Image has been successfully untagged"
                else:
                    return "Image was already untagged"

class ImageController(object):
    def __init__(self):
        self.tags = TagController()
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def details(self, image):
        image_folder = cherrypy.request.app.config['images']['path']
        full_path = os.path.join(current_dir, image_folder, image)
        details = get_image_details(full_path).__dict__ # required for JSON serialization for some reason
        details['tags'] = self.tags.list(image)
        return details
    
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def list(self, gallery=""):
        model = get_viewmodel()
        dbpath = cherrypy.request.app.config['database']['path']
        baseurl = get_base_url()
        result = {}
        with GoddamnDatabase(dbpath):
            images = Image.select()
            if not gallery == "" and not gallery == None:
                images = images.where(Image.gallery == gallery)
                result["gallery"] = gallery
                
            images = images.order_by(SQL('path collate nocase'))
            result["images"] = [get_relative_path(baseurl, i.path) for i in images]
        return result

class ApiController(object):
    def __init__(self):
        self.images = ImageController()

    def _cp_dispatch(self, vpath):
        cherrypy.log("Dispatching")
        return self

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def search(self, q="", t=""):
        if t != "":
            t = t.replace('+', ' ')
            cherrypy.log("Executing search for tags \"{}\"".format(t))
            tags = [tag.strip() for tag in t.split(' ') if tag and not tag.isspace()]
            return { "tags" : t, "results" : find_images_by_tags(tags) }
        cherrypy.log("Executing search for \"{}\"".format(q))
        return { "query" : q, "results" : find_images_by_name(q) }

    @cherrypy.expose
    def slack(self, **kwargs):
        if not 'slack' in cherrypy.request.app.config:
            return "You haven't configured your goddamn Slack integration at all."
        
        text = kwargs.get('text', '')
        if text == None or text == '':
            return "You need to enter an image name to search for."
            
        image = find_image(text)
        if image is None:
            return "No images were found that matched \"{}.\"".format(text)
            
        url = cherrypy.request.app.config['slack']['webhook_url']
        if url == None or url == '':
            return "You haven't configured the goddamn web hook."
        
        try:
            cherrypy.log("User {} ({}) in channel {} ({}) requests {}, returned image {}".format(kwargs['user_name'], kwargs['team_domain'], kwargs['channel_name'], kwargs['channel_id'], text, image))

            message = { "channel": kwargs['channel_id'] }
            details = get_image_details(image)
            
            # Send the image as an attachment because it looks more like a real Slack integration
            attachment = { "image_url": image, "fallback": image, "text": "*<@{}>*: `{}`\n{}".format(kwargs['user_name'], text, image), "mrkdwn_in": ["text"], "color": details.average_color }
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
            
            # Slack doesn't like when you return from your slash command
            # before you receive the response from the webhook.  Weird.
            response = con.getresponse()
            response.read()

            return ""
        except:
            cherrypy.log("An error occurred while attempting to send an image to Slack.", traceback=True)
            return "Something has gone horribly wrong."

def configure_routes(script_name=''):
    global application
    cherrypy.config.update('gdg.conf')

    dispatch = cherrypy.dispatch.RoutesDispatcher()
    dispatch.connect("delete_tag", "/api/images/{image:.*?}/tags/{tag}", TagController(), action='remove_tag', conditions={ "method": ["DELETE"] })
    dispatch.connect("add_tag", "/api/images/{image:.*?}/tags/{tag}", TagController(), action='add_tag', conditions={ "method": ["PUT", "PATCH"] })
    dispatch.connect("add_tag_post", "/api/images/{image:.*?}/tags", TagController(), action='add_tag', conditions={ "method": ["POST"] })
    dispatch.connect("image_tags", "/api/images/{image:.*?}/tags", TagController(), action='list')
    dispatch.connect("image", "/api/images/{image:.*?}", ImageController(), action='details')
    dispatch.connect("list_tags", "/api/tags", TagController(), action='list')
    dispatch.connect("api", "/api/images", ImageController(), action='list')
    dispatch.connect("api", "/api/list", ImageController(), action='list')
    dispatch.connect("search", "/api/search", ApiController(), action='search')
    dispatch.connect("slack", "/api/slack", ApiController(), action='slack')
    dispatch.connect("account_login", "/account/login", AccountController(), action='handle_login', conditions={ "method": ["POST"] })
    dispatch.connect("account", "/account/{action}", AccountController(), action='index')
    dispatch.connect("gallery_page", "/{gallery:.*?}/page/:page", GalleryController(), action='index')
    dispatch.connect("main_page", "/page/:page", GalleryController(), action='index')
    dispatch.connect("gallery", "/{gallery:.*?}", GalleryController(), action='index')
    route_config = { '/': { 'request.dispatch': dispatch } }

    application = cherrypy.tree.mount(root=None, script_name=script_name, config='gdg.conf')
    application.merge(route_config)

def main():
    configure_routes()
    cherrypy.log("Using database at {}".format(os.path.join(application.config['database']['path'], "gallery.db")))
    cherrypy.engine.start()
    cherrypy.engine.block()

def wsgi(env, start_response, script_name=''):
    global virtual_dir
    virtual_dir = script_name
    configure_routes(script_name)
    return cherrypy.tree(env, start_response)
