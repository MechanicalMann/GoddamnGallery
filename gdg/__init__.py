import cherrypy
from mako.template import Template
from mako.lookup import TemplateLookup

templates = TemplateLookup(directories=['html'])

class Gallery(object):
    @cherrypy.expose
    def index(self):
        tmp = templates.get_template("index.html")
        return tmp.render(title="Hello, World!")

def main():
    cherrypy.quickstart(Gallery(), config='gdg.conf')