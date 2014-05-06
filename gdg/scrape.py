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

    print(dbpath)
    
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
                    
        if len(deleted_files) > 0:
            with db.transaction():
                for f in deleted_files:
                    Image.delete().where(Image.path == f).execute()
    
    with GoddamnDatabase(dbpath) as db:
        for i in Image.select().where(Image.thumb == None):
            img = PIL.Image.open(i.path)
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
            
            counter = 1
            while os.path.isfile(thumb):
                thumb_name = thumb_name + counter
                thumb = get_thumb(thumb_path, thumb_name, name_parts[1])
                
            t.save(thumb)
            
            i.thumb = thumb
            i.save()
