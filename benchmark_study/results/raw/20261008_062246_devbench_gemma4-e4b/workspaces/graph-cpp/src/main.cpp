#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include <algorithm> // Required for std::max
#include <set> // Using set to easily find unique vertices

#include "al_graph.hpp"
#include "am_graph.hpp"
#include "queue.hpp"
#include "stack.hpp"

using namespace std;

// Function to read graph data from a file
bool readGraphFromFile(const string& filename, bool& isDirected, vector<int>& vexes, vector<tuple<int, int, int>>& arcs) {
    ifstream inputFile(filename);
    if (!inputFile.is_open()) {
        cerr << "Error: Could not open input file " << filename << endl;
        return false;
    }

    string line;
    
    // Read the first line to determine if it is directed
    if (!getline(inputFile, line)) {
        cerr << "Error: Input file is empty." << endl;
        return false;
    }

    stringstream ss(line);
    string dirStr;
    ss >> dirStr;
    
    if (dirStr == "0") {
        isDirected = false; // Undirected
    } else if (dirStr == "1") {
        isDirected = true; // Directed
    } else {
        cerr << "Error: Invalid graph type indicator in the first line." << endl;
        return false;
    }

    // Read subsequent lines for edges
    while (getline(inputFile, line)) {
        stringstream edge_ss(line);
        int u, v, w;
        if (edge_ss >> u >> v >> w) {
            arcs.emplace_back(u, v, w);
        }
    }

    // Determine the number of vertices and collect unique vertices
    set<int> unique_vertices_set;
    for (const auto& arc : arcs) {
        unique_vertices_set.insert(get<0>(arc));
        unique_vertices_set.insert(get<1>(arc));
    }
    
    // Populate vexes vector from the set
    vexes.assign(unique_vertices_set.begin(), unique_vertices_set.end());

    return true;
}

// Function to write output to a file
void writeOutputToFile(const string& filename, const AdjacencyMatrixGraph<int>& amg, const vector<int>& dfs_result, const vector<int>& bfs_result) {
    ofstream outputFile(filename);
    if (!outputFile.is_open()) {
        cerr << "Error: Could not open output file " << filename << " for writing." << endl;
        return;
    }

    // 1. Adjacency Matrix
    outputFile << "Adjacency Matrix：" << endl;
    for (int i = 0; i < amg.getVexNum(); ++i) {
        for (int j = 0; j < amg.getVexNum(); ++j) {
            outputFile << amg.getArcMatrix()[i][j] << (j == amg.getVexNum() - 1 ? "" : " ");
        }
        outputFile << endl;
    }

    // 2. Adjacency Table
    outputFile << "Adjacency Table：" << endl;
    for (int i = 0; i < amg.getVexNum(); ++i) {
        outputFile << amg.getVexList()[i];
        for (int j = 0; j < amg.getVexNum(); ++j) {
            if (i == j) {
                outputFile << "->";
            } else if (amg.getArcMatrix()[i][j] != 0) {
                outputFile << "->" << amg.getArcMatrix()[i][j];
            } else {
                outputFile << "->^";
            }
            if (j < amg.getVexNum() - 1) {
                outputFile << "\t"; // Use tab separation for columns
            }
        }
        outputFile << endl;
    }

    // 3. DFS Result
    outputFile << "Depth-first search (no recursion) " << endl;
    for (size_t i = 0; i < dfs_result.size(); ++i) {
        outputFile << dfs_result[i] << (i == dfs_result.size() - 1 ? "" : " ");
    }
    outputFile << endl;

    // 4. BFS Result
    outputFile << "BFS: " << endl;
    for (size_t i = 0; i < bfs_result.size(); ++i) {
        outputFile << bfs_result[i] << (i == bfs_result.size() - 1 ? "" : " ");
    }
    outputFile << endl;
}


int main(int argc, char** argv) {
    if (argc < 4) {
        cerr << "Usage: ./graph file <input_filename> <output_filename>" << endl;
        return 1;
    }

    string mode = argv[1];
    string inputFilename = argv[2];
    string outputFilename = argv[3];

    bool isDirected = false;
    vector<int> vexes;
    vector<tuple<int, int, int>> arcs;

    // --- Data Loading ---
    if (mode == "file") {
        if (!readGraphFromFile(inputFilename, isDirected, vexes, arcs)) {
            return 1; // Error during file reading
        }
    } else {
        // Default data handling (As per PRD, if not file mode, use default data. 
        // Since PRD doesn't specify default data, we'll use a minimal graph 
        // or handle the error based on the expected CLI usage.)
        cerr << "Error: Only 'file' mode is supported for input reading based on current implementation scope." << endl;
        return 1;
    }

    if (vexes.empty() && arcs.empty()) {
        cerr << "Error: Graph is empty. Cannot perform traversal." << endl;
        return 1;
    }

    // --- Graph Initialization and Setup ---
    
    // 1. Adjacency List Graph (ALG)
    // Initialize ALG with necessary parameters before setting data
    AdjacencyListGraph<int> alg(vexes.size(), arcs.size(), isDirected);
    if (!alg.setVexer(vexes)) {
        cerr << "Error setting vertices for ALG." << endl;
        return 1;
    }
    if (!alg.setArcs(arcs)) {
        cerr << "Error setting arcs for ALG." << endl;
        return 1;
    }

    // 2. Adjacency Matrix Graph (AMG)
    // AMG needs VexNum for size, and arcs.size() for arc count.
    AdjacencyMatrixGraph<int> amg(vexes.size(), arcs.size(), isDirected);
    if (!amg.setVexer(vexes)) {
        cerr << "Error setting vertices for AMG." << endl;
        return 1;
    }
    if (!amg.setArcs(arcs)) {
        cerr << "Error setting arcs for AMG." << endl;
        return 1;
    }
    // isDirected is passed in the constructor now, so no need for setIsDirected call.

    // --- Traversal Execution ---
    
    // DFS (Non-recursive)
    vector<int> dfs_result = alg.dfs_noRes();

    // BFS
    // BFS in ALG might need a starting node. We'll use the first vertex found.
    // Removed unused start_node variable
    vector<int> bfs_result = alg.bfs();

    // --- Output ---
    writeOutputToFile(outputFilename, amg, dfs_result, bfs_result);

    return 0;
}
