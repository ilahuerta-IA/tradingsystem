"""Temporary helper: fetch full SP500 ticker list from Wikipedia."""
import requests
from lxml import html

url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)
tree = html.fromstring(r.content)
tables = tree.xpath("//table[contains(@class, 'wikitable')]")
print(f"Found {len(tables)} wikitables")

if tables:
    rows = tables[0].xpath(".//tr")[1:]
    tickers = []
    for row in rows:
        cells = row.xpath(".//td")
        if cells:
            ticker = cells[0].text_content().strip()
            tickers.append(ticker.replace(".", "-"))
    tickers.sort()
    print(f"Total SP500 tickers: {len(tickers)}")
    # Print as Python list for copy-paste
    for i in range(0, len(tickers), 10):
        chunk = tickers[i:i+10]
        line = ", ".join(f"'{t}'" for t in chunk)
        print(f"    {line},")
