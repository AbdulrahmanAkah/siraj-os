from core.entities import Person, Place, Event

person = Person(
    name="Muhammad",
    arabic_name="محمد ﷺ"
)

place = Place(
    name="Makkah",
    arabic_name="مكة"
)

event = Event(
    name="Battle of Badr",
    arabic_name="غزوة بدر"
)

print(person.to_dict())
print(place.to_dict())
print(event.to_dict())