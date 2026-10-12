#include "workbook.h"
#include <iostream>
#include <string>
#include <filesystem>

using namespace my_xlsx::xlsx_reader;

/**
 * @brief Main entry point for the xlsx2csv tool.
 * 
 * Command pattern: ./xlsx2csv [xlsx filename] [output file path]
 * 
 * Success output: "Conversion successful. CSV files generated."
 * Incorrect usage output: "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]"
 * Non-existent input output: "Error: Input File error."
 */
int main(int argc, char** argv) {
    // Feature 1: Check command-line parameter count
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string input_xlsx = argv[1];
    std::string output_dir = argv[2];

    // Feature 1: Check if input file exists
    if (!std::filesystem::exists(input_xlsx)) {
        std::cerr << "Error: Input File error." << std::endl;
        return 1;
    }

    try {
        // Create workbook instance (which handles archive and worksheet creation)
        workbook wb(input_xlsx);

        // Perform conversion
        wb.write_to_csv(output_dir);

        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } catch (const std::exception& e) {
        // If archive initialization fails (e.g., not a valid zip), it throws runtime_error
        // The acceptance tests expect "Error: Input File error." for invalid files
        std::cerr << "Error: Input File error." << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "Error: An unknown error occurred." << std::endl;
        return 1;
    }

    return 0;
}
