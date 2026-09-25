"""Location gazetteer: name -> bounding box knowledge.

Used by the rule-based NLP layer to resolve place names from a user query into
an area-of-interest bounding box. Approximate but valid geographic extents.
"""
from __future__ import annotations


def _bb(min_lng, min_lat, max_lng, max_lat) -> dict:
    return {
        "min_lng": min_lng,
        "min_lat": min_lat,
        "max_lng": max_lng,
        "max_lat": max_lat,
    }


GAZETTEER: dict[str, dict] = {
    # ---------------- India states ----------------
    "kerala": {"name": "Kerala", "country": "India", "kind": "state", "bbox": _bb(74.8, 8.0, 77.6, 12.8)},
    "tamil nadu": {"name": "Tamil Nadu", "country": "India", "kind": "state", "bbox": _bb(76.2, 8.0, 80.4, 13.6)},
    "karnataka": {"name": "Karnataka", "country": "India", "kind": "state", "bbox": _bb(74.0, 11.6, 78.6, 18.4)},
    "maharashtra": {"name": "Maharashtra", "country": "India", "kind": "state", "bbox": _bb(72.6, 15.6, 80.9, 22.0)},
    "gujarat": {"name": "Gujarat", "country": "India", "kind": "state", "bbox": _bb(68.1, 20.0, 74.5, 24.7)},
    "punjab": {"name": "Punjab", "country": "India", "kind": "state", "bbox": _bb(73.8, 29.5, 76.9, 32.5)},
    "uttar pradesh": {"name": "Uttar Pradesh", "country": "India", "kind": "state", "bbox": _bb(77.0, 23.8, 84.6, 30.4)},
    "bihar": {"name": "Bihar", "country": "India", "kind": "state", "bbox": _bb(83.3, 24.6, 88.3, 27.6)},
    "west bengal": {"name": "West Bengal", "country": "India", "kind": "state", "bbox": _bb(85.7, 21.5, 89.9, 27.2)},
    "odisha": {"name": "Odisha", "country": "India", "kind": "state", "bbox": _bb(81.4, 17.8, 87.5, 22.6)},
    "uttarakhand": {"name": "Uttarakhand", "country": "India", "kind": "state", "bbox": _bb(77.5, 28.7, 81.0, 31.5)},
    "himachal pradesh": {"name": "Himachal Pradesh", "country": "India", "kind": "state", "bbox": _bb(75.6, 30.3, 79.2, 33.3)},
    "rajasthan": {"name": "Rajasthan", "country": "India", "kind": "state", "bbox": _bb(69.5, 23.0, 78.3, 30.2)},
    "assam": {"name": "Assam", "country": "India", "kind": "state", "bbox": _bb(89.6, 24.1, 97.4, 28.0)},
    "jharkhand": {"name": "Jharkhand", "country": "India", "kind": "state", "bbox": _bb(83.3, 21.9, 87.9, 25.3)},
    "andhra pradesh": {"name": "Andhra Pradesh", "country": "India", "kind": "state", "bbox": _bb(76.7, 12.6, 84.8, 19.9)},
    "telangana": {"name": "Telangana", "country": "India", "kind": "state", "bbox": _bb(77.2, 15.8, 81.0, 19.9)},
    "madhya pradesh": {"name": "Madhya Pradesh", "country": "India", "kind": "state", "bbox": _bb(74.0, 21.1, 82.8, 26.9)},
    "chhattisgarh": {"name": "Chhattisgarh", "country": "India", "kind": "state", "bbox": _bb(80.2, 17.8, 84.4, 24.1)},
    "haryana": {"name": "Haryana", "country": "India", "kind": "state", "bbox": _bb(74.4, 27.6, 77.6, 30.9)},
    "jammu and kashmir": {"name": "Jammu & Kashmir", "country": "India", "kind": "state", "bbox": _bb(73.5, 32.2, 80.3, 36.0)},
    "ladakh": {"name": "Ladakh", "country": "India", "kind": "state", "bbox": _bb(75.0, 31.5, 80.0, 36.0)},
    "arunachal pradesh": {"name": "Arunachal Pradesh", "country": "India", "kind": "state", "bbox": _bb(91.5, 26.6, 97.4, 29.5)},
    "nagaland": {"name": "Nagaland", "country": "India", "kind": "state", "bbox": _bb(93.3, 25.2, 95.3, 27.0)},
    "manipur": {"name": "Manipur", "country": "India", "kind": "state", "bbox": _bb(93.0, 23.8, 94.8, 25.7)},
    "mizoram": {"name": "Mizoram", "country": "India", "kind": "state", "bbox": _bb(92.2, 21.9, 93.5, 24.3)},
    "meghalaya": {"name": "Meghalaya", "country": "India", "kind": "state", "bbox": _bb(89.8, 24.9, 92.8, 26.2)},
    "tripura": {"name": "Tripura", "country": "India", "kind": "state", "bbox": _bb(91.1, 22.9, 92.3, 24.5)},
    "sikkim": {"name": "Sikkim", "country": "India", "kind": "state", "bbox": _bb(88.0, 27.0, 88.9, 28.2)},
    "goa": {"name": "Goa", "country": "India", "kind": "state", "bbox": _bb(73.7, 14.9, 74.3, 15.8)},
    "india": {"name": "India", "country": "India", "kind": "country", "bbox": _bb(67.5, 6.5, 97.5, 36.0)},
    # ---------------- India cities ----------------
    "mumbai": {"name": "Mumbai", "country": "India", "kind": "city", "bbox": _bb(72.7, 18.9, 73.0, 19.3)},
    "delhi": {"name": "Delhi NCR", "country": "India", "kind": "city", "bbox": _bb(76.8, 28.4, 77.4, 28.9)},
    "new delhi": {"name": "Delhi NCR", "country": "India", "kind": "city", "bbox": _bb(76.8, 28.4, 77.4, 28.9)},
    "chennai": {"name": "Chennai", "country": "India", "kind": "city", "bbox": _bb(80.1, 12.9, 80.4, 13.2)},
    "kolkata": {"name": "Kolkata", "country": "India", "kind": "city", "bbox": _bb(88.2, 22.4, 88.5, 22.7)},
    "bengaluru": {"name": "Bengaluru", "country": "India", "kind": "city", "bbox": _bb(77.4, 12.8, 77.8, 13.2)},
    "hyderabad": {"name": "Hyderabad", "country": "India", "kind": "city", "bbox": _bb(78.3, 17.2, 78.7, 17.6)},
    "pune": {"name": "Pune", "country": "India", "kind": "city", "bbox": _bb(73.7, 18.4, 74.0, 18.7)},
    "kochi": {"name": "Kochi", "country": "India", "kind": "city", "bbox": _bb(76.1, 9.8, 76.4, 10.1)},
    "thiruvananthapuram": {"name": "Thiruvananthapuram", "country": "India", "kind": "city", "bbox": _bb(76.8, 8.4, 77.1, 8.7)},
    "srinagar": {"name": "Srinagar", "country": "India", "kind": "city", "bbox": _bb(74.7, 34.0, 74.9, 34.2)},
    "dehradun": {"name": "Dehradun", "country": "India", "kind": "city", "bbox": _bb(77.9, 30.2, 78.2, 30.5)},
    "lucknow": {"name": "Lucknow", "country": "India", "kind": "city", "bbox": _bb(80.8, 26.7, 81.1, 27.0)},
    "patna": {"name": "Patna", "country": "India", "kind": "city", "bbox": _bb(85.0, 25.5, 85.3, 25.8)},
    "amritsar": {"name": "Amritsar", "country": "India", "kind": "city", "bbox": _bb(74.8, 31.5, 75.1, 31.8)},
# ---------------- Global ----------------
    "california": {"name": "California", "country": "USA", "kind": "state", "bbox": _bb(-124.4, 32.5, -114.1, 42.0)},
    "texas": {"name": "Texas", "country": "USA", "kind": "state", "bbox": _bb(-106.6, 25.8, -93.5, 36.5)},
    "florida": {"name": "Florida", "country": "USA", "kind": "state", "bbox": _bb(-87.6, 24.5, -80.0, 31.0)},
    "usa": {"name": "USA", "country": "USA", "kind": "country", "bbox": _bb(-125.0, 24.0, -66.9, 49.4)},
    "bangladesh": {"name": "Bangladesh", "country": "Bangladesh", "kind": "country", "bbox": _bb(88.0, 20.5, 92.7, 26.6)},
    "nepal": {"name": "Nepal", "country": "Nepal", "kind": "country", "bbox": _bb(80.0, 26.3, 88.2, 30.5)},
    "myanmar": {"name": "Myanmar", "country": "Myanmar", "kind": "country", "bbox": _bb(92.1, 9.6, 101.2, 28.5)},
    "vietnam": {"name": "Vietnam", "country": "Vietnam", "kind": "country", "bbox": _bb(102.1, 8.5, 109.5, 23.4)},
    "brazil": {"name": "Brazil", "country": "Brazil", "kind": "country", "bbox": _bb(-74.0, -33.8, -34.7, 5.3)},
    "amazon": {"name": "Amazon basin", "country": "Brazil", "kind": "region", "bbox": _bb(-74.0, -12.0, -47.0, 2.0)},
    "amazon basin": {"name": "Amazon basin", "country": "Brazil", "kind": "region", "bbox": _bb(-74.0, -12.0, -47.0, 2.0)},
    "netherlands": {"name": "Netherlands", "country": "Netherlands", "kind": "country", "bbox": _bb(3.3, 50.7, 7.3, 53.6)},
    "australia": {"name": "Australia", "country": "Australia", "kind": "country", "bbox": _bb(112.9, -43.6, 153.6, -10.7)},
    "new south wales": {"name": "New South Wales", "country": "Australia", "kind": "state", "bbox": _bb(140.9, -37.5, 153.6, -28.1)},
    "sahel": {"name": "Sahel", "country": "Africa", "kind": "region", "bbox": _bb(-17.5, 12.0, 43.0, 24.0)},
    "japan": {"name": "Japan", "country": "Japan", "kind": "country", "bbox": _bb(129.0, 30.5, 146.0, 45.5)},
    "indonesia": {"name": "Indonesia", "country": "Indonesia", "kind": "country", "bbox": _bb(95.0, -10.5, 141.0, 6.5)},
    "philippines": {"name": "Philippines", "country": "Philippines", "kind": "country", "bbox": _bb(116.9, 4.5, 126.6, 21.1)},
    "sri lanka": {"name": "Sri Lanka", "country": "Sri Lanka", "kind": "country", "bbox": _bb(79.6, 5.9, 81.9, 9.9)},
    "pacific northwest": {"name": "Pacific Northwest", "country": "USA", "kind": "region", "bbox": _bb(-124.5, 42.0, -116.5, 50.0)},
}


def resolve_location(text_lower: str) -> dict | None:
    """Find the best-known place mention in a lower-cased query."""
    best: dict | None = None
    best_len = 0
    for key, entry in GAZETTEER.items():
        if key in text_lower and len(key) > best_len:
            best = entry
            best_len = len(key)
    return best