"""Coordinates the OSM place extract does not hold, geocoded one at a time.

Everything here is either not tagged as a `place` at all -- a hippodrome, a mall,
an island, an expo centre -- or missing from the extract for reasons of its own.
Нивки and Березняки are the second kind and the ones that mattered: real Kyiv
districts, 200 and 60 mentions, and the only OSM places of those names in the
whole oblast are villages 90 km away.

Each entry carries the OSM object it came from, so it can be checked rather than
believed. Two were dropped on inspection instead of being written down:

- **Десна** was the only one dropped: Nominatim answered with a street in Litky,
  20 km from the town.

Антонов needed him to say what it is -- "це завод ім. Антонова, на Святошині" --
and then it geocodes exactly, to the serial plant on vulytsia Mrii. The queries I
tried first ("Завод Антонова", the English name, the airfield) all returned
nothing, which is the ordinary way local knowledge beats a search string.

And four have no point by nature: Правий берег and Лівий берег are halves of a
city, Київщина is the oblast, Водосховище is a reservoir 60 km long. A radius
should not pretend otherwise, so they stay without coordinates and the caller has
to cope with `None`.
"""

HAND: dict[str, tuple[float, float, str]] = {
    "Нивки": (50.47016, 30.40931, "n2189566461"),
    "Березняки": (50.42874, 30.60420, "n2189566459"),
    "Іподром": (50.37553, 30.46039, "w436160459"),      # пр. Глушкова, 10
    "Труханів": (50.48522, 30.54840, "r20109338"),
    "Виставковий центр": (50.38250, 30.47758, "n5267955453"),   # ВДНГ
    "Республіка": (50.37345, 30.44603, "w293888317"),   # Кільцева, Теремки-II
    "Антонов": (50.45917, 30.39592, "n2706632496"),     # завод, вул. Мрії
    # Landmarks the channels use as origins -- "Реактивний з ТЕЦ-5 на Жуляни" is
    # a bearing, not a place name. Each checked against what this gazetteer
    # already said about it: ТЕЦ-5 Holosiiv, ТЕЦ-6 Troieshchyna, ТЕЦ-2 Darnytsia,
    # Lavina by Vynohradar.
    "ТЕЦ-5": (50.39423, 30.56838, "r6674937"),
    "ТЕЦ-6": (50.53123, 30.66698, "w106296381"),
    "ТЕЦ-2": (50.44796, 30.63725, "n11443564769"),
    "Лавіна": (50.49553, 30.36058, "w446901282"),
    "Вокзал": (50.44019, 30.48901, "n440084976"),       # Київ-Пасажирський
    "Десна": (50.92478, 30.77298, "w167051677"),        # 59 км, Броварський бік
}

# Six names stay without a point, and each for a reason a radius has to respect.
# This is the whole argument for the radius being an overlay rather than a
# replacement: these keep the tier the gazetteer gave them by hand.
#
#   Київщина    1083 mentions -- the oblast itself, not a place in it
#   Водосховище  153 -- a reservoir sixty kilometres long
#   Правий берег  32 -- half a city
#   Проспект       9 -- a mall; Nominatim answered with ТРЦ СкайМолл on another
#                        avenue, and a wrong point is worse than none, because
#                        the radius would act on it
#   Кільцева       6 -- a road thirty kilometres long
#   Києво-Святошинський район 1 -- an administrative district, since abolished
WITHOUT_POINT = ("Київщина", "Водосховище", "Правий берег", "Проспект",
                 "Кільцева", "Києво-Святошинський район")
