from flask import Flask, render_template, request, redirect, url_for
import re
import requests
from urllib.parse import urlencode
from datetime import datetime
from collections import defaultdict

app = Flask(__name__) 

@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html', active_page="home") 

@app.route('/about')
def about():
    return render_template('about.html', active_page="about")

@app.route('/stats')
def stats():
    return render_template('stats.html', active_page="stats")

@app.route('/help')
def help():
    return render_template('help.html', active_page="help")

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.route("/formulaire")
def formulaire(): 
    return render_template("formulaire.html", active_page="formulaire")

@app.route("/resultats")
def resultats(): 
    return render_template("resultats.html", active_page="resultats")

@app.route("/evenements")
def evenements():
    return render_template("evenements.html", active_page="evenements")


if __name__ == '__main__':
    app.run(debug=True)
