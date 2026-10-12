#include "worksheet.h"
#include <sstream>
#include "workbook.h"
#include "types.h"

namespace xlsx2csv {

class Worksheet {
public:
    Worksheet(const std::vector<xlsx2csv::cell>& cells, std::uint32_t sheet_id, const std::string& name, const xlsx2csv::Workbook* workbook_ptr)
        : _name(name), _sheet_id(sheet_id), _workbook(workbook_ptr), _cells(cells) {
        // Determine the number of rows and columns
        row_num = 0;
        column_num = 0;
        for (const auto& c : cells) {
            row_num = std::max(row_num, std::get<0>(c));
            column_num = std::max(column_num, std::get<1>(c));
        }
        row_info.resize(row_num);
        for (const auto& c : cells) {
            row_info[std::get<0>(c) - 1].push_back(std::get<1>(c));
        }
    }

    std::string get_name() const {
        return _name;
    }

    std::string to_csv() const {
        std::ostringstream csv_stream;
        for (std::uint32_t row = 0; row < row_num; ++row) {
            for (std::uint32_t col = 0; col < column_num; ++col) {
                if (col > 0) {
                    csv_stream << ",";
                }
                bool found = false;
                for (const auto& cell : _cells) {
                    if (std::get<0>(cell) == row + 1 && std::get<1>(cell) == col + 1) {
                        std::uint32_t shared_string_idx = std::get<2>(cell);
                        csv_stream << _workbook->get_shared_string(shared_string_idx);
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    csv_stream << "";
                }
            }
            csv_stream << "\n";
        }
        return csv_stream.str();
    }

private:
    const std::string _name;
    const std::uint32_t _sheet_id;
    const xlsx2csv::Workbook* _workbook;
    const std::vector<xlsx2csv::cell> _cells;
    std::uint32_t row_num;
    std::uint32_t column_num;
    std::vector<std::vector<std::uint32_t>> row_info;
};

} // namespace xlsx2csv
