"""
Paikallinen tilastosovellus
- Ei käytä internetiä.
- Lukee tilastot.db-tiedoston käyttäjän datakansiosta (ks. asetukset.py).
- Edellyttää Pythonin lisäksi pandas- ja matplotlib-kirjastoja.
Käynnistys: python sovellus.py
"""

import os
import re
import sqlite3
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from asetukset import TIETOKANTA


KANSIO = Path(__file__).resolve().parent

TILASTOT = {
    "Väestö": "vaesto_11ra",
    "Työttömyysaste, kausitasoitettu": "tyottomyysaste_135z",
    "Tehdyt työtunnit": "tyotunnit_13at",
    "Tavaroiden ja palveluiden vienti, milj. €": "ulkomaankauppa_12gq",
    "Vienti: viisi suurinta vientimaata, milj. €": "vientimaat_12gq",
    "Kauppatase (tavarat), 12 kk liukuva summa, milj. €": "kauppatase_12gf",
    "Vaihtotase, 12 kk liukuva summa, milj. €": "vaihtotase_12gf",
    "BKT:n volyymin vuosimuutos, %": "bkt_15a9",
    "Yksityisten kulutusmenojen volyymi, kausitasoitettu (milj. €, 2015)": "yksityiset_kulutusmenot_132h",
    "Kotitalouksien käytettävissä oleva nettotulo, reaalinen vuosimuutos, % (neljännes)":
        "kotitalouksien_reaalitulo_15a7",
    "Kotitalouksien käytettävissä oleva nettotulo, reaalinen vuosimuutos, % (vuosi)":
        "kotitalouksien_kaytettava_tulo_15a9",
    "Inflaatio (vuosimuutos, %)": "inflaatio_122p",
    "EDP-velka (sulautettu), milj. €": "edp_velka_11yv",
    "S&P 500 (kuukausi)": "sp500_yahoo",
    "Intia, Nifty 50 (kuukausi)": "nifty50_yahoo",
    "OMX Helsinki 25 (kuukausi)": "omxh25_yahoo",
    "Kiina, Shanghai Composite (kuukausi)": "shanghai_yahoo",
    "Inflaation alaerät (euroalue, %-yks.)": "inflaatio_ctrb_eurostat",
    "Korot, OIS (1 kk, 1 v, 5 v, 10 v)": "korot_ois_ekp",
    "12 kk Euribor (kuukausikeskiarvo, %)": "euribor_12kk_ekp",
    "10 v valtionlainakorot (Suomi, Saksa, Ranska, Italia)": "valtionlainakorot_10v_eurostat",
    "Kuluttajien luottamus (CCI)": "kuluttajien_luottamus_11cc",
    "Kotitalouksien velkaantumisaste, %": "kotitalouksien_velkaantumisaste_129g",
    "Brent-raakaöljy (USD/barreli)": "brent_oljy_fred",
    "Teollisuustuotanto, kausitasoitettu (2021=100)": "teollisuustuotanto_14mh",
    "Palvelualojen liikevaihto, kausitasoitettu (2021=100)": "palvelut_liikevaihto_14k7",
    "Tuotannon suhdannekuvaaja, kausitasoitettu (2015=100)": "tuotannon_suhdanne_132f",
    "Teollisuuden uudet tilaukset, trendi (2021=100)": "teollisuus_tilaukset_14mi",
    "Kulta (USD/unssi, kuukausi)": "kulta_yahoo",
    "Kupari (USD/pauna, kuukausi)": "kupari_yahoo",
    "Maakaasu, Henry Hub (USD/MMBtu, kuukausi)": "maakaasu_yahoo",
    "Väkiluvun muutos, %: Helsinki, Tampere, Turku": "vaeston_muutos_kaupungit_11ra",
    "Asunnot: hintaindeksi, kerrostalot (2025=100, kuukausi)": "asunnot_hintaindeksi_kk",
    "Asunnot: neliöhinnat, kerrostalot (€/m²)": "asunnot_neliohinnat_13mx",
    "Asunnot: kauppojen lukumäärä, kerrostalot": "asunnot_kauppamaarat_13mx",
    "Asunnot: neliövuokrat, vapaarahoitteiset (€/m²/kk)": "asunnot_neliovuokrat",
    "Kuntien välinen nettomuutto": "nettomuutto_11ae",
    "Asuntotuotanto, 12 kk summa (koko maa)": "asuntotuotanto_156f",
    "Väestöennuste 2024: väkiluku": "vaestoennuste_14wx",
    "Väestöennuste 2024: 20–34-vuotiaat": "vaestoennuste_20_34_14wx",
}

# Asuntodashboardissa näytettävät kaupungit (samat nimet kuin hae_tilastot.py:ssä;
# tietokannassa on lisäksi Espoo, Vantaa ja Oulu)
KAUPUNKINIMET = ["Helsinki", "Tampere", "Turku"]

# Tietolähde taulun nimen päätteen mukaan (hae_tilastot.py nimeää taulut näin);
# muut taulut ovat Tilastokeskuksen PxWeb-rajapinnasta
LAHTEET = {
    "_yahoo": "Yahoo Finance",
    "_eurostat": "Eurostat",
    "_ekp": "Euroopan keskuspankki (EKP)",
    "_fred": "FRED (Federal Reserve Bank of St. Louis)",
    "_maailmanpankki": "Maailmanpankki",
}


def tilaston_lahde(taulu):
    """Palauttaa tietokantataulun tietolähteen nimen."""
    for paate, lahde in LAHTEET.items():
        if taulu.endswith(paate):
            return lahde
    return "Tilastokeskus"

# Tunnistaa otsikot: 1975, 2024*, 2020Q1, 2020M03 sekä näiden perässä
# olevan tekstin (esim. "1976 Volyymin muutokset, %")
AIKA_RE = re.compile(r"^(\d{4})(?:Q([1-4])|M(\d{2}))?\*?(?:\s|$)")

def lue_taulutietokanta(taulu):
    """Lukee yhden taulun paikallisesta SQLite-tietokannasta."""
    with sqlite3.connect(TIETOKANTA) as conn:
        olemassa = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            conn, params=(taulu,)
        )
        if olemassa.empty:
            raise ValueError(f"Tietokannasta ei löydy taulua: {taulu}")
        return pd.read_sql_query(f'SELECT * FROM "{taulu}"', conn)


def muunna_numeerinen(arvot):
    """Muuntaa suomalaiset desimaalipilkut numeroiksi."""
    return pd.to_numeric(
        arvot.astype(str).str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )

def valitse_aikasarakkeet(data):
    """Etsii leveästä taulusta vuosi-, neljännes- ja kuukausisarakkeet."""
    return [c for c in data.columns if AIKA_RE.match(str(c).strip())]


def aika_sarakkeesta(nimi):
    """Muuttaa sarakeotsikon tai aika-arvon päivämääräksi."""
    s = str(nimi).strip()
    m = AIKA_RE.match(s)
    if m:
        vuosi = int(m.group(1))
        if m.group(2):
            kuukausi = (int(m.group(2)) - 1) * 3 + 1
        elif m.group(3):
            kuukausi = int(m.group(3))
        else:
            kuukausi = 1
        return pd.Timestamp(vuosi, kuukausi, 1)
    return pd.to_datetime(s.rstrip("*"), errors="coerce")

def lisaa_sarja(df, poissulje):
    """Muodostaa Sarja-sarakkeen luokittelevista sarakkeista (2–12 eri arvoa),
    jotta eri sarjat piirtyvät omina viivoinaan."""
    luokat = []
    for c in df.columns:
        if c in poissulje or c in ("Aika", "Arvo", "Sarja"):
            continue
        n = df[c].nunique(dropna=True)
        if 1 < n <= 12 and muunna_numeerinen(df[c]).notna().mean() < 0.5:
            luokat.append(c)
    if luokat:
        df["Sarja"] = df[luokat].astype(str).agg(" / ".join, axis=1)
    return df


def muodosta_pitka_data(data, tilasto):
    """
    Muuntaa vuosi-/neljännes-/kuukausisarakkeet pitkään muotoon.
    Jos taulu on jo pitkässä muodossa (aika omassa sarakkeessaan),
    tunnistaa aika- ja arvosarakkeet.
    """
    data = data.copy()
    aikamuuttujat = valitse_aikasarakkeet(data)

    # --- Leveä muoto: ajat ovat sarakeotsikoissa ---
    if aikamuuttujat:
        id_vars = [c for c in data.columns if c not in aikamuuttujat]
        pitkana = data.melt(
            id_vars=id_vars,
            value_vars=aikamuuttujat,
            var_name="Ajankohta_otsikko",
            value_name="Arvo"
        )
        pitkana["Aika"] = pitkana["Ajankohta_otsikko"].map(aika_sarakkeesta)
        pitkana["Aika"] = pd.to_datetime(pitkana["Aika"], errors="coerce")
        pitkana["Arvo"] = muunna_numeerinen(pitkana["Arvo"])
        pitkana = pitkana.dropna(subset=["Aika", "Arvo"])

        # Ulkomaankauppa: tavarat ja palvelut ovat otsikoissa ("2013Q1 G Tavarat Vienti, ...")
        palveluera = pitkana["Ajankohta_otsikko"].str.extract(r"\b(Tavarat|Palvelut)\b")[0]
        if palveluera.notna().all():
            pitkana["Sarja"] = palveluera.map(
                {"Tavarat": "Tavaroiden vienti", "Palvelut": "Palveluiden vienti"}
            )
        else:
            pitkana = lisaa_sarja(pitkana, {"Ajankohta_otsikko"})
        return pitkana

    # --- Pitkä muoto: aika on omassa sarakkeessaan ---
    aikaehdokkaat = [
        c for c in data.columns
        if any(k in str(c).lower() for k in
               ("vuosi", "kuukausi", "neljännes", "neljannes",
                "ajankohta", "aika", "time", "period"))
    ]

    if not aikaehdokkaat:
        for c in data.columns:
            sample = data[c].dropna().astype(str).str.strip().str.rstrip("*").head(20)
            if not sample.empty and sample.str.match(
                r"^\d{4}([-/]\d{1,2})?([-/]\d{1,2})?$"
                r"|^\d{4}\s?[QqKk][1-4]$"
                r"|^\d{4}\s?[Mm]\d{1,2}$"
            ).mean() >= 0.6:
                aikaehdokkaat.append(c)
                break

    if not aikaehdokkaat:
        return pd.DataFrame()

    aikac = aikaehdokkaat[0]

    # Kaikki numeeriset sarakkeet ovat arvosarakkeita (esim. trendi, kausitasoitettu).
    arvosarakkeet = [
        c for c in data.columns
        if c != aikac and muunna_numeerinen(data[c]).notna().mean() >= 0.5
    ]
    if not arvosarakkeet:
        return pd.DataFrame()

    tulos = data.copy()
    tulos["Aika"] = pd.to_datetime(
        tulos[aikac].map(aika_sarakkeesta), errors="coerce"
    )

    if len(arvosarakkeet) == 1:
        tulos["Arvo"] = muunna_numeerinen(tulos[arvosarakkeet[0]])
    else:
        id_vars = [c for c in tulos.columns if c not in arvosarakkeet]
        tulos = tulos.melt(
            id_vars=id_vars,
            value_vars=arvosarakkeet,
            var_name="Mittari",
            value_name="Arvo"
        )
        tulos["Arvo"] = muunna_numeerinen(tulos["Arvo"])

    tulos = tulos.dropna(subset=["Aika", "Arvo"])
    return lisaa_sarja(tulos, {aikac})

PAIVITYS_KOODI = """
import sys
sys.path.insert(0, sys.argv[1])
import hae_tilastot
sys.exit(hae_tilastot.main())
"""



def kaynnista_paivitys(root, nappi, tila_label, valmis_callback):
    """Ajaa päivityksen erillisessä prosessissa ja seuraa sitä pääsäikeestä."""
    nappi.config(state="disabled")
    tila_label.config(text="Päivitetään tietokantaa netistä, odota hetki...")

    try:
        prosessi = subprocess.Popen(
            [sys.executable, "-c", PAIVITYS_KOODI, str(KANSIO)],
            cwd=str(KANSIO),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # Windowsilla putken oletusmerkistö on cp1252, joten käytetään UTF-8:aa
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except Exception as e:
        paivitys_valmis(nappi, tila_label, valmis_callback, -1, str(e))
        return

    tarkista_paivitys(root, prosessi, nappi, tila_label, valmis_callback)


def tarkista_paivitys(root, prosessi, nappi, tila_label, valmis_callback):
    """Kysyy 300 ms välein, onko prosessi valmis. Ajetaan pääsäikeessä."""
    if prosessi.poll() is None:
        root.after(
            300, tarkista_paivitys,
            root, prosessi, nappi, tila_label, valmis_callback
        )
        return
    tuloste = prosessi.stdout.read()
    paivitys_valmis(nappi, tila_label, valmis_callback, prosessi.returncode, tuloste)


def paivitys_valmis(nappi, tila_label, valmis_callback, koodi, tuloste):
    nappi.config(state="normal")
    if koodi == 0:
        valmis_callback()
        messagebox.showinfo("Valmis", "Tietokanta päivitetty.")
    else:
        tila_label.config(text="Tietokannan päivitys epäonnistui.")
        messagebox.showerror("Päivitys epäonnistui", (tuloste or "Tuntematon virhe")[-1500:])
        valmis_callback()


def muista_aika(arvo, loppu):
    """Muuttaa valinnan ("2010" tai "2010-03-01") ajankohdaksi. Pelkkä vuosi
    tarkoittaa päättymisaikana koko vuotta."""
    aika = pd.to_datetime(arvo, errors="coerce")
    if pd.isna(aika):
        return None
    if loppu and re.fullmatch(r"\d{4}", str(arvo).strip()):
        aika = pd.Timestamp(aika.year, 12, 31, 23, 59, 59)
    return aika


def valitse_muistettu(valinnat, muistettu, loppu):
    """Palauttaa muistettua ajankohtaa lähimmän valinnan: alkuun ensimmäisen
    valinnan muistetusta eteenpäin, loppuun viimeisen valinnan siihen asti.
    Jos muistettua ei ole tai se ei osu aineistoon, palauttaa ääripään."""
    if not valinnat:
        return ""
    oletus = valinnat[-1] if loppu else valinnat[0]
    if muistettu is None:
        return oletus
    if loppu:
        osumat = [v for v in valinnat if muista_aika(v, loppu=False) <= muistettu]
        return osumat[-1] if osumat else oletus
    # vuosivalinta kelpaa alkuun, jos vuosi sisältää muistetun ajankohdan
    osumat = [v for v in valinnat if muista_aika(v, loppu=True) >= muistettu]
    return osumat[0] if osumat else oletus


def palauta_tavallinen_nakyma(app):
    """Tuo taulukon ja aikavälivalinnat takaisin dashboardin jälkeen."""
    app.tree.master.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    app.alku_combo.config(state="readonly")
    app.loppu_combo.config(state="readonly")

PYLVAS_TILASTOT = {
    "Inflaation alaerät (euroalue, %-yks.)",
    "Vienti: viisi suurinta vientimaata, milj. €",
}
RYHMAPYLVAS_TILASTOT = {"Väkiluvun muutos, %: Helsinki, Tampere, Turku"}
MAX_ERAA = 5


# ==================================================
# DASHBOARDIT
# Uusi dashboard = yksi uusi rivi tähän sanakirjaan.
# Paneeli: (otsikko, tietokantataulu, tyyli)  tai
#          (otsikko, tietokantataulu, tyyli, sarja)  -> näyttää taulusta vain yhden sarjan
#          (sarja voi olla myös lista sarjoja)
# tyyli: "viiva", "pylvas" (pinottu pylväskuvaaja) tai
#        "ryhmapylvas" (sarjat vierekkäin)
# Paneelien määrä voi olla mikä tahansa; asettelu muodostuu automaattisesti
# (kaksi saraketta, pariton viimeinen paneeli levitetään koko leveydelle).
# ==================================================

DASHBOARDIT = {
    "1_kansantalous": [
        ("BKT:n volyymin vuosimuutos, %", "bkt_15a9", "pylvas"),
        ("Inflaatio (vuosimuutos, %)", "inflaatio_122p", "viiva"),
        ("Julkisyhteisöjen EDP-velka, milj. €", "edp_velka_11yv", "viiva"),
        ("Työttömyysaste, kausitasoitettu, %", "tyottomyysaste_135z", "viiva"),
    ],
    "2_tuotanto": [
        ("Teollisuustuotanto, kausitasoitettu (2021=100)", "teollisuustuotanto_14mh", "viiva"),
        ("Palvelualojen liikevaihto, kausitasoitettu (2021=100)", "palvelut_liikevaihto_14k7", "viiva"),
        ("Tuotannon suhdannekuvaaja, kausitasoitettu (2015=100)", "tuotannon_suhdanne_132f", "viiva"),
        ("Teollisuuden uudet tilaukset, trendi (2021=100)", "teollisuus_tilaukset_14mi", "viiva"),
    ],
    "3_kuluttajat_ja_kotitaloudet": [
        ("Kotitalouksien käytettävissä olevan nettotulon reaalinen vuosimuutos, %",
         "kotitalouksien_reaalitulo_15a7", "viiva"),
        ("Kuluttajien luottamus (CCI), saldoluku", "kuluttajien_luottamus_11cc", "viiva"),
        ("Kotitalouksien velkaantumisaste, %", "kotitalouksien_velkaantumisaste_129g", "viiva"),
        ("Yksityisten kulutusmenojen volyymi, kausitasoitettu (milj. €, 2015)",
         "yksityiset_kulutusmenot_132h", "viiva"),
    ],
    "4_ulkomaankauppa": [
        ("Tavaroiden ja palveluiden vienti, milj. € (neljännes)", "ulkomaankauppa_12gq", "viiva"),
        ("Kokonaisvienti ja viisi suurinta vientimaata, milj. € (vuosi)", "vientimaat_12gq",
         "pylvas"),
        ("Kauppatase (tavarat), 12 kk liukuva summa, milj. €", "kauppatase_12gf", "viiva"),
        ("Vaihtotase, 12 kk liukuva summa, milj. €", "vaihtotase_12gf", "viiva"),
    ],
    "5_asunnot": [
        ("Vanhojen kerrostaloasuntojen hintaindeksi (2025=100)", "asunnot_hintaindeksi_kk",
         "viiva", KAUPUNKINIMET),
        ("Vapaarahoitteiset neliövuokrat, €/m²/kk", "asunnot_neliovuokrat", "viiva",
         KAUPUNKINIMET),
        ("Kauppojen lukumäärä, kerrostalot", "asunnot_kauppamaarat_13mx", "viiva",
         KAUPUNKINIMET),
        ("12 kk Euribor, %", "euribor_12kk_ekp", "viiva"),
        ("Uudet asunnot, 12 kk summa (koko maa)", "asuntotuotanto_156f", "viiva"),
        ("Väkiluvun muutos, %", "vaeston_muutos_kaupungit_11ra", "ryhmapylvas"),
    ],
    "6_korot_ja_inflaatio": [
        ("10 v valtionlainakorot, %", "valtionlainakorot_10v_eurostat", "viiva"),
        ("OIS-korot (EKP), %", "korot_ois_ekp", "viiva"),
        ("Euroalueen inflaatio: alaerien kontribuutiot, %-yks.", "inflaatio_ctrb_eurostat", "pylvas"),
    ],
    "7_pörssit": [
        ("USA: S&P 500, kuukauden sulkuarvo", "sp500_yahoo", "viiva"),
        ("Suomi: OMX Helsinki 25, kuukauden sulkuarvo", "omxh25_yahoo", "viiva"),
        ("Intia: Nifty 50, kuukauden sulkuarvo", "nifty50_yahoo", "viiva"),
        ("Kiina: Shanghai Composite, kuukauden sulkuarvo", "shanghai_yahoo", "viiva"),
    ],
    "8_bkt_kasvu_globaalisti": [
        ("USA: BKT:n volyymin vuosimuutos, %", "bkt_kasvu_maailmanpankki", "pylvas", "USA"),
        ("Kiina: BKT:n volyymin vuosimuutos, %", "bkt_kasvu_maailmanpankki", "pylvas", "Kiina"),
        ("Intia: BKT:n volyymin vuosimuutos, %", "bkt_kasvu_maailmanpankki", "pylvas", "Intia"),
        ("EU: BKT:n volyymin vuosimuutos, %", "bkt_kasvu_maailmanpankki", "pylvas", "EU"),
    ],
    "9_öljy_ja_raaka-aineet": [
        ("Brent-raakaöljy, USD/barreli", "brent_oljy_fred", "viiva"),
        ("Kulta, USD/unssi", "kulta_yahoo", "viiva"),
        ("Kupari, USD/pauna", "kupari_yahoo", "viiva"),
        ("Maakaasu (Henry Hub), USD/MMBtu", "maakaasu_yahoo", "viiva"),
    ],
}

MAX_SARJAA = 6          # viivakuvaajassa enintään näin monta sarjaa / paneeli

# Paneelin alle kirjoitettava huomautus (avaimena paneelin otsikko)
HUOMAUTUKSET = {
    "Vapaarahoitteiset neliövuokrat, €/m²/kk":
        "Huom. tilastoinnin muutos 2025 (uusi taulukko, taso ei vertailukelpoinen)",
}


def piirra_pylvaat(ax, data):
    """Pinottu pylväskuvaaja. Positiiviset arvot pinotaan nollan yläpuolelle,
    negatiiviset alapuolelle. Suurin erä on alimpana."""
    from matplotlib import colormaps
    varit = colormaps["tab20"].colors

    leveä = data.pivot_table(
        index="Aika", columns="Sarja", values="Arvo", aggfunc="sum"
    ).sort_index()
    sarjat = list(leveä.abs().mean().sort_values(ascending=False).index)
    sarjat.sort(key=lambda s: str(s).startswith("Muut"))   # "Muut ..." ylimmäksi

    x = leveä.index
    vali = pd.Series(x).diff().dt.days.median() if len(x) > 1 else 30
    leveys = 0.8 * vali                       # sopii kuukausi-, neljännes- ja vuosisarjoille

    pos_pohja = pd.Series(0.0, index=x)
    neg_pohja = pd.Series(0.0, index=x)
    for i, s in enumerate(sarjat):
        arvot = leveä[s].fillna(0.0)
        pohja = pos_pohja.where(arvot >= 0, neg_pohja)
        ax.bar(x, arvot, bottom=pohja, width=leveys, label=s, color=varit[i % len(varit)])
        pos_pohja = pos_pohja + arvot.clip(lower=0)
        neg_pohja = neg_pohja + arvot.clip(upper=0)

    ax.axhline(0, color="black", linewidth=0.8)
    if len(sarjat) > 1:
        ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0))


def piirra_ryhmapylvaat(ax, data):
    """Ryhmitelty pylväskuvaaja: sarjat vierekkäin samalla ajankohdalla."""
    leveä = data.pivot_table(
        index="Aika", columns="Sarja", values="Arvo", aggfunc="mean"
    ).sort_index()
    sarjat = list(leveä.columns)

    x = leveä.index
    vali = pd.Series(x).diff().dt.days.median() if len(x) > 1 else 365
    leveys = 0.8 * vali / len(sarjat)          # ryhmä vie 80 % ajankohtien välistä
    for i, s in enumerate(sarjat):
        siirto = pd.to_timedelta((i - (len(sarjat) - 1) / 2) * leveys, unit="D")
        ax.bar(x + siirto, leveä[s], width=leveys, label=str(s))

    ax.axhline(0, color="black", linewidth=0.8)
    if len(sarjat) > 1:
        ax.legend()


def piirra_paneeli(ax, otsikko, tyyli, data, virhe, lahde, alku, loppu):
    """Piirtää yhden dashboardin kuvaajan valitulle aikavälille."""
    ax.set_title(otsikko, fontsize=10)
    alateksti = f"Lähde: {lahde}"
    if otsikko in HUOMAUTUKSET:
        alateksti += f"  |  {HUOMAUTUKSET[otsikko]}"
    ax.set_xlabel(alateksti, fontsize=7, style="italic", color="dimgray", loc="left")
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.3)

    if not virhe:
        data = data[data["Aika"].between(alku, loppu)]
        virhe = None if not data.empty else "Valitulla aikavälillä ei ole tietoja"
    if virhe:
        ax.text(0.5, 0.5, virhe, ha="center", va="center",
                transform=ax.transAxes, fontsize=8)
        return

    if "Sarja" not in data.columns or data["Sarja"].isna().all():
        data = data.assign(Sarja=otsikko)

    if tyyli == "pylvas":
        piirra_pylvaat(ax, data)
        return
    if tyyli == "ryhmapylvas":
        piirra_ryhmapylvaat(ax, data)
        if ax.get_legend():
            ax.legend(fontsize=7)
        return

    ryhmat = list(data.dropna(subset=["Sarja"]).groupby("Sarja"))[:MAX_SARJAA]
    for nimi, ryhma in ryhmat:
        ryhma = ryhma.sort_values("Aika")
        ax.plot(ryhma["Aika"], ryhma["Arvo"], linewidth=1.5, label=str(nimi))
    if len(ryhmat) > 1:
        ax.legend(fontsize=7)


def lataa_dashboard_data(paneelit):
    """Lukee dashboardin taulut tietokannasta. Palauttaa (otsikko, tyyli, data, virhe, lähde)."""
    tulos = []
    for otsikko, taulu, tyyli, *suodatin in paneelit:
        try:
            data = muodosta_pitka_data(lue_taulutietokanta(taulu), otsikko)
            if suodatin and not data.empty:                  # valinnainen sarjarajaus
                valitut = suodatin[0]
                if isinstance(valitut, str):
                    valitut = [valitut]
                data = data[data["Sarja"].isin(valitut)]
            virhe = None if not data.empty else "Aikarakennetta tai sarjaa ei löytynyt"
        except Exception as e:
            data, virhe = pd.DataFrame(), f"Ei tietoja\n{str(e)[:70]}"
        tulos.append((otsikko, tyyli, data, virhe, tilaston_lahde(taulu)))
    return tulos


def piirra_dashboard(app):
    """Piirtää dashboardin valittujen vuosien (Alkaen / Päättyen) mukaan."""
    app.tyhjenna_kuvaaja()

    try:
        alku = pd.Timestamp(int(app.alku_var.get()), 1, 1)
        loppu = pd.Timestamp(int(app.loppu_var.get()), 12, 31, 23, 59, 59)
        if alku > loppu:
            alku, loppu = (pd.Timestamp(loppu.year, 1, 1),
                           pd.Timestamp(alku.year, 12, 31, 23, 59, 59))
    except ValueError:
        alku, loppu = pd.Timestamp("1900-01-01"), pd.Timestamp("2100-12-31")

    n = len(app.dash_data)
    sarakkeita = 2 if n > 1 else 1
    rivit = -(-n // sarakkeita)

    fig = Figure(figsize=(11, 6.5), dpi=100)
    ruudukko = fig.add_gridspec(rivit, sarakkeita)
    for i, (otsikko, tyyli, data, virhe, lahde) in enumerate(app.dash_data):
        r, c = divmod(i, sarakkeita)
        viimeinen_pariton = (i == n - 1) and (n % sarakkeita != 0)
        ax = fig.add_subplot(ruudukko[r, :] if viimeinen_pariton else ruudukko[r, c])
        piirra_paneeli(ax, otsikko, tyyli, data, virhe, lahde, alku, loppu)
    fig.tight_layout()

    canvas = FigureCanvasTkAgg(fig, master=app.kuvaaja_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)


def nayta_dashboard(app, nimi):
    """Näyttää valitun dashboardin: kuvaajat ilman taulukkoa."""
    app.tree.master.pack_forget()          # piilottaa taulukon
    app.data = pd.DataFrame()
    app.dash_data = lataa_dashboard_data(DASHBOARDIT[nimi])

    # Alkaen/Päättyen-valinnat vuosina: kaikkien paneelien yhteinen aikaväli
    valinnat = [str(v) for v in sorted({
        int(v) for _o, _t, data, virhe, _l in app.dash_data if not virhe
        for v in data["Aika"].dt.year.unique()
    })]
    app.alku_combo["values"] = valinnat
    app.loppu_combo["values"] = valinnat
    app.alku_combo.config(state="readonly")
    app.loppu_combo.config(state="readonly")
    app.alku_var.set(valitse_muistettu(valinnat, app.muistettu_alku, loppu=False))
    app.loppu_var.set(valitse_muistettu(valinnat, app.muistettu_loppu, loppu=True))

    app.tila.config(text=f"Dashboard: {nimi}")
    piirra_dashboard(app)


class TilastoSovellus:
    def __init__(self, root):
        self.root = root
        self.root.title("Tilastot")
        self.root.geometry("1100x760")
        self.data = pd.DataFrame()
        self.filtered = pd.DataFrame()
        self.muistettu_alku = None      # käyttäjän valitsema aikaväli säilyy
        self.muistettu_loppu = None     # tilastosta toiseen siirryttäessä

        yla = ttk.Frame(root, padding=10)
        yla.pack(fill="x")

        ttk.Label(yla, text="Tilasto:").pack(side="left")
        self.tilasto_var = tk.StringVar(value=list(DASHBOARDIT)[0])
        self.tilasto_combo = ttk.Combobox(
            yla, textvariable=self.tilasto_var,
            values=list(DASHBOARDIT) + list(TILASTOT.keys()),
            state="readonly", width=34
        )
        self.tilasto_combo.pack(side="left", padx=(8, 18))
        self.tilasto_combo.bind("<<ComboboxSelected>>", lambda _e: self.lataa())

        ttk.Label(yla, text="Alkaen:").pack(side="left")
        self.alku_var = tk.StringVar()
        self.alku_combo = ttk.Combobox(yla, textvariable=self.alku_var, state="readonly", width=12)
        self.alku_combo.pack(side="left", padx=5)
        self.alku_combo.bind("<<ComboboxSelected>>", lambda _e: self.aika_valittu(loppu=False))

        ttk.Label(yla, text="Päättyen:").pack(side="left")
        self.loppu_var = tk.StringVar()
        self.loppu_combo = ttk.Combobox(yla, textvariable=self.loppu_var, state="readonly", width=12)
        self.loppu_combo.pack(side="left", padx=5)
        self.loppu_combo.bind("<<ComboboxSelected>>", lambda _e: self.aika_valittu(loppu=True))

        ttk.Button(yla, text="Lataa uudelleen", command=self.lataa).pack(side="left", padx=(10, 4))
        self.paivita_nappi = ttk.Button(
            yla, text="Päivitä tietokanta netistä",
            command=lambda: kaynnista_paivitys(
                self.root, self.paivita_nappi, self.tila, self.lataa
            )
        )
        self.paivita_nappi.pack(side="left", padx=4)

        self.tila = ttk.Label(root, text=f"Tietokanta: {TIETOKANTA}", padding=(10, 0, 10, 8))
        self.tila.pack(fill="x")

        self.kuvaaja_frame = ttk.Frame(root, padding=(10, 0, 10, 5))
        self.kuvaaja_frame.pack(fill="both", expand=True)

        taulukko_frame = ttk.LabelFrame(root, text="Tiedot", padding=8)
        taulukko_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tree = ttk.Treeview(taulukko_frame, show="headings")
        yscroll = ttk.Scrollbar(taulukko_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(taulukko_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        taulukko_frame.rowconfigure(0, weight=1)
        taulukko_frame.columnconfigure(0, weight=1)

        self.lataa()

    def lataa(self):
        nimi = self.tilasto_var.get()
        if nimi in DASHBOARDIT:
            nayta_dashboard(self, nimi)
            return
        palauta_tavallinen_nakyma(self)
        try:
            raaka = lue_taulutietokanta(TILASTOT[nimi])
            self.data = muodosta_pitka_data(raaka, nimi)
        except Exception as e:
            messagebox.showerror(
                "Tietojen lataus epäonnistui",
                f"{e}\n\nVarmista, että tietokanta on olemassa: {TIETOKANTA}\n"
                "Sen voi luoda painikkeella Päivitä tietokanta netistä."
            )
            return

        if self.data.empty or "Aika" not in self.data.columns:
            self.tila.config(
                text=f"{nimi}: aineiston aikarakennetta ei tunnistettu. "
                     f"Tietokannan sarakkeet: {', '.join(map(str, raaka.columns))}"
            )
            self.tyhjenna_kuvaaja()
            self.paivita_taulukko(raaka)
            return

        ajat = sorted(self.data["Aika"].dropna().dt.strftime("%Y-%m-%d").unique())
        if len(ajat) > 1500:    # päiväsarja: tarjotaan kuukausien alut
            valinnat = sorted({a[:7] + "-01" for a in ajat} | {ajat[0], ajat[-1]})
        else:
            valinnat = ajat
        self.alku_combo["values"] = valinnat
        self.loppu_combo["values"] = valinnat
        self.alku_var.set(valitse_muistettu(valinnat, self.muistettu_alku, loppu=False))
        self.loppu_var.set(valitse_muistettu(valinnat, self.muistettu_loppu, loppu=True))
        self.tila.config(text=f"{nimi} — {len(self.data)} havaintoa | Paikallinen tietokanta")
        self.paivita()

    def aika_valittu(self, loppu):
        """Muistaa käyttäjän muuttaman aikarajan seuraavia tilastoja varten.
        Ensimmäinen / viimeinen valinta tarkoittaa "alusta" / "loppuun asti"."""
        combo, var = (self.loppu_combo, self.loppu_var) if loppu else (self.alku_combo, self.alku_var)
        valinnat = list(combo["values"])
        arvo = var.get()
        if valinnat and arvo == (valinnat[-1] if loppu else valinnat[0]):
            muistettu = None
        else:
            muistettu = muista_aika(arvo, loppu)
        if loppu:
            self.muistettu_loppu = muistettu
        else:
            self.muistettu_alku = muistettu
        self.paivita()

    def paivita(self):
        if self.tilasto_var.get() in DASHBOARDIT:
            piirra_dashboard(self)
            return
        if self.data.empty or "Aika" not in self.data.columns:
            return
        alku = pd.to_datetime(self.alku_var.get(), errors="coerce")
        loppu = pd.to_datetime(self.loppu_var.get(), errors="coerce")
        if pd.isna(alku) or pd.isna(loppu):
            self.filtered = self.data.copy()
        else:
            if alku > loppu:
                alku, loppu = loppu, alku
            self.filtered = self.data[
                self.data["Aika"].between(alku, loppu + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            ].copy()
        self.piirra()
        self.paivita_taulukko(self.filtered)

    def tyhjenna_kuvaaja(self):
        for widget in self.kuvaaja_frame.winfo_children():
            widget.destroy()

    def piirra(self):
        self.tyhjenna_kuvaaja()
        if self.filtered.empty:
            ttk.Label(self.kuvaaja_frame, text="Valitulla aikavälillä ei ole tietoja.").pack()
            return

        fig = Figure(figsize=(9, 3.2), dpi=100)
        ax = fig.add_subplot(111)

        if self.tilasto_var.get() in PYLVAS_TILASTOT:
            piirra_pylvaat(ax, self.filtered)
            ax.set_ylabel("Prosenttiyksikköä")
        elif self.tilasto_var.get() in RYHMAPYLVAS_TILASTOT:
            piirra_ryhmapylvaat(ax, self.filtered)
            ax.set_ylabel("%")
        elif "Sarja" in self.filtered.columns and self.filtered["Sarja"].notna().any():
            for sarja, ryhma in self.filtered.dropna(subset=["Sarja"]).groupby("Sarja"):
                ryhma = ryhma.sort_values("Aika")
                ax.plot(ryhma["Aika"], ryhma["Arvo"], linewidth=1.2,
                    marker="o" if len(ryhma) <= 150 else None,
                    label=str(sarja))
            ax.legend()
            ax.set_ylabel("Arvo")
        else:
            ryhma = self.filtered.sort_values("Aika")
            ax.plot(ryhma["Aika"], ryhma["Arvo"], marker="o")
            ax.set_ylabel("Arvo")

        ax.set_title(self.tilasto_var.get())
        ax.set_xlabel("Ajankohta")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        # Lähde pakataan ennen kuvaajaa, jotta se pysyy näkyvissä pienessäkin ikkunassa
        lahde = tilaston_lahde(TILASTOT[self.tilasto_var.get()])
        ttk.Label(self.kuvaaja_frame, text=f"Lähde: {lahde}",
                  foreground="dimgray").pack(side="bottom", anchor="w")

        canvas = FigureCanvasTkAgg(fig, master=self.kuvaaja_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        

    def paivita_taulukko(self, data):
        self.tree.delete(*self.tree.get_children())
        columns = list(data.columns)
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=str(col))
            self.tree.column(col, width=150, minwidth=80, stretch=True)
        for _, row in data.head(1000).iterrows():
            values = []
            for value in row:
                if pd.isna(value):
                    values.append("")
                elif isinstance(value, pd.Timestamp):
                    values.append(value.strftime("%Y-%m-%d"))
                else:
                    values.append(str(value))
            self.tree.insert("", "end", values=values)


def main():
    root = tk.Tk()
    TilastoSovellus(root)
    root.mainloop()


if __name__ == "__main__":
    main()
    

    
