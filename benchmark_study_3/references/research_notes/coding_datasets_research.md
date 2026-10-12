> 編碼任務的資料集調查：2026-10-10 開始這次評測前，委派給研究用的子代理做的網路調查（原文是英文，照原樣保存；報告裡引用的數字以原始論文為準，標 UNVERIFIED 的是調查時沒能確認的）。

# Evaluation datasets for small, tested Python and C++ projects (checked 2026-10-10)

**Bottom line:** no public benchmark fits the scope well. The best base is your own DevBench copy (7 Python + 5 C++ small repos, already local). Turn it into test-writing, bug-fix and feature tasks, add Aider polyglot (C++ + Python) to compare against published numbers, and score test writing mainly by mutation score. Everything runs offline without Docker or root. I made no code changes; this is web research plus reading your local DevBench copy.

## 1. DevBench unit and acceptance testing (you already have the data)
- **Links:** [arXiv 2403.08604](https://arxiv.org/abs/2403.08604) · [open-compass/DevEval](https://github.com/open-compass/DevEval)
- **License:** code Apache-2.0, data CC BY 4.0
- **Local copy:** `/home/amr-base/Coding_agent_harness/benchmark_study/datasets/devbench_subset` (about 7 MB)

**What the model gets:** the PRD, UML diagrams and architecture design. Source code is included only when the `read_src_code` flag is set. Acceptance testing and unit testing are two separate tasks.

**How it is scored:**
- **Oracle Test:** the generated tests run against the reference implementation, and the score is the percentage that pass. I could not confirm whether this is counted per test case (UNVERIFIED).
- **Coverage:** executed statements ÷ all statements.
- Each repo counts equally in the average. Coverage numbers in parentheses below cover only repos whose generated tests actually ran.
- There is no mutation score and no per-language breakdown.

**How C++ coverage is measured** (I checked your local copy): `makefile_test` compiles with `-fprofile-arcs -ftest-coverage`, then runs `gcov -r -b` on the `src/*.cpp` files. That gives line percentage plus branch data. It has problems:
- graph-cpp is header-only, so gcov measures almost nothing there.
- people_management counts its own test file in the coverage.
- The released Python harness runs `pytest --cov=.`, which also counts the test files.
- Your machine only has `gcov-11`; there is no plain `gcov` command, so these makefiles will fail as written.

**Published results** (unit testing excludes the 2 JavaScript repos):

| Model | Acceptance | Unit oracle | Coverage (executable repos only) |
|---|---|---|---|
| GPT-4-Turbo-0125 | 29.2 | 36.5 | 33.2 (66.3) |
| GPT-4-Turbo-1106 | 25.9 | 33.6 | 36.7 (66.7) |
| DeepSeek-Coder-33B | 13.6 | 32.8 | 35.7 (79.4) |
| CodeLlama-34B | 4.5 | 21.1 | 25.4 (72.6) |
| DeepSeek-Coder-6.7B | 20.5 (the paper calls these tests "meaningless but executable") | 23.5 | 28.2 (70.6) |

## 2. Test-generation benchmarks

| Benchmark | Languages / size | Project size | Metrics | Docker / offline | Results for 7–35B models |
|---|---|---|---|---|---|
| **TestGenEval** 2024 [2410.00752](https://arxiv.org/abs/2410.00752), HF `kjain14/testgeneval` and `kjain14/testgenevallite`, CC-BY-NC | Python only: 1,210 file pairs from 11 SWE-bench repos; Lite has 160 | Large (code files average ~782 LOC) | pass@1 (any test / all tests), line coverage, mutation score (cosmic-ray) | Docker required (image size UNVERIFIED) | Codestral-22B 72.7 / 33.0 / 14.2 (pass / coverage / mutation); Gemma-2-27B 57.7 / 30.1 / 14.6; Llama-3.1-8B 30.5 / 14.1 / 6.8; GPT-4o 64.0 / 35.2 / 18.8 |
| **TestEval** 2024 [2406.04531](https://arxiv.org/abs/2406.04531), MIT, 0.6 MB | Python: 210 LeetCode programs | Single function | Overall line/branch coverage; coverage of specific target lines, branches and paths | No Docker | DeepSeek-Coder-33B 94.9% line, 70.5% on target lines; CodeLlama-7B 86.1 / 58.1; GPT-4o 98.7 / 81.0 |
| **ProjectTest** (since renamed MultiFileTest) 2025 [2502.06556](https://arxiv.org/abs/2502.06556), [GitHub](https://github.com/YiboWANG214/ProjectTest), MIT, ~12 MB | 20 projects each in Python, Java and JavaScript; **no C++** | Python averages 6.1 files / 655 LOC | Compile rate, correctness, line/branch coverage | No Docker | DeepSeek-Coder-6.7B 37% correct / 39% line coverage; CodeQwen1.5-7B 24 / 43; Claude-3.5-Sonnet 64 / 51 |
| CITYWALK 2025 [2501.16155](https://arxiv.org/abs/2501.16155) | C++ with GoogleTest, 1,288 target methods | 10 projects, 1.9k–149k LOC | Line/branch coverage (llvm-cov) | Artifact on Zenodo (license UNVERIFIED) | A method paper, not a reusable benchmark |
| CPP-UT-Bench 2024 [2412.02735](https://arxiv.org/abs/2412.02735), CC BY 4.0 | C++, 2,653 code/test pairs | 14 large repos | **An LLM judges the tests; they are never run** | — | Not usable for execution scoring |

**Out of scope:**
- SWT-bench [2406.12952](https://arxiv.org/abs/2406.12952): Python SWE-bench repos, Docker, about 120 GB.
- TAM-Eval [2601.18241](https://arxiv.org/abs/2601.18241): Python, Java and Go test maintenance in 192 real repos, Docker, mutation via mutpy.
- ChatUniTest, ChatTester and HITS are Java-only.
- XRepoTest [2608.25939](https://arxiv.org/abs/2608.25939) covers only Rust, Go, Julia, PHP and Ruby.

**DevBench's 5 C++ repos are the only executable unit-test benchmark on small C++ projects.**

**Coverage alone barely separates models:**
- On TestEval, even 7B models exceed 85% line coverage.
- [2609.24341](https://arxiv.org/abs/2609.24341) found coverage "near its ceiling".
- Mutation score does separate them: on TestGenEval, GPT-4o reaches 35% coverage but only 19% mutation score.

## 3. Multi-file editing on small repos

| Benchmark | Tasks | Files changed | Evaluation | Results for 7–35B models |
|---|---|---|---|---|
| **Aider polyglot** 2024 ([blog](https://aider.chat/2024/12/21/polyglot.html), [repo](https://github.com/Aider-AI/polyglot-benchmark); Exercism exercises, MIT; ~1 MB) | 225 total; **C++ 26, Python 34** | C++: always a `.h` and a `.cpp`; Python: 1 file (33 of 34) | Hidden tests: C++ uses **Catch2, not GoogleTest**; Python uses pytest. Two tries, the second with the test output. Docker is recommended for safety but not required | Qwen2.5-Coder-32B 16.4% (whole-file edits) / 8.0% (diff edits); gemma-3-27b 4.9%; Qwen3-32B 40.0% |
| RES-Q 2024 [2406.16801](https://arxiv.org/abs/2406.16801), MIT | 100 (95 Python, 5 JS) | 1–6 files (49 single-file), in 14 mid-size repos (median 6.5k LOC) | Test scripts in conda environments, no Docker | DeepSeek-Coder-V2 26%, Llama-3-70B 20%, Qwen2-72B 16% |
| CanItEdit 2023 [2312.12450](https://arxiv.org/abs/2312.12450), MIT, 255 kB | 105 Python | 1 file (~45 LOC) | Hidden tests | DeepSeek-Coder-33B 49.8%, DeepSeek-Coder-6.7B 41.0%, StarCoder2-15B 42.0%, GPT-4 63.3% |
| CodeEditorBench 2024 [2404.03543](https://arxiv.org/abs/2404.03543) | 7,961 tasks in C++, Java and Python | 1 file (competitive programming) | Online judge running in Docker | DeepSeek-Coder-33B win rate 0.74 |
| ClassEval 2023 [2308.01861](https://arxiv.org/abs/2308.01861), data CC BY-NC | 100 Python classes | 1 class | 33 tests per class | GPT-4 37.6%, WizardCoder 12.2% |
| LiveRepoReflection 2025 [2507.09866](https://arxiv.org/abs/2507.09866) | 1,888 synthetic tasks (Python 820, C++ 143) | About 8 files per task | Tests | Qwen3-32B: Python 7.7%, C++ 5.6% (almost everything fails) |

**Confirmed out of scope:**
- **Large repos:**
  - EvoCodeBench [2404.00599](https://arxiv.org/abs/2404.00599): 25 real repos.
  - FEA-Bench [2503.06680](https://arxiv.org/abs/2503.06680): 1,401 tasks across 83 repos.
  - NoCode-bench, now renamed Doc2Feat-Bench [2507.18130](https://arxiv.org/abs/2507.18130): 634 tasks across 10 projects, Docker.
- **From scratch, not edits:** Commit0 [2412.01769](https://arxiv.org/abs/2412.01769): 54 libraries, Docker or Modal; Llama-3.1-70B scores 2.5%.

## 4. Bug datasets

**C/C++:**
- Defects4C [2510.11059](https://arxiv.org/abs/2510.11059): 248 bugs in 41 real projects, Docker. GPT-4 fixes 9.0%, DeepSeek-Coder-6.7B 1.2%.
- [BugsC++](https://github.com/Suresoft-GLaDOS/bugscpp): 215 bugs in 27 projects, Docker required.
- [IntroClass / ManyBugs](https://repairbenchmarks.cs.umass.edu/) (BSD): IntroClass has 998 defects in 6 tiny C programs; ManyBugs is large C code.
- [Codeflaws](https://github.com/codeflaws/codeflaws): 3,902 defects in single-file C programs, with held-out tests.
- DebugBench [2401.04621](https://arxiv.org/abs/2401.04621): scored by submitting to LeetCode's online judge, so it **cannot run offline**.
- HumanEvalFix (`bigcode/humanevalpack`, MIT): 164 tasks each in Python and C++. Qwen2.5-Coder-7B fixes 78.7% in Python and 49.4% in C++ (reported in [2503.17793](https://arxiv.org/abs/2503.17793)).
- None of these fits: each is either a large project or a single-file program.

**Python:**
- QuixBugs: 40 one-line bugs.
- BugsInPy: 493 bugs in 17 large projects.
- ConDefects: 1,625 single-file programs.
- All weak fits.

**SWE-smith** [2504.21798](https://arxiv.org/abs/2504.21798) (MIT):
- **Method:** it injects bugs into working code and keeps those that break at least one passing test. An LM then writes the issue text from the diff and the failing test's output.
- **Success rate per bug-generation strategy:**
  - LM-modified code: 56%.
  - Automatic syntax-tree edits: 40%.
  - Combining existing bugs: 97%.
- **C++ support:** the [repo](https://github.com/SWE-bench/SWE-smith) now includes C++ edit rules (flip operators, remove conditionals, loops or assignments, change constants, shuffle lines).
- **Running without Docker:** the official pipeline needs Docker. Calling the C++ edit rules directly on a small repo should work (UNVERIFIED).

## 5. Tools (no root needed unless stated)
- **Python:**
  - coverage.py and pytest-cov are already in your venv; add `--cov-branch` for branch coverage.
  - mutmut 3.8 (pip, BSD) needs fork support and works with pytest only.
  - cosmic-ray 8.7 (pip, MIT) is the tool TestGenEval uses.
- **C++:**
  - gcov comes with GCC. Symlink `gcov-11` to `gcov`, or pass `--gcov-executable gcov-11` to gcovr.
  - gcovr 8.6 (pip, BSD) is already in your venv; it gives line and branch coverage as JSON.
  - universalmutator 1.14.1 (pip, MIT) mutates code with regular expressions, so it works with any compiler, including your g++-11. Usage: `analyze_mutants file.cpp "make test"`.
  - The SWE-smith C++ edit rules from section 4.
- **Need clang/LLVM, which is not installed here and not available via pip:**
  - llvm-cov.
  - [Mull](https://github.com/mull-project/mull) 0.34: deb/rpm packages, needs a matching LLVM version.
  - [Dredd](https://github.com/mc-imperial/dredd): needs the Clang 17 packages.
  - dextool: needs a D compiler plus LLVM.

## 6. Recommendation: about 70 tasks, offline, no Docker
1. **DevBench-based suite on existing code: 12 repos (7 Python, 5 C++, 2–11 files each), about 48 tasks.** The reference implementation is the starting code; the official unit and acceptance tests are hidden and used for scoring.
   - **(a) Test writing, 12 tasks:** delete the tests, give the source code, and ask for pytest or GoogleTest tests.
   - **(b) Bug fixing, 24 tasks:** inject bugs the SWE-smith way and keep only those that make the official tests fail. About half should combine 2–3 bugs in different files.
   - **(c) Feature re-implementation, 12 tasks:** remove a feature that spans 2–5 files and ask for it back from the PRD.
   - Caveat: the Python repos are public GitHub projects that models may have seen. Injected bugs and removed features reduce this risk.
2. **Aider polyglot, 10 C++ + 10 Python exercises:** lets you compare against the published numbers in section 3. Each exercise ships a reference solution (`.meta/example.*`), so these can also become test-writing tasks.
3. **ProjectTest Python, 5–8 projects:** multi-file test writing with published numbers for 7B models.
4. **Optional:** CanItEdit and TestEval as quick single-file checks. For more C++, the Exercism C++ track has 86 exercises (MIT).

**How to score test writing.** Report each part separately, then combine:
1. **Hygiene:**
   - The agent may change test files only.
   - Every test needs at least one assertion.
   - Run the tests twice to catch flaky ones.
2. **Validity:** pass rate on the reference code (DevBench's Oracle Test). Drop the failing tests.
3. **Line and branch coverage of the production code** by the passing tests. This also avoids the DevBench coverage problems from section 1.
   - Python: `pytest --cov=<pkg> --cov-branch --cov-report=json`
   - C++: `gcovr --filter 'src/|include/' --exclude 'unit_tests/' --json-summary`
4. **Mutation score:**
   - **Tools:** mutmut or cosmic-ray for Python; universalmutator or the SWE-smith C++ edit rules for C++.
   - **Filter:** keep only mutants that the official test suite kills. This removes mutants that don't actually change behaviour.
   - **Score:** mutants killed by the generated tests ÷ mutants killed by the official tests.
   - **Cap:** about 50–100 mutants per repo.
5. **Bug detection:** run the generated tests against the bugs from task (b). Score = fraction of bugs where at least one test fails.

**Suggested combined score:** the tests must first pass the validity check; then score = 0.5 × mutation score + 0.3 × branch coverage relative to the official tests + 0.2 × bug detection.
