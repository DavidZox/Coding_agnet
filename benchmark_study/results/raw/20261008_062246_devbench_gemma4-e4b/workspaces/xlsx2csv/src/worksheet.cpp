#include "worksheet.h"
#include "workbook.h"
#include <sstream>
#include <iostream>

Worksheet::Worksheet(const std::vector<cell>& cells, std::uint32_t sheet_id, const std::string& name, Workbook* workbook_ptr)
    : _cells(cells), _sheet_id(sheet_id), _name(name), _workbook(workbook_ptr) {}

std::string Worksheet::get_name() const {
    return _name;
}

std::string Worksheet::to_csv() const {
    std::stringstream csv_stream;
    
    // 獲取 Workbook 指針
    Workbook* workbook_ptr = _workbook;

    if (!workbook_ptr) {
        // 處理 Workbook 指針為空的情況，雖然在設計上不應該發生
        return ""; 
    }

    // 遍歷所有儲存的 cell
    // 為了模擬多行 CSV，我們需要一個機制來追蹤當前正在處理的行。
    // 由於 _cells 是 std::vector<cell>，我們必須假設它已經按行順序排列，
    // 並且我們需要一個邏輯來判斷一行結束。
    
    // 由於我們沒有明確的行結束標記，我們將依賴於 row_id 的變化來模擬換行。
    // 我們需要一個變數來追蹤前一個 row_id。
    std::uint32_t last_row_id = 0;
    std::vector<std::string> current_row_values;

    for (const auto& cell : _cells) {
        // cell: std::tuple<row_id, column_id, shared_string_id>
        std::uint32_t row_id = std::get<0>(cell);
        std::uint32_t col_id = std::get<1>(cell);
        std::uint32_t ss_idx = std::get<2>(cell);

        // 獲取共享字串
        std::string cell_value = workbook_ptr->get_shared_string(ss_idx);

        // 檢查是否換行 (row_id 改變)
        if (row_id != last_row_id && last_row_id != 0) {
            // 輸出前一行數據
            for (size_t i = 0; i < current_row_values.size(); ++i) {
                csv_stream << current_row_values[i];
                if (i < current_row_values.size() - 1) {
                    csv_stream << ",";
                }
            }
            csv_stream << "\n";
            
            // 開始新的一行
            current_row_values.clear();
        }
        
        // 將當前 cell 的值加入當前行
        current_row_values.push_back(cell_value);
        last_row_id = row_id;
    }
    
    // 輸出最後一行數據
    if (!current_row_values.empty()) {
        for (size_t i = 0; i < current_row_values.size(); ++i) {
            csv_stream << current_row_values[i];
            if (i < current_row_values.size() - 1) {
                csv_stream << ",";
            }
        }
        csv_stream << "\n";
    }
    
    return csv_stream.str();
}
