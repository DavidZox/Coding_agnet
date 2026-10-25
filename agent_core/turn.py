"""回合層的共用函式（CLI 與 Web 都用）：工具回傳怎麼進主對話、捨棄通知、回合結束的軟水位壓縮。"""
import os
from .config import (
    MIN_COMPRESS_TOKENS,
    RAW_RESULT_MAX_TOKENS,
    SOFT_TOKEN_THRESHOLD,
    TOOL_REDUCED_TAG,
    TOOL_RESULT_TOKEN_THRESHOLD,
    TOOL_SUMMARY_TAG,
    TOOL_TRUNCATED_TAG,
)
from . import prompt_files
from .protocol import is_exempt_result, is_skill_doc_result, tool_result_message

_RESULTS = "harness/tool_results.md"   # 捨棄通知、沒有提煉時只給成功／失敗的那一則


def _append_discarded_tool_result(agent):
    """使用者選擇不把工具結果加入上下文時，仍需告知 AI「工具已執行完畢」，
    避免它誤以為指令根本沒被處理而重複嘗試。同樣包上系統回傳的框架句。"""
    agent.messages.append({
        'role': 'user',
        'content': tool_result_message(
            prompt_files.load(_RESULTS, "discarded"),
            (agent._last_assistant_step() or {}).get("action"),
        ),
    })

def _content_for_context(result, tool_tokens, agent=None, use_summary=True):
    """決定要餵給主對話的內容。技能規格文件、已提煉過的結果（result_recall）：原封不動。其餘依上下文模式：

    claude_code 模式（agent.context_mode）：一律交給 agent.raw_result_for_context——原文直接進上下文（第一行註明
    存檔編號），超過 RAW_RESULT_MAX_TOKENS 保留頭尾；不呼叫任何模型，要查細節由模型自己決定。

    harness 模式：門檻內原封不動。超過 TOOL_RESULT_TOKEN_THRESHOLD 時：
    - use_summary=True（預設）且提供 agent：交給 agent.summarize_tool_result()——獨立、乾淨的 session 拿完整原始輸出
      + 使用者目標 + 這一步的目的做任務導向提煉（長的依結構切段、每段一個 worker 再整合，見 agent_core/extract.py），
      主對話收到的是跟任務有關的重點（每條附原文的行號）。例外只有 is_exempt_result 的那幾種：規格文件、
      已經是提煉結果的、程式整理好的報告（數據分析、工作流）——直接原文。
    - use_summary=False（/summarize off）、沒有 agent、或摘要 session 失敗：退回只給成功／失敗判定——零延遲，
      但模型拿不到內容，只能換更精確的參數重查。
    """
    if is_exempt_result(result, tool_tokens):
        return result
    if agent is not None and getattr(agent, "context_mode", "harness") == "claude_code":
        return agent.raw_result_for_context(result, tool_tokens)
    if tool_tokens <= TOOL_RESULT_TOKEN_THRESHOLD:
        return result

    if use_summary and agent is not None:
        try:
            summary = agent.summarize_tool_result(result, tool_tokens)
            # 摘要不比原文短時直接給原文：實測 700 tokens 左右的結構化輸出（ros2 node info）會被摘要 session「展開」成
            # 900 多 tokens，門檻的目的是省上下文，這時原文反而更省、也不會有摘要自己數錯的問題。
            if agent.count_tokens(summary) < tool_tokens:
                return summary
            print(f"ℹ️ 任務導向摘要（≈{agent.count_tokens(summary)} tokens）不比原文（≈{tool_tokens} tokens）短，主對話改收完整原文")
            return result
        except Exception as e:
            print(f"⚠️ 獨立摘要 session 執行失敗，改用成功/失敗判定：{e}")

    status = prompt_files.load(_RESULTS, "reduced_failed" if result.lstrip().startswith("[ERROR]") else "reduced_ok")
    rid = getattr(agent, "last_result_id", None) if agent is not None else None
    recall = (prompt_files.load(_RESULTS, "reduced_recall", rid=rid) if rid else prompt_files.load(_RESULTS, "reduced_no_recall"))
    return f"{TOOL_REDUCED_TAG}\n" + prompt_files.load(_RESULTS, "reduced", status=status, tokens=tool_tokens,
                                                     threshold=TOOL_RESULT_TOKEN_THRESHOLD, recall=recall)


def oversized_notice(agent, tool_tokens, use_summary):
    """工具回傳超過門檻時給使用者看的一句話（CLI 印出、Web 推 system 事件）：依上下文模式說明 AI 會收到什麼。"""
    if getattr(agent, "context_mode", "harness") == "claude_code":
        if tool_tokens > RAW_RESULT_MAX_TOKENS:
            return (f"⚠️ 此工具回傳約 {tool_tokens} tokens，超過 claude_code 模式的上限 {RAW_RESULT_MAX_TOKENS}：AI 會收到原文頭尾、"
                    f"中間註明省略多少與存檔編號，要不要回存檔查由 AI 自己決定。")
        return f"⚠️ 此工具回傳約 {tool_tokens} tokens（claude_code 模式）：原文直接進上下文，不經獨立 session 摘要。"
    return (f"⚠️ 此工具回傳約 {tool_tokens} tokens，超過門檻 {TOOL_RESULT_TOKEN_THRESHOLD}，"
            + ("加入上下文前將交由獨立 session 依目前任務擷取重點。" if use_summary
               else "加入上下文時只保留成功／失敗判定（/summarize on 可改為獨立 session 摘要）。"))


def context_kind(content, tool_tokens=None):
    """主對話實際收到的是哪一種：summary（任務導向摘要）／reduced（只有成功／失敗）／truncated（claude_code 模式的原文頭尾）
    ／doc（規格文件，完整放行）／raw（完整原文）。CLI 與 Web 用同一個判斷來標示，使用者永遠同時看得到完整原文與 AI 收到的版本。"""
    if content.startswith(TOOL_SUMMARY_TAG):
        return "summary"
    if content.startswith(TOOL_REDUCED_TAG):
        return "reduced"
    if content.startswith(TOOL_TRUNCATED_TAG):
        return "truncated"
    if is_skill_doc_result(content):
        return "doc"
    return "raw"

def after_turn_compression(agent, parallel, notify):
    """回合結束後的軟水位檢查（CLI 與 Web Console 共用）。

    這個時間點最終答案已經送出、模型閒著，壓縮不會拉長任何一次回覆的等待時間，切點也剛好
    落在任務邊界。parallel=True（/parallel_cal on）時改在背景執行緒做，主對話可以立刻繼續；
    否則同步做完再回到等待輸入。notify 是輸出通知的函式（CLI 用 print，Web 推 system 事件）。
    claude_code 模式先清除舊的工具回傳（不呼叫模型、原文在存檔），清完低於軟水位就不壓縮。
    回傳 None（未觸發）／'cleared'／'sync'／'background'。"""
    ctx_before = agent.context_tokens()
    if ctx_before <= SOFT_TOKEN_THRESHOLD:
        return None
    if getattr(agent, "context_mode", "harness") == "claude_code" and agent.clear_old_tool_results():
        info = agent.last_clearing
        notify(f"🧹 回合結束，上下文約 {ctx_before} tokens 超過軟水位 {SOFT_TOKEN_THRESHOLD}：先把 {info['results']} 則舊的工具回傳"
               f"清成存檔編號（騰出約 {info['tokens']} tokens，原文仍在存檔、AI 可取回）；上下文約 {agent.context_tokens()} tokens。")
        if agent.context_tokens() <= SOFT_TOKEN_THRESHOLD:
            return 'cleared'
    # 可壓的內容太少就不值得一次模型呼叫（system prompt 本身很大時，超過水位卻沒什麼可壓是常態）
    if agent.compressible_tokens() < MIN_COMPRESS_TOKENS:
        return None
    if parallel:
        if agent.start_background_compression():
            notify(
                f"🗜️ 回合結束，上下文約 {ctx_before} tokens 超過軟水位 {SOFT_TOKEN_THRESHOLD}，"
                f"已在背景開始壓縮（/parallel_cal on），完成後會通知。"
            )
            return 'background'
        return None
    notify(f"🗜️ 回合結束，上下文約 {ctx_before} tokens 超過軟水位 {SOFT_TOKEN_THRESHOLD}，壓縮中...")
    if agent.compress_context_to_file():
        info = agent.last_compression
        archived = f"；被壓縮的對話原文存成 #{info['archive_id']}" if info.get('archive_id') else ""
        notify(
            f"📦 已將 {info['messages']} 則舊對話融合成摘要（約 {info['summary_tokens']} tokens）並歸檔："
            f"{os.path.basename(info['file'])}{archived}；上下文約 {agent.context_tokens()} tokens。"
        )
        return 'sync'
    return None
