"""
Hakee tilastoja netistä ja tallentaa ne SQLite-tietokantaan tilastot.db
(samaan kansioon kuin tämä tiedosto).

Lähteet:
  - Tilastokeskus (PxWeb-rajapinta), myös asuntosijoittajan tilastot
    (asuntojen hinnat, vuokrat, kauppamäärät, muuttoliike, asuntotuotanto,
    väestöennuste)
  - Yahoo Finance (pörssi-indeksit, yfinance-kirjasto)
  - Eurostat (inflaation alaerien kontribuutiot, 10 v valtionlainakorot)
  - Maailmanpankki (BKT:n kasvu USA, Kiina, Intia, EU)
  - FRED (Brent-raakaöljyn hinta)
  - Euroopan keskuspankki EKP (OIS-korot, 12 kk Euribor)

Käynnistys: python projekti_nolla.py
"""

import re
import sqlite3
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==================================================
# ASETUKSET
# ==================================================

TIETOKANTA = Path(__file__).resolve().parent / "tilastot.db"

# Tilastokeskuksen rajapinta sallii n. 30 kyselyä / 10 s. Kun raja ylittyy
# (429 Too Many Requests), odotetaan ja yritetään uudelleen (5, 10, 20, 40 s).
PXWEB_ISTUNTO = requests.Session()
PXWEB_ISTUNTO.mount("https://pxdata.stat.fi", HTTPAdapter(max_retries=Retry(
    total=4, status_forcelist=[429], backoff_factor=5,
    allowed_methods=None, raise_on_status=False,
)))

# --------------------------------------------------
# Tilastokeskus
# --------------------------------------------------

TILASTOT = {
    "1": {
        "nimi": "Väestö",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/vaerak/11ra.px"
        ),
        "taulu": "vaesto_11ra",
        "mittari": "Väestö",
    },
    "2": {
        "nimi": "Työttömyysaste, kausitasoitettu",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/tyti/135z.px"
        ),
        "taulu": "tyottomyysaste_135z",
        "mittari": "Työttömyysaste",
        "koodit": ["Tyottaste_kausi"],
    },
    "3": {
        "nimi": "Tehdyt työtunnit, 15–65-vuotiaat",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/tyti/13at.px"
        ),
        "taulu": "tyotunnit_13at",
        "mittari": "Työtunnit",
    },
    "4": {
        "nimi": "Tavaroiden ja palveluiden vienti",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/tpulk/12gq.px"
        ),
        "taulu": "ulkomaankauppa_12gq",
        "mittari": "Vienti",
        "kysely": [
            {
                "code": "valtio_27_20180101",
                "selection": {"filter": "item", "values": ["ULK"]},
            },
            {
                "code": "timeperiod_q",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["G", "S"]},   # Tavarat, Palvelut
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["tpulk_C"]},  # Vienti
            },
        ],
    },
    "5": {
        "nimi": "BKT:n volyymin vuosimuutos, %",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/ntp/15a9.px"
        ),
        "taulu": "bkt_15a9",
        "mittari": "BKT",
        "kysely": [
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["B1GMH"]},
            },
            {
                "code": "timeperiod_y",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["ntp-vol_muutos"]},
            },
        ],
    },
    "6": {
        "nimi": "Inflaatio (kuluttajahintaindeksin vuosimuutos, %)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/khi/122p.px"
        ),
        "taulu": "inflaatio_122p",
        "mittari": "Inflaatio",
    },
    "7": {
        "nimi": "Julkisyhteisöjen EDP-velka (sulautettu), milj. euroa",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/jyev/11yv.px"
        ),
        "taulu": "edp_velka_11yv",
        "mittari": "EDP-velka",
        "koodit": ["S13_C", "F2-F4"],
    },
    "8": {
        "nimi": "Kuluttajien luottamusindikaattori (CCI)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/kbar/11cc.px"
        ),
        "taulu": "kuluttajien_luottamus_11cc",
        "mittari": "Kuluttajien luottamus",
        "koodit": ["CCI_A1"],
    },
    "9": {
        "nimi": "Kotitalouksien velkaantumisaste, %",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/rtp/129g.px"
        ),
        "taulu": "kotitalouksien_velkaantumisaste_129g",
        "mittari": "Velkaantumisaste",
        "koodit": ["F4_B6N"],
    },
    "10": {
        "nimi": "Teollisuustuotannon volyymi-indeksi, kausitasoitettu (2021=100)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/ttvi/14mh.px"
        ),
        "taulu": "teollisuustuotanto_14mh",
        "mittari": "Teollisuustuotanto",
        "kysely": [
            {
                "code": "timeperiod_m",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "toimiala_78_20180201",
                "selection": {"filter": "item", "values": ["BTD"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["ttvi-Kausitasoitettu"]},
            },
        ],
    },
    "11": {
        "nimi": "Palvelualojen liikevaihtokuvaaja, kausitasoitettu (2021=100)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/plv/14k7.px"
        ),
        "taulu": "palvelut_liikevaihto_14k7",
        "mittari": "Palvelujen liikevaihto",
        "kysely": [
            {
                "code": "timeperiod_m",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "nace_8_20180101",
                "selection": {"filter": "item", "values": ["H_I_J_L_M_N_R_S"]},
            },
            {
                "code": "luokkaryhma_2_20180301",
                "selection": {"filter": "item", "values": ["lv"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["plv-kausitasoitettu"]},
            },
        ],
    },
    "12": {
        "nimi": "Tuotannon suhdannekuvaaja, kausitasoitettu (2015=100)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/ktkk/132f.px"
        ),
        "taulu": "tuotannon_suhdanne_132f",
        "mittari": "Tuotannon suhdanne",
        "kysely": [
            {
                "code": "timeperiod_m",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "toimiala_79_20180101",
                "selection": {"filter": "item", "values": ["SSS"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["ind_kausit_2015"]},
            },
        ],
    },
    "13": {
        "nimi": "Teollisuuden uudet tilaukset, trendi (2021=100)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/teul/14mi.px"
        ),
        "taulu": "teollisuus_tilaukset_14mi",
        "mittari": "Uudet tilaukset",
        "kysely": [
            {
                "code": "timeperiod_m",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "toimiala_17_20220818",
                "selection": {"filter": "item", "values": ["C"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["teul-Trendi"]},
            },
        ],
    },
    "14": {
        "nimi": "Väkiluvun muutos, %: Helsinki, Tampere ja Turku",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/vaerak/11ra.px"
        ),
        "taulu": "vaeston_muutos_kaupungit_11ra",
        "mittari": "Väkiluvun muutos",
        "kysely": [
            {
                "code": "alue_23_20260101",
                "selection": {"filter": "item", "values": ["KU091", "KU837", "KU853"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["kokmuutos_p"]},
            },
            {
                "code": "timeperiod_y",
                "selection": {"filter": "all", "values": ["*"]},
            },
        ],
    },
    "15": {
        "nimi": "Yksityisten kulutusmenojen volyymi, kausitasoitettu (viitevuosi 2015, milj. €)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/ntp/132h.px"
        ),
        "taulu": "yksityiset_kulutusmenot_132h",
        "mittari": "Yksityiset kulutusmenot",
        "kysely": [
            {
                "code": "timeperiod_q",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["P3KS14_S15"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["kausitvv2015"]},
            },
        ],
    },
    "16": {
        "nimi": "Kotitalouksien käytettävissä olevan nettotulon reaalinen vuosimuutos, %",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/ntp/15a9.px"
        ),
        "taulu": "kotitalouksien_kaytettava_tulo_15a9",
        "mittari": "Käytettävissä oleva tulo",
        "kysely": [
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["B6NS14"]},
            },
            {
                "code": "timeperiod_y",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["ntp-vol_muutos"]},
            },
        ],
    },
    # Sama sarja kuin Tilastokeskuksen Talouden tilannekuva -sivulla
    # ("käytettävissä olevan nettotulon reaalinen vuosimuutos"): oikaistu tulo B7N
    "17": {
        "nimi": "Kotitalouksien käytettävissä olevan nettotulon reaalinen vuosimuutos, % (neljännes)",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/ntp/15a7.px"
        ),
        "taulu": "kotitalouksien_reaalitulo_15a7",
        "mittari": "Käytettävissä oleva tulo",
        "kysely": [
            {
                "code": "sektoriluokitus_7_20230101",
                "selection": {"filter": "item", "values": ["S14"]},
            },
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["B7N"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["ntp-vol_muutos"]},
            },
            {
                "code": "timeperiod_q",
                "selection": {"filter": "all", "values": ["*"]},
            },
        ],
    },
    "18": {
        "nimi": "Kauppatase (tavarat), 12 kk liukuva summa, milj. €",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/mata/12gf.px"
        ),
        "taulu": "kauppatase_12gf",
        "mittari": "Kauppatase",
        "kysely": [
            {
                "code": "timeperiod_m",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["G"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["B12"]},
            },
        ],
    },
    "19": {
        "nimi": "Vaihtotase, 12 kk liukuva summa, milj. €",
        "api": (
            "https://pxdata.stat.fi/PxWeb/api/v1/fi/"
            "StatFin/mata/12gf.px"
        ),
        "taulu": "vaihtotase_12gf",
        "mittari": "Vaihtotase",
        "kysely": [
            {
                "code": "timeperiod_m",
                "selection": {"filter": "all", "values": ["*"]},
            },
            {
                "code": "taloustoimi_1_20180101",
                "selection": {"filter": "item", "values": ["CA"]},
            },
            {
                "code": "contentscode",
                "selection": {"filter": "item", "values": ["B12"]},
            },
        ],
    },
}

# --------------------------------------------------
# Tilastokeskus: asuntosijoittajan tilastot
# Haetaan JSON-stat2-muodossa ja tallennetaan pitkässä muodossa:
# aika (Vuosi / Neljännes / Kuukausi), Sarja, Arvo.
#
# Jokaisella tilastolla on yksi tai useampi lähde ("lahteet"):
#   aika     = aikamuuttujan koodi (haetaan koko aikasarja)
#   sarjat   = {muuttuja: {arvokoodi: sarjan nimen osa}} -> nimen osat
#              yhdistetään pilkulla; tyhjä osa jätetään pois
#   kiinteat = {muuttuja: [arvokoodit]} -> rajaukset, eivät näy sarjan nimessä
# Jos samalle ajankohdalle ja sarjalle tulee useita arvoja, käytetään
# myöhemmän lähteen / myöhemmän kiinteän koodin arvoa (oletus) tai
# lasketaan ne yhteen ("yhdista": "summa", esim. ikäryhmät).
# "ketjuta": True ketjuttaa eri perusvuoden indeksilähteet yhdeksi sarjaksi
# uusimman lähteen perusvuoteen (päällekkäisten ajankohtien keskiarvoilla).
# --------------------------------------------------

PXWEB = "https://pxdata.stat.fi/PxWeb/api/v1/fi/"

# Seurattavat kaupungit (kuntanumero: nimi). Vuokratilastossa 049 on
# "Espoo-Kauniainen", mutta nimetään yhtenäisesti Espooksi.
KAUPUNGIT = {
    "091": "Helsinki",
    "049": "Espoo",
    "092": "Vantaa",
    "837": "Tampere",
    "853": "Turku",
    "564": "Oulu",
}
KAUPUNGIT_KU = {"KU" + koodi: nimi for koodi, nimi in KAUPUNGIT.items()}

ASUNTOTILASTOT = {
    "1": {
        "nimi": "Vanhojen kerrostaloasuntojen neliöhinnat, €/m² (vuosittain)",
        "taulu": "asunnot_neliohinnat_13mx",
        "lahteet": [{
            "api": PXWEB + "StatFin/ashi/13mx.px",
            "aika": "timeperiod_y",
            "sarjat": {"kunta_1_20150101": KAUPUNGIT},
            "kiinteat": {
                "talotyyppi_5_20111209": ["3"],                 # kerrostalot
                "contentscode": ["keskihinta_aritm_nw"],
            },
        }],
    },
    "2": {
        "nimi": "Vanhojen kerrostaloasuntojen kauppojen lukumäärä (vuosittain)",
        "taulu": "asunnot_kauppamaarat_13mx",
        "lahteet": [{
            "api": PXWEB + "StatFin/ashi/13mx.px",
            "aika": "timeperiod_y",
            "sarjat": {"kunta_1_20150101": KAUPUNGIT},
            "kiinteat": {
                "talotyyppi_5_20111209": ["3"],
                # sarja vaihtuu 2020: vanha (-2019) ja uusi (2020-) yhdeksi sarjaksi
                "contentscode": ["lkm_julk19", "lkm_julk20"],
            },
        }],
    },
    "3": {
        "nimi": "Vapaarahoitteisten vuokra-asuntojen neliövuokrat, €/m²/kk (neljännesvuosittain)",
        "taulu": "asunnot_neliovuokrat",
        "lahteet": [
            {   # vanha taulukko (2015=100), 2015Q1-2025Q4, ei enää päivity
                "api": PXWEB + "StatFin_Passiivi/asvu/statfinpas_asvu_pxt_11x4_2025q4.px",
                "aika": "Vuosineljännes",
                "sarjat": {
                    "Alue": KAUPUNGIT,
                    "Huoneluku": {"00": "", "01": "yksiöt", "02": "kaksiot"},
                },
                "kiinteat": {"Rahoitusmuoto": ["1"], "Tiedot": ["keskivuokra"]},
            },
            {   # uusi taulukko (2025=100), 2025Q1-, korvaa päällekkäiset neljännekset
                "api": PXWEB + "StatFin/asvu/15fa.px",
                "aika": "timeperiod_q",
                "sarjat": {
                    "alue_44_20260101": KAUPUNGIT,
                    "huoneluku_5_20260101": {"SSS": "", "1": "yksiöt", "2": "kaksiot"},
                },
                "kiinteat": {
                    "rahoitus_2_20260101": ["1"],
                    "contentscode": ["asvu_keskineliovuokra"],
                },
            },
        ],
    },
    "4": {
        "nimi": "Kuntien välinen nettomuutto (vuosittain)",
        "taulu": "nettomuutto_11ae",
        "lahteet": [{
            "api": PXWEB + "StatFin/muutl/11ae.px",
            "aika": "timeperiod_y",
            "sarjat": {"alue_23_20260101": KAUPUNGIT_KU},
            "kiinteat": {"contentscode": ["muutl-vm43_netto"]},
        }],
    },
    "5": {
        "nimi": "Asuntotuotanto: uudet asunnot, liukuva 12 kk summa (koko maa)",
        "taulu": "asuntotuotanto_156f",
        "lahteet": [{
            "api": PXWEB + "StatFin/raku/156f.px",
            "aika": "timeperiod_m",
            "sarjat": {"rakennusvaihe_1_20250101": {
                "1": "Rakentamisluvat",
                "2": "Aloitetut",
                "3": "Valmistuneet",
            }},
            "kiinteat": {
                "alue_23_20260101": ["SSS"],                    # koko maa
                "rakennus_6_20180101": ["01"],                  # asuinrakennukset
                "contentscode": ["raku-uusiAsuntoLkm_lvs"],     # uudet asunnot, 12 kk summa
            },
        }],
    },
    "6": {
        "nimi": "Väestöennuste 2024: väkiluku 2024-2045",
        "taulu": "vaestoennuste_14wx",
        "lahteet": [{
            "api": PXWEB + "StatFin/vaenn/14wx.px",
            "aika": "timeperiod_y",
            "sarjat": {"alue_23_20240101": KAUPUNGIT_KU},
            "kiinteat": {
                "sukupuoli_9_20180101": ["SSS"],
                "ikaryhma_10_20180101": ["SSS"],
                "contentscode": ["vaesto_e24"],
            },
        }],
    },
    "7": {
        "nimi": "Väestöennuste 2024: 20-34-vuotiaat 2024-2045",
        "taulu": "vaestoennuste_20_34_14wx",
        "yhdista": "summa",                                     # ikävuodet yhteen
        "lahteet": [{
            "api": PXWEB + "StatFin/vaenn/14wx.px",
            "aika": "timeperiod_y",
            "sarjat": {"alue_23_20240101": KAUPUNGIT_KU},
            "kiinteat": {
                "sukupuoli_9_20180101": ["SSS"],
                "ikaryhma_10_20180101": [f"{ika:03d}" for ika in range(20, 35)],
                "contentscode": ["vaesto_e24"],
            },
        }],
    },
    "8": {
        "nimi": "Vanhojen kerrostaloasuntojen hintaindeksi (2025=100), kuukausittain",
        "taulu": "asunnot_hintaindeksi_kk",
        "ketjuta": True,
        "lahteet": [
            {   # 2015=100, 2015M01-2022M02, ei enää päivity
                "api": PXWEB + "StatFin_Passiivi/ashi/statfinpas_ashi_pxt_112n_2022m02.px",
                "aika": "Kuukausi",
                "sarjat": {"Alue": KAUPUNGIT},
                "kiinteat": {"Talotyyppi": ["3"], "Tiedot": ["ketjutettu_lv"]},
            },
            {   # 2020=100, 2020M01-2026M04, ei enää päivity
                "api": PXWEB + "StatFin_Passiivi/ashi/statfin_pas_13ms.px",
                "aika": "timeperiod_m",
                "sarjat": {"alue_43_20220407": KAUPUNGIT},
                "kiinteat": {
                    "talotyyppi_5_20111209": ["3"],             # kerrostalot
                    "contentscode": ["ketj_P_QA_T"],
                },
            },
            {   # 2025=100, 2025M01-, voimassa oleva taulukko
                "api": PXWEB + "StatFin/ashi/15iq.px",
                "aika": "timeperiod_m",
                "sarjat": {"alue_43_20260625": KAUPUNGIT},
                "kiinteat": {
                    "talotyyppi_5_20111209": ["3"],
                    "contentscode": ["ashivm_indeksi_2025"],
                },
            },
        ],
    },
}

# --------------------------------------------------
# Yahoo Finance
# --------------------------------------------------

PORSSIT = {
    "1": {"nimi": "S&P 500", "symboli": "^GSPC", "taulu": "sp500_yahoo"},
    "2": {"nimi": "Intia, Nifty 50", "symboli": "^NSEI", "taulu": "nifty50_yahoo"},
    "3": {"nimi": "OMX Helsinki 25", "symboli": "^OMXH25", "taulu": "omxh25_yahoo"},
    "4": {"nimi": "Kiina, Shanghai Composite", "symboli": "000001.SS", "taulu": "shanghai_yahoo"},
    # Raaka-aineet: lähimmän futuurisopimuksen hinta
    "5": {"nimi": "Kulta (USD/unssi)", "symboli": "GC=F", "taulu": "kulta_yahoo"},
    "6": {"nimi": "Kupari (USD/pauna)", "symboli": "HG=F", "taulu": "kupari_yahoo"},
    "7": {"nimi": "Maakaasu, Henry Hub (USD/MMBtu)", "symboli": "NG=F", "taulu": "maakaasu_yahoo"},
}

# --------------------------------------------------
# Eurostat
# --------------------------------------------------

EUROSTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"

EUROSTAT = {
    "1": {
        "nimi": "Inflaation alaerien kontribuutiot (euroalue, %-yksikköä)",
        "datasetti": "prc_hicp_ctr",
        "geo": "EA",
        "taulu": "inflaatio_ctrb_eurostat",
        "koodi_regex": r"^CP(?!00$)\d{2}$",   # pääryhmät CP01–CP13 (CP00 = koko inflaatio, pois)
        "alkaen": "2026-01",             # ECOICOP version 2 -luokitus alkaa 2026-01
    },
}

# ECOICOP version 2 (= UN COICOP 2018) -pääryhmät
PAARYHMIEN_NIMET = {
    "CP01": "Ruoka ja alkoholittomat juomat",
    "CP02": "Alkoholi ja tupakka",
    "CP03": "Vaatteet ja jalkineet",
    "CP04": "Asuminen ja energia",
    "CP05": "Kodin kalusteet ja laitteet",
    "CP06": "Terveys",
    "CP07": "Liikenne",
    "CP08": "Tieto ja viestintä",
    "CP09": "Vapaa-aika ja kulttuuri",
    "CP10": "Koulutus",
    "CP11": "Ravintolat ja majoitus",
    "CP12": "Vakuutus ja rahoituspalvelut",
    "CP13": "Henkilökohtainen hoito ja muut",
}

# --------------------------------------------------
# Eurostat: valmiit sarjat sellaisenaan (10 v valtionlainakorot)
# --------------------------------------------------

# EMU:n lähentymiskriteerin mukainen 10 vuoden valtionlainan korko.
# Kuukausitaulukko on voimassa; päiväsarja irt_lt_mcby_d päättyi kesäkuussa 2025.
EUROSTAT_SARJAT = {
    "1": {
        "nimi": "10 v valtionlainakorot: Suomi, Saksa, Ranska ja Italia (kuukausittain)",
        "datasetti": "irt_lt_mcby_m",
        "suodatin": {"geo": ["FI", "DE", "FR", "IT"]},
        "sarjadimensio": "geo",
        "sarjojen_nimet": {"FI": "Suomi", "DE": "Saksa", "FR": "Ranska", "IT": "Italia"},
        "taulu": "valtionlainakorot_10v_eurostat",
    },
}


# --------------------------------------------------
# FRED (St. Louisin keskuspankki): yksittäiset aikasarjat
# --------------------------------------------------

FRED_API = "https://fred.stlouisfed.org/graph/fredgraph.csv"      # ei API-avainta

FRED = {
    "1": {
        "nimi": "Brent-raakaöljyn hinta (Europe), dollaria barrelilta",
        # MCOILBRENTEU = kuukausisarja, DCOILBRENTEU = päiväsarja (lähde: U.S. EIA)
        "sarja": "MCOILBRENTEU",
        "taulu": "brent_oljy_fred",
        "sarjan_nimi": "Brent-raakaöljy, USD/barreli",
    },
}


# --------------------------------------------------
# Maailmanpankki (World Bank Open Data, ei API-avainta)
# --------------------------------------------------

WORLDBANK_API = "https://api.worldbank.org/v2/country/{maat}/indicator/{indikaattori}"

WORLDBANK = {
    "1": {
        "nimi": "BKT:n volyymin vuosimuutos, %: USA, Kiina, Intia ja EU (Maailmanpankki)",
        "indikaattori": "NY.GDP.MKTP.KD.ZG",      # BKT:n kasvu (vuosimuutos, %)
        # maakoodi (ISO3 tai aluekoodi): sarjan nimi
        "maat": {"USA": "USA", "CHN": "Kiina", "IND": "Intia", "EUU": "EU"},
        "taulu": "bkt_kasvu_maailmanpankki",
    },
}


# --------------------------------------------------
# EKP (Euroopan keskuspankki): OIS-korot
# --------------------------------------------------

EKP_API = "https://data-api.ecb.europa.eu/service/data/"

# EKP:n rahamarkkinatilasto (MMSR): euroalueen OIS-kauppojen painotetut
# keskikorot maturiteettiryhmittäin. Avaimen maturiteettikohta on jätetty
# tyhjäksi (..), jolloin haetaan kaikki maturiteetit, ja haluttu ryhmä
# valitaan sen nimen perusteella.
OIS = {
    "1": {
        "nimi": "Korot: OIS 1 kk, 1 v, 5 v ja 10 v (EKP, euroalue)",
        "taulu": "korot_ois_ekp",
        "avain": "MMSR/B.U2._X._Z.S1ZV._Z.O._X.WR._X.._Z._Z.EUR._Z",
        # sarjan nimi: maturiteettiryhmän nimi EKP:n tilastossa
        "sarjat": {
            "1 kk": "1 month",
            "1 v": "12 months",
            "5 v": "5 years",
            "10 v": "10 years",
        },
    },
}

# EKP: valmiit kuukausisarjat sellaisenaan (avain = tietokanta/sarjan avain)
EKP_SARJAT = {
    "1": {
        "nimi": "12 kk Euribor, kuukausikeskiarvo (EKP)",
        "taulu": "euribor_12kk_ekp",
        "avain": "FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA",
        "sarjan_nimi": "12 kk Euribor",
    },
}

# --------------------------------------------------
# Tilastokeskus: tavaroiden ja palveluiden vienti maittain
# Neljännekset summataan vuosiksi (vain täydet vuodet). Suurimmat maat
# valitaan viimeisen täyden vuoden mukaan; loput = "Muut maat", jolloin
# pylväiden korkeus on kokonaisvienti.
# --------------------------------------------------

VIENTIMAAT = {
    "1": {
        "nimi": "Vienti: viisi suurinta vientimaata, milj. €",
        "taulu": "vientimaat_12gq",
        "api": PXWEB + "StatFin/tpulk/12gq.px",
        "maita": 5,
    },
}


# ==================================================
# 1. TILASTOKESKUS: TAULUKON METATIEDOT
# ==================================================

def hae_taulukko(tilasto):
    """Hakee valitun taulukon metatiedot."""

    vastaus = PXWEB_ISTUNTO.get(tilasto["api"], timeout=30)
    vastaus.raise_for_status()

    taulukko = vastaus.json()

    print("\nTaulukko:", taulukko.get("title", tilasto["nimi"]))

    return taulukko


# ==================================================
# 2. TILASTOKESKUS: RAJAPINTAKYSELY
# ==================================================

def valitse_arvot(muuttuja, tilasto):
    """Valitsee alueen, ajanjakson ja mittarin metatietojen perusteella."""

    nimi = muuttuja["text"].lower()
    arvot = muuttuja["values"]
    tekstit = muuttuja.get("valueTexts", arvot)

    # Aikamuuttuja: haetaan koko saatavilla oleva aikasarja
    if muuttuja.get("time") or any(
        sana in nimi for sana in ("vuosi", "kuukausi", "neljännes", "ajankohta")
    ):
        return arvot

    # Koko Suomi, jos aluevalinta löytyy
    if "alue" in nimi:
        ehdokkaat = [
            i for i, teksti in enumerate(tekstit)
            if str(teksti).strip().lower() in ("koko maa", "koko suomi")
        ]

        if ehdokkaat:
            return [arvot[ehdokkaat[0]]]

    # Väestötaulukon mittari
    if tilasto["mittari"] == "Väestö" and "tiedot" in nimi:
        ehdokkaat = [
            i for i, teksti in enumerate(tekstit)
            if "väestö 31.12." in str(teksti).lower()
        ]

        if ehdokkaat:
            return [arvot[ehdokkaat[0]]]

    # Ikämuuttuja: pyritään valitsemaan 15–65-vuotiaat
    if "ikä" in nimi or "ikäryhmä" in nimi:
        ehdokkaat = [
            i for i, teksti in enumerate(tekstit)
            if str(teksti).strip().lower() in
            ("15-65", "15–65", "15-64", "15–64",
             "15 - 65", "15–74", "15-74")
        ]

        if ehdokkaat:
            return [arvot[ehdokkaat[0]]]

    # Mittarimuuttuja: etsitään tilaston mittaria vastaava vaihtoehto
    mittari = tilasto["mittari"].lower()

    if any(sana in nimi for sana in ("tiedot", "muuttuja", "mittari")):
        ehdokkaat = [
            i for i, teksti in enumerate(tekstit)
            if mittari in str(teksti).lower()
        ]

        if ehdokkaat:
            return [arvot[ehdokkaat[0]]]

    # Muissa muuttujissa käytetään ensimmäistä arvoa.
    return [arvot[0]]


def valitse_koodeilla(muuttuja, koodit):
    """Palauttaa ne muuttujan arvot, jotka vastaavat annettuja koodeja.
    Koodi täsmää joko arvoon itseensä tai arvon tekstin alkuun
    (esim. 'S13_C Julkisyhteisöt')."""
    arvot = muuttuja["values"]
    tekstit = muuttuja.get("valueTexts", arvot)
    osumat = []
    for arvo, teksti in zip(arvot, tekstit):
        teksti = str(teksti).strip()
        if any(arvo == k or teksti == k or teksti.startswith(k + " ") for k in koodit):
            osumat.append(arvo)
    return osumat


def muodosta_kysely(taulukko, tilasto):
    """Muodostaa valitun taulukon PxWeb-kyselyn."""

    # Valmis, käsin kirjoitettu kysely (esim. BKT)
    if "kysely" in tilasto:
        return tilasto["kysely"]

    koodit = tilasto.get("koodit", [])
    kysely = []

    for muuttuja in taulukko["variables"]:
        arvot = None

        # Aikamuuttujaa ei rajata koodeilla: haetaan koko aikasarja
        if koodit and not muuttuja.get("time"):
            osumat = valitse_koodeilla(muuttuja, koodit)
            if osumat:
                arvot = osumat

        if arvot is None:
            arvot = valitse_arvot(muuttuja, tilasto)

        kysely.append({
            "code": muuttuja["code"],
            "selection": {
                "filter": "item",
                "values": arvot
            }
        })

    return kysely


# ==================================================
# 3. TILASTOKESKUS: TILASTOLUVUT
# ==================================================

def hae_tilastot(kysely, tilasto):
    """Hakee tilastot ja palauttaa DataFrame-muodossa."""

    print("\nHaetaan tilastolukuja...")

    vastaus = PXWEB_ISTUNTO.post(
        tilasto["api"],
        json={
            "query": kysely,
            "response": {"format": "csv"}
        },
        timeout=60
    )

    vastaus.raise_for_status()

    data = pd.read_csv(
        StringIO(vastaus.content.decode("utf-8-sig")),
        sep=None,
        engine="python"
    )

    return data


# ==================================================
# 4. TALLENNUS TIETOKANTAAN
# ==================================================

def tallenna_tietokantaan(data, tilasto):
    """Tallentaa tiedot tilaston omaan tietokantatauluun."""

    if data.empty:
        print("Rajapinta ei palauttanut tilastorivejä.")
        return

    with sqlite3.connect(TIETOKANTA) as yhteys:
        data.to_sql(
            tilasto["taulu"],
            yhteys,
            if_exists="replace",
            index=False
        )

    print(f"\nTallennettiin {len(data)} riviä.")
    print("Taulu:", tilasto["taulu"])
    print("Tietokanta:", TIETOKANTA)


def hae_ja_tallenna(tilasto):
    """Hakee yhden Tilastokeskuksen tilaston ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN: {tilasto['nimi']}")
    print("=" * 50)

    taulukko = hae_taulukko(tilasto)
    kysely = muodosta_kysely(taulukko, tilasto)
    data = hae_tilastot(kysely, tilasto)

    if data.empty:
        print("Rajapinta ei palauttanut tilastorivejä.")
        return False

    tallenna_tietokantaan(data, tilasto)
    return True


# ==================================================
# 4b. TILASTOKESKUS: ASUNTOSIJOITTAJAN TILASTOT (PITKÄ MUOTO)
# ==================================================

def muodosta_asuntokysely(lahde):
    """Muodostaa PxWeb-kyselyn lähteen asetuksista: koko aikasarja,
    sarjamuuttujien arvot ja kiinteät rajaukset."""

    kysely = [{"code": lahde["aika"], "selection": {"filter": "all", "values": ["*"]}}]

    for muuttuja, nimet in lahde["sarjat"].items():
        kysely.append({"code": muuttuja,
                       "selection": {"filter": "item", "values": list(nimet)}})

    for muuttuja, koodit in lahde.get("kiinteat", {}).items():
        kysely.append({"code": muuttuja,
                       "selection": {"filter": "item", "values": list(koodit)}})

    return kysely


def hae_pxweb_lahde(lahde, jarjestys):
    """Hakee yhden PxWeb-lähteen JSON-stat2-muodossa. Palauttaa sarakkeet
    aika, Sarja, Arvo ja etusija (suurempi etusija voittaa päällekkäisissä)."""

    vastaus = PXWEB_ISTUNTO.post(
        lahde["api"],
        json={"query": muodosta_asuntokysely(lahde),
              "response": {"format": "json-stat2"}},
        timeout=120,
    )
    vastaus.raise_for_status()

    data, _kategoriat, _nimet = jsonstat_dataframe(vastaus.json())
    if data.empty:
        return data

    # Sarjan nimi: sarjamuuttujien nimet pilkulla yhdistettynä, tyhjät pois
    osat = [data[m].map(nimet).fillna(data[m]) for m, nimet in lahde["sarjat"].items()]
    sarja = osat[0]
    for osa in osat[1:]:
        sarja = sarja.where(osa == "", sarja + ", " + osa)

    # Etusija: myöhempi lähde ja myöhempi kiinteä koodi voittavat
    etusija = pd.Series(jarjestys * 1000, index=data.index)
    for muuttuja, koodit in lahde.get("kiinteat", {}).items():
        etusija = etusija + data[muuttuja].map({k: i for i, k in enumerate(koodit)})

    return pd.DataFrame({
        "aika": data[lahde["aika"]].astype(str),
        "Sarja": sarja,
        "Arvo": data["arvo"].astype(float),
        "etusija": etusija,
    })


def ketjuta_lahteet(data):
    """Ketjuttaa eri perusvuoden indeksilähteet: vanhemman lähteen sarja
    kerrotaan niin, että sen keskiarvo päällekkäisinä ajankohtina on sama
    kuin seuraavan (jo ketjutetun) lähteen. Tulos on uusimman lähteen perusvuodessa."""

    data = data.copy()
    lahde = data["etusija"] // 1000
    lahteet = sorted(lahde.unique())

    for vanha, uusi in zip(reversed(lahteet[:-1]), reversed(lahteet[1:])):
        for sarja in data.loc[lahde == vanha, "Sarja"].unique():
            v_maski = (lahde == vanha) & (data["Sarja"] == sarja)
            v = data[v_maski].set_index("aika")["Arvo"]
            u = data[(lahde == uusi) & (data["Sarja"] == sarja)].set_index("aika")["Arvo"]
            yhteiset = v.index.intersection(u.index)
            if yhteiset.empty:
                raise ValueError(f"Ketjutus: ei päällekkäisiä ajankohtia sarjalle {sarja}")
            data.loc[v_maski, "Arvo"] *= u[yhteiset].mean() / v[yhteiset].mean()

    return data


def hae_asuntotilasto(kohde):
    """Hakee asuntotilaston kaikki lähteet ja yhdistää ne yhdeksi pitkäksi
    taulukoksi: Vuosi / Neljännes / Kuukausi, Sarja, Arvo."""

    osat = [hae_pxweb_lahde(lahde, i) for i, lahde in enumerate(kohde["lahteet"])]
    osat = [osa for osa in osat if not osa.empty]
    if not osat:
        return pd.DataFrame()

    data = pd.concat(osat, ignore_index=True)

    if kohde.get("ketjuta"):
        data = ketjuta_lahteet(data)

    if kohde.get("yhdista") == "summa":
        data = data.groupby(["aika", "Sarja"], as_index=False)["Arvo"].sum()
    else:
        data = (data.sort_values("etusija", kind="stable")
                    .drop_duplicates(["aika", "Sarja"], keep="last"))

    # Aikasarakkeen nimi aikamuodon mukaan (app2 tunnistaa nämä)
    if data["aika"].str.contains("Q").any():
        aikasarake = "Neljännes"
    elif data["aika"].str.contains("M").any():
        aikasarake = "Kuukausi"
    else:
        aikasarake = "Vuosi"

    tulos = pd.DataFrame({
        aikasarake: data["aika"],
        "Sarja": data["Sarja"],
        "Arvo": data["Arvo"].round(2),
    })
    return tulos.sort_values([aikasarake, "Sarja"]).reset_index(drop=True)


def hae_ja_tallenna_asunnot(kohde):
    """Hakee asuntosijoittajan tilaston ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (asunnot): {kohde['nimi']}")
    print("=" * 50)

    data = hae_asuntotilasto(kohde)

    if data.empty:
        print("Rajapinta ei palauttanut tilastorivejä.")
        return False

    aikasarake = data.columns[0]
    for sarja, ryhma in data.groupby("Sarja"):
        print(f"  {sarja}: {ryhma[aikasarake].iloc[0]} -> {ryhma[aikasarake].iloc[-1]}, "
              f"{len(ryhma)} havaintoa")

    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 5. YAHOO FINANCE: PÖRSSIT
# ==================================================

def hae_yahoo(porssi):
    """Hakee indeksin koko historian Yahoosta ja palauttaa kuukauden
    viimeiset päätösarvot samassa muodossa kuin Tilastokeskuksen kuukausisarjat."""

    import yfinance as yf   # tuodaan tässä, ettei puuttuva kirjasto kaada muuta hakua

    sarja = yf.Ticker(porssi["symboli"]).history(
        period="max", interval="1d", auto_adjust=False
    )["Close"]

    if sarja.empty:
        return pd.DataFrame()

    sarja.index = pd.to_datetime(sarja.index).tz_localize(None)

    try:
        kk = sarja.resample("ME").last()
    except ValueError:          # vanhempi pandas
        kk = sarja.resample("M").last()
    kk = kk.dropna()

    print(f"Yahoo: {porssi['symboli']} {kk.index[0].date()} -> {kk.index[-1].date()}")

    return pd.DataFrame({
        "Kuukausi": [f"{d.year}M{d.month:02d}" for d in kk.index],
        "Sulkuarvo": kk.values.round(2),
    })


def hae_ja_tallenna_porssi(porssi):
    """Hakee yhden indeksin Yahoosta ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (Yahoo): {porssi['nimi']}")
    print("=" * 50)

    data = hae_yahoo(porssi)

    if data.empty:
        print("Yahoo ei palauttanut tietoja.")
        return False

    tallenna_tietokantaan(data, porssi)
    return True


# ==================================================
# 6. EUROSTAT: INFLAATION ALAERIEN KONTRIBUUTIOT
# ==================================================

def jsonstat_dataframe(d):
    """Muuntaa Eurostatin JSON-stat-vastauksen DataFrameksi.
    Palauttaa (data, kategoriat, nimet): data-sarakkeina dimensiot ja 'arvo',
    kategoriat = {dimensio: [koodit]}, nimet = {dimensio: {koodi: nimi}}."""

    ids = d["id"]
    koot = d["size"]

    kategoriat = {}
    nimet = {}
    for dim in ids:
        kat = d["dimension"][dim]["category"]
        idx = kat["index"]
        kategoriat[dim] = idx if isinstance(idx, list) else sorted(idx, key=idx.get)
        nimet[dim] = kat.get("label", {})

    arvot = d["value"]
    pari = arvot.items() if isinstance(arvot, dict) else enumerate(arvot)

    rivit = []
    for avain, arvo in pari:
        if arvo is None:
            continue
        n = int(avain)
        koodit = []
        for dim, koko in zip(reversed(ids), reversed(koot)):
            n, jaannos = divmod(n, koko)
            koodit.append(kategoriat[dim][jaannos])
        koodit.reverse()
        rivi = dict(zip(ids, koodit))
        rivi["arvo"] = arvo
        rivit.append(rivi)

    return pd.DataFrame(rivit), kategoriat, nimet


def hae_eurostat(kohde):
    """Hakee Eurostatin JSON-stat-taulukon ja palauttaa pääryhmien
    kontribuutiot pitkässä muodossa: Kuukausi, Sarja, Arvo."""

    vastaus = requests.get(
        EUROSTAT_API + kohde["datasetti"],
        params={"format": "JSON", "lang": "EN", "geo": kohde["geo"]},
        timeout=180,
    )
    vastaus.raise_for_status()
    d = vastaus.json()

    data, kategoriat, nimet = jsonstat_dataframe(d)
    ids = list(kategoriat)

    coicop_dim = next((x for x in ids if x.startswith("coicop")), None)
    if coicop_dim is None:
        raise ValueError(f"Luokitusdimensiota ei löytynyt. Dimensiot: {ids}")

    if data.empty:
        return data

    # Jos taulukossa on useita taajuuksia, pidetään kuukausitiedot
    if "freq" in data.columns and "M" in set(data["freq"]):
        data = data[data["freq"] == "M"]

    if "unit" in data.columns and data["unit"].nunique() > 1:
        raise ValueError(f"Taulukossa on useita yksiköitä: {sorted(data['unit'].unique())}")

    regex = re.compile(kohde["koodi_regex"])
    valitut = [k for k in kategoriat[coicop_dim] if regex.match(k)]
    if not valitut:
        raise ValueError(
            f"Koodeja ei löytynyt mallilla {kohde['koodi_regex']}. "
            f"Taulukon koodit: {kategoriat[coicop_dim][:60]}"
        )

    print("Pääryhmät:")
    for k in valitut:
        print(f"  {k} | {nimet[coicop_dim].get(k, '')}")

    data = data[data[coicop_dim].isin(valitut)]

    # Rajaus: vain annetusta kuukaudesta alkaen (esim. "2026-01")
    alkaen = kohde.get("alkaen")
    if alkaen:
        data = data[data["time"].astype(str) >= alkaen]
    if data.empty:
        raise ValueError(f"Ei tietoja ajalta {alkaen} alkaen.")

    def kuukausi(t):
        m = re.match(r"^(\d{4})-(\d{2})$", str(t))
        return f"{m.group(1)}M{m.group(2)}" if m else str(t)

    def sarjan_nimi(k):
        return PAARYHMIEN_NIMET.get(k) or nimet[coicop_dim].get(k, k)

    tulos = pd.DataFrame({
        "Kuukausi": data["time"].map(kuukausi),
        "Sarja": data[coicop_dim].map(sarjan_nimi),
        "Arvo": data["arvo"].astype(float).round(3),
    })
    return tulos.sort_values(["Kuukausi", "Sarja"]).reset_index(drop=True)


def hae_ja_tallenna_eurostat(kohde):
    """Hakee Eurostatin tilaston ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (Eurostat): {kohde['nimi']}")
    print("=" * 50)

    data = hae_eurostat(kohde)

    if data.empty:
        print("Eurostat ei palauttanut tietoja.")
        return False

    print(f"Eurostat: {data['Kuukausi'].iloc[0]} -> {data['Kuukausi'].iloc[-1]}, "
          f"sarjoja {data['Sarja'].nunique()}")
    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 6b. EUROSTAT: VALMIIT SARJAT SELLAISENAAN (EI AGGREGOINTIA)
# ==================================================

def hae_eurostat_sarjat(kohde):
    """Hakee Eurostatin JSON-stat-sarjat sellaisenaan (ei aggregointia).
    Palauttaa pitkässä muodossa: Kuukausi (tai Ajankohta päiväsarjalle), Sarja, Arvo."""

    vastaus = requests.get(
        EUROSTAT_API + kohde["datasetti"],
        params={"format": "JSON", "lang": "EN", **kohde["suodatin"]},
        timeout=180,
    )
    vastaus.raise_for_status()

    data, kategoriat, _nimet = jsonstat_dataframe(vastaus.json())
    if data.empty:
        return data

    dim = kohde["sarjadimensio"]
    nimet = kohde["sarjojen_nimet"]

    puuttuvat = [k for k in nimet if k not in set(data[dim])]
    if puuttuvat:
        print(f"Varoitus: sarjoja ei löytynyt: {puuttuvat}")

    data = data[data[dim].isin(nimet)]
    if data.empty:
        raise ValueError(f"Yhtään sarjaa ei löytynyt: {list(nimet)}")

    ajat = data["time"].astype(str)
    if ajat.str.fullmatch(r"\d{4}-\d{2}").all():
        # kuukausisarja: 2026-08 -> 2026M08 (kuten muissa kuukausisarjoissa)
        aika = ajat.str.replace(r"^(\d{4})-(\d{2})$", r"\1M\2", regex=True)
        aikasarake = "Kuukausi"
    else:
        aika, aikasarake = ajat, "Ajankohta"

    tulos = pd.DataFrame({
        aikasarake: aika,
        "Sarja": data[dim].map(nimet),
        "Arvo": data["arvo"].astype(float).round(3),
    })
    return tulos.sort_values([aikasarake, "Sarja"]).reset_index(drop=True)


def hae_ja_tallenna_eurostat_sarjat(kohde):
    """Hakee Eurostatin sarjat sellaisenaan ja tallentaa ne tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (Eurostat): {kohde['nimi']}")
    print("=" * 50)

    data = hae_eurostat_sarjat(kohde)

    if data.empty:
        print("Eurostat ei palauttanut tietoja.")
        return False

    aikasarake = data.columns[0]
    for sarja, ryhma in data.groupby("Sarja"):
        print(f"  {sarja}: {ryhma[aikasarake].iloc[0]} -> {ryhma[aikasarake].iloc[-1]}, "
              f"{len(ryhma)} havaintoa")

    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 6c. FRED: YKSITTÄISET AIKASARJAT
# ==================================================

def hae_fred(kohde):
    """Hakee yhden FRED-sarjan CSV:nä (ei API-avainta) sellaisenaan.
    Palauttaa: Kuukausi (tai Ajankohta päiväsarjalle), Sarja, Arvo."""

    vastaus = requests.get(FRED_API, params={"id": kohde["sarja"]}, timeout=60)
    vastaus.raise_for_status()

    raaka = pd.read_csv(StringIO(vastaus.text))
    if raaka.shape[1] < 2:
        raise ValueError(f"Odottamaton vastaus sarjalle {kohde['sarja']}: {list(raaka.columns)}")

    aika = pd.to_datetime(raaka.iloc[:, 0], errors="coerce")
    arvo = pd.to_numeric(raaka.iloc[:, 1], errors="coerce")     # puuttuva arvo on "."
    sarja = pd.DataFrame({"aika": aika, "arvo": arvo}).dropna()
    if sarja.empty:
        raise ValueError(f"Sarjalla {kohde['sarja']} ei ole havaintoja.")

    if (sarja["aika"].dt.day == 1).all():       # kuukausisarja
        ajat = sarja["aika"].dt.strftime("%YM%m")
        aikasarake = "Kuukausi"
    else:                                       # päiväsarja
        ajat = sarja["aika"].dt.strftime("%Y-%m-%d")
        aikasarake = "Ajankohta"

    return pd.DataFrame({
        aikasarake: ajat.values,
        "Sarja": kohde["sarjan_nimi"],
        "Arvo": sarja["arvo"].round(3).values,
    })


def hae_ja_tallenna_fred(kohde):
    """Hakee FRED-sarjan ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (FRED): {kohde['nimi']}")
    print("=" * 50)

    data = hae_fred(kohde)

    if data.empty:
        print("FRED ei palauttanut tietoja.")
        return False

    aikasarake = data.columns[0]
    print(f"FRED {kohde['sarja']}: {data[aikasarake].iloc[0]} -> {data[aikasarake].iloc[-1]}, "
          f"{len(data)} havaintoa")
    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 6d. MAAILMANPANKKI: VUOSISARJAT MAITTAIN
# ==================================================

def hae_worldbank(kohde):
    """Hakee Maailmanpankin vuosisarjat usealle maalle/alueelle yhdellä kyselyllä.
    Palauttaa pitkässä muodossa: Vuosi, Sarja, Arvo."""

    url = WORLDBANK_API.format(
        maat=";".join(kohde["maat"]), indikaattori=kohde["indikaattori"]
    )

    havainnot = []
    sivu = 1
    while True:
        vastaus = requests.get(
            url, params={"format": "json", "per_page": 1000, "page": sivu}, timeout=60
        )
        vastaus.raise_for_status()
        j = vastaus.json()

        # Virhetilanteessa Maailmanpankki palauttaa listan, jossa on vain viesti
        if not isinstance(j, list) or len(j) < 2 or j[1] is None:
            raise ValueError(f"Maailmanpankin vastaus ei kelpaa: {str(j)[:200]}")

        havainnot += j[1]
        if sivu >= int(j[0].get("pages", 1)):
            break
        sivu += 1

    rivit = []
    for h in havainnot:
        koodi = h.get("countryiso3code") or h.get("country", {}).get("id")
        if h.get("value") is None or koodi not in kohde["maat"]:
            continue                                  # ei vielä julkaistua arvoa / tuntematon maa
        rivit.append((str(h["date"]), kohde["maat"][koodi], float(h["value"])))

    if not rivit:
        raise ValueError("Maailmanpankki ei palauttanut havaintoja.")

    loydetyt = {r[1] for r in rivit}
    puuttuvat = [n for n in kohde["maat"].values() if n not in loydetyt]
    if puuttuvat:
        print(f"Varoitus: ei havaintoja: {puuttuvat}")

    data = pd.DataFrame(rivit, columns=["Vuosi", "Sarja", "Arvo"])
    data["Arvo"] = data["Arvo"].round(3)
    return data.sort_values(["Vuosi", "Sarja"]).reset_index(drop=True)


def hae_ja_tallenna_worldbank(kohde):
    """Hakee Maailmanpankin sarjat ja tallentaa ne tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (Maailmanpankki): {kohde['nimi']}")
    print("=" * 50)

    data = hae_worldbank(kohde)

    for sarja, ryhma in data.groupby("Sarja"):
        print(f"  {sarja}: {ryhma['Vuosi'].iloc[0]} -> {ryhma['Vuosi'].iloc[-1]}, "
              f"{len(ryhma)} havaintoa")

    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 7. EKP: OIS-KOROT
# ==================================================

def hae_ois(kohde):
    """Hakee OIS-korot EKP:n MMSR-tilastosta (SDMX-JSON) ja palauttaa ne
    pitkässä muodossa: Kuukausi, Sarja, Arvo. Päiväarvoista lasketaan
    kuukausikeskiarvot."""

    vastaus = requests.get(
        EKP_API + kohde["avain"], params={"format": "jsondata"}, timeout=180
    )
    vastaus.raise_for_status()
    j = vastaus.json()
    j = j.get("data", j)                      # joissain vastauksissa "data"-kääre

    dimensiot = j["structure"]["dimensions"]
    sarja_dimt = dimensiot["series"]
    aikaleimat = [v["id"] for v in dimensiot["observation"][0]["values"]]

    # Maturiteettidimensio: se, jonka arvojen nimissä on sana "bucket"
    mat_idx = next(
        (i for i, d in enumerate(sarja_dimt)
         if any("bucket" in str(v.get("name", "")).lower() for v in d["values"])),
        None,
    )
    if mat_idx is None:
        raise ValueError("Maturiteettiryhmiä ei löytynyt EKP:n vastauksesta.")

    def siisti(nimi):
        return str(nimi).lower().replace("(bucket)", "").strip()

    nimet = {siisti(v.get("name", "")): k
             for k, v in enumerate(sarja_dimt[mat_idx]["values"])}
    print("EKP:n OIS-maturiteettiryhmät:", sorted(nimet))

    sarjat = j["dataSets"][0]["series"]
    osat = []
    virheet = []

    for otsikko, haettu in kohde["sarjat"].items():
        if haettu not in nimet:
            virheet.append(f"{otsikko}: ryhmää '{haettu}' ei löydy")
            print(f"Varoitus: {virheet[-1]}")
            continue

        halutut = nimet[haettu]
        arvot = {}
        for avain, s in sarjat.items():
            if int(avain.split(":")[mat_idx]) != halutut:
                continue
            for t, o in s["observations"].items():
                if o and o[0] is not None:
                    arvot[aikaleimat[int(t)]] = float(o[0])

        sarja = pd.Series(arvot)
        if sarja.empty:
            virheet.append(f"{otsikko}: ei havaintoja")
            print(f"Varoitus: {virheet[-1]}")
            continue

        sarja.index = pd.to_datetime(sarja.index, errors="coerce")
        sarja = sarja[sarja.index.notna()]
        kk = sarja.groupby([sarja.index.year, sarja.index.month]).mean()

        (v0, k0), (v1, k1) = kk.index[0], kk.index[-1]
        print(f"EKP OIS: {otsikko}: {v0}M{k0:02d} -> {v1}M{k1:02d}")

        osat.append(pd.DataFrame({
            "Kuukausi": [f"{v}M{k:02d}" for v, k in kk.index],
            "Sarja": otsikko,
            "Arvo": kk.values.round(3),
        }))

    if not osat:
        raise ValueError("Yhtään OIS-sarjaa ei saatu: " + "; ".join(virheet))

    tulos = pd.concat(osat, ignore_index=True)
    return tulos.sort_values(["Kuukausi", "Sarja"]).reset_index(drop=True)


def hae_ja_tallenna_ois(kohde):
    """Hakee OIS-korot EKP:n rajapinnasta ja tallentaa ne tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (EKP): {kohde['nimi']}")
    print("=" * 50)

    data = hae_ois(kohde)

    if data.empty:
        print("EKP ei palauttanut tietoja.")
        return False

    tallenna_tietokantaan(data, kohde)
    return True


def hae_ekp_sarja(kohde):
    """Hakee yhden EKP:n kuukausisarjan CSV:nä. Palauttaa: Kuukausi, Sarja, Arvo."""

    vastaus = requests.get(
        EKP_API + kohde["avain"], params={"format": "csvdata"}, timeout=60
    )
    vastaus.raise_for_status()

    raaka = pd.read_csv(StringIO(vastaus.text))
    sarja = raaka[["TIME_PERIOD", "OBS_VALUE"]].dropna()
    if sarja.empty:
        raise ValueError(f"Sarjalla {kohde['avain']} ei ole havaintoja.")

    return pd.DataFrame({
        # 2026-09 -> 2026M09 (kuten muissa kuukausisarjoissa)
        "Kuukausi": sarja["TIME_PERIOD"].str.replace(r"^(\d{4})-(\d{2})$", r"\1M\2", regex=True),
        "Sarja": kohde["sarjan_nimi"],
        "Arvo": sarja["OBS_VALUE"].astype(float).round(3),
    }).reset_index(drop=True)


def hae_ja_tallenna_ekp_sarja(kohde):
    """Hakee EKP:n sarjan ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (EKP): {kohde['nimi']}")
    print("=" * 50)

    data = hae_ekp_sarja(kohde)

    print(f"EKP {kohde['sarjan_nimi']}: {data['Kuukausi'].iloc[0]} -> "
          f"{data['Kuukausi'].iloc[-1]}, {len(data)} havaintoa")
    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 7b. TILASTOKESKUS: VIENTI MAITTAIN
# ==================================================

def hae_vientimaat(kohde):
    """Hakee viennin maittain ja laskee vuosisummat suurimmille maille
    ja muille maille. Palauttaa: Vuosi, Sarja, Arvo."""

    kysely = [
        {"code": "valtio_27_20180101", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "timeperiod_q", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "taloustoimi_1_20180101", "selection": {"filter": "item", "values": ["GS"]}},
        {"code": "contentscode", "selection": {"filter": "item", "values": ["tpulk_C"]}},
    ]
    vastaus = PXWEB_ISTUNTO.post(
        kohde["api"],
        json={"query": kysely, "response": {"format": "json-stat2"}},
        timeout=60
    )
    vastaus.raise_for_status()

    data, _kategoriat, nimet = jsonstat_dataframe(vastaus.json())
    data = data.rename(columns={"valtio_27_20180101": "maa"})
    data["Vuosi"] = data["timeperiod_q"].str[:4]

    # Vain täydet vuodet (kaikki neljä neljännestä)
    taydet = data.groupby("Vuosi")["timeperiod_q"].nunique()
    data = data[data["Vuosi"].isin(taydet[taydet == 4].index)]
    vuodet = data.groupby(["Vuosi", "maa"], as_index=False)["arvo"].sum()

    # Yksittäiset maat ovat numerokoodeja (esim. 840), alueet kirjainkoodeja
    maat = vuodet[vuodet["maa"].str.fullmatch(r"\d{3}")]
    viimeisin = maat["Vuosi"].max()
    suurimmat = (maat[maat["Vuosi"] == viimeisin]
                 .nlargest(kohde["maita"], "arvo")["maa"].tolist())

    leveä = vuodet.pivot(index="Vuosi", columns="maa", values="arvo")
    tulos = leveä[suurimmat].rename(columns=nimet["valtio_27_20180101"])
    tulos["Muut maat"] = leveä["ULK"] - leveä[suurimmat].sum(axis=1)

    return (tulos.reset_index()
                 .melt(id_vars="Vuosi", var_name="Sarja", value_name="Arvo")
                 .dropna(subset=["Arvo"]))


def hae_ja_tallenna_vientimaat(kohde):
    """Hakee viennin maittain ja tallentaa sen tietokantaan."""

    print("\n" + "=" * 50)
    print(f"HAETAAN (Tilastokeskus): {kohde['nimi']}")
    print("=" * 50)

    data = hae_vientimaat(kohde)

    print(f"Maat: {', '.join(m for m in data['Sarja'].unique() if m != 'Muut maat')}; "
          f"{data['Vuosi'].min()} -> {data['Vuosi'].max()}")
    tallenna_tietokantaan(data, kohde)
    return True


# ==================================================
# 8. OHJELMAN PÄÄTOIMINTO
# ==================================================

def main():
    """Hakee kaikki tilastot ja tallentaa ne tietokantaan."""

    tyot = (
        [(t["nimi"], hae_ja_tallenna, t) for t in TILASTOT.values()]
        + [(a["nimi"], hae_ja_tallenna_asunnot, a) for a in ASUNTOTILASTOT.values()]
        + [(p["nimi"], hae_ja_tallenna_porssi, p) for p in PORSSIT.values()]
        + [(e["nimi"], hae_ja_tallenna_eurostat, e) for e in EUROSTAT.values()]
        + [(e["nimi"], hae_ja_tallenna_eurostat_sarjat, e) for e in EUROSTAT_SARJAT.values()]
        + [(w["nimi"], hae_ja_tallenna_worldbank, w) for w in WORLDBANK.values()]
        + [(f["nimi"], hae_ja_tallenna_fred, f) for f in FRED.values()]
        + [(o["nimi"], hae_ja_tallenna_ois, o) for o in OIS.values()]
        + [(e["nimi"], hae_ja_tallenna_ekp_sarja, e) for e in EKP_SARJAT.values()]
        + [(v["nimi"], hae_ja_tallenna_vientimaat, v) for v in VIENTIMAAT.values()]
    )

    onnistuneet = []
    epaonnistuneet = []

    for nimi, funktio, kohde in tyot:
        try:
            if funktio(kohde):
                onnistuneet.append(nimi)
            else:
                epaonnistuneet.append(f"{nimi}: ei rivejä")

        except requests.RequestException as e:
            epaonnistuneet.append(f"{nimi}: rajapintahaku epäonnistui ({e})")

        except (KeyError, ValueError, IndexError) as e:
            epaonnistuneet.append(f"{nimi}: tietojen käsittely epäonnistui ({e})")

        except sqlite3.Error as e:
            epaonnistuneet.append(f"{nimi}: tietokantavirhe ({e})")

        except Exception as e:      # esim. yfinance-virheet
            epaonnistuneet.append(f"{nimi}: virhe ({e})")

    print("\n" + "=" * 50)
    print("YHTEENVETO")
    print("=" * 50)
    print("Tallennettu:", ", ".join(onnistuneet) or "ei mitään")

    if epaonnistuneet:
        print("\nEpäonnistui:")
        for rivi in epaonnistuneet:
            print(" -", rivi)

    return 1 if epaonnistuneet else 0


if __name__ == "__main__":
    sys.exit(main())