#include <iostream>
#include <string>
#include <filesystem>
#include "workbook.h"

namespace fs = std::filesystem;

int main(int argc, char** argv) {
    // Check command-line arguments count
    if (argc != 3) {
        std::cout << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string input_xlsx = argv[1];
    std::string output_path = argv[2];

    // Check if input file exists
    if (!fs::exists(input_xlsx)) {
        std::cout << "Error: Input File error." << std::endl;
        return 1;
    }

    try {
        // Initialize workbook
        workbook wb(input_xlsx);
        
        // Perform conversion
        wb.write_to_csv(output_path);
        
        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } catch (const std::exception& e) {
        // In case of unexpected errors during processing
        std::cout << "Error: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cout << "Error: An unknown error occurred." << std::endl;
        return 1;
    }

    return 0;
}
