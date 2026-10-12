#include "../include/workbook.h"
#include "../include/utils.h"
#include <iostream>
#include <string>
#include <vector>

/**
 * @brief Main entry point of the XLSX to CSV conversion tool.
 * 
 * @param argc Argument count.
 * @param argv Argument vector.
 * @return int Exit status code.
 */
int main(int argc, char** argv) {
    // Feature 1: Command-Line Conversion Check
    if (argc != 3) {
        std::cout << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string xlsx_filename = argv[1];
    std::string output_path = argv[2];

    // Check for input file existence (Feature 1 requirement)
    std::ifstream check_file(xlsx_filename);
    if (!check_file.is_open()) {
        std::cout << "Error: Input File error." << std::endl;
        return 1;
    }
    check_file.close();

    try {
        // Workbook class handles initialization, parsing, and conversion
        workbook wb(xlsx_filename);

        // Feature 2 & 3: Conversion and Data Integrity
        wb.write_to_csv(output_path);

        // Success message
        std::cout << "Conversion successful. CSV files generated." << std::endl;
        return 0;

    } catch (const std::exception& e) {
        std::cerr << "An unexpected error occurred during conversion: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "An unknown error occurred during conversion." << std::endl;
        return 1;
    }
}
