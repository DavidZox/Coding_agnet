"""量測 Ollama 的 think 參數對三個模型的實際效果（評估報告的 thinking 建議用）：每個模型 × think=true／false × 5 個提示，記錄
有沒有思考內容（message.thinking）、思考與回答的 token 數、耗時、回答對不對；不支援 thinking 的模型送 true 時記錄錯誤訊息。
用跟 harness 一樣的設定（format=JSON schema、temperature 0.2、num_ctx 32768）。

    OLLAMA_HOST=127.0.0.1:11435 python3 benchmark_study_2/analysis/think_probe.py
結果：results/raw/think_probe/results.json 與 results/tables/think_probe.md。
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
MODELS = ["deepseek-r1:32b", "gemma4:26b", "qwen2.5-coder:32b"]
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
PROMPTS = [
    ("17 乘以 23 等於多少？只回答數字。", "391"),
    ("Python 的 list.sort() 回傳什麼？只回答一個詞。", "None"),
    ("一個有 7 個節點的完全圖有幾條邊？只回答數字。", "21"),
    ("C++ 裡 std::vector 的 size() 回傳的型別名稱是什麼（不含 std::）？只回答型別。", "size_type"),
    ("把字串 'harness' 反轉後是什麼？只回答結果。", "ssenrah"),
]


def main():
    import ollama
    out = []
    for model in MODELS:
        for think in (True, False):
            for prompt, expect in PROMPTS:
                t0 = time.time()
                rec = {"model": model, "think": think, "prompt": prompt}
                try:
                    r = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}], format=SCHEMA, think=think,
                                    options={"temperature": 0.2, "num_ctx": 32768, "num_predict": 4096})
                    msg = r["message"]
                    thinking = (getattr(msg, "thinking", None) or "").strip()
                    content = (msg["content"] or "").strip()
                    try:
                        ans = str(json.loads(content).get("answer", ""))
                    except ValueError:
                        ans = content
                    rec.update(seconds=round(time.time() - t0, 1), thinking_chars=len(thinking), eval_tokens=r.get("eval_count"),
                               answer=ans[:200], correct=expect.lower() in ans.lower(), error=None)
                except Exception as e:      # noqa: BLE001
                    rec.update(seconds=round(time.time() - t0, 1), error=str(e)[:300])
                out.append(rec)
                print(model, think, rec.get("thinking_chars"), rec.get("eval_tokens"), rec.get("correct"), rec.get("error") or "", flush=True)
    raw = os.path.join(STUDY, "results", "raw", "think_probe")
    os.makedirs(raw, exist_ok=True)
    with open(os.path.join(raw, "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    rows = ["| 模型 | think | 有思考內容的次數 | 平均思考字數 | 平均輸出 tokens | 平均秒數 | 答對 | 錯誤 |", "|---|---|---|---|---|---|---|---|"]
    for model in MODELS:
        for think in (True, False):
            g = [r for r in out if r["model"] == model and r["think"] == think]
            ok = [r for r in g if not r["error"]]
            err = sorted({r["error"][:80] for r in g if r["error"]})
            n = max(1, len(ok))
            rows.append(f"| {model} | {'true' if think else 'false'} | {sum(1 for r in ok if r['thinking_chars'] > 0)}/{len(g)} | "
                        f"{sum(r['thinking_chars'] for r in ok) / n:.0f} | {sum(r['eval_tokens'] or 0 for r in ok) / n:.0f} | "
                        f"{sum(r['seconds'] for r in ok) / n:.1f} | {sum(1 for r in ok if r['correct'])}/{len(g)} | {'；'.join(err) or '—'} |")
    tables = os.path.join(STUDY, "results", "tables")
    os.makedirs(tables, exist_ok=True)
    with open(os.path.join(tables, "think_probe.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
