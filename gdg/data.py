from peewee import *

database = SqliteDatabase(None)

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
    def __init__(self, dbname):
        if dbname == None:
            dbname = 'gallery.db'
        self.dbname = dbname
    def __enter__(self):
        database.init(self.dbname)
        database.connect()
        return database
    def __exit__(self, t, v, tb):
        database.close()