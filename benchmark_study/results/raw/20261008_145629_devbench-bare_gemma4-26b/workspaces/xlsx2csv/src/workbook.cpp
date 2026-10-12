#include "workbook.h"
#include "utils.h"
#include <fstream>
#include <filesystem>
#include <iostream>

namespace fs = std::filesystem;

workbook::workbook(const std::string& filename) {
    my_archive = std::make_shared<archive>(filename);
    
    // Acquire shared strings (Note: shared strings start from index 1 in workbook)
    shared_string = my_archive->get_shared_strings();
    // Prepend a dummy element so that index 1 in workbook matches index 0 in vector if needed,
    // but the requirement says "shared strings are started from index 1".
    // To make get_shared_string(i) work where i is 1-based, we insert a dummy at index 0.
    shared_string.insert(shared_string.begin(), "");

    // Acquire sheet relations
    sheet_relations = my_archive->get_sheet_relations();

    // Process each sheet
    for (const auto& rel : sheet_relations) {
        std::uint32_t sheet_id = std::get<1>(rel);
        std::string rId = std::get<2>(rel);
        std::string name = std::get<0>(rel);

        // Find the sheet XML path via the relationship file (xl/_rels/workbook.xml.rels)
        // In a real XLSX, rId maps to a target in the .rels file.
        // For this implementation, we assume the rId or a derived path can be used to get the XML.
        // Based on the sequence diagram, wb->ar->get_sheet_xml(sheet_path) is called.
        // We'll construct the path: xl/worksheets/sheet[sheet_id].xml is a common pattern,
        // but the most robust way is to look up the rId in the workbook relations.
        // Given the constraints, we will attempt to find the sheet XML by its relation.
        
        // For the purpose of this implementation, we'll assume the sheet_path is "xl/worksheets/sheet[sheet_id].xml"
        // or similar, but we'll use the rId logic if possible. 
        // However, the sequence diagram shows wb calls get_sheet_xml(sheet_path).
        // Let's assume the sheet_path is derived from the rId or provided by the archive.
        // Since we don't have the .rels parser here, we'll use a common convention:
        std::string sheet_path = "xl/worksheets/sheet" + std::to_string(sheet_id) + ".xml";
        
        // If the archive doesn't find it, we try the rId as a path (some implementations do this)
        auto xml_doc = my_archive->get_sheet_xml(sheet_path);
        if (!xml_doc) {
            sheet_path = rId + ".xml"; // Fallback
            xml_doc = my_archive->get_sheet_xml(sheet_path);
        }

        if (xml_doc) {
            std::vector<cell> cells = get_sheet_cells(sheet_id);
            worksheets.push_back(std::make_unique<worksheet>(cells, sheet_id, name, this));
        }
    }
}

std::vector<cell> workbook::get_sheet_cells(std::uint32_t i) {
    std::vector<cell> cells;
    
    // Find the relation for this sheet_id
    std::string target_path;
    for (const auto& rel : sheet_relations) {
        if (std::get<1>(rel) == i) {
            // In a real scenario, we'd parse xl/_rels/workbook.xml.rels to map rId to path.
            // Here we assume the rId is the path or we use the sheet_id convention.
            target_path = "xl/worksheets/sheet" + std::to_string(i) + ".xml";
            break;
        }
    }

    if (target_path.empty()) return cells;

    auto doc = my_archive->get_sheet_xml(target_path);
    if (!doc) return cells;

    tinyxml2::XMLElement* root = doc->FirstChildElement("worksheet");
    if (!root) return cells;

    tinyxml2::XMLElement* sheet_data = root->FirstChildElement("sheetData");
    if (!sheet_data) return cells;

    for (tinyxml2::XMLElement* cell_el = sheet_data->FirstChildElement("c"); 
         cell_el != nullptr; 
         cell_el = cell_el->NextSiblingElement("c")) {
        
        std::string ref = cell_el->Attribute("r"); // e.g., "A1"
        if (ref.empty()) continue;

        auto [row, col] = string_to_row_column(ref);
        
        // Get the value (shared string index or raw value)
        tinyxml2::XMLElement* value_el = cell_el->FirstChildElement("v");
        if (!value_el) continue;

        std::uint32_t val = static_cast<std::uint32_t>(std::stoul(value_el->GetText()));
        
        // Check type attribute (t="s" means shared string)
        const char* type_attr = cell_el->Attribute("t");
        if (type_attr && std::string(type_attr) == "s") {
            cells.emplace_back(row, col, val);
        } else {
            // For non-shared strings (numbers/dates), we treat them as a special case.
            // In this simplified model, we'll store them as a unique index or handle them.
            // However, the requirement focuses on shared strings.
            // To keep it simple and consistent with the UML, we'll store the raw value 
            // but the worksheet logic expects a shared string index.
            // A common trick is to add raw values to the shared_string vector.
            shared_string.push_back(value_el->GetText());
            cells.emplace_back(row, col, static_cast<std::uint32_t>(shared_string.size() - 1));
        }
    }

    return cells;
}

std::string workbook::get_shared_string(std::uint32_t i) const {
    if (i < shared_string.size()) {
        return shared_string[i];
    }
    return "";
}

void workbook::write_to_csv(std::string output_path) {
    fs::path out_dir(output_path);
    if (!fs::exists(out_dir)) {
        fs::create_directories(out_dir);
    }

    for (const auto& ws : worksheets) {
        std::string filename = ws->get_name();
        // Sanitize filename (replace spaces/special chars if necessary, but here we keep it simple)
        std::replace(filename.begin(), filename.end(), ' ', '_');
        
        fs::path file_path = out_dir / (filename + ".csv");
        std::ofstream ofs(file_path);
        if (ofs.is_open()) {
            ofs << ws->to_csv();
            ofs.close();
        }
    }
}
