"""State -> TSO control area ("grid zone") for the map. The zone is the DOMINANT one; states that other sources list under more than one TSO are flagged as split.
Sources (details in data/DATA_SOURCES.md):
 [WD]  Deutscher Bundestag, Wissenschaftliche Dienste, WD 5 - 3000 - 117/16 (2017), section 2 "Stromnetzstruktur" (quotes netztransparenz.de and the ewi Energy Research & Scenarios study).
 [SMARD] SMARD "Control area" article, https://www.smard.de/page/en/wiki-article/5884/205642
The sources are qualitative; no source gives area or load shares, so 'dominant' is a judgement."""
STATES = {  # BKG 2-digit state key -> (ISO 3166-2 code, German name, dominant zone, other TSOs that also serve part of the state per [WD]/ewi)
    "01": ("SH", "Schleswig-Holstein", "TenneT", []),
    "02": ("HH", "Hamburg", "50Hertz", []),
    "03": ("NI", "Niedersachsen", "TenneT", ["Amprion"]),
    "04": ("HB", "Bremen", "TenneT", []),
    "05": ("NW", "Nordrhein-Westfalen", "Amprion", ["TenneT"]),
    "06": ("HE", "Hessen", "TenneT", ["Amprion"]),
    "07": ("RP", "Rheinland-Pfalz", "Amprion", []),
    "08": ("BW", "Baden-Württemberg", "TransnetBW", ["Amprion"]),
    "09": ("BY", "Bayern", "TenneT", ["Amprion"]),
    "10": ("SL", "Saarland", "Amprion", []),
    "11": ("BE", "Berlin", "50Hertz", []),
    "12": ("BB", "Brandenburg", "50Hertz", []),
    "13": ("MV", "Mecklenburg-Vorpommern", "50Hertz", []),
    "14": ("SN", "Sachsen", "50Hertz", []),
    "15": ("ST", "Sachsen-Anhalt", "50Hertz", []),
    "16": ("TH", "Thüringen", "50Hertz", []),
}
