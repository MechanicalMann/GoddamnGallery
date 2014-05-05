import os
import ConfigParser
import PIL
from peewee import *
import gdg
from gdg.data import *

config = ConfigParser()

def get_files(path):
    for root, dirs, files in os.walk(path):
        for filename in files:
            yield os.path.join(root, filename)

def get_thumb(path, base, ext):
    return os.path.join(path, base + ext);

def main():
    config.read(os.path.join(gdg.current_dir, 'gdg.conf'))
    dbpath = config['database']['path']
    
    with GoddamnDatabase(dbpath) as db:
        current = Image.select(Image.path)
        ondisk = get_files(config['images']['path'])
        new = set(ondisk) - set(current)
        deleted = set(current) - set(ondisk)
        
        with db.transaction():
            for f in new:
                i = Image()
                i.path = f
                i.save()
            
        with db.transaction():
            for f in deleted:
                Image.delete().where(Image.path == f).execute()
    
    with GoddamnDatabase(dbpath) as db:
        for i in Image.select().where(Image.thumb == None):
            img = Image.open(PIL.Image.open(i.path))
            x = 0
            w = min(img.size)
            h = w
            
            if (img.size[0] > img.size[1]):
                x = int((i.size[0] - w) / 2)
            
            box = (x, 0, x + w, h)
            
            c = img.crop(box)
            t = c.resize((200, 200), PIL.Image.ANTIALIAS)
            
            path_parts = os.path.split(i.path)
            name_parts = os.path.splitext(path_parts[1])
            
            thumb_name = config['thumbnails']['prefix'] + name_parts[0] + config['thumbnails']['postfix']
            
            thumb = get_thumb(path_parts[0], thumb_name, name_parts[1])
            
            counter = 1
            while os.path.isfile(thumb):
                thumb_name = thumb_name + counter
                thumb = get_thumb(path_parts[0], thumb_name, name_parts[1])
                
            t.save(thumb)
            
            i.thumb = thumb
            i.save()
