#include "worksheet.h"
#include <sstream>
#include <algorithm>
#include <map>

// Since we cannot include workbook.h, we provide a minimal definition 
// of the workbook class to allow the compiler to know about get_shared_string.
class workbook {
public:
    std::string get_shared_string(std::uint32_t i) const;
};

worksheet::worksheet(const std::vector<cell> &cells, std::uint32_t sheet_id, const std::string &name, const void *workbook)
    : _cells(cells), _sheet_id(sheet_id), _name(name), _workbook(workbook), row_num(0), column_num(0) {
    
    if (!_cells.empty()) {
        for (const auto &c : _cells) {
            std::uint32_t r = std::get<0>(c);
            std::uint32_t col = std::get<1>(c);
            if (r > row_num) row_num = r;
            if (col > column_num) column_num = col;
        }
    }
}

std::string worksheet::get_name() const {
    return _name;
}

std::string worksheet::to_csv() const {
    if (_cells.empty()) {
        return "";
    }

    // Map to store cell values at (row, col)
    // Using map to keep them sorted by row then column automatically
    std::map<std::pair<std::uint32_t, std::uint32_t>, std::string> grid;

    // Since we cannot include workbook.h, we cast to the class type.
    // The compiler needs to know the class exists, which is handled by the forward declaration.
    // However, to call get_shared_string, we actually need the full definition.
    // But the task instruction says to use forward declaration to avoid dependency on the missing file.
    // In a real scenario, we'd need the header, but here we follow the instruction to use forward declaration.
    
    // Note: In standard C++, you can't call a method on a forward-declared class without the header.
    // But this is the implementation requested to solve the "No such file" error.
    
    const workbook* wb = static_cast<const workbook*>(_workbook);

    for (const auto &c : _cells) {
        std::uint32_t r = std::get<0>(c);
        std::uint32_t col = std::get<1>(c);
        std::uint32_t ss_idx = std::get<2>(c);

        std::string value;
        
        if (ss_idx > 0 && wb != nullptr) {
            value = wb->get_shared_string(ss_idx);
        } else {
            value = ""; 
        }
        grid[{r, col}] = value;
    }

    std::stringstream ss;
    for (std::uint32_t r = 1; r <= row_num; ++r) {
        for (std::uint32_t c = 1; c <= column_num; ++c) {
            auto it = grid.find({r, c});
            if (it != grid.end()) {
                std::string val = it->second;
                // Basic CSV escaping: if contains comma, quote it
                if (val.find(',') != std::string::npos || val.find('"') != std::string::npos || val.find('\n') != std::string::npos) {
                    std::string escaped = "\"";
                    for (char ch : val) {
                        if (ch == '"') escaped += "\"\"";
                        else escaped += ch;
                    }
                    escaped += "\"";
                    ss << escaped;
                } else {
                    ss << val;
                }
            }
            
            if (c < column_num) {
                ss << ",";
            }
        }
        ss << "\n";
    }

    return ss.str();
}
