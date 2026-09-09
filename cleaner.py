import sys
import urllib.request
import urllib.error
import yaml
import re
import socket
import json
from concurrent.futures import ThreadPoolExecutor

# ==================================================
# ОПЦИОНАЛЬНЫЕ ПРОВЕРКИ (1 - включено, 0 - выключено)
# ==================================================
CHECK_DUPLICATES = 1  # удаление дубликатов
CHECK_PING = 0        # TCP‑проверка доступности узлов

# ==================================================
# ФИЛЬТРАЦИЯ СТРАН
# ==================================================
# 1. Если список НЕ пустой, скрипт возьмёт ТОЛЬКО эти страны (из числа доступных)
INCLUDE_ONLY_COUNTRIES = []
# 2. Список стран, которые нужно ВСЕГДА ИСКЛЮЧАТЬ (Укажите коды стран, которые не нужны)
EXCLUDE_COUNTRIES = [
    "AE",  # United Arab Emirates
    "AR",  # Argentina
    "BG",  # Bulgaria
    "CA",  # Canada
    "DK",  # Denmark
    "EE",  # Estonia
    "FI",  # Finland
    "HK",  # Hong Kong
    "IN",  # India
    "JP",  # Japan
    "KR",  # South Korea
    "KZ",  # Kazakhstan
    "LA",  # Laos
    "RU",  # Russia
    "SD",  # Sudan
    "TW",  # Taiwan
    "UA",  # Ukraine
    "ZA",  # South Africa
    "US"
]

GITHUB_TREE_URL = "https://api.github.com/repos/Au1rxx/free-vpn-subscriptions/git/trees/main?recursive=1"
BASE_URL = "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/by-country/clash-{country_code}.yaml"
PING_TIMEOUT = 3.0

COUNTRY_NAMES = {
    "AE": "United Arab Emirates", "AF": "Afghanistan", "AL": "Albania", "AR": "Argentina", 
    "AT": "Austria", "AU": "Australia", "BA": "Bosnia and Herzegovina", "BD": "Bangladesh", 
    "BE": "Belgium", "BG": "Bulgaria", "BR": "Brazil", "BY": "Belarus", "CA": "Canada", 
    "CH": "Switzerland", "CL": "Chile", "CN": "China", "CO": "Colombia", "CY": "Cyprus", 
    "CZ": "Czechia", "DE": "Germany", "DK": "Denmark", "DZ": "Algeria", "EE": "Estonia", 
    "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "United Kingdom", 
    "GE": "Georgia", "GR": "Greece", "HK": "Hong Kong", "HR": "Croatia", "HU": "Hungary", 
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IN": "India", "IQ": "Iraq", 
    "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JP": "Japan", "KE": "Kenya", 
    "KG": "Kyrgyzstan", "KR": "South Korea", "KZ": "Kazakhstan", "LA": "Laos", 
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MD": "Moldova", 
    "MK": "North Macedonia", "MM": "Myanmar", "MN": "Mongolia", "MX": "Mexico", 
    "MY": "Malaysia", "NL": "Netherlands", "NO": "Norway", "NZ": "New Zealand", 
    "PE": "Peru", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", 
    "QA": "Qatar", "RO": "Romania", "RS": "Serbia", "RU": "Russia", "SA": "Saudi Arabia", 
    "SD": "Sudan", "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia", "SK": "Slovakia", 
    "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan", "UA": "Ukraine", "US": "United States", 
    "UZ": "Uzbekistan", "VN": "Vietnam", "YE": "Yemen", "ZA": "South Africa"
}

def get_country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code.upper(), "Unknown")

def get_flag_emoji(country_code: str) -> str:
    code = country_code.upper()
    if len(code) != 2:
        return "🌐"
    return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))

def fetch_all_repo_countries() -> list[str]:
    print("[*] Сканирование репозитория для поиска всех доступных стран...")
    try:
        req = urllib.request.Request(
            GITHUB_TREE_URL, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            all_found = set()
            pattern = re.compile(r"^output/by-country/clash-([a-z2-9]{2})\.yaml$", re.IGNORECASE)
            
            for item in data.get("tree", []):
                path = item.get("path", "")
                match = pattern.match(path)
                if match:
                    all_found.add(match.group(1).upper())

            sorted_countries = sorted(list(all_found))
            print(f"[+] Всего стран в репозитории: {len(sorted_countries)}")
            return sorted_countries

    except Exception as e:
        print(f"[-] Ошибка при автоматическом получении списка стран: {e}")
        return []

def download_country_yaml(country_code: str) -> dict | None:
    code_upper = country_code.upper()
    url = BASE_URL.format(country_code=code_upper)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            return yaml.safe_load(content)
    except Exception as e:
        print(f"[-] Ошибка загрузки {code_upper}: {e}")
    return None

def is_node_alive(proxy: dict) -> bool:
    server = proxy.get("server")
    port = proxy.get("port")
    if not server or not port:
        return False
    try:
        with socket.create_connection((server, int(port)), timeout=PING_TIMEOUT):
            return True
    except Exception:
        return False

def check_proxy_worker(proxy: dict) -> dict | None:
    if is_node_alive(proxy):
        return proxy
    return None

def main():
    all_repo_countries = fetch_all_repo_countries()

    if not all_repo_countries:
        print(" ОШИБКА: Не удалось получить список доступных стран!")
        sys.exit(1)

    include_set = set(c.upper() for c in INCLUDE_ONLY_COUNTRIES)
    exclude_set = set(c.upper() for c in EXCLUDE_COUNTRIES)

    raw_proxies = []

    print("\n" + "=" * 50)
    print(" 1. ЗАГРУЗКА ИСТОЧНИКОВ")
    print("=" * 50)

    for code in all_repo_countries:
        c_name = get_country_name(code)
        
        # Проверка фильтров
        if exclude_set and code in exclude_set:
            print(f"[-] [{code}] → {c_name:<22}: Пропущена (исключена фильтром).")
            continue
        if include_set and code not in include_set:
            print(f"[-] [{code}] → {c_name:<22}: Пропущена (не входит в INCLUDE_ONLY).")
            continue

        # Загрузка
        data = download_country_yaml(code)
        if not data or "proxies" not in data or not data["proxies"]:
            print(f"[-] [{code}] → {c_name:<22}: Не удалось получить узлы.")
            continue

        count = len(data["proxies"])
        print(f"[+] [{code}] → {c_name:<22}: Загружено {count} узлов.")

        flag = get_flag_emoji(code)
        for p in data["proxies"]:
            p["_country_code"] = code
            p["_flag"] = flag
            raw_proxies.append(p)

    total_downloaded = len(raw_proxies)
    if total_downloaded == 0:
        print("\n ОШИБКА: Не удалось получить ни одного прокси!")
        sys.exit(1)

    # ==================================================
    # 2. Удаление дубликатов
    # ==================================================
    if CHECK_DUPLICATES:
        unique_proxies = []
        seen_endpoints = set()
        for p in raw_proxies:
            endpoint = (p.get("server"), p.get("port"), p.get("type"))
            if endpoint not in seen_endpoints:
                seen_endpoints.add(endpoint)
                unique_proxies.append(p)
        duplicates_removed = total_downloaded - len(unique_proxies)
    else:
        unique_proxies = raw_proxies[:]
        duplicates_removed = 0

    print("\n" + "=" * 50)
    print(" 2. ПРОВЕРКА И ФИЛЬТРАЦИЯ")
    print("=" * 50)
    print(f"• Всего скачано:          {total_downloaded}")
    print(f"• Найдено дубликатов:      {duplicates_removed}")
    print(f"• Уникальных для проверки: {len(unique_proxies)}")

    # ==================================================
    # 3. Проверка пинга
    # ==================================================
    if CHECK_PING:
        print(f"• Проверка доступности (таймаут {PING_TIMEOUT}сек)...")
        alive_proxies = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = executor.map(check_proxy_worker, unique_proxies)
            for res in results:
                if res:
                    alive_proxies.append(res)

        dead_nodes = len(unique_proxies) - len(alive_proxies)

        if not alive_proxies:
            print("\n ВНИМАНИЕ: Ни один узел не ответил. Берём первые 20 без отсева.")
            alive_proxies = unique_proxies[:20]
    else:
        alive_proxies = unique_proxies[:]
        dead_nodes = 0

    # ==================================================
    # 4. Формирование конфига
    # ==================================================
    final_proxies = []
    proxy_names = []

    for idx, p in enumerate(alive_proxies, 1):
        code = p.pop("_country_code", "")
        flag = p.pop("_flag", "🌐")
        node_type = p.get("type", "node")

        new_name = f"{flag} {code} - {node_type} {idx}"
        p["name"] = new_name

        final_proxies.append(p)
        proxy_names.append(new_name)

    final_config = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "127.0.0.1:9090",
        "proxies": final_proxies,
        "proxy-groups": [
            {
                "name": "PROXIES",
                "type": "select",
                "proxies": ["AUTO"] + proxy_names
            },
            {
                "name": "AUTO",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 100,
                "proxies": proxy_names
            }
        ],
        "rules": [
            "GEOIP,LAN,DIRECT",
            "MATCH,PROXIES"
        ]
    }

    output_filename = "clash-filtered.yaml"
    with open(output_filename, "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, sort_keys=False)

    print("\n" + "=" * 50)
    print(" 3. ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 50)
    print(f"• Исходно узлов:           {total_downloaded}")
    print(f"• Отсеяно дублей:          {duplicates_removed}")
    print(f"• Не ответили на TCP:      {dead_nodes}")
    print(f"• Сохранено в {output_filename}: {len(final_proxies)} узлов")
    print(f"\n[УСПЕХ] Файл '{output_filename}' обновлен!")

if __name__ == "__main__":
    main()
