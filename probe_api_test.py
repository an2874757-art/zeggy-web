# -*- coding: utf-8 -*-
"""اختبار وصول المصدر من داخل GitHub Actions (تشخيص الحظر)"""
import json
import sys
import urllib.request
import urllib.error

def probe(path):
    req = urllib.request.Request(
        "https://cinema.albox.co/api/v4" + path,
        headers={
            "App-Version": "1.14.8",
            "Device-Store": "web",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) Chrome/122 Mobile Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, (e.read()[:180] or b"")
    except Exception as e:
        return "ERR", str(e)[:180]


print("IP:", urllib.request.urlopen("https://api.ipify.org", timeout=15).read().decode())
print("home:", probe("/home"))
print("cats:", probe("/categories/more"))
print("search:", probe("/search?term=&category_id=18&page_number=1&page_size=40"))
