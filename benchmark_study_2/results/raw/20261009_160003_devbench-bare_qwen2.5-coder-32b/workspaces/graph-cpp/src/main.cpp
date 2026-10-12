#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <tuple>
#include <string>
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

    std::vector<std::tuple<int, int, int>> arcs;
    std::vector<int> vexes;
    int start, end, weight;

    while (inputFile >> start >> end >> weight) {
        arcs.emplace_back(start, end, weight);
        if (std::find(vexes.begin(), vexes.end(), start) == vexes.end()) {
            vexes.push_back(start);
        }
        if (std::find(vexes.begin(), vexes.end(), end) == vexes.end()) {
            vexes.push_back(end);
        }
    }

    AdjacencyListGraph<int> alGraph(vexes.size(), arcs.size(), isDirected);
    AdjacencyMatrixGraph<int> amGraph(vexes.size(), arcs.size(), isDirected);

    if (!alGraph.setVexer(vexes) || !alGraph.setArcs(arcs)) {
        std::cerr << "Failed to set graph data for adjacency list graph." << std::endl;
        return -1;
    }

    if (!amGraph.setVexer(vexes) || !amGraph.setArcs(arcs)) {
        std::cerr << "Failed to set graph data for adjacency matrix graph." << std::endl;
        return -1;
    }

    std::ofstream outputFile(outputFilename);
    if (!outputFile.is_open()) {
        std::cerr << "Failed to open output file: " << outputFilename << std::endl;
        return -1;
    }

    outputFile << amGraph;
    outputFile << alGraph;

    std::vector<int> dfsResult = alGraph.dfs_noRes();
    outputFile << "Depth-first search (no recursion)\n";
    for (size_t i = 0; i < dfsResult.size(); ++i) {
        outputFile << dfsResult[i];
        if (i < dfsResult.size() - 1) {
            outputFile << " ";
        }
    }
    outputFile << "\n";

    std::vector<int> bfsResult = alGraph.bfs();
    outputFile << "BFS:\n";
    for (size_t i = 0; i < bfsResult.size(); ++i) {
        outputFile << bfsResult[i];
        if (i < bfsResult.size() - 1) {
            outputFile << " ";
        }
    }
    outputFile << "\n";

    return 0;
}
