import requests

BASE_URL = "https://api.hoyodecrimen.com/api/v1"

def main():
    crimes = requests.get(f"{BASE_URL}/crimes", timeout=30)
    crimes.raise_for_status()

    cuadrantes = requests.get(f"{BASE_URL}/cuadrantes", timeout=30)
    cuadrantes.raise_for_status()

    print("Crime endpoint status:", crimes.status_code)
    print("Cuadrante endpoint status:", cuadrantes.status_code)

    print("\nCrime response preview:")
    print(str(crimes.json())[:1000])

    print("\nCuadrante response preview:")
    print(str(cuadrantes.json())[:1000])

if __name__ == "__main__":
    main()
