import os
import mimetypes
import ConfigParser
import PIL
from PIL import Image
from peewee import *
import gdg
from gdg.data import *

config = ConfigParser.ConfigParser()

def is_image(file):
    return (mimetypes.guess_type(file)[0] and mimetypes.guess_type(file)[0].startswith('image'))

def get_image_files(path, follow_links=True):
    images = []
    for root, dirs, files in os.walk(path, followlinks=follow_links):
        for filename in files:
            if (is_image(filename)):
                images.append(os.path.join(root, filename))
    return images

def get_thumb(path, base, ext):
    return os.path.join(path, base + ext)

def get_directory(path):
    path = path.translate(None, '"\'')
    if (path == None or path == 'gdg.current_dir'):
        return gdg.current_dir
    if (os.path.isdir(path)):
        return os.path.abspath(path)
    return os.path.join(gdg.current_dir, path)

def scrape_images():
    config.read(os.path.join(gdg.current_dir, 'gdg.conf'))
    dbpath = get_directory(config.get('database', 'path'))
    dbfile = os.path.join(dbpath, 'gallery.db')
    
    print("Using database " + dbfile)
    
    if not os.path.isfile(dbfile):
        try:
            print("No database exists, initializing.")
            initscript = os.path.join(gdg.current_dir, 'gallery.sql')
            import io, sqlite3
            conn = sqlite3.connect(dbfile)
            with open(initscript, 'r') as sql:
                script = sql.read()
                conn.executescript(script)
            conn.close()
        except Exception as ex:
            print("Unable to initialize database at {}: {}.  Aborting.".format(dbfile, str(ex)))
            exit()

    with GoddamnDatabase(dbpath) as db:
        current = [i.path for i in Image.select()]
        imgpath = get_directory(config.get('images', 'path'))
        print("Searching {} for new images...".format(imgpath))
        ondisk = get_image_files(imgpath, config.get('images', 'follow_links'))
        new_files = set(ondisk) - set(current)
        deleted_files = set(current) - set(ondisk)
        
        if len(new_files) > 0:
            with db.transaction():
                for f in new_files:
                    i = Image()
                    i.path = f
                    i.save()
                    print("Found new image: " + f)
                    
        if len(deleted_files) > 0:
            with db.transaction():
                for f in deleted_files:
                    img = Image.get(Image.path == f)
                    try:
                        if os.path.isfile(img.thumb):
                            os.remove(img.thumb)
                    except Exception as ex:
                        print("Unable to delete thumbnail for deleted image: {}.  You will need to remove this manually.".format(img.thumb))
                    img.delete_instance()
                    print("Removed record of deleted image " + f)

    # 2nd pass - derives metadata, etc 
    # currently: if there's a thumbnail, assume all processing is complete.
    with GoddamnDatabase(dbpath) as db:
        for i in Image.select().where(Image.thumb == None):
            extract_image_metadata(i)
            make_thumbnail(i)
            derive_average_color(i)

def extract_image_metadata(i):
# function determines image dimensions
    try:
        print("Grabbing metadata for image " + i.path)
        img = PIL.Image.open(i.path)
        i.x = img.size[0]
        i.y = img.size[1]
        i.save()

    except Exception as ex:
        print("Unable to obtain metadata for image " + i.path + ": " + str(ex))


def make_thumbnail(i):
# function generates 200px square thumbnail

    try:
        print("Thumbnailing image " + i.path)
        img = PIL.Image.open(i.path)
       
        # If the image isn't RGB, convert it to RGB.
        if (img.mode != "RGB"):
            try:
                img = img.convert("RGB")
            except Exception as ex:
                print("RGB conversion error for image " + i.path + ": " + str(ex))

        x = 0
        w = min(img.size)
        h = w
        
        if (img.size[0] > img.size[1]):
            x = int((img.size[0] - w) / 2)
        
        box = (x, 0, x + w, h)
        
        c = img.crop(box)
        t = c.resize((200, 200), PIL.Image.ANTIALIAS)
        
        path_parts = os.path.split(i.path)
        name_parts = os.path.splitext(path_parts[1])
        thumb_path = get_directory(config.get('thumbnails', 'path'))
        
        thumb_name = config.get('thumbnails', 'prefix').translate(None, '"\'') + name_parts[0] + config.get('thumbnails', 'postfix').translate(None, '"\'')
        
        thumb = get_thumb(thumb_path, thumb_name, ".jpg")
        
        counter = 0
        while os.path.isfile(thumb):
            counter += 1
            new_thumb_name = thumb_name + str(counter)
            thumb = get_thumb(thumb_path, new_thumb_name, ".jpg") 
            
        t.save(thumb, "JPEG")
        
        i.thumb = thumb

        i.save()

    except Exception as ex:
        print("Unable to generate thumb for image " + i.path + ": " + str(ex))


def derive_average_color(i):
# function determines average color from histogram

# TOFIX: Do not convert non-RGB images to RGB. This should save calc time.

    try:
        print("Getting average color of image " + i.path)
        img = PIL.Image.open(i.path)

        # If the image isn't RGB, convert it to RGB.
        if (img.mode != "RGB"):
            try:
                img = img.convert("RGB")
            except Exception as ex:
                print("RGB conversion error for image " + i.path + ": " + str(ex))
        
        hist = img.histogram()
        r = hist[0:256]
        g = hist[256:512]
        b = hist[512:768]
        
        i.r = sum(i*w for i, w in enumerate(r)) / sum(r)
        i.g = sum(i*w for i, w in enumerate(g)) / sum(g)
        i.b = sum(i*w for i, w in enumerate(b)) / sum(b)
        
        i.save()
    except Exception as ex:
        print("Unable to find average color for image " + i.path + ": " + str(ex))

def derive_frequent_colors(image):
    #lol
    print("Functionality not implemented.")
