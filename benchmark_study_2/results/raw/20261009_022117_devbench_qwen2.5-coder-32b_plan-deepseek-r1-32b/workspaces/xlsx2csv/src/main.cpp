#include <iostream>
#include <fstream>
#include <memory>
#include <string>
#include <filesystem>
#include "workbook.h"

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string input_file = argv[1];
    std::string output_path = argv[2];

    if (!std::filesystem::exists(input_file)) {
        std::cerr << "Error: Input File error." << std::endl;
        return 1;
    }

    try {
        std::unique_ptr<workbook> wb = std::make_unique<workbook>(input_file);
        wb->write_to_csv(output_path);
        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
