#include <iostream>
#include <string>
#include <fstream>
#include <filesystem>
#include "workbook.h"
#include "worksheet.h" // Include worksheet.h to ensure Worksheet is fully defined before Workbook is used in main
#include "types.h"    // Include types.h for type definitions if needed, though workbook.h should cover most dependencies

namespace fs = std::filesystem;

int main(int argc, char** argv) {
    // Check for correct number of arguments
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string xlsx_filename = argv[1];
    std::string output_path = argv[2];

    // Check if input file exists
    if (!fs::exists(xlsx_filename)) {
        std::cerr << "Error: Input File error." << std::endl;
        return 1;
    }

    try {
        // Create Workbook instance and perform conversion
        Workbook workbook(xlsx_filename);
        workbook.write_to_csv(output_path);

        // Success message
        std::cout << "Conversion successful. CSV files generated." << std::endl;
        return 0;
    } catch (const std::exception& e) {
        // Catch any other exceptions during processing (e.g., parsing errors)
        std::cerr << "An unexpected error occurred during conversion: " << e.what() << std::endl;
        return 1;
    }
}
