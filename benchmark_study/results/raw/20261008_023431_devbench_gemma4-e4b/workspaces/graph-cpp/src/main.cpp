#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <tuple>
#include <algorithm> // Required for std::max
#include "al_graph.hpp"
#include "am_graph.hpp"
#include "queue.hpp"
#include "stack.hpp"

using namespace std;

// Helper function to read graph data from a file
bool readGraphFromFile(const string& filename, bool& isDirected, vector<int>& vexes, vector<tuple<int, int, int>>& arcs) {
    ifstream file(filename);
    if (!file.is_open()) {
        cerr << "Error: Could not open file " << filename << endl;
        return false;
    }

    string line;
    if (!getline(file, line)) {
        cerr << "Error: File is empty." << endl;
        return false;
    }

    // Read directed flag
    stringstream ss_dir(line);
    string dir_str;
    ss_dir >> dir_str;
    if (dir_str == "0") {
        isDirected = false; // Undirected
    } else if (dir_str == "1") {
        isDirected = true; // Directed
    } else {
        cerr << "Error: Invalid directed flag in the first line." << endl;
        return false;
    }

    // Read edges
    int start, end, weight;
    while (getline(file, line)) {
        stringstream ss_edge(line);
        if (ss_edge >> start >> end >> weight) {
            arcs.emplace_back(start, end, weight);
        }
    }

    // Determine number of vertices based on max vertex index + 1
    int max_vex = 0;
    for (const auto& arc : arcs) {
        max_vex = max({max_vex, get<0>(arc), get<1>(arc)});
    }
    // Vexes are 0-indexed, so we need max_vex + 1 vertices
    vexes.resize(max_vex + 1);
    for (size_t i = 0; i < vexes.size(); ++i) {
        vexes[i] = i; // Assign vertex ID as index
    }

    return true;
}

// Function to print the results to the output file
void printResults(const string& outputFilename, const AdjacencyListGraph<int>& alg, const AdjacencyMatrixGraph<int>& amg) {
    ofstream outfile(outputFilename);
    if (!outfile.is_open()) {
        cerr << "Error: Could not open output file " << outputFilename << endl;
        return;
    }

    // 1. Print Adjacency Matrix
    outfile << "Adjacency Matrix：" << endl;
    for (int i = 0; i < amg.getVexNum(); ++i) {
        for (int j = 0; j < amg.getVexNum(); ++j) {
            outfile << amg.getArcMatrix()[i][j] << (j == amg.getVexNum() - 1 ? "" : " ");
        }
        outfile << endl;
    }

    // 2. Print Adjacency Table
    outfile << "Adjacency Table：" << endl;
    for (int i = 0; i < amg.getVexNum(); ++i) {
        outfile << i;
        for (int j = 0; j < amg.getVexNum(); ++j) {
            if (i == j) {
                outfile << "\t";
            } else if (amg.getArcMatrix()[i][j] > 0) {
                // Format: j -> weight -> ^
                outfile << "\t" << j << " -> " << amg.getArcMatrix()[i][j] << " -> ^";
            } else {
                outfile << "\t";
            }
        }
        outfile << endl;
    }

    // 3. Print DFS result
    outfile << "Depth-first search (no recursion) " << endl;
    vector<int> dfs_result = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_result.size(); ++i) {
        outfile << dfs_result[i] << (i == dfs_result.size() - 1 ? "" : " ");
    }
    outfile << endl;

    // 4. Print BFS result
    outfile << "BFS: " << endl;
    vector<int> bfs_result = alg.bfs();
    for (size_t i = 0; i < bfs_result.size(); ++i) {
        outfile << bfs_result[i] << (i == bfs_result.size() - 1 ? "" : " ");
    }
    outfile << endl;

    outfile.close();
    cout << "Results successfully written to " << outputFilename << endl;
}


int main(int argc, char** argv) {
    // Check for file mode: ./graph file <input_filename> <output_filename>
    if (argc < 4 || string(argv[1]) != "file") {
        // Default data mode (as per UML_sequence.md)
        // Hardcoded data for default execution path
        bool isDirected = false;
        vector<int> vexes = {0, 1, 2, 3, 4}; // 5 vertices
        vector<tuple<int, int, int>> arcs = {
            {0, 1, 1}, {0, 2, 1}, {1, 2, 4}, {1, 3, 9}, {1, 4, 2}, 
            {2, 3, 5}, {2, 4, 6}, {3, 0, 3}, {3, 1, 5}, {3, 2, 8}
        };
        
        // Use default output filename if not provided, or handle error
        string outputFilename = "output.txt"; 
        if (argc == 3 && string(argv[1]) != "file") {
             // If only 3 args, assume default data and use argv[2] as output file
             outputFilename = argv[2];
        }
        
        cout << "Running with default hardcoded graph data." << endl;

        // --- Initialize Graphs ---
        int num_vexes = vexes.size();
        int num_arcs = arcs.size();

        // Initialize Adjacency List Graph
        AdjacencyListGraph<int> alg(num_vexes, num_arcs, isDirected);
        if (!alg.setVexes(vexes)) {
            cerr << "Failed to set vertices for ALG." << endl;
            return 1;
        }
        if (!alg.setArcs(arcs)) {
            cerr << "Failed to set arcs for ALG." << endl;
            return 1;
        }

        // Initialize Adjacency Matrix Graph
        AdjacencyMatrixGraph<int> amg(num_vexes, num_arcs, isDirected);
        if (!amg.setVexes(vexes)) {
            cerr << "Failed to set vertices for AMG." << endl;
            return 1;
        }
        if (!amg.setArcs(arcs)) {
            cerr << "Failed to set arcs for AMG." << endl;
            return 1;
        }

        // --- Output Results ---
        printResults(outputFilename, alg, amg);
        return 0;
    }

    // --- File Mode Execution ---
    string inputFilename = argv[2];
    string outputFilename = argv[3];

    bool isDirected = false;
    vector<int> vexes;
    vector<tuple<int, int, int>> arcs;

    // --- Read Graph Data ---
    bool success = readGraphFromFile(inputFilename, isDirected, vexes, arcs);

    if (!success) {
        cerr << "Failed to read graph data. Exiting." << endl;
        return 1;
    }

    // --- Initialize Graphs ---
    // VexNum for AMG is Vexes.size() (since it's 0-indexed up to max_vex)
    // ArcNum is arcs.size()
    int num_vexes = vexes.size();
    int num_arcs = arcs.size();

    // Initialize Adjacency List Graph
    AdjacencyListGraph<int> alg(num_vexes, num_arcs, isDirected);
    if (!alg.setVexes(vexes)) {
        cerr << "Failed to set vertices for ALG." << endl;
        return 1;
    }
    if (!alg.setArcs(arcs)) {
        cerr << "Failed to set arcs for ALG." << endl;
        return 1;
    }

    // Initialize Adjacency Matrix Graph
    // AMG size needs to be num_vexes x num_vexes
    AdjacencyMatrixGraph<int> amg(num_vexes, num_arcs, isDirected);
    if (!amg.setVexes(vexes)) {
        cerr << "Failed to set vertices for AMG." << endl;
        return 1;
    }
    if (!amg.setArcs(arcs)) {
        cerr << "Failed to set arcs for AMG." << endl;
        return 1;
    }

    // --- Output Results ---
    printResults(outputFilename, alg, amg);

    return 0;
}
