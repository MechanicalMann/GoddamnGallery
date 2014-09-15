#!/usr/bin/env python2
from gdg import wsgi

def application(env, response):
    return wsgi(env, response)
