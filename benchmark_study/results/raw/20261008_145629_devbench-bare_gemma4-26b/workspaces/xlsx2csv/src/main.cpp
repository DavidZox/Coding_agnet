#include <iostream>
#include <string>
#include <filesystem>
#include "workbook.h"

/**
 * @brief Main entry point of the xlsx2csv software.
 * 
 * The program follows the command pattern:
 * ./xlsx2csv [xlsx filename] [output file path]
 * 
 * Requirements:
 * - On successful conversion: "Conversion successful. CSV files generated."
 * - Incorrect command-line parameters: "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]"
 * - Non-existent input file: "Error: Input File error."
 */
int main(int argc, char** argv) {
    // Check for correct number of arguments
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string input_filename = argv[1];
    std::string output_path = argv[2];

    // Check if input file exists
    if (!std::filesystem::exists(input_filename)) {
        std::cerr << "Error: Input File error." << std::endl;
        return 1;
    }

    try {
        // Create workbook instance (this also initializes the archive and worksheets)
        workbook wb(input_filename);

        // Perform the conversion
        wb.write_to_csv(output_path);

        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } catch (const std::exception& e) {
        // Handle potential errors during archive opening or XML parsing
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
