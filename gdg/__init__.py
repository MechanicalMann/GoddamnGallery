import os
import cherrypy
from mako.template import Template
from mako.lookup import TemplateLookup

# Content is relative to the base directory, not the module directory.
current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

templates = TemplateLookup(directories=['html'])

class Gallery(object):
    @cherrypy.expose
    def index(self):
        tmp = templates.get_template("index.html")
        return tmp.render(title="Hello, World!")

def main():
    cherrypy.quickstart(Gallery(), config='gdg.conf')