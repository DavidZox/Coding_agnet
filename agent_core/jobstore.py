"""JobStore：一次多步驟工作的存檔（工具回傳的提煉、數據分析；之後的任務引擎也用這一套）。

每一次工作一個資料夾 logs/<種類>/<編號>/：
- job.json：狀態與結果（原子寫入：先寫 .tmp 再換名，讀的人不會讀到寫一半的檔）；
- events.jsonl：進度（每一行一個事件，含時間）；
- calls.jsonl：每次模型呼叫的輸入與輸出（system／user prompt、模型的原文、解析後的結果、程式核對的結果、耗時）；
- 其他產物：報告、提煉結果…（write）。
編號是時間（YYYYmmdd_HHMMSS，同一秒有兩個就加 _2），可以帶一個後綴（例如 recall_12）。中間產物與最終產物都在同一個資料夾，
事後可以照著 calls.jsonl 重看每一步看到什麼、寫了什麼、程式擋掉了什麼。"""
import json
import os
import shutil
import time


class JobStore:

    def __init__(self, root):
        self.root = root

    def path(self, jid, rel=""):
        return os.path.join(self.root, jid, rel) if rel else os.path.join(self.root, jid)

    def new_id(self, suffix=""):
        """建一個新的工作資料夾，回傳編號（同一秒裡、不同執行緒同時建也不會重複）。"""
        os.makedirs(self.root, exist_ok=True)
        base = time.strftime("%Y%m%d_%H%M%S") + (f"_{suffix}" if suffix else "")
        jid, n = base, 1
        while True:
            try:
                os.makedirs(self.path(jid))
                return jid
            except FileExistsError:
                n += 1
                jid = f"{base}_{n}"

    def save(self, job):
        """job.json（job["id"] 是編號）。"""
        d = self.path(job["id"])
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "job.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, os.path.join(d, "job.json"))

    def write(self, jid, rel, text):
        p = self.path(jid, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def append(self, jid, name, record):
        """jsonl 追加一行（events.jsonl、calls.jsonl）；沒有 ts 就補上。寫不進去不影響工作本身。"""
        rec = dict(record)
        rec.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            os.makedirs(self.path(jid), exist_ok=True)
            with open(self.path(jid, name), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    def load(self, jid):
        try:
            with open(self.path(jid, "job.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def read_jsonl(self, jid, name):
        out = []
        try:
            with open(self.path(jid, name), encoding="utf-8") as f:
                for ln in f:
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        continue
        except OSError:
            pass
        return out

    def ids(self):
        """全部的編號（舊→新）。"""
        try:
            return sorted(n for n in os.listdir(self.root) if os.path.isfile(self.path(n, "job.json")))
        except OSError:
            return []

    def recent(self, n=20):
        """最近 n 個工作的 job.json（新→舊）。"""
        out = []
        for jid in reversed(self.ids()):
            job = self.load(jid)
            if job:
                out.append(job)
            if len(out) >= n:
                break
        return out

    def mark_interrupted(self, active, stale_minutes=30, status="interrupted", explain=None):
        """啟動時：狀態還是進行中（active 裡的狀態）、但 events.jsonl 超過 stale_minutes 沒有更新的工作，是上一次程式在做完之前結束了
        ——改成 status（explain(job) 回傳的說明記在 error），畫面才不會一直顯示「進行中」。回傳改了幾個。"""
        changed = 0
        now = time.time()
        for jid in self.ids():
            job = self.load(jid)
            if not job or job.get("status") not in active:
                continue
            ev = self.path(jid, "events.jsonl")
            last = os.path.getmtime(ev) if os.path.exists(ev) else os.path.getmtime(self.path(jid, "job.json"))
            if now - last < stale_minutes * 60:
                continue
            if explain:
                job["error"] = explain(job)
            job["status"], job["updated"] = status, time.strftime("%Y-%m-%d %H:%M:%S")
            job.setdefault("id", jid)
            try:
                self.save(job)
                changed += 1
            except OSError:
                continue
        return changed

    def prune(self, keep):
        """只留最近 keep 個工作資料夾（刪最舊的）；回傳刪掉的編號。"""
        ids = self.ids()
        removed = ids[:max(0, len(ids) - keep)] if keep > 0 else []
        for jid in removed:
            shutil.rmtree(self.path(jid), ignore_errors=True)
        return removed
