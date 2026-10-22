# -*- coding: utf-8 -*-
"""
══════════════════════════════════════════════════════════════════════
 ZEEGY BOX — بناء الكتالوج الثابت (يعمل في GitHub Actions — Azure مسموح ✓)

 كل تنفيذ:
   ① يحدّث الرئيسة + التصنيفات + صفحات كل تصنيف
   ② يضيف العناصر الجديدة (تفاصيل + ملفات كل حلقة) بحدّ ميزانية
   ③ يعيد بناء فهرس البحث
   ④ يدفع التغييرات إلى هذا المستودع (push)

 العناصر القديمة تبقى من آخر زحف (قابل لإكمال تلقائي: كل جولة تعالج
 المفقود أولاً حتى ينحصر الاشتغال بالجديد فقط) ✓
 ══════════════════════════════════════════════════════════════════════
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://cinema.albox.co/api/v4"
UA = {
    "App-Version": "1.14.8",
    "Device-Store": "web",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/122 Mobile Safari/537.36",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATE_PATH = os.path.join(DATA_DIR, ".state.json")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")

MAX_PAGES_PER_CATEGORY = 250      # حد المصدر الرسمي
BACKFILL_BUDGET = int(os.environ.get("CATALOG_BUDGET", "2400"))
WORKERS = int(os.environ.get("CATALOG_WORKERS", "6"))
REQ_DELAY = float(os.environ.get("CATALOG_DELAY", "0.10"))  # عناية بالسيرفر

_lock = threading.Lock()
_req_gate = [0.0]


def fetch(path, tries=3):
    """JSON GET مع مهلة وإعادة — شامل قفل معدل الطلب"""
    for t in range(tries):
        with _lock:
            wait = _req_gate[0] - time.time()
            if wait > 0:
                time.sleep(wait)
            _req_gate[0] = time.time() + REQ_DELAY
        try:
            with urllib.request.urlopen(
                urllib.request.Request(API + path, headers=UA), timeout=45
            ) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            if e.code in (403, 429):
                time.sleep(2 + t * 3)
                continue
            time.sleep(1 + t)
        except Exception:
            time.sleep(1 + t)
    return None


def item_hash(it):
    """بصمة العنصر (العنوان + الصورة) لكشف التغيّرات بلا زحف"""
    return hashlib.sha1(
        json.dumps(
            [it.get("title"), (it.get("style") or {}).get("image")],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def save_json(rel, obj):
    path = os.path.join(DATA_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    data = text.encode("utf-8")
    if os.path.exists(path):
        with open(path, "rb") as f:
            if f.read() == data:
                return False          # بلا تغيير
    with open(path, "wb") as f:
        f.write(data)
    return True


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"shows": {}, "eps": {}, "items": {}}


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    state = load_state()
    shows_state = state.setdefault("shows", {})
    items_state = state.setdefault("items", {})
    changed_files = 0

    # ═══① الرئيسة ═══
    home = fetch("/home")
    if home and save_json("home.json", home):
        changed_files += 1
    print("✔ الرئيسة")

    # ═══② التصنيفات ═══
    cats = fetch("/categories/more")
    flat = []

    def flatten(nodes):
        for c in nodes or []:
            if c and c.get("id"):
                flat.append(c)
            flatten(c.get("subcategories"))

    if cats:
        flatten(cats.get("categories"))
        if save_json("categories.json", cats):
            changed_files += 1
    print("✔ التصنيفات:", len(flat))

    # ═══③ صفحات كل تصنيف + كشف الكون ═══
    universe = {}    # id -> العنصر الكامل كما يعيده المصدر
    shards = {}      # cid -> {id -> item} فهرس بصيغة شظايا
    page_jobs = []

    for c in flat:
        cid = c["id"]
        try:
            q = urllib.parse.urlencode({"term": "", "category_id": cid, "page_number": 1, "page_size": 40})
            first = fetch("/search?" + q)
        except Exception:
            continue
        if not first:
            continue
        tp = min(int(first.get("pagination", {}).get("total_pages", 1) or 1), MAX_PAGES_PER_CATEGORY)
        page_jobs.append((cid, 1, first))
        for p in range(2, tp + 1):
            page_jobs.append((cid, p, None))

    def index_items(d, cid=None):
        for it in (d.get("results") or []):
            if it and it.get("id"):
                try:
                    iid = int(it["id"])
                except (TypeError, ValueError):
                    continue
                universe[iid] = it
                if cid is not None:
                    shards.setdefault(str(cid), {})[iid] = it

    def save_cat_page(cid, page, data):
        if data is None:
            return
        index_items(data, cid)
        key = f"cat/{cid}-{page}.json"
        if save_json(key, data):
            return 1
        return 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = []
        for cid, page, data in page_jobs:
            if data is not None:
                futs.append(pool.submit(save_cat_page, cid, page, data))
            else:
                def job(cid=cid, page=page):
                    q = urllib.parse.urlencode({"term": "", "category_id": cid, "page_number": page, "page_size": 40})
                    return save_cat_page(cid, page, fetch("/search?" + q))
                futs.append(pool.submit(job))
        for fut in as_completed(futs):
            try:
                changed_files += fut.result() or 0
            except Exception:
                pass
    print("✔ صفحات التصنيفات:", len(page_jobs), "| عناصر معلومة:", len(universe))

    # ═══④ عناصر جديدة أو متغيّرة ═══
    new_ids = []
    for iid, it in universe.items():
        s = shows_state.get(str(iid))
        if s is None or s.get("h") != item_hash(it):
            new_ids.append(iid)
    print("جديد/متغيّر يحتاج زحف:", len(new_ids))

    def backfill(iid):
        it = universe.get(iid) or {}
        typ = str(it.get("type") or "")
        try:
            qs = f"?type={typ}" if typ else ""
            det = fetch(f"/shows/shows/dynamic/{iid}{qs}")
            if det is None:
                return None
            # مسارات الحلقات: تعمّق الوصول
            eps = []

            def walk_eps(o, d=0):
                if d > 7 or len(eps) > 400:
                    return
                if isinstance(o, dict):
                    if str(o.get("type") or "").lower() == "episode" and o.get("id"):
                        try:
                            eps.append(int(o["id"]))
                        except (TypeError, ValueError):
                            pass
                    if o.get("episode_id"):
                        try:
                            eps.append(int(o["episode_id"]))
                        except (TypeError, ValueError):
                            pass
                    for v in o.values():
                        walk_eps(v, d + 1)
                elif isinstance(o, list):
                    for x in o:
                        walk_eps(x, d + 1)

            walk_eps(det)
            eps = list(dict.fromkeys(eps))
            save_json(f"show/{iid}.json", det)
            for eid in eps:
                files = fetch(f"/shows/episodes/{eid}/files")
                if files is not None:
                    save_json(f"ep/{eid}.json", files)
            return {"h": item_hash(it), "ep": eps, "at": int(time.time())}
        except Exception:
            return None

    budget = min(len(new_ids), BACKFILL_BUDGET)
    done = 0
    if budget:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(backfill, iid): iid for iid in new_ids[:budget]}
            for fut in as_completed(futs):
                iid = futs[fut]
                try:
                    res = fut.result()
                    if res:
                        shows_state[str(iid)] = res
                        done += 1
                except Exception:
                    pass
                if done % 100 == 0 and done:
                    print(f"  … زحف {done}/{budget}")
    print(f"✔ زحف تفاصيل: {done}")

    # ═══⑤ فهرس البحث (شظايا لكل تصنيف — يتغيّر الجزئي فقط كل جولة) ═══
    try:
        total_idx = 0
        for cid, items in shards.items():
            lst = sorted(items.values(), key=lambda x: x["id"])
            total_idx += len(lst)
            if save_json(f"index/{cid}.json", lst):
                changed_files += 1
        # قائمة الشظايا (ترتيب ثابت حسب أرقام التصنيفات)
        cat_ids = sorted({str(c["id"]) for c in flat}, key=lambda s: int(s))
        extra = [c for c in shards if c not in cat_ids]
        if save_json("index/list.json", {"shards": cat_ids + sorted(extra, key=int)}):
            changed_files += 1
        print("✔ الفهرس:", total_idx, "عنصراً في", len(shards), "شظية")
    except Exception as e:
        print("⚠ فهرس:", e)

    # ═══⑥ الحالة ═══
    state["items"] = {
        str(i): (universe.get(i) or {}).get("title", "")
        for i in list(universe)[:50000]
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
    print("✔ الحالة:", len(shows_state), "عمل")

    print()
    print(f"ملفات متغيّرة هذه الجولة: {changed_files}")


if __name__ == "__main__":
    main()
