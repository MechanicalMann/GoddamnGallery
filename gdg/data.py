import os
from peewee import *

database = SqliteDatabase(None, threadlocals=True)

class BaseModel(Model):
    class Meta:
        database = database

class Image(BaseModel):
    color = CharField(null=True)
    path = CharField()
    thumb = CharField(null=True)
    x = IntegerField(null=True)
    y = IntegerField(null=True)

    class Meta:
        db_table = 'images'

class Tag(BaseModel):
    name = CharField()
    slug = CharField()

    class Meta:
        db_table = 'tags'

class GoddamnDatabase(object):
    def __init__(self, path):
        if path == None:
            path = os.path.dirname(__file__)
        self.dbname = os.path.join(path, 'gallery.db')
    def __enter__(self):
        database.init(self.dbname)
        database.connect()
        return database
    def __exit__(self, t, v, tb):
        database.close()