#include <iostream>
#include <fstream>
#include <string>
#include "workbook.h"

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 0;
    }

    std::string input_filename = argv[1];
    std::string output_path = argv[2];

    // Check if input file exists
    std::ifstream infile(input_filename);
    if (!infile.good()) {
        std::cerr << "Error: Input File error." << std::endl;
        return 0;
    }
    infile.close();

    try {
        workbook wb(input_filename);
        wb.write_to_csv(output_path);
        std::cout << "Conversion successful. CSV files generated." << std::endl;
    } catch (const std::exception& e) {
        // In case of unexpected errors during processing
        std::cerr << "Error: " << e.what() << std::endl;
        return 0;
    } catch (...) {
        std::cerr << "Error: An unknown error occurred." << std::endl;
        return 0;
    }

    return 0;
}
