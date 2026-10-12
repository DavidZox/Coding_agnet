#include "archive.h"
#include "miniz.h"
#include "tinyxml2.h"
#include <iostream>
#include <stdexcept>

archive::archive(const std::string& filename) : filename_(filename) {
    // In a real implementation, we might validate the zip file here.
}

archive::~archive() {
}

std::vector<sheet_desc> archive::get_sheet_relations() {
    std::vector<sheet_desc> relations;
    std::string xml_str = get_uncompressed_file("xl/worksheets/_rels/workbook.xml.rels");
    if (xml_str.empty()) {
        // Fallback for some XLSX structures where relations might be in workbook.xml
        xml_str = get_uncompressed_file("xl/workbook.xml");
    }

    tinyxml2::XMLDocument doc;
    if (doc.Parse(xml_str.c_str()) != tinyxml2::XML_SUCCESS) {
        return relations;
    }

    tinyxml2::XMLElement* root = doc.FirstChildElement("Relationships");
    if (!root) {
        // Try looking inside the workbook element if the root isn't Relationships
        tinyxml2::XMLElement* workbook = doc.FirstChildElement("workbook");
        if (workbook) {
            root = workbook->FirstChildElement("relationship"); // Some versions might differ
            // However, standard XLSX has a separate .rels file.
        }
    }

    // Standard XLSX: xl/_rels/workbook.xml.rels contains the sheet relations
    // We already loaded xl/_rels/workbook.xml.rels via get_uncompressed_file
    // Let's re-parse the specific rels file if we didn't find it in workbook.xml
    
    tinyxml2::XMLElement* rel = root ? root->FirstChildElement("Relationship") : nullptr;
    if (!rel) {
        // If the root itself was the Relationship (unlikely) or we need to find it
        rel = root; 
    }

    // Since we might have parsed the wrong file if workbook.xml was used, 
    // let's ensure we are parsing the .rels file.
    // The logic below assumes 'doc' is the parsed 'xl/_rels/workbook.xml.rels'
    
    // If the first attempt failed, let's try the explicit rels file
    if (relations.empty()) {
        std::string rels_content = get_uncompressed_file("xl/_rels/workbook.xml.rels");
        if (rels_content.empty()) return relations;
        doc.Clear();
        doc.Parse(rels_content.c_str());
        root = doc.RootElement();
    }

    if (root) {
        for (tinyxml2::XMLElement* e = root->FirstChildElement("Relationship"); e != nullptr; e = e->NextSiblingElement("Relationship")) {
            const char* rId = e->Attribute("Id");
            const char* target = e->Attribute("Target");
            if (rId && target) {
                // In XLSX, sheet relations are usually in xl/worksheets/_rels/workbook.xml.rels
                // The target might be "worksheets/sheet1.xml"
                // We need to find the sheet name. Sheet names are in xl/workbook.xml
                // This is a bit complex. Let's simplify:
                // We'll find the sheet name by looking at xl/workbook.xml
                // But for now, let's just collect the rId and target.
                // The requirements say sheet_desc is (name, id, rId).
                // We'll need to cross-reference with workbook.xml to get names and IDs.
            }
        }
    }

    // Correct approach:
    // 1. Parse xl/workbook.xml to get <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
    // 2. Parse xl/_rels/workbook.xml.rels to map rId1 -> worksheets/sheet1.xml
    
    std::string workbook_xml = get_uncompressed_file("xl/workbook.xml");
    tinyxml2::XMLDocument wb_doc;
    if (wb_doc.Parse(workbook_xml.c_str()) == tinyxml2::XML_SUCCESS) {
        tinyxml2::XMLElement* wb_el = wb_doc.FirstChildElement("workbook");
        if (wb_el) {
            for (tinyxml2::XMLElement* s = wb_el->FirstChildElement("sheet"); s != nullptr; s = s->NextSiblingElement("sheet")) {
                const char* name = s->Attribute("name");
                int sheetId = s->IntAttribute("sheetId");
                const char* rId = s->Attribute("r:id"); // Note: tinyxml2 handles namespaces if configured, but usually we just look for the attribute
                if (!rId) rId = s->Attribute("id"); // Fallback

                if (name && rId) {
                    // Now find the target for this rId in xl/_rels/workbook.xml.rels
                    std::string rels_xml = get_uncompressed_file("xl/_rels/workbook.xml.rels");
                    tinyxml2::XMLDocument rel_doc;
                    if (rel_doc.Parse(rels_xml.c_str()) == tinyxml2::XML_SUCCESS) {
                        tinyxml2::XMLElement* rel_root = rel_doc.RootElement();
                        if (rel_root) {
                            for (tinyxml2::XMLElement* re = rel_root->FirstChildElement("Relationship"); re != nullptr; re = re->NextSiblingElement("Relationship")) {
                                if (std::string(re->Attribute("Id")) == rId) {
                                    const char* target = re->Attribute("Target");
                                    if (target) {
                                        relations.push_back(std::make_tuple(std::string(name), (std::uint32_t)sheetId, std::string(target)));
                                        break;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    return relations;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) {
    if (xml_content.count(sheet_path)) {
        return xml_content[sheet_path];
    }

    std::string xml_str = get_uncompressed_file(sheet_path);
    if (xml_str.empty()) return nullptr;

    auto doc = std::make_shared<tinyxml2::XMLDocument>();
    if (doc->Parse(xml_str.c_str()) == tinyxml2::XML_SUCCESS) {
        xml_content[sheet_path] = doc;
        return doc;
    }

    return nullptr;
}

std::vector<std::string> archive::get_shared_strings() {
    std::vector<std::string> strings;
    std::string xml_str = get_uncompressed_file("xl/sharedStrings.xml");
    if (xml_str.empty()) return strings;

    tinyxml2::XMLDocument doc;
    if (doc.Parse(xml_str.c_str()) == tinyxml2::XML_SUCCESS) {
        tinyxml2::XMLElement* root = doc.FirstChildElement("sst");
        if (root) {
            for (tinyxml2::XMLElement* t = root->FirstChildElement("t"); t != nullptr; t = t->NextSiblingElement("t")) {
                const char* text = t->GetText();
                if (text) {
                    strings.push_back(std::string(text));
                } else {
                    strings.push_back("");
                }
            }
        }
    }
    return strings;
}

std::string archive::get_uncompressed_file(const std::string& internal_path) {
    if (archive_content.count(internal_path)) {
        return archive_content[internal_path];
    }

    mz_zip_archive zip_archive;
    memset(&zip_archive, 0, sizeof(zip_archive));

    if (mz_zip_reader_init_file(&zip_archive, filename_.c_str(), 0) != MZ_OK) {
        return "";
    }

    mz_uint file_index;
    if (mz_zip_reader_locate_file_v2(&zip_archive, internal_path.c_str(), nullptr, 0, &file_index) != MZ_OK) {
        mz_zip_reader_end(&zip_archive);
        return "";
    }

    mz_zip_archive_file_stat file_stat;
    if (mz_zip_reader_file_stat(&zip_archive, file_index, &file_stat) != MZ_OK) {
        mz_zip_reader_end(&zip_archive);
        return "";
    }

    size_t uncompressed_size = file_stat.m_uncomp_size;
    
    std::string content;
    content.resize(uncompressed_size);

    if (mz_zip_reader_extract_to_mem(&zip_archive, file_index, content.data(), uncompressed_size, 0) != MZ_OK) {
        mz_zip_reader_end(&zip_archive);
        return "";
    }

    mz_zip_reader_end(&zip_archive);
    archive_content[internal_path] = content;
    return content;
}
