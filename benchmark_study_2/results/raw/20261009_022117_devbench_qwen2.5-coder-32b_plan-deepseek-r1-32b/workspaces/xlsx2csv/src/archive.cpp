#include "archive.h"
#include "tinyxml2.h"
#include "miniz.h"
#include <fstream>
#include <sstream>
#include <iostream>

namespace {
    std::string_view get_file_content(const std::string& filename, std::vector<void*>& archive_files, std::unordered_map<std::string, std::string_view>& archive_content) {
        mz_zip_archive zip_archive;
        mz_zip_zero_struct(&zip_archive);

        if (!mz_zip_reader_init_file(&zip_archive, filename.c_str(), 0)) {
            throw std::runtime_error("Failed to open zip archive");
        }

        size_t file_index = 0;
        mz_zip_archive_file_stat file_stat;
        while (mz_zip_reader_file_stat(&zip_archive, file_index, &file_stat)) {
            void* file_data = nullptr;
            size_t file_size = 0;

            if (!mz_zip_reader_extract_to_heap(&zip_archive, file_index, &file_data, &file_size, 0)) {
                mz_zip_reader_end(&zip_archive);
                throw std::runtime_error("Failed to extract file from zip archive");
            }

            archive_files.push_back(file_data);
            archive_content[file_stat.m_filename] = std::string_view(static_cast<char*>(file_data), file_size);
            file_index++;
        }

        mz_zip_reader_end(&zip_archive);
        return archive_content[filename];
    }
}

archive::archive(const std::string& filename) {
    get_file_content(filename, archive_files, archive_content);

    mz_zip_archive zip_archive;
    mz_zip_zero_struct(&zip_archive);

    if (!mz_zip_reader_init_mem(&zip_archive, archive_content[filename].data(), archive_content[filename].size(), 0)) {
        throw std::runtime_error("Failed to initialize zip archive from memory");
    }

    size_t file_index = 0;
    mz_zip_archive_file_stat file_stat;
    while (mz_zip_reader_file_stat(&zip_archive, file_index, &file_stat)) {
        void* file_data = nullptr;
        size_t file_size = 0;

        if (!mz_zip_reader_extract_to_heap(&zip_archive, file_index, &file_data, &file_size, 0)) {
            mz_zip_reader_end(&zip_archive);
            throw std::runtime_error("Failed to extract file from zip archive");
        }

        archive_content[file_stat.m_filename] = std::string_view(static_cast<char*>(file_data), file_size);
        file_index++;
    }

    mz_zip_reader_end(&zip_archive);
}

std::vector<sheet_desc> archive::get_sheet_relations() const {
    std::vector<sheet_desc> sheet_relations;
    auto relations_xml = get_sheet_xml("[Content_Types].xml");

    if (!relations_xml) {
        throw std::runtime_error("Failed to get relations XML");
    }

    tinyxml2::XMLElement* root = relations_xml->FirstChildElement("Types");
    if (!root) {
        throw std::runtime_error("Invalid relations XML");
    }

    for (tinyxml2::XMLElement* override = root->FirstChildElement("Override"); override; override = override->NextSiblingElement("Override")) {
        const char* part_name = override->Attribute("PartName");
        const char* content_type = override->Attribute("ContentType");

        if (part_name && content_type && std::string(content_type) == "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml") {
            std::string sheet_path = std::string(part_name);
            std::string sheet_name = sheet_path.substr(sheet_path.find_last_of('/') + 1);
            sheet_name.erase(sheet_name.find_last_of('.'));

            std::string relation_id = get_relation_id_for_sheet(sheet_path);
            sheet_relations.emplace_back(sheet_name, sheet_relations.size() + 1, relation_id);
        }
    }

    return sheet_relations;
}

std::string archive::get_relation_id_for_sheet(const std::string& sheet_path) const {
    auto relations_xml = get_sheet_xml("_rels/.rels");

    if (!relations_xml) {
        throw std::runtime_error("Failed to get relations XML");
    }

    tinyxml2::XMLElement* root = relations_xml->FirstChildElement("Relationships");
    if (!root) {
        throw std::runtime_error("Invalid relations XML");
    }

    for (tinyxml2::XMLElement* relation = root->FirstChildElement("Relationship"); relation; relation = relation->NextSiblingElement("Relationship")) {
        const char* target = relation->Attribute("Target");
        const char* id = relation->Attribute("Id");

        if (target && id && std::string(target) == sheet_path.substr(3)) { // Remove "xl/" from sheet_path
            return id;
        }
    }

    return "";
}

std::vector<std::string> archive::get_shared_strings() const {
    std::vector<std::string> shared_strings;
    auto shared_strings_xml = get_sheet_xml("xl/sharedStrings.xml");

    if (!shared_strings_xml) {
        return shared_strings;
    }

    tinyxml2::XMLElement* root = shared_strings_xml->FirstChildElement("sst");
    if (!root) {
        throw std::runtime_error("Invalid shared strings XML");
    }

    for (tinyxml2::XMLElement* si = root->FirstChildElement("si"); si; si = si->NextSiblingElement("si")) {
        tinyxml2::XMLElement* t = si->FirstChildElement("t");
        if (t) {
            shared_strings.push_back(t->GetText() ? t->GetText() : "");
        }
    }

    return shared_strings;
}

std::shared_ptr<tinyxml2::XMLDocument> archive::get_sheet_xml(const std::string& sheet_path) const {
    auto it = xml_content.find(sheet_path);
    if (it != xml_content.end()) {
        return it->second;
    }

    auto content_it = archive_content.find(sheet_path);
    if (content_it == archive_content.end()) {
        return nullptr;
    }

    std::shared_ptr<tinyxml2::XMLDocument> xml_doc = std::make_shared<tinyxml2::XMLDocument>();
    if (xml_doc->Parse(content_it->second.data(), content_it->second.size()) != tinyxml2::XML_SUCCESS) {
        return nullptr;
    }

    xml_content[sheet_path] = xml_doc;
    return xml_doc;
}
