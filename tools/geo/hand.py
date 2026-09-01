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
}
