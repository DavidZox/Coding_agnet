"""coding orchestrator 的評測情境（run_coding_evals.py 用）。

每個情境：在 fixture 專案（evals/coding_fixtures/<名稱>/）的臨時副本上跑一個 coding job（自動核准、失敗就跳過），結束後檢查：
- hidden_tests：job 結束後才放進工作區的測試（agent 從頭到尾看不到），檢查行為是不是真的照任務做到——agent 自己寫的測試
  可能寫錯或寫得太鬆，不能拿來當唯一的標準；
- 整個專案的測試（agent 寫的＋原本的＋hidden）全部通過；
- unchanged：不准改的檔案（例如除錯任務的測試檔）沒有被改；
- absent：改名之類的任務，舊名稱不能再出現在指定目錄的程式檔（.py、C／C++）裡。
C／C++ 的情境（geometry_cpp：CMake＋gtest；ringbuf_c：Makefile＋gtest）用真的 gtest 驗證：hidden test 是 tests/ 底下的 .cpp，
CMakeLists.txt 與 Makefile 都用 glob 收集測試檔，放進去就會被建置。
ROS 2 的情境（ros2_ws：colcon 工作區，ament_cmake 的 amr_utils＋ament_python 的 amr_tools）照使用者實際的環境：這台主機沒有
ROS 2，code_test 每個套件分開跑，不依賴 ROS 的 gtest／pytest 照跑、需要 rclcpp／rclpy 的跳過；hidden test 放在套件的 test/。
- contains：{檔案: 正規表示式}，改完的檔案要符合（測不到的部分，例如 rclpy 的 node 有沒有照任務改）。
"""

HIDDEN_RESTOCK = '''import pytest
from inventory import Inventory


def make():
    inv = Inventory()
    inv.add("a", 1.0, 5)
    inv.add("b", 2.0, 1)
    inv.add("c", 3.0, 10)
    return inv


def test_hidden_restock_below():
    inv = make()
    assert inv.restock_below(5, 3) == ["b"]
    assert inv.items["b"].qty == 4 and inv.items["a"].qty == 5 and inv.items["c"].qty == 10


def test_hidden_restock_sorted():
    inv = Inventory()
    inv.add("z", 1.0, 1)
    inv.add("m", 1.0, 1)
    inv.add("a", 1.0, 9)
    assert inv.restock_below(2, 1) == ["m", "z"]


def test_hidden_remove_not_enough():
    inv = make()
    with pytest.raises(ValueError, match="not enough stock"):
        inv.remove("a", 9)
    assert inv.items["a"].qty == 5


def test_hidden_remove_exact_still_deletes():
    inv = make()
    inv.remove("a", 5)
    assert "a" not in inv.items
'''

HIDDEN_RENAME = '''import subprocess
import sys

from inventory import Inventory, storage


def test_hidden_total_renamed():
    inv = Inventory()
    inv.add("a", 1.5, 4)
    assert inv.total() == 6.0
    assert not hasattr(inv, "total_value")


def test_hidden_cli_total(tmp_path):
    f = tmp_path / "inv.json"
    inv = Inventory()
    inv.add("a", 1.5, 4)
    inv.add("b", 2.0, 1)
    storage.save(inv, f)
    out = subprocess.run([sys.executable, "-m", "inventory.cli", "--file", str(f), "total"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "8.00"
'''

HIDDEN_CSV = '''import csv
import subprocess
import sys

from inventory import Inventory, storage


def test_hidden_export_csv(tmp_path):
    inv = Inventory()
    inv.add("pear", 2.0, 1)
    inv.add("apple", 1.5, 4)
    p = tmp_path / "out.csv"
    storage.export_csv(inv, p)
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["name", "price", "qty"]
    assert rows[1:] == [["apple", "1.50", "4"], ["pear", "2.00", "1"]]


def test_hidden_cli_export(tmp_path):
    f = tmp_path / "inv.json"
    out = tmp_path / "x.csv"
    inv = Inventory()
    inv.add("apple", 1.5, 4)
    storage.save(inv, f)
    r = subprocess.run([sys.executable, "-m", "inventory.cli", "--file", str(f), "export", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.read_text(encoding="utf-8").splitlines()[:2] == ["name,price,qty", "apple,1.50,4"]
'''

HIDDEN_DISCOUNT = '''import pytest

from inventory import Inventory
from inventory.discount import apply_discount, discounted_total


def test_hidden_apply_discount():
    assert apply_discount(100, 15) == 85.0
    assert apply_discount(19.99, 10) == 17.99
    assert apply_discount(5, 0) == 5.0


@pytest.mark.parametrize("bad", [-1, 101])
def test_hidden_apply_discount_range(bad):
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        apply_discount(10, bad)


def test_hidden_discounted_total():
    inv = Inventory()
    inv.add("a", 1.5, 4)
    inv.add("b", 2.0, 1)
    assert discounted_total(inv, 50) == 4.0
'''

HIDDEN_CATEGORY = '''import json
import subprocess
import sys

from inventory import Inventory, Item, storage


def test_hidden_item_category_default():
    assert Item("a", 1.0, 1).category == "general"


def test_hidden_add_with_category_and_by_category():
    inv = Inventory()
    inv.add("pear", 2.0, 1, category="fruit")
    inv.add("apple", 1.5, 4, category="fruit")
    inv.add("hammer", 9.0, 1, category="tools")
    inv.add("misc", 1.0, 1)
    assert inv.by_category() == {"fruit": ["apple", "pear"], "general": ["misc"], "tools": ["hammer"]}


def test_hidden_storage_roundtrip_category(tmp_path):
    inv = Inventory()
    inv.add("apple", 1.5, 4, category="fruit")
    p = tmp_path / "inv.json"
    storage.save(inv, p)
    assert storage.load(p).items["apple"].category == "fruit"


def test_hidden_storage_loads_old_files_without_category(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps([{"name": "apple", "price": 1.5, "qty": 4}]), encoding="utf-8")
    assert storage.load(p).items["apple"].category == "general"


def test_hidden_cli_category(tmp_path):
    f = tmp_path / "inv.json"

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "inventory.cli", "--file", str(f), *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout

    run("add", "apple", "1.5", "4", "--category", "fruit")
    run("add", "hammer", "9", "1", "--category", "tools")
    run("add", "misc", "1", "1")
    assert run("categories").strip().splitlines() == ["fruit: 1", "general: 1", "tools: 1"]
'''

HIDDEN_CPP_PERIMETER = r'''#include <gtest/gtest.h>

#include <cmath>
#include <memory>

#include "geometry/circle.hpp"
#include "geometry/rectangle.hpp"
#include "geometry/shape.hpp"

using namespace geometry;

TEST(HiddenPerimeter, Circle) { EXPECT_NEAR(Circle(1.5).perimeter(), 2 * M_PI * 1.5, 1e-9); }

TEST(HiddenPerimeter, Rectangle) { EXPECT_DOUBLE_EQ(Rectangle(2.0, 3.5).perimeter(), 11.0); }

TEST(HiddenPerimeter, ThroughBasePointer) {
    std::unique_ptr<Shape> s = std::make_unique<Rectangle>(1.0, 1.0);
    EXPECT_DOUBLE_EQ(s->perimeter(), 4.0);
}
'''

HIDDEN_CPP_TRIANGLE = r'''#include <gtest/gtest.h>

#include <stdexcept>

#include "geometry/registry.hpp"
#include "geometry/triangle.hpp"

using namespace geometry;

TEST(HiddenTriangle, HeronArea) {
    Triangle t(3.0, 4.0, 5.0);
    EXPECT_NEAR(t.area(), 6.0, 1e-9);
    EXPECT_EQ(t.name(), "triangle");
}

TEST(HiddenTriangle, RejectsInvalidSides) {
    EXPECT_THROW(Triangle(1.0, 2.0, 3.0), std::invalid_argument);
    EXPECT_THROW(Triangle(-1.0, 2.0, 2.0), std::invalid_argument);
    EXPECT_THROW(Triangle(1.0, 1.0, 5.0), std::invalid_argument);
}

TEST(HiddenTriangle, ParseShape) {
    auto s = parse_shape("triangle 3 4 5");
    EXPECT_EQ(s->name(), "triangle");
    EXPECT_NEAR(s->area(), 6.0, 1e-9);
    EXPECT_THROW(parse_shape("triangle 3 4"), std::invalid_argument);
}
'''

HIDDEN_CPP_TOTAL = r'''#include <gtest/gtest.h>

#include "geometry/registry.hpp"

using namespace geometry;

TEST(HiddenTotal, SumsAllShapes) {
    auto shapes = parse_shapes("rect 1 2\nrect 3 1\n");
    EXPECT_DOUBLE_EQ(total_area(shapes), 5.0);
}

TEST(HiddenTotal, SingleShape) {
    auto shapes = parse_shapes("rect 2 2\n");
    EXPECT_DOUBLE_EQ(total_area(shapes), 4.0);
}

TEST(HiddenTotal, Empty) {
    ShapeList none;
    EXPECT_DOUBLE_EQ(total_area(none), 0.0);
}
'''

HIDDEN_C_PEEK_CLEAR = r'''#include <gtest/gtest.h>

#include "ringbuf.h"

TEST(HiddenPeek, OldestWithoutRemoving) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 3));
    double v = 0;
    EXPECT_FALSE(rb_peek_oldest(&rb, &v));
    for (double x : {1.0, 2.0, 3.0, 4.0}) {
        rb_push(&rb, x);
    }
    ASSERT_TRUE(rb_peek_oldest(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 2.0);
    EXPECT_EQ(rb_size(&rb), 3u);
    rb_free(&rb);
}

TEST(HiddenClear, EmptiesAndKeepsWorking) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 2));
    rb_push(&rb, 1.0);
    rb_push(&rb, 2.0);
    rb_clear(&rb);
    EXPECT_EQ(rb_size(&rb), 0u);
    double v = 0;
    EXPECT_FALSE(rb_pop(&rb, &v));
    rb_push(&rb, 5.0);
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(v, 5.0);
    rb_free(&rb);
}
'''

HIDDEN_C_MEAN = r'''#include <gtest/gtest.h>

#include "ringbuf.h"

TEST(HiddenMean, AfterWrapAndPop) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 3));
    for (double x : {1.0, 2.0, 3.0, 4.0}) {
        rb_push(&rb, x);
    }
    double v = 0;
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 3.5);
    ASSERT_TRUE(rb_pop(&rb, &v));
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 4.0);
    rb_free(&rb);
}

TEST(HiddenMean, FullAfterWrap) {
    RingBuf rb;
    ASSERT_TRUE(rb_init(&rb, 3));
    for (double x : {1.0, 2.0, 3.0, 4.0, 5.0}) {
        rb_push(&rb, x);
    }
    EXPECT_DOUBLE_EQ(rb_mean(&rb), 4.0);
    rb_free(&rb);
}
'''

HIDDEN_ROS_COMPOSE = '''#include <gtest/gtest.h>

#include <cmath>

#include "amr_utils/odom_math.hpp"

using amr_utils::Pose2D;

TEST(HiddenCompose, IdentityLeft) {
  Pose2D r = amr_utils::compose(Pose2D{}, Pose2D{1.0, 2.0, 0.3});
  EXPECT_NEAR(r.x, 1.0, 1e-9);
  EXPECT_NEAR(r.y, 2.0, 1e-9);
  EXPECT_NEAR(r.theta, 0.3, 1e-9);
}

TEST(HiddenCompose, RotatedFrame) {
  Pose2D r = amr_utils::compose(Pose2D{1.0, 1.0, M_PI / 2.0}, Pose2D{2.0, 0.0, 0.0});
  EXPECT_NEAR(r.x, 1.0, 1e-9);
  EXPECT_NEAR(r.y, 3.0, 1e-9);
  EXPECT_NEAR(r.theta, M_PI / 2.0, 1e-9);
}

TEST(HiddenCompose, ThetaWraps) {
  Pose2D r = amr_utils::compose(Pose2D{0.0, 0.0, 3.0}, Pose2D{0.0, 0.0, 0.5});
  EXPECT_NEAR(r.theta, 3.5 - 2.0 * M_PI, 1e-9);
}

TEST(HiddenCompose, ConstInputs) {
  const Pose2D a{0.5, -0.5, -0.4};
  const Pose2D b{1.0, 1.0, 0.2};
  Pose2D r = amr_utils::compose(a, b);
  EXPECT_NEAR(r.x, 0.5 + std::cos(-0.4) - std::sin(-0.4), 1e-9);
  EXPECT_NEAR(r.y, -0.5 + std::sin(-0.4) + std::cos(-0.4), 1e-9);
  EXPECT_NEAR(r.theta, -0.2, 1e-9);
}
'''

HIDDEN_ROS_NORMALIZE = '''#include <gtest/gtest.h>

#include <cmath>

#include "amr_utils/odom_math.hpp"

TEST(HiddenNormalize, NegativeWraps) {
  EXPECT_NEAR(amr_utils::normalize_angle(-3.0 * M_PI / 2.0), M_PI / 2.0, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-4.0), -4.0 + 2.0 * M_PI, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-7.0), -7.0 + 2.0 * M_PI, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-10.0), -10.0 + 4.0 * M_PI, 1e-9);
}

TEST(HiddenNormalize, PositiveStillWorks) {
  EXPECT_NEAR(amr_utils::normalize_angle(7.0), 7.0 - 2.0 * M_PI, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(0.5), 0.5, 1e-9);
  EXPECT_NEAR(amr_utils::normalize_angle(-0.5), -0.5, 1e-9);
}

TEST(HiddenNormalize, RotateBackwardsKeepsRange) {
  amr_utils::Pose2D p;
  for (int i = 0; i < 40; ++i) {
    p = amr_utils::integrate_diff_drive(p, 0.0, -1.0, 0.1);
  }
  EXPECT_GT(p.theta, -M_PI);
  EXPECT_LE(p.theta, M_PI);
  EXPECT_NEAR(p.theta, -4.0 + 2.0 * M_PI, 1e-6);
}
'''

HIDDEN_ROS_BATTERY = '''import pytest

from amr_tools.battery import is_low, percent


def test_hidden_is_low():
    assert is_low(22.3) is True
    assert is_low(25.0) is False
    assert is_low(23.6, threshold=60.0) is True
    assert is_low(24.5, threshold=60.0) is False


def test_hidden_is_low_bad_threshold():
    with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
        is_low(23.0, threshold=150)
    with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
        is_low(23.0, threshold=-1)


def test_hidden_percent_unchanged():
    assert percent(23.6) == pytest.approx(50.0)
    assert percent(30.0) == 100.0
'''

SCENARIOS = [
    {"id": "feature_restock", "fixture": "inventory_app", "desc": "同一個類別：新增方法＋修改既有方法的行為＋測試",
     "task": ("在 Inventory 新增 restock_below(threshold, amount) 方法：所有 qty < threshold 的品項 qty 加上 amount，回傳補貨品項名稱的"
              "排序清單。另外 remove() 在要移除的數量大於庫存時要 raise ValueError(\"not enough stock\")，而且不能改變任何東西。"
              "兩個行為都要加上測試。"),
     "hidden_tests": {"tests/test_hidden_restock.py": HIDDEN_RESTOCK}},
    {"id": "rename_cross_file", "fixture": "inventory_app", "desc": "跨檔改名：方法改名、所有使用處一起改＋CLI 新子指令",
     "task": ("把 Inventory.total_value() 改名為 total()，專案裡所有用到的地方（程式與測試）都要一起改；另外在 CLI 新增 total 子指令，"
              "印出總價值（兩位小數，例如 8.00）。"),
     "hidden_tests": {"tests/test_hidden_rename.py": HIDDEN_RENAME},
     "absent": {"pattern": r"(\.total_value\b|def total_value\b)", "dirs": ["inventory", "tests"]}},   # 方法的定義與呼叫（區域變數同名不算）
    {"id": "feature_csv_export", "fixture": "inventory_app", "desc": "多檔功能：storage 新函式＋CLI 新子指令＋測試",
     "task": ("新增 CSV 匯出：inventory/storage.py 新增 export_csv(inv, path)，寫出 CSV（標題列 name,price,qty，之後每個品項一列、"
              "依名稱排序，price 固定兩位小數）；CLI 新增 export 子指令（python3 -m inventory.cli --file inv.json export out.csv）"
              "呼叫它；並加上測試。"),
     "hidden_tests": {"tests/test_hidden_csv.py": HIDDEN_CSV}},
    {"id": "bugfix_textstats", "fixture": "textstats_app", "desc": "除錯：測試失敗，找出 bug 修正程式（不能改測試）",
     "task": "這個專案的測試有好幾個失敗，找出原因並修正程式。不要修改 tests/ 裡的測試。",
     "unchanged": ["tests/test_stats.py", "tests/test_report.py"]},
    {"id": "long_category_feature", "fixture": "inventory_app", "desc": "較長的跨檔功能：資料結構→商業邏輯→儲存（相容舊檔）→CLI→測試，5 個檔案",
     "task": ("幫品項加上分類（category）：\n"
              "1. inventory/models.py 的 Item 新增欄位 category: str，預設 \"general\"。\n"
              "2. Inventory.add(name, price, qty=1, category=\"general\")：新品項記下分類；品項已存在時只加數量（分類跟單價一樣以第一次為準）。\n"
              "3. Inventory 新增 by_category()：回傳 dict，key 是分類、value 是那個分類的品項名稱排序清單。\n"
              "4. inventory/storage.py 存檔時要存 category；讀檔時沒有 category 欄位的舊檔一律當成 \"general\"（舊的 JSON 檔要能讀）。\n"
              "5. CLI：add 子指令新增 --category 選項（預設 general），例如 python3 -m inventory.cli --file inv.json add apple 1.5 4 --category fruit；"
              "新增 categories 子指令，每個分類印一行「分類: 品項數」，依分類名稱排序，例如 fruit: 2。\n"
              "6. 每個行為都加上測試。"),
     "hidden_tests": {"tests/test_hidden_category.py": HIDDEN_CATEGORY}},
    {"id": "new_module", "fixture": "inventory_app", "desc": "新模組：照規格建立新檔＋使用既有類別＋測試",
     "task": ("新增 inventory/discount.py，提供 apply_discount(price, percent)：回傳打折後的價格（percent 是 0～100 的折扣百分比，"
              "超出範圍 raise ValueError(\"percent must be between 0 and 100\")，結果四捨五入到小數兩位）；以及 discounted_total(inv, percent)："
              "整個 Inventory 的總價值打折後的金額（同樣四捨五入兩位）。並寫測試。"),
     "hidden_tests": {"tests/test_hidden_discount.py": HIDDEN_DISCOUNT}},
    # ---- C／C++（真的 gtest）
    {"id": "cpp_perimeter", "fixture": "geometry_cpp", "lang": "cpp", "desc": "C++ 跨檔：介面加純虛擬方法、兩個子類別的標頭與實作、gtest 測試",
     "task": ("在 Shape 介面（include/geometry/shape.hpp）新增純虛擬方法 double perimeter() const（周長）；Circle 與 Rectangle 都要實作"
              "（標頭宣告、src/ 裡的實作）：Circle 是 2πr、Rectangle 是 2×(寬＋高)。並在 tests/ 加上 gtest 測試。"),
     "hidden_tests": {"tests/test_hidden_perimeter.cpp": HIDDEN_CPP_PERIMETER}},
    {"id": "cpp_triangle", "fixture": "geometry_cpp", "lang": "cpp", "desc": "C++ 新類別：新標頭＋新實作＋解析器支援＋gtest 測試",
     "task": ("新增三角形：include/geometry/triangle.hpp 與 src/triangle.cpp，類別 geometry::Triangle 繼承 Shape，建構子 "
              "Triangle(double a, double b, double c)（三邊長）；name() 回傳 \"triangle\"，area() 用海龍公式。任何一邊 <= 0、或不能組成"
              "三角形（任兩邊的和 <= 第三邊）時，建構子丟出 std::invalid_argument。src/registry.cpp 的 parse_shape 要支援 "
              "\"triangle a b c\"（少了邊長時丟出 std::invalid_argument）。並在 tests/ 加上 gtest 測試。"),
     "hidden_tests": {"tests/test_hidden_triangle.cpp": HIDDEN_CPP_TRIANGLE}},
    {"id": "cpp_bugfix_total", "fixture": "geometry_cpp", "lang": "cpp", "desc": "C++ 除錯：從症狀找出 bug、修正、加回歸測試",
     "task": ("geometry_cli 印出的 total（總面積）不對：檔案裡有 rect 1 2 與 rect 3 1 兩行時，total 應該是 5.00，實際卻印出 2.00。"
              "找出原因並修正，再加一個能抓到這個問題的 gtest 測試。"),
     "hidden_tests": {"tests/test_hidden_total.cpp": HIDDEN_CPP_TOTAL}},
    {"id": "c_ringbuf_api", "fixture": "ringbuf_c", "lang": "c", "desc": "C 新增 API：標頭宣告＋實作＋gtest（C++）測試",
     "task": ("在環形緩衝區新增兩個函式：bool rb_peek_oldest(const RingBuf *rb, double *out)——把最舊的值放到 *out 但不取出，"
              "緩衝區是空的時回傳 false；void rb_clear(RingBuf *rb)——清空所有元素（容量不變，之後可以繼續放）。宣告放在 "
              "include/ringbuf.h、實作放在 src/ringbuf.c，並在 tests/ 加上 gtest 測試。"),
     "hidden_tests": {"tests/test_hidden_peek_clear.cpp": HIDDEN_C_PEEK_CLEAR}},
    {"id": "c_bugfix_mean", "fixture": "ringbuf_c", "lang": "c", "desc": "C 除錯：環形緩衝區繞回後平均算錯",
     "task": ("rb_mean 在緩衝區繞回（wrap around）又取出元素（rb_pop）之後會算錯平均：例如容量 3，依序放入 1、2、3、4 之後取出一個，"
              "剩下 3 和 4，平均應該是 3.5。找出原因、修正 src/ringbuf.c，並加一個能抓到這個問題的 gtest 測試。"),
     "hidden_tests": {"tests/test_hidden_mean.cpp": HIDDEN_C_MEAN}},
    # ---- ROS 2 colcon 工作區（這台主機沒有 ROS 2）
    {"id": "ros2_cpp_compose", "fixture": "ros2_ws", "lang": "cpp", "desc": "ROS 2 C++ 套件：標頭＋實作新增函式、gtest 測試（需要 rclcpp 的跳過）",
     "task": ("在 amr_utils 套件（src/amr_utils）的 odom_math 新增函式 Pose2D compose(const Pose2D& a, const Pose2D& b)：b 是在 a 的座標系"
              "裡的相對位姿，回傳它在世界座標的位姿——x = a.x + cos(a.theta)·b.x − sin(a.theta)·b.y、"
              "y = a.y + sin(a.theta)·b.x + cos(a.theta)·b.y、theta = normalize_angle(a.theta + b.theta)。宣告放在 "
              "include/amr_utils/odom_math.hpp、實作放在 src/odom_math.cpp，並在 test/test_odom_math.cpp 加 gtest 測試。"),
     "hidden_tests": {"src/amr_utils/test/test_hidden_compose.cpp": HIDDEN_ROS_COMPOSE}},
    {"id": "ros2_cpp_bugfix_angle", "fixture": "ros2_ws", "lang": "cpp", "desc": "ROS 2 C++ 除錯：從症狀找出角度正規化的 bug、修正、加回歸測試",
     "task": ("amr_utils 的里程計在機器人往負方向轉超過半圈之後，theta 會跑出 (-π, π] 的範圍：normalize_angle(-3π/2) 應該是 π/2，"
              "實際卻回傳 -3π/2。找出原因、修正 src/amr_utils/src/odom_math.cpp，再在 src/amr_utils/test/test_odom_math.cpp "
              "加一個能抓到這個問題的 gtest 測試。"),
     "hidden_tests": {"src/amr_utils/test/test_hidden_normalize.cpp": HIDDEN_ROS_NORMALIZE}},
    {"id": "ros2_py_battery", "fixture": "ros2_ws", "desc": "ROS 2 Python 套件：純 Python 模組新增函式＋改 rclpy 的 node＋pytest 測試",
     "task": ("在 amr_tools 套件（src/amr_tools）的 amr_tools/battery.py 新增 is_low(voltage, threshold=20.0)：電量百分比"
              "（percent(voltage)）低於 threshold 時回傳 True，否則 False；threshold 不在 0～100 之間時 "
              "raise ValueError(\"threshold must be between 0 and 100\")。amr_tools/battery_node.py 的 BatteryMonitor 收到電量低的訊息時，"
              "改用 self.get_logger().warning 印出 battery low: 加上百分比（一位小數，例如 battery low: 9.4%）。"
              "並在 test/test_battery.py 加 pytest 測試。"),
     "hidden_tests": {"src/amr_tools/test/test_hidden_battery.py": HIDDEN_ROS_BATTERY},
     "contains": {"src/amr_tools/amr_tools/battery_node.py": r"get_logger\(\)\.warn(?:ing)?\(\s*f?['\"]battery low"}},
]

SCENARIO_BY_ID = {s["id"]: s for s in SCENARIOS}
