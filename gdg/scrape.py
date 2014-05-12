import os
import ConfigParser
import PIL
from PIL import Image
from peewee import *
import gdg
from gdg.data import *

config = ConfigParser.ConfigParser()

def get_files(path):
    images = []
    for root, dirs, files in os.walk(path):
        for filename in files:
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
        ondisk = get_files(get_directory(config.get('images', 'path')))
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
    
    with GoddamnDatabase(dbpath) as db:
        for i in Image.select().where(Image.thumb == None):
            try:
                print("Processing image " + i.path)
                img = PIL.Image.open(i.path)
                i.x = img.size[0]
                i.y = img.size[1]
                
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
                
                thumb = get_thumb(thumb_path, thumb_name, name_parts[1])
                
                counter = 0
                while os.path.isfile(thumb):
                    counter += 1
                    new_thumb_name = thumb_name + str(counter)
                    thumb = get_thumb(thumb_path, new_thumb_name, name_parts[1])
                    
                t.save(thumb)
                
                i.thumb = thumb
                
                hist = img.histogram()
                r = hist[0:256]
                g = hist[256:512]
                b = hist[512:768]
                
                i.r = sum(i*w for i, w in enumerate(r)) / sum(r)
                i.g = sum(i*w for i, w in enumerate(g)) / sum(g)
                i.b = sum(i*w for i, w in enumerate(b)) / sum(b)
                
                i.save()
            except Exception as ex:
                print("Unable to process image " + i.path + ": " + str(ex))
