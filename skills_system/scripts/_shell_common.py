"""執行 shell 指令的技能（host_runcmd、docker_runcmd、code_run）共用：把 harness 拆開的參數接回一行指令。

harness 用 shlex 把 action.args 拆成參數（_parse_script_args）。模型常常寫 `python3 -c "a; print(b)"`（外層沒有再包一層引號），
拆開後 `a; print(b)` 是一個參數；以前直接用空白接回去，引號就不見了，bash 把 `;` 當成指令分隔、括號變成語法錯誤
（實測 coding worker 同一個指令跑三次都失敗，模型怎麼改都不會過）。這裡把有空白或 shell 特殊字元的參數重新加引號；
運算子（&& | ;）、重導向（2>&1）、萬用字元（tests/*.py）保持原樣，所以 `make && ./run 2>&1`、`ls tests/*.py` 照常運作。
只用標準庫。
"""
import os
import re
import shlex

_SHELL_OPS = {"&&", "||", ";", "|", "&", "|&", ">", ">>", "<", "<<", "2>", "2>>", "&>", "(", ")"}
_REDIRECT_RE = re.compile(r"^\d*[<>]{1,2}&?\d*$|^\d*>&\d+$")
_NEEDS_QUOTE_RE = re.compile(r"[\s;&|()<>$`\"'\\]")


def rejoin_args(args):
    """參數 list → 一行指令；只有一個參數時原樣傳回（那是模型用引號包好的整串指令）。
    評測的對照組用 AGENT_ABLATE=rejoin 換回舊的接法（直接用空白接起來，引號會不見；平常不要設）。"""
    args = list(args)
    if len(args) == 1:
        return args[0]
    if "rejoin" in os.environ.get("AGENT_ABLATE", ""):
        return " ".join(args)
    out = []
    for a in args:
        if a in _SHELL_OPS or _REDIRECT_RE.match(a) or not _NEEDS_QUOTE_RE.search(a):
            out.append(a)
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*=)(.*)$", a, re.S)       # FOO="a b" → FOO='a b'
        out.append(m.group(1) + shlex.quote(m.group(2)) if m else shlex.quote(a))
    return " ".join(out)
