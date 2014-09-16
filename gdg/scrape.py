import os
import mimetypes
import ConfigParser
import PIL
from multiprocessing import Pool
from PIL import Image, ImageOps
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

                    g = os.path.dirname(os.path.relpath(f, imgpath)).replace('\\', '/')
                    
                    i.path = f
                    i.gallery = g

                    if g == '':
                        i.parent = None
                    else:
                        i.parent = os.path.dirname(g)

                    i.save()
                print("Added {} new images.".format(len(new_files)))
                    
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
                print("Removed records for {} deleted images.".format(len(deleted_files)))

    # 2nd pass - derives metadata, etc 
    # currently: if there's a thumbnail, assume all processing is complete.
    with GoddamnDatabase(dbpath) as db:
        q = Image.select().where(Image.thumb == None).naive()
        total = q.count()
        if total == 0:
            return

        thumb_path = get_directory(config.get('thumbnails', 'path'))
        thumb_prefix = config.get('thumbnails', 'prefix').translate(None, '"\'')
        thumb_postfix = config.get('thumbnails', 'postfix').translate(None, '"\'')
        thumb_aspect_ratio = config.get('thumbnails', 'aspect_ratio').translate(None, '"\'')

        pool = Pool()
        to_save = []
        try:
            result = pool.map_async(scrape_image_data, [(i, thumb_path, thumb_prefix, thumb_postfix, thumb_aspect_ratio) for i in q.iterator()], 25)
            to_save = result.get()
        except KeyboardInterrupt:
            pool.terminate()
            print("Scrape halted.")
            return

        # Should this be a configuration variable?
        bsize = 50

        for b in range(0, len(to_save), bsize):
            with db.transaction():
                for i in to_save[b:b+bsize]:
                    if i == None: continue
                    try:
                        i.save()
                    except Exception as e:
                        print("Error saving data for image {}: {}".format(i.path), str(ex))

def scrape_image_data((i, thumb_path, thumb_prefix, thumb_postfix, thumb_aspect_ratio)):
    try:
        # open image
        image = PIL.Image.open(i.path)
        image = normalize_image(image)
        extract_image_metadata(i, image)
        make_thumbnail(i, image, thumb_path, thumb_prefix, thumb_postfix, thumb_aspect_ratio)
        derive_average_color(i, image)
        # derive_frequent_colors(i, image)
        return i
    except Exception as ex:
        print("Error processing image {}: {}".format(i.path, str(ex)))

def normalize_image(image):
# ensures passed in PIL.Image is RGB
    # If the image isn't RGB, convert it to RGB.
    if (image.mode != "RGB"):
        try:
            image = image.convert("RGB")
        except Exception as ex:
            print("RGB conversion error for image {}: {}".format(i.path, str(ex)))
    return image


def extract_image_metadata(i, img):
# function determines image dimensions
    try:
        i.x = img.size[0]
        i.y = img.size[1]

    except Exception as ex:
        print("Unable to obtain metadata for image {}: {}".format(i.path, str(ex)))


def make_thumbnail(i, img, thumb_path, thumb_prefix, thumb_postfix, thumb_aspect_ratio):
# function generates 200px (square/ratio-maintained) thumbnail
# NOTE: img is set to this reduced size thumbnail
    try:
        # TODO: configurable thumb size 
        size = (200, 200)
        if (thumb_aspect_ratio == "square"):
            img = ImageOps.fit(img, size, PIL.Image.ANTIALIAS)
        elif (thumb_aspect_ratio == "top_square"):
            x = 0
            w = min(img.size)
            h = w
            
            if (img.size[0] > img.size[1]):
                x = int((img.size[0] - w) / 2)
            
            box = (x, 0, x + w, h)
            
            c = img.crop(box)
            img = c.resize(size, PIL.Image.ANTIALIAS)
        else:   # "proportional"
            img.thumbnail(size, PIL.Image.ANTIALIAS)

        
        path_parts = os.path.split(i.path)
        name_parts = os.path.splitext(path_parts[1])
        
        thumb_name = thumb_prefix + name_parts[0] + thumb_postfix
        
        thumb = get_thumb(thumb_path, thumb_name, ".jpg")
        
        counter = 0
        while os.path.isfile(thumb):
            counter += 1
            new_thumb_name = thumb_name + str(counter)
            thumb = get_thumb(thumb_path, new_thumb_name, ".jpg") 
            
        img.save(thumb, "JPEG")
        
        i.thumb = thumb

    except Exception as ex:
        print("Unable to generate thumb for image {}: {}".format(i.path, str(ex)))


def derive_average_color(i, img):
# function determines average color from histogram

# TOFIX: Do not convert non-RGB images to RGB. This should save calc time.

    try:
        hist = img.histogram()
        r = hist[0:256]
        g = hist[256:512]
        b = hist[512:768]
        
        i.r = sum(i*w for i, w in enumerate(r)) / sum(r)
        i.g = sum(i*w for i, w in enumerate(g)) / sum(g)
        i.b = sum(i*w for i, w in enumerate(b)) / sum(b)
        
    except Exception as ex:
        print("Unable to find average color for image {}: {}".format(i.path, str(ex)))

def derive_frequent_colors(i, img, num_colors=3):
    #lol
    pass
