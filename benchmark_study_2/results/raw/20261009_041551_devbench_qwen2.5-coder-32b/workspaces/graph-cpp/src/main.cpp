#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <tuple>
#include <string>
#include <algorithm>  // Include for std::find
#include "al_graph.hpp"
#include "am_graph.hpp"

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0] << " file [filename] [output file path]" << std::endl;
        return -1;
    }

    std::string mode = argv[1];
    std::string inputFilename = argv[2];
    std::string outputFilename = argv[3];

    if (mode != "file") {
        std::cerr << "Invalid mode. Only 'file' mode is supported." << std::endl;
        return -1;
    }

    std::ifstream inputFile(inputFilename);
    if (!inputFile.is_open()) {
        std::cerr << "Failed to open input file: " << inputFilename << std::endl;
        return -1;
    }

    int isDirected;
    inputFile >> isDirected;

    std::vector<std::string> vexes;
    std::vector<std::tuple<int, int, int>> arcs;

    std::string line;
    while (std::getline(inputFile, line)) {
        std::istringstream iss(line);
        int start, end, weight;
        if (iss >> start >> end >> weight) {
            arcs.emplace_back(start, end, weight);
            std::string startStr = std::to_string(start);
            std::string endStr = std::to_string(end);
            if (std::find(vexes.begin(), vexes.end(), startStr) == vexes.end()) {
                vexes.push_back(startStr);
            }
            if (std::find(vexes.begin(), vexes.end(), endStr) == vexes.end()) {
                vexes.push_back(endStr);
            }
        }
    }

    inputFile.close();

    AdjacencyListGraph<int> alGraph(vexes.size(), arcs.size(), isDirected);
    AdjacencyMatrixGraph<int> amGraph(vexes.size(), arcs.size(), isDirected);

    std::vector<int> vexInts;
    for (const auto& vex : vexes) {
        vexInts.push_back(std::stoi(vex));
    }

    if (!alGraph.setVexes(vexInts) || !alGraph.setArcs(arcs)) {
        std::cerr << "Failed to set graph data for AdjacencyListGraph." << std::endl;
        return -1;
    }

    if (!amGraph.setVexes(vexInts) || !amGraph.setArcs(arcs)) {
        std::cerr << "Failed to set graph data for AdjacencyMatrixGraph." << std::endl;
        return -1;
    }

    std::ofstream outputFile(outputFilename);
    if (!outputFile.is_open()) {
        std::cerr << "Failed to open output file: " << outputFilename << std::endl;
        return -1;
    }

    outputFile << "Adjacency Matrix:\n" << amGraph << "\n";
    outputFile << "Adjacency Table:\n" << alGraph << "\n";

    outputFile << "Depth-first search (no recursion)\n";
    std::vector<int> dfsResult = alGraph.dfs_noRes();
    for (size_t i = 0; i < dfsResult.size(); ++i) {
        outputFile << dfsResult[i];
        if (i < dfsResult.size() - 1) {
            outputFile << " ";
        }
    }
    outputFile << "\n";

    outputFile << "BFS:\n";
    std::vector<int> bfsResult = alGraph.bfs();
    for (size_t i = 0; i < bfsResult.size(); ++i) {
        outputFile << bfsResult[i];
        if (i < bfsResult.size() - 1) {
            outputFile << " ";
        }
    }
    outputFile << "\n";

    outputFile.close();

    return 0;
}
