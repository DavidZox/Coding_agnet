"""真實專案評測沒過的每一題，照「第一個出錯的地方」分層（步驟 0 的方法；新舊的 worker 都能用）。

沒過的每一項在每一層有沒有出現：工具的原文 → 事實（提煉的結果、公佈欄的事實）→ 下一層的回答（公佈欄或子工作階段的回答、中階的報告、
交給領域的結果）→ 主對話最後的回覆。每一項推第一個沒出現的層，一題取最前面的那一項：找（原文裡沒有）、看（原文有，事實與下一層的回答都沒有）、
回答・下一層（事實有，下一層的回答沒有）、回答・主對話（下一層的回答有，最後的回覆沒有）、評測或算（最後的回覆裡每一組寫法都在，核對還是沒過）。
比對用寬鬆的（每一組寫法都出現過，不管距離與同一行）。分工（交下去的子目標掉了條件、只交了一部分）程式看不出來，所以每一題也列出交給領域的
子目標與項目。推出來的類別只是起點，要逐題打開紀錄確認（設計筆記 2.44、2.45）。

    python3 evals/repo/layers.py <結果目錄>…     # 每一題一段，最後是每個模型、每一組的彙總
"""
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import checks      # noqa: E402
import questions   # noqa: E402

ORDER = ["找", "看", "回答・下一層", "回答・主對話", "評測或算", "其他"]


def _body(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if text.startswith("---\n") and "\n---\n" in text:
        text = text.split("\n---\n", 1)[1]
    return text


def _jobs(logdir, kind):
    for path in sorted(glob.glob(os.path.join(logdir, f"{kind}_jobs", "*", "job.json"))):
        with open(path, encoding="utf-8") as f:
            yield json.load(f)


def layer_texts(logdir):
    """一題的紀錄目錄（結果目錄的 logs/<題目>）→ 原文、事實、下一層的回答三段文字。交給領域的結果（`_domain_` 的 #編號）不算：
    它是下面幾層的合成（公佈欄的報告連事實一起列），各層從自己的 job 取。"""
    raw, facts, answers = [], [], []
    for path in sorted(glob.glob(os.path.join(logdir, "tool_results", "*.md"))):
        if not path.endswith("index.md") and "_domain_" not in os.path.basename(path):
            raw.append(_body(path))
    for job in _jobs(logdir, "extract"):
        fin = job.get("final") or {}
        facts.append(str(fin.get("answer") or ""))
        facts += [str(x.get("text") if isinstance(x, dict) else x) for x in fin.get("facts") or []]
    for job in _jobs(logdir, "board"):
        facts += ["\n".join([f.get("text") or ""] + list(f.get("refs") or []) + list(f.get("rows") or [])) for f in job.get("facts") or []]
        answers += [f"{a.get('item')}. {a.get('text')} " + " ".join(a.get("refs") or []) for a in job.get("answers") or []]
    for job in _jobs(logdir, "sub"):
        answers += [f"{a.get('item')}. {a.get('text')}" for a in job.get("answers") or []]
    for job in _jobs(logdir, "mid"):
        answers.append(str((job.get("result") or {}).get("report") or ""))
    return "\n".join(raw), "\n".join(facts), "\n".join(answers)


def _seen(text, item):
    return all(checks.positions(text, grp) for grp in item["all"])


def guess(raw, facts, answers, reply, item):
    """沒過的一項 → 第一個沒出現的層。"""
    if not (_seen(raw, item) or _seen(facts, item) or _seen(answers, item)):
        return "找"
    if not (_seen(facts, item) or _seen(answers, item)):
        return "看"
    if not _seen(answers, item):
        return "回答・下一層"
    if not _seen(reply, item):
        return "回答・主對話"
    return "評測或算"


def trace(result_dir, by_id=None):
    """一個結果目錄 → 沒過的每一題：模型、組、沒過的每一項推的層、這一題推的層（沒過的項目裡最前面的；沒有沒過的項目＝其他，例如寫了不該寫的）、
    交給領域的子目標與項目。"""
    by_id = by_id or {q["id"]: q for q in questions.load()["questions"]}
    out = []
    with open(os.path.join(result_dir, "runs.jsonl"), encoding="utf-8") as f:
        runs = [json.loads(line) for line in f if line.strip()]
    for r in runs:
        if r["score"]["passed"]:
            continue
        q = by_id[r["id"]]
        raw, facts, answers = layer_texts(os.path.join(result_dir, "logs", r["id"]))
        reply = r.get("reply") or ""
        items = [{"label": it["label"], "guess": guess(raw, facts, answers, reply, it)}
                 for it, s in zip(q["items"], r["score"]["items"]) if not s["ok"]]
        first = min((x["guess"] for x in items), key=ORDER.index) if items else "其他"
        dispatch = [{"domain": c.get("domain"), "goal": c.get("goal"), "items": c.get("items")} for c in r.get("tool_calls") or [] if c.get("domain")]
        out.append({"id": r["id"], "set": r["set"], "model": r.get("model"), "guess": first, "items": items, "dispatch": dispatch})
    return out


def main(dirs):
    rows, runs = [], collections.Counter()
    for d in dirs:
        traced = trace(d)
        with open(os.path.join(d, "runs.jsonl"), encoding="utf-8") as f:
            model = (json.loads(f.readline() or "{}")).get("model")
        runs[model] += 1
        for t in traced:
            print(f"❌ {t['id']}（{t['set']}，{t['model']}，{os.path.basename(d.rstrip('/'))}）→ {t['guess']}")
            for x in t["items"]:
                print(f"   - {x['label'][:70]}：{x['guess']}")
            for c in t["dispatch"]:
                print(f"   分工：{c['domain']}｜{str(c['goal'])[:100]}｜{c['items']}")
        rows += traced
    print("\n| 模型 | 組 | 幾次 | 沒過的題次 | " + " | ".join(ORDER) + " |")
    print("|---|---|---|---|" + "---|" * len(ORDER))
    for (model, sid), c in sorted(collections.Counter((t["model"], t["set"]) for t in rows).items()):
        by = collections.Counter(t["guess"] for t in rows if t["model"] == model and t["set"] == sid)
        print(f"| {model} | {sid} | {runs[model]} | {c} | " + " | ".join(str(by.get(k, 0)) for k in ORDER) + " |")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
