#include <iostream>
#include <fstream>
#include <string>
#include "workbook.h"

int main(int argc, char** argv) {
    // Check if the number of arguments is correct
    // argv[0] is the program name, argv[1] is xlsx filename, argv[2] is output path
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string xlsx_filename = argv[1];
    std::string output_path = argv[2];

    // Check if the input file exists
    std::ifstream infile(xlsx_filename);
    if (!infile.good()) {
        std::cerr << "Error: Input File error." << std::endl;
        return 1;
    }
    infile.close();

    try {
        // Initialize workbook and perform conversion
        workbook wb(xlsx_filename);
        wb.write_to_csv(output_path);
        
        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } catch (const std::exception& e) {
        // In case of unexpected errors during processing
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "Error: An unknown error occurred." << std::endl;
        return 1;
    }

    return 0;
}
