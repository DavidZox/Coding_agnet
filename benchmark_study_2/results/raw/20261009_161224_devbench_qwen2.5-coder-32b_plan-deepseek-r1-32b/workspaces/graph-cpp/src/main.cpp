#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <tuple>
#include <string>
#include <algorithm>
#include "al_graph.hpp"
#include "am_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc != 4) {
        cerr << "Usage: " << argv[0] << " file [filename] [output file path]" << endl;
        return -1;
    }

    string mode = argv[1];
    string inputFilename = argv[2];
    string outputFilename = argv[3];

    if (mode != "file") {
        cerr << "Invalid mode. Only 'file' mode is supported." << endl;
        return -1;
    }

    ifstream inputFile(inputFilename);
    if (!inputFile.is_open()) {
        cerr << "Failed to open input file: " << inputFilename << endl;
        return -1;
    }

    int isDirected;
    inputFile >> isDirected;

    vector<string> vexes;
    vector<tuple<string, string, int>> arcs;

    string line;
    while (getline(inputFile, line)) {
        if (line.empty()) continue;
        stringstream ss(line);
        string start, end;
        int weight;
        ss >> start >> end >> weight;
        vexes.push_back(start);
        vexes.push_back(end);
        arcs.emplace_back(start, end, weight);
    }

    inputFile.close();

    // Remove duplicates from vexes
    sort(vexes.begin(), vexes.end());
    vexes.erase(unique(vexes.begin(), vexes.end()), vexes.end());

    graph::AdjacencyListGraph<string> alGraph(vexes.size(), arcs.size(), isDirected);
    AdjacencyMatrixGraph<string> amGraph(vexes.size(), arcs.size(), isDirected);

    if (!alGraph.setVexes(vexes) || !amGraph.setVexes(vexes)) {
        cerr << "Failed to set vertices." << endl;
        return -1;
    }

    if (!alGraph.setArcs(arcs) || !amGraph.setArcs(arcs)) {
        cerr << "Failed to set arcs." << endl;
        return -1;
    }

    ofstream outputFile(outputFilename);
    if (!outputFile.is_open()) {
        cerr << "Failed to open output file: " << outputFilename << endl;
        return -1;
    }

    outputFile << "Adjacency Matrix:\n" << amGraph << "\n";
    outputFile << "Adjacency Table:\n" << alGraph << "\n";

    outputFile << "Depth-first search (no recursion)\n";
    vector<string> dfsResult = alGraph.dfs_noRes();
    for (const auto& vertex : dfsResult) {
        outputFile << vertex << " ";
    }
    outputFile << "\n";

    outputFile << "BFS:\n";
    vector<string> bfsResult = alGraph.bfs();
    for (const auto& vertex : bfsResult) {
        outputFile << vertex << " ";
    }
    outputFile << "\n";

    outputFile.close();

    return 0;
}
