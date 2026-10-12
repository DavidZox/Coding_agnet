"""Generate fe_specs.json: exact `old` texts are cut from the reference files (line ranges / literal strings)
and checked to occur exactly once."""
import json
import os
import sys

DATA = "/home/amr-base/Coding_agent_harness/evals/devbench/data"
OUT = "/home/amr-base/Coding_agent_harness/benchmark_study_3/datasets/small_projects/fe_specs.json"
PY = {"readtime", "particle-swarm-optimization", "chakin", "stocktrends", "geotext", "hone", "lice"}


def path(repo, rel):
    return os.path.join(DATA, "python" if repo in PY else "cpp", repo, rel)


def read(repo, rel):
    with open(path(repo, rel), encoding="utf-8") as f:
        return f.read()


def L(repo, rel, a, b):
    """lines a..b (1-based, inclusive), with their line endings."""
    lines = read(repo, rel).splitlines(keepends=True)
    return "".join(lines[a - 1:b])


def E(repo, rel, old, new=""):
    return {"file": rel, "old": old, "new": new}


def EL(repo, rel, a, b, new=""):
    return E(repo, rel, L(repo, rel, a, b), new)


def EALL(repo, rel, new=""):
    return E(repo, rel, read(repo, rel), new)


SPECS = []


def spec(repo, feature, request, files, edits):
    SPECS.append({"repo": repo, "feature": feature, "request": request.strip(), "files": files, "edits": edits})


# ---------------------------------------------------------------- readtime
R = "readtime"
spec(R, "HTML 與 Markdown 的閱讀時間估算", """
目前 readtime 只能估算純文字的閱讀時間（`readtime.api.of_text`），請加上 HTML 與 Markdown 的支援：

1. 在 `readtime/api.py` 新增 `of_html(html, wpm=265)` 與 `of_markdown(markdown, wpm=265)`，用法跟 `of_text` 一樣，回傳 `Result`（`result.wpm` 要等於傳入的 wpm，預設 265）。
2. `readtime.utils.read_time(content, format, wpm)` 的 `format` 除了 `'text'`，還要支援 `'html'` 與 `'markdown'`（跟現在一樣不分大小寫）；其他格式維持現在的行為：丟出 `Exception('Unsupported format: <format>')`。
3. HTML 的算法：抽出 HTML 的可見文字（去掉標籤，連續空白合併成一個空格），字數用跟純文字相同的方式計算（`read_time_as_seconds`）；文件裡的 `<img>` 圖片張數傳給 `read_time_as_seconds` 的 `images` 參數（圖片加時的規則已經寫好）。
4. Markdown：先用 `markdown2` 轉成 HTML，再用跟 HTML 相同的方式計算。
5. 解析 HTML 的部分請寫成 `readtime/utils.py` 的 `parse_html(el)`（架構文件有列）：輸入是用 `pyquery` 解析好的元素，回傳 `(純文字, 圖片張數)`。需要的套件（markdown2、pyquery、lxml）都已經裝好。

驗證參考：`samples/html.html` 與 `samples/markdown.md` 用預設 wpm 計算都應該是 236 秒（`result.text == '4 min'`、`str(result) == '4 min read'`），而且結果可以跟 `of_text` 的結果相加（`Result` 已經支援 `+`）。
""", ["readtime/api.py", "readtime/utils.py"], [
    EL(R, "readtime/api.py", 27, 54),
    EL(R, "readtime/utils.py", 16, 19),
    E(R, "readtime/utils.py", "Supported formats are 'text', 'markdown', and 'html'.", "Supported format is 'text'."),
    EL(R, "readtime/utils.py", 49, 59),
    EL(R, "readtime/utils.py", 94, 128),
    E(R, "unit_tests/test_custom_wpm.py", "from readtime.api import of_text,of_html,of_markdown\n", "from readtime.api import of_text\n"),
    EL(R, "unit_tests/test_custom_wpm.py", 22, 37),
])

# ---------------------------------------------------------------- particle-swarm-optimization
R = "particle-swarm-optimization"
spec(R, "粒子移動：速度與位置更新", """
目前 `pso/pso_simple.py` 的 `minimize()` 每一輪只會評估粒子、更新最佳解，粒子本身完全不會移動，所以最佳化沒有任何進展。請補上粒子的移動：

1. `Particle.update_velocity(pos_best_g)`：依標準 PSO 公式就地更新每一維的速度：`v = w*v + c1*r1*(個體最佳位置 - 目前位置) + c2*r2*(全域最佳位置 - 目前位置)`，慣性權重 `w = 0.5`、認知常數 `c1 = 1`、社會常數 `c2 = 2`，`r1`、`r2` 是每一維各自抽的 [0, 1) 均勻亂數。速度、目前位置、個體最佳位置分別是 `self.velocity_i`、`self.position_i`、`self.pos_best_i`（都是 list），`pos_best_g` 是全域最佳位置。
2. `Particle.update_position(bounds)`：每一維 `位置 += 速度`，然後夾回邊界內：`bounds` 是每一維一個 `(最小值, 最大值)`，超過最大值就設成最大值、低於最小值就設成最小值。例：位置 `[2, 3]`、速度 `[0.5, 0.5]`、邊界 `[(-10, 10), (-10, 10)]`，更新後位置是 `[2.5, 3.5]`。
3. `minimize()`：每一輪在所有粒子都評估完、全域最佳更新之後，對每個粒子先呼叫 `update_velocity(pos_best_g)`、再呼叫 `update_position(bounds)`。

這兩個方法要能直接在 `Particle` 物件上呼叫（不必先跑過 `minimize`；維度數就是位置的長度）。完成後 `minimize(sphere, [5, 5], [(-10, 10), (-10, 10)], num_particles=15, maxiter=30)` 找到的解應該明顯比起點好。
""", ["pso/pso_simple.py"], [
    EL(R, "pso/pso_simple.py", 47, 90),
    EL(R, "pso/pso_simple.py", 134, 138),
    EL(R, "unit_tests/test_pso_simple.py", 28, 87),
])

# ---------------------------------------------------------------- chakin
R = "chakin"
CHAKIN_TEST = """    def test_load_datasets(self):
        df = load_datasets()
        for column in ['Name', 'Dimension', 'Corpus', 'VocabularySize', 'Method', 'Language', 'Author', 'URL']:
            self.assertIn(column, df.columns)
        self.assertEqual(df.iloc[self.number]['Name'], self.name)
"""
spec(R, "下載預訓練詞向量（download）", """
chakin 目前只能搜尋詞向量（`search`），還不能下載。請加上下載功能：

1. 在 `chakin/downloader.py` 新增 `download(number=-1, name="", save_dir='./')`，並從 `chakin/__init__.py` 匯出（可以用 `chakin.download(...)`，跟 `search` 一樣）。
2. 選擇要下載的詞向量：`number > -1` 時取 `load_datasets()` 的第 `number` 列（從 0 起算的列位置，例如 `number=22` 是 `word2vec.Wiki-NEologd.50d`）；否則取 `Name` 欄位等於 `name` 的那一列。找不到 URL 時印出 `The word vector you specified was not found. Please specify correct name.`。
3. 存檔位置：`save_dir` 不存在就建立；檔名是 URL 最後一個 `/` 之後的部分，存到 `os.path.join(save_dir, 檔名)`。
4. 下載要用模組層級匯入的 `urlretrieve`（`from six.moves.urllib.request import urlretrieve` 或 `from urllib.request import urlretrieve` 都可以，但必須能以 `chakin.downloader.urlretrieve` 取用——測試會 mock 這個名稱），呼叫方式是 `urlretrieve(url, 存檔路徑, reporthook=進度回呼)`。進度回呼的參數是 `(count, blockSize, totalSize)`，用 progressbar2（`progressbar` 模組，已經裝好）顯示進度條：第一次被呼叫時把進度條最大值設成 `totalSize` 並開始，之後更新為 `min(count * blockSize, totalSize)`；下載完呼叫 `finish()`。
5. 回傳下載後的檔案路徑（`urlretrieve` 回傳的 tuple 的第一個元素）。
""", ["chakin/downloader.py", "chakin/__init__.py"], [
    EL(R, "chakin/downloader.py", 5, 6),
    EL(R, "chakin/downloader.py", 14, 49),
    E(R, "chakin/__init__.py", "from .downloader import download, search", "from .downloader import search"),
    E(R, "unit_tests/test_downloader.py", "from chakin.downloader import load_datasets, download\n", "from chakin.downloader import load_datasets\n"),
    EL(R, "unit_tests/test_downloader.py", 12, 34, CHAKIN_TEST),
])

# ---------------------------------------------------------------- stocktrends
R = "stocktrends"
spec(R, "Renko 磚形圖（收盤價模式）", """
`stocktrends/indicators.py` 的 `Renko` 類別目前只有參數（`brick_size`、`chart_type`、`PERIOD_CLOSE`／`PRICE_MOVEMENT` 等常數），還不能產生圖表資料。請實作收盤價（period close）模式的 Renko：

1. `Renko.get_ohlc_data()`：`chart_type == Renko.PERIOD_CLOSE`（預設值）時呼叫 `period_close_bricks()`，否則呼叫 `price_movement_bricks()`（維持現在的空實作）；回傳結果 DataFrame（同時存在 `self.cdf`）。
2. `Renko.period_close_bricks()`：用 `self.df` 的 `date, open, high, low, close` 欄位與磚塊大小 `b = self.brick_size` 產生磚塊，回傳欄位依序為 `date, open, high, low, close, uptrend` 的 DataFrame，index 從 0 重新編號（不要多出舊 index 欄）。規則：
   - 第一塊磚：第一列收盤價往下取到 b 的整數倍得 c（`close // b * b`），日期是第一列的日期，`open = c - b、high = c、low = c - b、close = c、uptrend = True`。
   - 接著逐列處理所有資料（包含第一列），以該列收盤價與目前最後一塊磚的收盤價 `last` 計算 `n = int((close - last) / b)`（往 0 截斷）。同方向至少 1 塊就疊磚：上升趨勢 n ≥ 1 時往上疊 n 塊，下降趨勢 n ≤ -1 時往下疊 |n| 塊；反方向要至少 2 塊才反轉（上升趨勢 n ≤ -2、下降趨勢 n ≥ 2），反轉時第一塊新磚從最後一塊磚的開盤價（`last ∓ b`）開始，所以實際疊 |n| - 1 塊。其他情況不產生磚。
   - 上升磚：`open = x、high = x + b、low = x、close = x + b`；下降磚：`open = x、high = x、low = x - b、close = x - b`（x 是這塊磚的起點，也就是前一塊新磚的收盤價）。每塊磚的日期是觸發它的那一列的日期，`uptrend` 是這塊磚的方向。

驗證參考：`acceptance_samples/HOOLI.csv` 用 `brick_size = 4` 產生的磚要跟 `acceptance_samples/hooli_renko_4.csv` 一致（特別是 close 欄）；`unit_samples/HDFCLIFE.csv`（欄名先轉小寫）用 `brick_size = 20` 會得到 84 塊磚（shape `(84, 6)`）。
""", ["stocktrends/indicators.py"], [
    EL(R, "stocktrends/indicators.py", 42, 58),
    EL(R, "stocktrends/indicators.py", 61, 130),
    EL(R, "unit_tests/test_renko.py", 3, 14),
])

# ---------------------------------------------------------------- geotext
R = "geotext"
spec(R, "國籍辨識與國家提及次數統計", """
`GeoText` 目前能找出文字裡的城市（`cities`）與國家（`countries`），請加上國籍辨識與國家提及次數統計：

1. 載入國籍資料：`build_index()` 回傳的 namedtuple `Index` 要多一個欄位 `nationalities`（欄位順序 `nationalities, cities, countries`），資料來自 `geotext/data_file/nationalities.txt`：每行是 `國籍:國家代碼`（例如 `afghan:AF`），用 `read_table` 以 `:` 分隔讀成 dict（鍵是小寫的國籍、值是國家代碼）。`GeoText.index.nationalities` 要可以取用。
2. `GeoText(text).nationalities`：跟 `countries` 一樣，從同一批候選詞（同一個 regex 找出來的）中挑出小寫後存在於國籍資料的詞，保留原文與出現順序（可重複）。例：`'Japanese people like anime. French people often drink wine. Chinese people enjoy fireworks.'` → `['Japanese', 'French', 'Chinese']`。
3. `GeoText(text).country_mentions`：`collections.OrderedDict`，鍵是國家代碼、值是被提及的次數。依序把 `countries`（國名對應的代碼）、`cities`（城市對應的國家代碼；有傳 `country` 參數時用過濾後的城市）、`nationalities`（國籍對應的代碼）裡每一個都算一次，再依次數由多到少排序；次數相同時保持第一次出現的先後（也就是 `Counter(...).most_common()` 的順序）。例：`'New York, Texas, and also China'` → `OrderedDict([('US', 2), ('CN', 1)])`；`'I would like to visit Lima, Dublin and Moscow (Russia).'` → `{'PE': 1, 'IE': 1, 'RU': 2}`。
""", ["geotext/geotext.py"], [
    E(R, "geotext/geotext.py", "from collections import namedtuple, Counter, OrderedDict\n", "from collections import namedtuple\n"),
    E(R, "geotext/geotext.py", "    A namedtuple with three fields: nationalities cities countries\n",
      "    A namedtuple with two fields: cities countries\n"),
    E(R, "geotext/geotext.py", "    nationalities = read_table(get_data_path('nationalities.txt'), sep=':')\n\n", ""),
    E(R, "geotext/geotext.py", "    Index = namedtuple('Index', 'nationalities cities countries')\n    return Index(nationalities, cities, countries)\n",
      "    Index = namedtuple('Index', 'cities countries')\n    return Index(cities, countries)\n"),
    E(R, "geotext/geotext.py", "\n    >>> GeoText('New York, Texas, and also China').country_mentions\n    OrderedDict([(u'US', 2), (u'CN', 1)])\n", ""),
    EL(R, "geotext/geotext.py", 119, 131),
    EL(R, "unit_tests/test_geotext.py", 99, 105),
    EL(R, "unit_tests/test_geotext.py", 115, 121),
])

# ---------------------------------------------------------------- hone
R = "hone"
spec(R, "由欄位名稱自動推斷巢狀 JSON 結構", """
目前 `Hone.convert(csv_filepath, schema)` 一定要傳入 schema（巢狀結構）才能轉換。請加上「由 CSV 欄位名稱自動推斷巢狀結構」的功能：

1. 新增 `Hone.get_schema(csv_filepath)`：讀取 CSV 的欄位名稱，回傳推斷出來的巢狀結構（dict）。
2. `convert(csv_filepath, schema=None)`：沒有傳 schema（或傳入空值）時，用同樣的方式從欄位名稱推斷結構再轉換。
3. 結構的格式跟現在 `convert` 接受的 schema 相同：葉節點的值是原始欄位名稱，鍵是該層的名稱。例：欄位 `name, age (years), weight (kg), birth day, birth month, birth year, adopted, adopted_since` 會得到 `{"name": "name", "age (years)": "age (years)", "weight (kg)": "weight (kg)", "birth": {"day": "birth day", "month": "birth month", "year": "birth year"}, "adopted": "adopted", "adopted_since": "adopted_since"}`（就是 `data_file/small_cats_dataset/nested_schema.json`）。
4. 分組規則（分隔字元是 `self.delimiters`，預設 `[",", "_", " "]`）：
   - 欄位名稱裡任一個分隔字元之前的部分（再去掉結尾的分隔字元）都是可能的前綴。
   - 前綴 P 要形成一個巢狀群組，必須至少有 2 個欄位名稱以「P＋分隔字元」開頭，而且 P 本身不是某個欄位名稱（所以 `adopted` 與 `adopted_since` 不會合併）。有多個可能的前綴時優先用最短的；已經分進某個群組的欄位不會再被分到別的群組。
   - 群組成員的鍵是去掉 P 以及緊接在後面的分隔字元之後剩下的部分；群組內部再用同樣的規則遞迴分組。
   - 沒有被分組的欄位直接放在該層，鍵與值都是欄位名稱。

`data_file/` 裡三組資料（`small_cats_dataset`、`comma_test`、`quotes_test`）的 `dataset.csv` 不給 schema 轉換的結果，都要等於各自的 `nested_dataset.json`。
""", ["hone/hone.py"], [
    E(R, "hone/hone.py", "        column_schema = schema\n        if not column_schema:\n            column_schema = self.generate_full_structure(column_names)\n",
      "        column_schema = schema\n"),
    EL(R, "hone/hone.py", 46, 111),
    EL(R, "hone/hone.py", 128, 179),
    EL(R, "unit_tests/test_csv_utils.py", 24, 39),
    EL(R, "unit_tests/test_hone.py", 15, 38),
])

# ---------------------------------------------------------------- lice
R = "lice"
LICE_HEADER_OLD = """        content = generate_license(template, get_context(args))
        out = format_license(content, lang)
        out.seek(0)
        sys.stdout.write(out.getvalue())
        out.close()  # free content memory (paranoic memory stuff)
        sys.exit(0)
"""
LICE_HEADER_NEW = """        content = generate_license(template, get_context(args))
        sys.stdout.write(content.getvalue())
        content.close()
        sys.exit(0)
"""
LICE_OUT_NEW = """    content = generate_license(template, get_context(args))

    if args.ofile != "stdout":
        with open(args.ofile, "w") as f:
            f.write(content.getvalue())
    else:
        sys.stdout.write(content.getvalue())
    content.close()  # free content memory (paranoic memory stuff)
"""
spec(R, "依程式語言格式化授權文字（-l/--language、--languages、依副檔名自動判斷）", """
`lice` 目前只能輸出純文字的授權條款。`lice/core.py` 已經有語言對照表 `LANGS`（副檔名 → 註解風格）與 `LANG_CMT`（註解風格 → `[開頭, 每行前綴, 結尾]`），但還沒有用到。請加上「把授權條款格式化成指定程式語言的註解」的功能：

1. `format_license(template, lang)`：`template` 是 `StringIO`，回傳新的 `StringIO`。`lang` 是 `LANGS` 的鍵（副檔名），是 `None` 或空字串時當成 `'txt'`。輸出格式：先寫「開頭」加 `\\n`；接著從頭讀 template 的每一行，每行前面加上「每行前綴」再加一個空格；最後寫「結尾」加 `\\n`（結尾直接接在最後一行後面，最後一行沒有換行時就會在同一行）。例：`format_license(StringIO('Example License Text'), 'c').getvalue() == '/*\\n * Example License Text */\\n'`；`'py'` 得到 `'\\n# Example License Text\\n'`。
2. `get_suffix(name)`：檔名含有 `.` 且最後一段副檔名在 `LANGS` 裡就回傳該副檔名（`'example.py'` → `'py'`），否則回傳 `False`（例如 `'example'`、`'example.xyz'`）。
3. 命令列 `main()`：
   - 新增 `-l/--language`（dest `language`）：指定輸出格式的語言；不在 `LANGS` 裡時在 stderr 印出說明（不認得這個副檔名）並以 exit code 1 結束。
   - 新增 `--languages`（dest `list_languages`）：依字母順序每行印一個支援的副檔名，然後 `sys.exit(0)`。
   - `--header` 產生的檔頭與一般的授權條款輸出，都要先用 `format_license(內容, 語言)` 格式化（沒指定語言就是 txt 格式）再輸出。
   - `-f/--file`：檔名本身有可辨識的副檔名時，用該副檔名的格式並寫到這個檔名；否則有 `-l` 時寫到 `檔名.語言`（用該語言的格式），都沒有就用 txt 格式寫到該檔名。寫檔維持 `open(輸出檔名, "w")`；沒有 `-f` 時輸出到 stdout。
""", ["lice/core.py"], [
    EL(R, "lice/core.py", 177, 206),
    EL(R, "lice/core.py", 233, 236),
    E(R, "lice/core.py", "        help='Name of the output source file (with -l, '\n        'extension can be ommitted)')\n",
      "        help='Name of the output file')\n"),
    EL(R, "lice/core.py", 247, 249),
    EL(R, "lice/core.py", 257, 266),
    E(R, "lice/core.py", LICE_HEADER_OLD, LICE_HEADER_NEW),
    EL(R, "lice/core.py", 327, 333),
    EL(R, "lice/core.py", 341, 363, LICE_OUT_NEW),
    E(R, "unit_tests/test_lice.py", "    format_license,get_suffix,load_file_template, \n", "    load_file_template, \n"),
    EL(R, "unit_tests/test_lice.py", 171, 197),
    EL(R, "unit_tests/test_lice.py", 237, 246),
])

# ---------------------------------------------------------------- area_calculation
R = "area_calculation"
spec(R, "圓形 Circle（類別＋主程式計算圓面積）", """
目前專案有 `Shape`、`Rectangle`、`Square`，請補上 PRD 裡的圓形 `Circle`，並讓主程式也計算圓面積：

1. `include/Circle.hpp`：類別 `Circle` 公開繼承 `Shape`，私有成員 `double radius`；建構子 `Circle()`（半徑 0）與 `Circle(double _r)`、解構子 `~Circle()`，以及覆寫的 `double calcArea()`，回傳 `3.14159265 * radius * radius`。建構與解構時照 PRD 輸出追蹤訊息（各自一行）：`Circle()`、`Circle(r)`（就是字面上的 `Circle(r)`，不是實際半徑）、`~Circle()`。請跟 `Square.hpp` 一樣寫成 header-only（成員函式的定義直接寫在標頭檔；建置檔不會另外編譯 Circle 的 .cpp）。
2. `src/main.cpp`：輸入檔的第一個數字是圓的半徑。先讀半徑、建立 `Circle` 並輸出面積（一行），再照現在的方式處理長方形（寬、高）與正方形（邊長）。物件都是 main 的區域變數，程式結束時解構訊息會依建立的相反順序印出。

`inputs/` 每個輸入檔在 `expected_outputs/` 都有完整的預期輸出（包含建構／解構訊息）可以對照。
""", ["include/Circle.hpp", "src/main.cpp"], [
    EALL(R, "include/Circle.hpp"),
    E(R, "src/main.cpp", '#include "Circle.hpp"\n', ""),
    EL(R, "src/main.cpp", 18, 22, "    double x, y, a;\n"),
    EALL(R, "unit_tests/test_Circle.cpp"),
])

# ---------------------------------------------------------------- graph-cpp
R = "graph-cpp"
spec(R, "廣度優先走訪（BFS）與自製佇列 Queue", """
PRD 的 Feature 2（廣度優先走訪，BFS）還沒做。請補上：

1. `include/queue.hpp`：自製的泛型佇列 `template <class T> class Queue`（PRD 規定不能用 STL 的 queue／stack），header-only，用鏈結串列實作。公開成員：`bool empty()`、`void push(const T& data)`（加到尾端）、`T front()`（回傳最前面的元素，不移除）、`T pop()`（移除並回傳最前面的元素）；解構時釋放所有節點。佇列是空的時候 `front()` 與 `pop()` 都要丟 `std::out_of_range`。
2. `AdjacencyListGraph<VertexType>::bfs()`（`include/al_graph.hpp`，public）：回傳 `std::vector<VertexType>`，從第一個頂點（`setVexes` 給的第一個）開始做廣度優先走訪，鄰居依鄰接串列的順序（也就是 `setArcs` 加入的順序）拜訪；還有沒走到的頂點時（例如有向圖或不連通的圖），依頂點順序從下一個還沒拜訪的頂點繼續走訪，直到所有頂點都拜訪過。請用上面的 `Queue`。
3. `src/main.cpp`：在 DFS 的結果之後輸出一行 `BFS: `，下一行輸出 BFS 的結果（每個頂點後面接一個空格）並換行——格式跟 `expected_outputs/` 裡的檔案一致。

例：無向圖、邊為 `1-2, 1-3, 2-4, 2-5, 3-6, 3-7, 4-8, 5-8, 6-8, 7-8`（頂點依序 1～8）時，BFS 是 `1 2 3 4 5 6 7 8`。
""", ["include/queue.hpp", "include/al_graph.hpp", "src/main.cpp"], [
    EALL(R, "include/queue.hpp"),
    E(R, "include/al_graph.hpp", '#include "queue.hpp"\n', ""),
    EL(R, "include/al_graph.hpp", 30, 82),
    EL(R, "include/al_graph.hpp", 135, 150),
    EL(R, "src/main.cpp", 78, 80),
    EALL(R, "unit_tests/test_queue.cpp"),
    EL(R, "unit_tests/test_al_graph.cpp", 33, 38),
])

# ---------------------------------------------------------------- logistic_system
R = "logistic_system"
spec(R, "寄送與簽收快遞（send／sign）", """
PRD 的「Parcel Sending & Receiving」（登入後的 `send`、`sign` 指令）還沒做，請補上（會動到 `expressage`、`logistics` 的標頭與實作，以及 `main.cpp`）：

1. `bool ExpressageNode::Sign(string time)`：已經簽收（`Flag == true`）就回傳 `false`；否則把 `signTime` 設成 `time`、`Flag` 設成 `true`，回傳 `true`。
2. `bool LogisticSys::assignExpressage(int curAccount, string receiverId, string remark, string time)`（寄件）：`curAccount` 是帳號索引（`Login` 的回傳值），不合法（< 0 或 ≥ 帳號數）回傳 `false`。收件人帳號不存在、收件人是 root、收件人就是寄件人自己、或寄件人餘額不足 15 元時回傳 `false`（注意是檢查寄件人的餘額）。成功時新增一筆快遞：編號是 `"KD"` 加上「新增前的快遞筆數」補零到 8 位數（例如目前有 2 筆時，新編號是 `KD00000002`），寄件人是目前帳號的 id、收件人 `receiverId`、寄件時間 `time`、簽收時間 `"NULL"`、備註 `remark`、未簽收；加到快遞清單最後、快遞筆數加一；寄件人扣 15 元、root 帳號加 15 元；回傳 `true`。
3. `bool LogisticSys::signExpressage(int curAccount, string id, string time)`（簽收）：帳號索引不合法回傳 `false`；找到第一筆編號為 `id` 的快遞時，如果已經簽收或目前帳號不是收件人就回傳 `false`，否則回傳該筆 `Sign(time)` 的結果；找不到回傳 `false`。
4. `main.cpp` 登入後的指令：`send <收件人帳號> <備註> <寄件時間>` 呼叫 `assignExpressage`；`sign <快遞編號> <簽收時間>` 呼叫 `signExpressage`；成功輸出 `Succeed.`、失敗輸出 `Failed.`（各一行，跟其他指令一致）。
""", ["include/expressage.h", "src/expressage.cpp", "include/logistics.h", "src/logistics.cpp", "src/main.cpp"], [
    E(R, "include/expressage.h", "    bool Sign(string time);\n", ""),
    EL(R, "src/expressage.cpp", 36, 43),
    EL(R, "include/logistics.h", 30, 32),
    EL(R, "src/logistics.cpp", 142, 173),
    EL(R, "src/main.cpp", 114, 137),
    EL(R, "unit_tests/test_expressage.cpp", 28, 34),
    EL(R, "unit_tests/test_logistics.cpp", 163, 208),
])

# ---------------------------------------------------------------- people_management
R = "people_management"
spec(R, "導師關係管理（mentor assign／lookup）", """
請補上導師（mentorship）功能：命令列 `./UMM mentor assign -student <學生ID> -mentor <導師ID>` 與 `./UMM mentor lookup -student <學生ID>`（或 `-mentor <導師ID>`）。

1. 資料表：建立新資料庫時，除了 people 與 school，也要執行 `sql/mentorship.sql` 建立 `mentorship` 表（檔案已經在 `sql/` 裡；路徑常數請比照 `people_sql_name` 加在 `include/common.h`）。
2. `validate_options(subcommand, target)`：`subcommand` 是 `mentor` 時，target 只能是 `assign` 或 `lookup`；其他 target 在 stderr 印出說明並回傳 `false`。
3. `handle_options(...)`：`mentor` 子命令呼叫 `people_management.mentor(target, options)`；回傳值不是 0 時在 stderr 印出錯誤並回傳 `FAILURE`，否則回傳 `SUCCESS`。
4. 新增 `int PeopleManagement::mentor(const std::string& target, const std::map<std::string, std::string>& options) const`（宣告在 `include/people_management.h`），回傳 `common.h` 的狀態碼：
   - 不論 target 為何，先檢查：有給 `-student` 且值不是空字串時，該 ID 必須是 people 表中 type = 1（學生）的人；有給 `-mentor` 且值不是空字串時，必須是 type = 2（導師）的人；不符合就回傳 `RECORD_NOT_EXISTS`。值是空字串的選項視同沒給。
   - `assign`：學生與導師都要給，否則回傳 `NOT_ENOUGH_OPTIONS`。該學生已經有導師就改成新的導師，否則新增一筆 `(student, mentor)`；成功回傳 `SUCCESS`，SQL 執行失敗回傳 `SQL_EXECUTION_ERROR`。
   - 其他 target（`lookup`）：學生與導師都給 → `INVALID_OPTION`；都沒給 → `NOT_ENOUGH_OPTIONS`；只給學生 → 列出這個學生的導師；只給導師 → 列出這位導師的所有學生。先輸出表頭 `student\\t\\tname\\t\\tmentor\\t\\tname`，每筆輸出學生 ID、學生姓名、導師 ID、導師姓名（用現有 `search_callback` 的格式）；成功回傳 `SUCCESS`。
""", ["include/common.h", "include/people_management.h", "src/people_management.cpp"], [
    E(R, "include/common.h", 'const char* const mentorship_sql_name = "sql/mentorship.sql";\n', ""),
    E(R, "include/people_management.h",
      "    int mentor(const std::string& target, const std::map<std::string, std::string>& options) const;\n", ""),
    EL(R, "src/people_management.cpp", 4, 9, "    if (contains(commands, subcommand)) {\n"),
    EL(R, "src/people_management.cpp", 68, 72),
    E(R, "src/people_management.cpp", "        execute_sql_from_file(mentorship_sql_name);\n", ""),
    EL(R, "src/people_management.cpp", 354, 425),
    EL(R, "tests/unit_testing.cpp", 34, 42),
    EL(R, "tests/unit_testing.cpp", 53, 120),
    EL(R, "tests/unit_testing.cpp", 235, 275),
])

# ---------------------------------------------------------------- xlsx2csv
R = "xlsx2csv"
spec(R, "輸出 CSV 檔（worksheet::to_csv、workbook::write_to_csv）", """
目前程式已經會讀 XLSX（工作表清單、共用字串、各工作表的儲存格都解析好了），但還不會輸出 CSV。請補上輸出功能：

1. `std::string worksheet::to_csv() const`（`include/worksheet.h`、`src/worksheet.cpp`）：把工作表轉成 CSV 字串。列從第 1 列到最大列號、欄從第 1 欄到最大欄號（`load_cells()` 已經算好 `row_num`、`column_num`，`row_info[列][欄]` 是該儲存格的共用字串索引，列與欄都從 1 起算；文字用 workbook 的 `get_shared_string(索引)` 取得，沒有資料的儲存格是空字串）。同一列的儲存格用 `,` 分隔（不加引號），每一列（包含最後一列）後面接 `\\n`。
2. `void workbook::write_to_csv(std::string output_dir)`（`include/workbook.h`、`src/workbook.cpp`）：每個工作表寫一個檔案 `output_dir + "/" + 工作表名稱 + ".csv"`，內容是該工作表 `to_csv()` 的結果後面再加一個換行（`std::endl`），所以檔案最後會多一行空行。
3. `src/main.cpp`：建立 workbook 之後呼叫 `write_to_csv(輸出路徑)`，然後才印出成功訊息（訊息與錯誤處理維持現狀）。

`expected_outputs/` 裡有 `inputs/test001～003.xlsx` 的正確輸出可以對照（例如 `expected_outputs/test001/Sheet1.csv`）。
""", ["include/worksheet.h", "src/worksheet.cpp", "include/workbook.h", "src/workbook.cpp", "src/main.cpp"], [
    E(R, "include/worksheet.h", "            std::string to_csv() const;\n\n", ""),
    E(R, "include/worksheet.h", "            std::string get_cell(std::uint32_t row_idx, std::uint32_t column_idx) const;\n", ""),
    EL(R, "src/worksheet.cpp", 19, 34),
    EL(R, "src/worksheet.cpp", 59, 73),
    E(R, "include/workbook.h", "            void write_to_csv(std::string output_dir);\n", ""),
    EL(R, "src/workbook.cpp", 45, 53),
    E(R, "src/main.cpp", "    my_workbook.write_to_csv(savepath);\n", ""),
    EL(R, "unit_tests/test_workbook.cpp", 110, 119),
])


def main():
    review = "--review" in sys.argv
    ok = True
    for s in SPECS:
        texts = {}
        for e in s["edits"]:
            key = e["file"]
            if key not in texts:
                texts[key] = read(s["repo"], key)
            n = texts[key].count(e["old"])
            if n != 1 or not e["old"]:
                ok = False
                print(f"!! {s['repo']} {key}: old occurs {n} times: {e['old'][:80]!r}")
            else:
                texts[key] = texts[key].replace(e["old"], e["new"], 1)
            if review:
                print(f"===== {s['repo']} :: {key}  (-{e['old'].count(chr(10))} lines, +{e['new'].count(chr(10))})")
                print(e["old"], end="" if e["old"].endswith("\n") else "\n")
                if e["new"]:
                    print("----- new:")
                    print(e["new"], end="" if e["new"].endswith("\n") else "\n")
    if not ok:
        sys.exit(1)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(SPECS, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"wrote {len(SPECS)} specs → {OUT}")


if __name__ == "__main__":
    main()
