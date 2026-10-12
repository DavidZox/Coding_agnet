#include <iostream>
#include <string>
#include "workbook.h"

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]" << std::endl;
        return 1;
    }

    std::string input_filename = argv[1];
    std::string output_path = argv[2];

    try {
        xlsx2csv::workbook wb(input_filename);
        wb.write_to_csv(output_path);
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
