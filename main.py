from flask import Flask, render_template, request, jsonify, session
from tinydb import TinyDB, Query
import pygame
import threading
import time
import qrcode
import socket
import os
import atexit
from datetime import datetime, timedelta
import random
import string
from flask_session import Session

app = Flask(__name__)

# nastavitev seje
app.config['SECRET_KEY'] = "skrivni ključ" 
app.config['SESSION_TYPE'] = 'filesystem'

# inicializacija seje
Session(app)

# inicializacija baz
baza_pesmi = TinyDB('vse_glasbe.json')
cakalna_vrsta_baza = TinyDB('cakalna_vrsta.json')
trenutna_pesem_baza = TinyDB('trenutna_pesem.json')
vnosi_pesmi = TinyDB('vnos_pesmi.json')
baza_kod = TinyDB('baza_kod.json')


# napolni bazo, ko se prorgram začne
if not trenutna_pesem_baza.all():
    trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})

# napolni 10x, da bo tabela vedno imela 5x vrstic
if len(cakalna_vrsta_baza.all()) < 11:
    for x in range(5 - len(cakalna_vrsta_baza.all())):
        cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": ""})


def generiraj_kodo():
    #generira naključno 4 mestno kodo
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


# inicializacija pygame mixerja za predvajanje zvoka
pygame.mixer.init()  

@app.route("/")
def zacetna_stran():
    # generiranje QR kode z lokalnim IP-jem in prikaz tabele z čakalno vrsto ter trenutno pesmijo 
    static_mapa = os.path.join(os.path.dirname(__file__), 'static')
    qr_pot = os.path.join(static_mapa, 'qr_slika.png')
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    url = f'http://{local_ip}:5000/pesmi'
    qr = qrcode.make(url)
    qr.save(qr_pot)

    # preveri ali obstaja veljavna koda
    kode = Query()
    trenuten_cas = datetime.now()
    veljavna_koda = baza_kod.get(kode.iztekla > trenuten_cas.isoformat())
    if not veljavna_koda:
        # generira novo kodo in jo shrani v bazo
        nova_koda = generiraj_kodo()
        iztekla = trenuten_cas + timedelta(minutes=3)
        baza_kod.truncate()
        baza_kod.insert({"koda": nova_koda, "iztekla": iztekla.isoformat()})
        koda = nova_koda
    else:
        koda = veljavna_koda['koda']

    cakalna_vrsta = cakalna_vrsta_baza.all()
    trenutna = trenutna_pesem_baza.all()
    trenutna_pesem = trenutna[0]['naslov']
    return render_template("index.html", slika="qr_slika.png", cakalna_vrsta=cakalna_vrsta, trenutna_pesem=trenutna_pesem, koda=koda)

@app.route("/pesmi", methods=["GET", "POST"])
def pesmi():
    # uporabnik vnese kodo
    if request.method =="POST":
        uporabniska_koda = request.form['koda']
        kode = Query()
        trenutni_cas = datetime.now()
        pravilna_koda = baza_kod.get((kode.koda == uporabniska_koda) & (kode.iztekla > trenutni_cas.isoformat()))

        if not pravilna_koda:
            return render_template("pesmi.html", napaka="Koda je napačna ali je potekla.", pesmi=[], show_code_form=True)
        
        # shrani kodo skupaj s časom, če je veljavna 
        session['uporabniska_koda'] = uporabniska_koda
        session['cas_kode'] = trenutni_cas.isoformat()
        # pošlje bazo vseh pesmi za predvajanje
        pesmi = sorted(baza_pesmi.all(), key=lambda x: x['naslov'].lower())
        return render_template("pesmi.html", pesmi=pesmi, show_code_form=False)
    # GET zahteva prikazuje formo za vnos kode
    return render_template("pesmi.html", pesmi=[], show_code_form=True)

@app.route("/v_cakalno_vrsto", methods=["POST"])
def shrani():
    # pridobi pesem iz baze in jo zamenja z "Ni izbrane pesmi" v čakalni vrsti
    pesem = Query()
    data = request.get_json()
    pesem_id = int(data['id'])
    uporabniska_koda = data.get('koda')

    # preveri ali je koda še veljavna (1 minuta od vnosa) 
    cas_kode = session.get('cas_kode')
    if not cas_kode or not uporabniska_koda:
        return jsonify({"error": "Koda je napačna ali je potekla."}), 400

    try:
        cas_kode = datetime.fromisoformat(cas_kode)
        trenutni_cas = datetime.now()
        if trenutni_cas > cas_kode + timedelta(minutes=1):
            return jsonify({"error": "Koda je potekla (1 minuta). Počakaj na novo kodo"}), 400
    except ValueError:
        return jsonify({"error": "Neveljaven čas seje."}), 400
    
    # preveri ali je uporabnik že dodal pesem z to kodo
    uporabljene_kode = session.get('uporabljene_kode', [])
    if uporabniska_koda in uporabljene_kode:
        return jsonify({"error": "S to kodo si že izbral pesem. Počakaj na novo kodo"}), 429

    # doda pesem v čakalno vrsto
    izbrana_pesem = baza_pesmi.get(pesem.id == pesem_id)
    if izbrana_pesem:
        dodana_pesem = {
            "id": izbrana_pesem["id"],
            "naslov": izbrana_pesem["naslov"],
            "avtor": izbrana_pesem["avtor"],
            "datoteka": izbrana_pesem["datoteka"]
        }
        cakalna_vrsta = cakalna_vrsta_baza.search(pesem.naslov == "Ni izbrane pesmi")
        if cakalna_vrsta:
            cakalna_vrsta_baza.update(dodana_pesem, doc_ids=[cakalna_vrsta[0].doc_id])
            # preveri ali je uporabnik že uporabil kodo
            uporabljene_kode.append(uporabniska_koda)
            session['uporabljene_kode'] = uporabljene_kode
            # počisti sejo za naslednjo kodo
            session.pop('uporabniska_koda', None)
            session.pop('cas_kode', None)
            # za predvajanje naslednje pesmi ko se trenutna konča
            if not pygame.mixer.music.get_busy():
                threading.Thread(target=predvajaj_naslednjo).start() # thread je potreben, da se pesem predvaja v ozadju, AI
            return jsonify({"message": f"Pesem '{izbrana_pesem['naslov']}' dodana v čakalno vrsto."})
        else:
            return jsonify({"error": "Čakalna vrsta je polna"}), 400     
    return jsonify({"error": "Pesem ni najdena"}), 404

def predvajaj_naslednjo():
    
    while True:
        cakalna_vrsta = cakalna_vrsta_baza.all()
        if not cakalna_vrsta:
            break
        # po vsakem koncu pesmi se napolni tabelo z "Ni izbrane pesmi" da bo vedno 5 vrstic
        if len(cakalna_vrsta_baza.all()) < 11:
            for x in range(6 - len(cakalna_vrsta_baza.all())):
                cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": ""})
        # pot do datoteke pesmi
        pesem = cakalna_vrsta[0]
        relativna_pot = pesem["datoteka"]
        absolutna_pot = os.path.join(app.root_path, 'static', relativna_pot)
        #doda izbrano pesem v trenutno pesem bazo in izbriše prejšnjo
        pygame.mixer.music.load(absolutna_pot)
        trenutna_pesem_baza.truncate()  
        trenutna_pesem_baza.insert({
            "id": pesem["id"],
            "naslov": pesem["naslov"],
            "avtor": pesem["avtor"],
            "datoteka": pesem["datoteka"]
        })
        # predvaja pesem in jo odstrani iz čakalne vrste
        pygame.mixer.music.play()
        cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id]) 

        while pygame.mixer.music.get_busy():
            time.sleep(1)
        # po končani pesmi se izpiše "Ni trenutne pesmi" v tabeli
        if not pygame.mixer.music.get_busy():
            trenutna_pesem_baza.truncate()
            trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})

@app.route("/zabelezeno")
def zabelezeno():
    # za prikaz strani potem, ko uporabnik izbere pesem
    return render_template("zabelezeno.html")


@app.route("/dodaj_pesem", methods=["POST"])
def dodaj_pesem():
    # dobi naslov pesmi, ki ga je vnesel uporabnik in ga shranil v bazo
    pesem = request.form['pesem']
    vnosi_pesmi.insert({"pesem": pesem})
    return render_template("zabelezeno.html")

@app.route("/prepozno")
def prepozno():
    # pokaze to spletno stran, ce je zmanjkalo casa
    return render_template("prepozno.html")

def izprazni_bazo():
    # za izbrisanje baz ko se program ugasne
    cakalna_vrsta_baza.truncate()
    trenutna_pesem_baza.truncate()
    vnosi_pesmi.truncate()
    baza_kod.truncate()

# izvede izprazni_bazo() ko se program ugasne
atexit.register(izprazni_bazo)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)