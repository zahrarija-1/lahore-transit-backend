from db_tools import (
    route_information,
    get_route_stops,
    get_stop_routes,
    fare_calculator,
    service_information,
    route_search
)


print("\n" + "=" * 60)
print("TEST 1: ROUTE INFORMATION")
print("=" * 60)

result = route_information("FRT09")
print(result)


print("\n" + "=" * 60)
print("TEST 2: ROUTE STOPS")
print("=" * 60)

result = get_route_stops("FRT09")
print(result)


print("\n" + "=" * 60)
print("TEST 3: STOP ROUTES")
print("=" * 60)

result = get_stop_routes("R.A. Bazar")
print(result)


print("\n" + "=" * 60)
print("TEST 4: FARE")
print("=" * 60)

result = fare_calculator(service_type="Metrobus")
print(result)


print("\n" + "=" * 60)
print("TEST 5: SERVICE INFORMATION")
print("=" * 60)

result = service_information("Metrobus")
print(result)


print("\n" + "=" * 60)
print("TEST 6: ROUTE SEARCH")
print("=" * 60)

result = route_search(
    "R.A. Bazar",
    "Chungi Amar Sidhu"
)

print(result)