from flask import Flask, render_template, request, jsonify, session, redirect, url_for
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
import xml.etree.ElementTree as ET
from xml.dom import minidom
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import webbrowser
import json

app = Flask(__name__)

# nastavitev seje
app.config['SECRET_KEY'] = "skrivni ključ" 
app.config['SESSION_TYPE'] = 'filesystem'

# inicializacija seje
Session(app)

# nastavitev verzije
global je_placljiva_verzija
je_placljiva_verzija = False  

# aktivaciske kode za aktivacijo plačljive verzije
AKTIVACIJSKA_KODA_3_MINUTE = "123" 
AKTIVACIJSKA_KODA_6_MINUT = "456"  
AKTIVACIJSKA_KODA_12_MINUT = "789" 

# inicializacija baz za shranjevanje
baza_pesmi = TinyDB('vse_pesmi.json')
baza_privzetih_pesmi = TinyDB('privzete_glasbe.json')
cakalna_vrsta_baza = TinyDB('cakalna_vrsta.json')
trenutna_pesem_baza = TinyDB('trenutna_pesem.json')
vnosi_pesmi = TinyDB('vnos_pesmi.json')
baza_kod = TinyDB('baza_kod.json')
baza_uporabnikov = TinyDB('uporabniki.json')
baza_verzija = TinyDB('verzija.json')

# pot do mape muske
muske_mapa = os.path.join(app.root_path, 'static', 'muske')

# posodobi bazo vseh pesmi ob zagonu
if os.path.exists(muske_mapa):
    # pridobi seznam datotek v mapi in rezultate shrani v množico (set)
    trenutne_datoteke = {datoteka for datoteka in os.listdir(muske_mapa) if datoteka.endswith('.mp3')}
    # pridobi seznam datotek v bazi brez poti do datoteke
    datoteke_v_bazi = {os.path.basename(pesem['datoteka']) for pesem in baza_pesmi.all()}
    
    # odstrani pesmi, ki niso več v mapi
    for pesem in baza_pesmi.all():
        if os.path.basename(pesem['datoteka']) not in trenutne_datoteke:
            baza_pesmi.remove(doc_ids=[pesem.doc_id])

    # določi najvišji ID za novo dodane pesmi
    max_id = max([pesem['id'] for pesem in baza_pesmi.all()], default=0)
    # doda nove pesmi, ki jih še ni v bazi
    for datoteka in trenutne_datoteke:
        if datoteka not in datoteke_v_bazi:
            # razdeli ime datoteke na avtorja in naslov
            ime_brez_koncnice = os.path.splitext(datoteka)[0]
            avtor = "Neznan"
            naslov = ime_brez_koncnice
            # preveri, če ime datoteke vsebuje ločilo " - "
            if " - " in ime_brez_koncnice:
                deli = ime_brez_koncnice.split(" - ", 1)
                avtor = deli[0].strip()
                naslov = deli[1].strip()
            baza_pesmi.insert({
                "id": max_id + 1,
                "naslov": naslov,
                "avtor": avtor,
                "datoteka": os.path.join('muske', datoteka)
            })
            max_id += 1

# posodobi bazo privzetih pesmi ob zagonu
privzete_pesmi_mapa = os.path.join(app.root_path, 'static', 'privzete_pesmi')
if os.path.exists(privzete_pesmi_mapa):
    # pridobi seznam datotek v mapi
    trenutne_privzete = {datoteka for datoteka in os.listdir(privzete_pesmi_mapa) if datoteka.endswith('.mp3')}
    # pridobi seznam datotek v bazi
    privzete_v_bazi = {os.path.basename(pesem['datoteka']) for pesem in baza_privzetih_pesmi.all()}
    
    # odstrani pesmi, ki niso več v mapi
    for pesem in baza_privzetih_pesmi.all():
        if os.path.basename(pesem['datoteka']) not in trenutne_privzete:
            baza_privzetih_pesmi.remove(doc_ids=[pesem.doc_id])

    # določi najvišji ID za novo dodane privzete pesmi
    max_privzeti_id = max([pesem['id'] for pesem in baza_privzetih_pesmi.all()], default=0)
    
    # dodaj nove pesmi, ki jih še ni v bazi
    for datoteka in trenutne_privzete:
        if datoteka not in privzete_v_bazi:
            # razdeli ime datoteke na avtorja in naslov
            ime_brez_koncnice = os.path.splitext(datoteka)[0]
            avtor = "Neznan"
            naslov = ime_brez_koncnice
            # preveri, če ime datoteke vsebuje ločilo " - "
            if " - " in ime_brez_koncnice:
                deli = ime_brez_koncnice.split(" - ", 1)
                avtor = deli[0].strip()
                naslov = deli[1].strip()
            baza_privzetih_pesmi.insert({
                "id": max_privzeti_id + 1,
                "naslov": naslov,
                "avtor": avtor,
                "datoteka": os.path.join('privzete_pesmi', datoteka)
            })
            max_privzeti_id += 1

# napolni bazo, ko se program začne
if not trenutna_pesem_baza.all():
    trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})

# napolni 5x, da bo tabela vedno imela 5 vrstic
cakalna_vrsta_baza.truncate()
for _ in range(5):
    cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": "", "vloga": "gost"})

def generiraj_kodo():
    # generira naključno 3 mestno kodo
    return ''.join(random.choices(string.digits, k=3))

def zapis_v_xml(pesem, datum):
    # funkcija za zapis v XML datoteko
    xml_datoteka = 'predvajane_pesmi.xml'
    koren = None
    # preveri, ali datoteka obstaja in jo prebere
    try:
        if os.path.exists(xml_datoteka):
            drevo = ET.parse(xml_datoteka)
            koren = drevo.getroot()
    # če datoteka ne obstaja ali je poškodovana se ustvari nov element
    except ET.ParseError:
        print(f"Datoteka {xml_datoteka} je poškodovana. Ustvarjam novo.")

    if koren is None:
        koren = ET.Element("predvajane_pesmi")
    

    vnos = ET.SubElement(koren, "pesem")
    ET.SubElement(vnos, "datum").text = datum
    ET.SubElement(vnos, "avtor").text = pesem['avtor']
    ET.SubElement(vnos, "naslov").text = pesem['naslov']
    
    # ustvari XML niz z uporabo minidom
    xmlstr = minidom.parseString(ET.tostring(koren, encoding='utf-8')).toprettyxml(indent="    ", encoding='utf-8').decode('utf-8')
    # odstrani prazne vrstice
    xmlstr = '\n'.join(line for line in xmlstr.splitlines() if line.strip())

    with open(xml_datoteka, "w", encoding="utf-8") as datoteka:
        datoteka.write(xmlstr)

def preveri_prijavo():
    # preveri ali je uporabnik prijavljen ali gost
    return 'uporabnik_id' in session and (session.get('vloga') in ['gost', 'prijavljen'])

def pridobi_prijavljenega_uporabnika():
    # če je preveri_prijavo False, uporabnik ni prijavljen in nima določene vloge in uporabniškega imena
    if not preveri_prijavo():
        return False, None, None
    vloga = session.get('vloga')
    uporabnisko_ime = None

    if vloga == 'prijavljen':
        # pridobi podatke o prijavljenem uporabniku iz baze
        uporabnik = Query()
        uporabnik_data = baza_uporabnikov.get(uporabnik.id == session['uporabnik_id'])
        if uporabnik_data:
            uporabnisko_ime = uporabnik_data['uporabnisko_ime']
    return True, vloga, uporabnisko_ime

def preveri_verzijo():
    # preveri, ali je aktivirana plačljiva verzija
    global je_placljiva_verzija
    verzija = baza_verzija.all()
    trenutni_cas = datetime.now()
    if verzija:
        # preveri veljavnost aktivacije
        aktivacija = verzija[0]
        cas_aktivacije = datetime.fromisoformat(aktivacija['cas_aktivacije'])
        trajanje = aktivacija['trajanje']
        iztek = cas_aktivacije + timedelta(minutes=trajanje)
        if trenutni_cas <= iztek:
            je_placljiva_verzija = True
        else:
            je_placljiva_verzija = False
            # počisti bazo po poteku aktivacije
            baza_verzija.truncate()
    else:
        je_placljiva_verzija = False

@app.route("/registracija", methods=["GET", "POST"])
def registracija():
    preveri_verzijo() 
    if request.method == "POST":
        eposta = request.form.get("eposta")
        geslo = request.form.get("geslo")
        uporabnisko_ime = request.form.get("uporabnisko_ime")

        if not eposta or not geslo or not uporabnisko_ime:
            return render_template("registracija.html", napaka="Vsa polja so obvezna.")
        
        uporabnik = Query()
        if baza_uporabnikov.get(uporabnik.eposta == eposta):
            return render_template("registracija.html", napaka="Uporabnik s to e-pošto že obstaja.")

        # shrani novega uporabnika z zakodiranim geslom
        sifrirano_geslo = generate_password_hash(geslo)
        baza_uporabnikov.insert({
            "id": str(uuid.uuid4()),
            "eposta": eposta,
            "uporabnisko_ime": uporabnisko_ime,
            "geslo": sifrirano_geslo,
            "vloga": "prijavljen"
        })
        return redirect(url_for("prijava"))
    return render_template("registracija.html")

@app.route("/prijava", methods=["GET", "POST"])
def prijava():
    preveri_verzijo()
    if request.method == "POST":
        # prijava kot gost
        if "prijava_kot_gost" in request.form:
            session["vloga"] = "gost"
            session["uporabnik_id"] = str(uuid.uuid4())
            return redirect(url_for("pesmi"))
        
        eposta = request.form.get("eposta")
        geslo = request.form.get("geslo")
        if not eposta or not geslo:
            return render_template("prijava.html", napaka="Vsa polja so obvezna.")
        
        # preveri ali uporabnik obstaja in ali je geslo pravilno
        uporabnik = Query()
        uporabnik_data = baza_uporabnikov.get(uporabnik.eposta == eposta)
        if uporabnik_data and check_password_hash(uporabnik_data["geslo"], geslo):
            session["uporabnik_id"] = uporabnik_data["id"]
            session["vloga"] = "prijavljen"
            return redirect(url_for("pesmi"))
        else:
            return render_template("prijava.html", napaka="Napačna e-pošta ali geslo.")
    return render_template("prijava.html", napaka=None)
        
@app.route("/odjava")
def odjava():
    # odjavi uporabnika in počisti sejo
    preveri_verzijo()
    session.clear()
    return redirect(url_for("pesmi"))

@app.route("/aktiviraj", methods=["POST"])
def aktiviraj():
    # aktivira plačljivo verzijo z vnosom kode
    global je_placljiva_verzija
    data = request.get_json()
    vnesena_koda = data.get("koda")
    trenutni_cas = datetime.now()

    # Določitev trajanja glede na kodo
    if vnesena_koda == AKTIVACIJSKA_KODA_3_MINUTE:
        trajanje = 3
        je_placljiva_verzija = True
    elif vnesena_koda == AKTIVACIJSKA_KODA_6_MINUT:
        trajanje = 6
        je_placljiva_verzija = True
    elif vnesena_koda == AKTIVACIJSKA_KODA_12_MINUT:
        trajanje = 12
        je_placljiva_verzija = True
    else:
        return jsonify({"success": False, "message": "Napačna aktivacijska koda."}), 400

    # Shranjevanje aktivacije v bazo
    baza_verzija.truncate()
    baza_verzija.insert({
        "koda": vnesena_koda,
        "cas_aktivacije": trenutni_cas.isoformat(),
        "trajanje": trajanje
    })

    return jsonify({"success": True, "message": f"Verzija uspešno nadgrajena v plačljivo za {trajanje} minut!"})

# inicializacija pygame mixerja za predvajanje zvoka
pygame.mixer.init()  

@app.route("/")
def zacetna_stran():
    # generiranje QR kode z lokalnim IP-jem in prikaz tabele z čakalno vrsto ter trenutno pesmijo 
    preveri_verzijo()
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
        iztekla = trenuten_cas + timedelta(minutes=1)
        baza_kod.truncate()
        baza_kod.insert({"koda": nova_koda, "iztekla": iztekla.isoformat()})
        koda = nova_koda
    else:
        koda = veljavna_koda['koda']

    cakalna_vrsta = cakalna_vrsta_baza.all()
    trenutna = trenutna_pesem_baza.all()
    trenutna_pesem = trenutna[0]['naslov']
    
    # naključna izbira pesmi iz privzetih pesmi ob zagonu, če ni izbrane
    if trenutna_pesem == "Ni trenutne pesmi" and baza_privzetih_pesmi.all():
        nakljucna_pesem = random.choice(baza_privzetih_pesmi.all())
        cakalna_vrsta_baza.update({
            "id": nakljucna_pesem["id"],
            "naslov": nakljucna_pesem["naslov"],
            "avtor": nakljucna_pesem["avtor"],
            "datoteka": nakljucna_pesem["datoteka"],
            "vloga": "gost" 
        }, doc_ids=[cakalna_vrsta[0].doc_id])
        threading.Thread(target=predvajaj_naslednjo).start()

    # pridobi podatke o prijavljenem uporabniku
    prijavljen, vloga, uporabnisko_ime = pridobi_prijavljenega_uporabnika()
    return render_template("index.html", slika="qr_slika.png", cakalna_vrsta=cakalna_vrsta, trenutna_pesem=trenutna_pesem, koda=koda, prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime, je_placljiva_verzija=je_placljiva_verzija)

@app.route("/pesmi", methods=["GET", "POST"])
def pesmi():
    # prikaz seznama pesmi ali obrazca za vnos kode
    preveri_verzijo()
    if "uporabnik_id" not in session:
        # dodeli vlogo gosta novim obiskovalcem
        session["vloga"] = "gost"
        session["uporabnik_id"] = str(uuid.uuid4())
    
    # pridobi podatke o prijavljenem uporabniku
    prijavljen, vloga, uporabnisko_ime = pridobi_prijavljenega_uporabnika()
    
    if request.method == "POST":
        # uporabnik vnese kodo
        uporabniska_koda = request.form['koda']
        kode = Query()
        trenutni_cas = datetime.now()
        pravilna_koda = baza_kod.get((kode.koda == uporabniska_koda) & (kode.iztekla > trenutni_cas.isoformat()))

        if not pravilna_koda:
            return render_template("pesmi.html", napaka="Koda je napačna ali je potekla.", pesmi=[], prikazi_vnos_kode=True, prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime, je_placljiva_verzija=je_placljiva_verzija)
        
        # shrani kodo skupaj s časom, če je veljavna 
        session['uporabniska_koda'] = uporabniska_koda
        session['cas_kode'] = trenutni_cas.isoformat()
        # pošlje bazo vseh pesmi za predvajanje
        pesmi = sorted(baza_pesmi.all(), key=lambda x: x['naslov'].lower())
        return render_template("pesmi.html", pesmi=pesmi, prikazi_vnos_kode=False, prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime, je_placljiva_verzija=je_placljiva_verzija)
    
    # GET zahteva prikazuje formo za vnos kode
    return render_template("pesmi.html", pesmi=[], prikazi_vnos_kode=True, prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime, je_placljiva_verzija=je_placljiva_verzija)

@app.route("/v_cakalno_vrsto", methods=["POST"])
def shrani():
    preveri_verzijo()
    if not preveri_prijavo():
        return jsonify({"error": "Potrebna je prijava."}), 401
    
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

    izbrana_pesem = baza_pesmi.get(pesem.id == pesem_id)
    if izbrana_pesem:
        # določi vlogo uporabnika (prijavljen ali gost)
        vloga = "prijavljen" if session.get("vloga") == "prijavljen" else "gost"
        dodana_pesem = {
            "id": izbrana_pesem["id"],
            "naslov": izbrana_pesem["naslov"],
            "avtor": izbrana_pesem["avtor"],
            "datoteka": izbrana_pesem["datoteka"],
            "vloga": vloga
        }
        cakalna_vrsta = cakalna_vrsta_baza.all()
        if cakalna_vrsta:
            if session.get("vloga") == "prijavljen":
                # premakne pesmi navzdol in doda pesem prijavljenega uporabnika na vrh
                trenutna_vrsta = list(cakalna_vrsta)
                if trenutna_vrsta[-1]["naslov"] != "Ni izbrane pesmi":
                    cakalna_vrsta_baza.remove(doc_ids=[trenutna_vrsta[-1].doc_id])
                    cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": "", "vloga": "gost"})
                    trenutna_vrsta = cakalna_vrsta_baza.all()
                for i in range(len(trenutna_vrsta) - 1, 0, -1):
                    cakalna_vrsta_baza.update(trenutna_vrsta[i - 1], doc_ids=[trenutna_vrsta[i].doc_id])
                cakalna_vrsta_baza.update(dodana_pesem, doc_ids=[trenutna_vrsta[0].doc_id])
            else:
                # doda pesem gosta na prvo prosto mesto
                prosto_mesto = None
                for vnos in cakalna_vrsta:
                    if vnos["naslov"] == "Ni izbrane pesmi":
                        prosto_mesto = vnos
                        break
                if prosto_mesto:
                    cakalna_vrsta_baza.update(dodana_pesem, doc_ids=[prosto_mesto.doc_id])
            
            # označi kodo kot uporabljeno
            uporabljene_kode.append(uporabniska_koda)
            session['uporabljene_kode'] = uporabljene_kode
            # počisti sejo za naslednjo kodo
            session.pop('uporabniska_koda', None)
            session.pop('cas_kode', None)
            # za predvajanje naslednje pesmi ko se trenutna konča
            if not pygame.mixer.music.get_busy():
                threading.Thread(target=predvajaj_naslednjo).start()
            return jsonify({"message": f"Pesem '{izbrana_pesem['naslov']}' dodana v čakalno vrsto."})
        else:
            return jsonify({"error": "Čakalna vrsta je polna"}), 400     
    return jsonify({"error": "Pesem ni najdena"}), 404 # not found

def predvajaj_naslednjo():
    while True:
        # poskusi prebrati čakalno vrsto iz baze
        try:
            cakalna_vrsta = cakalna_vrsta_baza.all()
        except json.decoder.JSONDecodeError as e:
            # če je cakalna_vrsta.json poškodovana, izpiše napako in inicializira bazo
            print(f"Napaka pri branju cakalna_vrsta.json: {e}")
            cakalna_vrsta_baza.truncate()
            for _ in range(5):
                cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": "", "vloga": "gost"})
            cakalna_vrsta = cakalna_vrsta_baza.all()
        
        # pridobi naslednjo pesem: iz čakalne vrste ali naključno privzeto
        pesem = None
        iz_cakalne_vrste = False 

        # če obstajajo izbrane pesmi, izbere prvo iz čakalne vrste
        if cakalna_vrsta and not all(p["naslov"] == "Ni izbrane pesmi" for p in cakalna_vrsta):
            pesem = cakalna_vrsta[0]
            iz_cakalne_vrste = True
        # če je čakalna vrsta prazna, izbere naključno privzeto
        elif baza_privzetih_pesmi.all():
            pesem = random.choice(baza_privzetih_pesmi.all())
        else:
            # če ni nobenih pesmi, nastavi "Ni trenutne pesmi" in konča zanko
            trenutna_pesem_baza.truncate()
            trenutna_pesem_baza.insert({"id": 0, "naslov": "Ni trenutne pesmi", "avtor": "", "datoteka": ""})
            break
        
        # preveri pot do datoteke
        relativna_pot = pesem["datoteka"]
        absolutna_pot = os.path.join(app.root_path, 'static', relativna_pot)
        if not relativna_pot or not os.path.isfile(absolutna_pot):
            # če pot ni veljavna, izpiše napako in poskusi z naslednjo pesmijo
            print(f"Neveljavna datoteka ali pot: {absolutna_pot}")
            if iz_cakalne_vrste:
                # odstrani pesem samo če je iz čakalne vrste
                try:
                    cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id])
                except KeyError:
                    print(f"Dokument {pesem.doc_id} ni najdena v čakalni vrsti bazi")
                # napolni čakalno vrsto, da ima vedno 5 vnosov
                while len(cakalna_vrsta_baza.all()) < 5:
                    cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": "", "vloga": "gost"})
            continue
        
        # poskusi naložiti pesem
        try:
            pygame.mixer.music.load(absolutna_pot)
        except pygame.error as e:
            # če nalaganje ne uspe, izpiše napako in poskusi z naslednjo pesmijo
            print(f"Napaka pri nalaganju pesmi {absolutna_pot}: {e}")
            if iz_cakalne_vrste:
                # odstrani pesem samo če je iz čakalne vrste
                try:
                    cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id])
                except KeyError:
                    print(f"Dokument {pesem.doc_id} ni najdena v čakalni vrsti bazi")
                while len(cakalna_vrsta_baza.all()) < 5:
                    cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": "", "vloga": "gost"})
            continue
        
        # posodobi trenutno pesem
        trenutna_pesem_baza.truncate()
        trenutna_pesem_baza.insert({
            "id": pesem["id"],
            "naslov": pesem["naslov"],
            "avtor": pesem["avtor"],
            "datoteka": pesem["datoteka"]
        })
        
        # zapiše predvajano pesem v XML
        datum = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        zapis_v_xml(pesem, datum)
        
        # predvaja pesem
        pygame.mixer.music.play()
        
        # odstrani pesem iz čakalne vrste če je bila izbrana iz tam
        if iz_cakalne_vrste:
            try:
                cakalna_vrsta_baza.remove(doc_ids=[pesem.doc_id])
            except KeyError:
                print(f"Dokument {pesem.doc_id} ni najdena v čakalni vrsti bazi")
            while len(cakalna_vrsta_baza.all()) < 5:
                cakalna_vrsta_baza.insert({"id": 0, "naslov": "Ni izbrane pesmi", "avtor": "", "datoteka": "", "vloga": "gost"})
        
        # počaka, da se pesem konča
        while pygame.mixer.music.get_busy():
            time.sleep(1)

@app.route("/zabelezeno")
def zabelezeno():
    # za prikaz strani potem, ko uporabnik izbere pesem
    preveri_verzijo()
    if not preveri_prijavo():
        return redirect(url_for("prijava"))    
    
    # pridobi podatke o prijavljenem uporabniku
    prijavljen, vloga, uporabnisko_ime = pridobi_prijavljenega_uporabnika()
    return render_template("zabelezeno.html", prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime)

@app.route("/dodaj_pesem", methods=["POST"])
def dodaj_pesem():
    # dobi naslov pesmi, ki ga je vnesel uporabnik in ga shranil v bazo
    preveri_verzijo()
    if not preveri_prijavo():
        return redirect(url_for("prijava"))    
    
    pesem = request.form['pesem']
    vnosi_pesmi.insert({"pesem": pesem})
    
    # pridobi podatke o prijavljenem uporabniku
    prijavljen, vloga, uporabnisko_ime = pridobi_prijavljenega_uporabnika()
    return render_template("zabelezeno.html", prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime)

@app.route("/prepozno")
def prepozno():
    # pokaze to spletno stran, ce je zmanjkalo casa
    preveri_verzijo()
    if not preveri_prijavo():
        return redirect(url_for("prijava"))    
    
    # pridobi podatke o prijavljenem uporabniku
    prijavljen, vloga, uporabnisko_ime = pridobi_prijavljenega_uporabnika()
    return render_template("prepozno.html", prijavljen=prijavljen, vloga=vloga, uporabnisko_ime=uporabnisko_ime)

def izprazni_bazo():
    # za izbrisanje baz ko se program ugasne
    cakalna_vrsta_baza.truncate()
    trenutna_pesem_baza.truncate()
    baza_kod.truncate()

# izvede izprazni_bazo() ko se program ugasne
atexit.register(izprazni_bazo)

if __name__ == "__main__":
    # odpre brskalnik ob zagonu aplikacije
    webbrowser.open("http://localhost:5000/")
    app.run(host='0.0.0.0', port=5000)
