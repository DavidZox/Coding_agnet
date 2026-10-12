#ifndef WORKBOOK_H
#define WORKBOOK_H

#include <string>
#include <vector>
#include <memory>
#include <tuple>
#include <unordered_map>
#include "worksheet.h" // Include worksheet.h to ensure Worksheet is fully defined
#include "archive.h"  // Include archive.h to ensure Archive is fully defined
#include "types.h"    // Include types.h for sheet_desc and cell definitions

// Types defined in types.h (now fully available via include/types.h)
// using sheet_desc = std::tuple<std::string, std::uint32_t, std::string>;
// using cell = std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>;

class Workbook {
public:
    // Constructor
    Workbook(const std::string& xlsx_filename);

    // Public methods
    void write_to_csv(std::string output_path);
    std::string get_shared_string(std::uint32_t i) const;

private:
    // Member variables
    std::vector<std::unique_ptr<Worksheet>> worksheets;
    std::vector<sheet_desc> sheet_relations;
    std::vector<std::string> shared_string;
    std::shared_ptr<Archive> my_archive;
    
    // Private helper methods
    std::vector<cell> get_sheet_cells(std::uint32_t sheet_id);
};

#endif // WORKBOOK_H
