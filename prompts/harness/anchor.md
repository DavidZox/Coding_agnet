交給獨立 session（提煉、recall）的「使用者的目標」（agent_core/prompt.py 的 _build_task_anchor_text）：Objective、使用者最新的一句、
同一串對話較早的幾句（任務線）。{名稱} 是程式填的值。

<!-- @objective -->
使用者設定的最高優先 Objective：{objective}

<!-- @latest -->
使用者最新的訊息：{task}

<!-- @none -->
(未取得使用者原始任務敘述)

<!-- @earlier -->
這串對話較早的使用者訊息（舊→新；最新訊息可能只是對其中一項的追問，原本的目的看這裡）：
