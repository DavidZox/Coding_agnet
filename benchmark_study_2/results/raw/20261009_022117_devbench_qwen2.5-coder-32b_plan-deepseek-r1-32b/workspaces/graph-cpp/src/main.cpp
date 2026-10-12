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

    string filename = argv[2];
    string outputFilename = argv[3];
    ifstream inputFile(filename);
    ofstream outputFile(outputFilename);

    if (!inputFile.is_open()) {
        cerr << "Error opening input file: " << filename << endl;
        return -1;
    }

    if (!outputFile.is_open()) {
        cerr << "Error opening output file: " << outputFilename << endl;
        return -1;
    }

    int isDirected;
    inputFile >> isDirected;

    vector<string> vexes;
    vector<tuple<string, string, int>> arcs;

    string line;
    while (getline(inputFile, line)) {
        istringstream iss(line);
        string start, end;
        int weight;
        if (iss >> start >> end >> weight) {
            int startIndex = find(vexes.begin(), vexes.end(), start) - vexes.begin();
            if (startIndex == vexes.size()) {
                vexes.push_back(start);
                startIndex = vexes.size() - 1;
            }
            int endIndex = find(vexes.begin(), vexes.end(), end) - vexes.begin();
            if (endIndex == vexes.size()) {
                vexes.push_back(end);
                endIndex = vexes.size() - 1;
            }
            arcs.emplace_back(start, end, weight);
        }
    }

    inputFile.close();

    graph::AdjacencyListGraph<string> alGraph(vexes.size(), arcs.size(), isDirected);
    graph::AdjacencyMatrixGraph<string> amGraph(vexes.size(), arcs.size(), isDirected);

    if (!alGraph.setVexes(vexes)) {
        cerr << "Error setting vertices in AdjacencyListGraph" << endl;
        return -1;
    }

    if (!amGraph.setVexes(vexes)) {
        cerr << "Error setting vertices in AdjacencyMatrixGraph" << endl;
        return -1;
    }

    vector<tuple<int, int, int>> intArcs;
    for (const auto& arc : arcs) {
        int start = alGraph.locateVex(get<0>(arc));
        int end = alGraph.locateVex(get<1>(arc));
        int weight = get<2>(arc);
        intArcs.emplace_back(start, end, weight);
    }

    if (!alGraph.setArcs(intArcs)) {
        cerr << "Error setting arcs in AdjacencyListGraph" << endl;
        return -1;
    }

    if (!amGraph.setArcs(arcs)) {
        cerr << "Error setting arcs in AdjacencyMatrixGraph" << endl;
        return -1;
    }

    outputFile << amGraph << endl;
    outputFile << alGraph << endl;

    vector<string> dfsResult = alGraph.dfs_noRes();
    outputFile << "Depth-first search (no recursion)\n";
    for (const auto& vertex : dfsResult) {
        outputFile << vertex << " ";
    }
    outputFile << "\n";

    vector<string> bfsResult = alGraph.bfs();
    outputFile << "BFS:\n";
    for (const auto& vertex : bfsResult) {
        outputFile << vertex << " ";
    }
    outputFile << "\n";

    outputFile.close();

    return 0;
}
