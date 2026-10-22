import requests
import json

url = "https://api.hoyodecrimen.com/api/v1/cuadrantes/N-1.4.7/crimes/all/series"

response = requests.get(url, timeout=60)

print("Status:", response.status_code)

data = response.json()

print("\nTop-level keys:")
print(data.keys())

rows = data.get("rows", [])

print("\nNumber of rows:")
print(len(rows))

print("\nFirst row:")
print(json.dumps(rows[0], indent=2, ensure_ascii=False))

print("\nFirst row keys:")
print(rows[0].keys())
