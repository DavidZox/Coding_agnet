#include <iostream>
#include <string>
#include <memory>
#include "workbook.h" // Include workbook.h first, as it is the main entry point logic
#include "archive.h"
#include "worksheet.h"

int main(int argc, char** argv) {
    // Feature 1: Command-Line Conversion
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string xlsx_filename = argv[1];
    std::string output_path = argv[2];

    // Check if input file exists (basic check, assuming file system interaction is handled by Archive/OS)
    // For this implementation, we rely on Workbook/Archive to handle file existence errors during construction/processing.
    // However, to satisfy the specific error message requirement: "Error: Input File error."
    // We'll assume a check mechanism or rely on the constructor failing gracefully.

    try {
        // Workbook constructor handles Archive creation and loading
        std::unique_ptr<Workbook> workbook = std::make_unique<Workbook>(xlsx_filename);

        // Feature 2 & 3: Conversion and Data Integrity
        // write_to_csv handles multi-sheet support and writing individual CSVs
        workbook->write_to_csv(output_path);

        // Success message
        std::cout << "Conversion successful. CSV files generated." << std::endl;
        return 0;

    } catch (const std::runtime_error& e) {
        // Catch errors from Workbook/Archive (e.g., file not found, XML parsing errors)
        std::string error_msg = e.what();

        // Specific error handling based on PRD requirements
        if (error_msg.find("Input File error.") != std::string::npos) {
            std::cerr << "Error: Input File error." << std::endl;
            return 1;
        }
        
        // General error handling for other issues (like parsing errors)
        std::cerr << "Conversion failed: " << error_msg << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "An unknown error occurred during conversion." << std::endl;
        return 1;
    }
}
