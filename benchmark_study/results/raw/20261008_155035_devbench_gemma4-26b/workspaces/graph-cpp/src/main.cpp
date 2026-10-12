#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include <algorithm>
#include "al_graph.hpp"
#include "am_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        return -1;
    }

    string filename = "";
    string output_path = "";

    if (argc == 4 && string(argv[1]) == "file") {
        filename = argv[2];
        output_path = argv[3];
    } else if (argc == 2) {
        // If only one argument is provided, we assume it's the filename and output to stdout or handle as per requirement
        // But the spec says: ./graph file [filename] [output file path]
        // If the user doesn't provide output path, we'll default to stdout or handle error.
        // Given the example: ./graph file input.txt output.txt
        // We will follow the command line pattern strictly.
        return -1; 
    } else {
        return -1;
    }

    ifstream infile(filename);
    if (!infile.is_open()) {
        cerr << "Error opening input file." << endl;
        return -1;
    }

    int isDirected;
    if (!(infile >> isDirected)) {
        return -1;
    }

    struct Edge {
        int u, v, w;
    };
    vector<Edge> edges;
    int max_v = 0;

    int u, v, w;
    while (infile >> u >> v >> w) {
        edges.push_back({u, v, w});
        max_v = max({max_v, u, v});
    }
    infile.close();

    // Determine number of vertices. The problem doesn't explicitly say how many vertices there are,
    // but usually it's the max index found or provided.
    // Based on the example, vertices are 1-indexed.
    int vexNum = max_v;
    
    // Prepare vertex list (1 to vexNum)
    vector<int> vexList;
    for (int i = 1; i <= vexNum; ++i) {
        vexList.push_back(i);
    }

    // Prepare arcs for AdjacencyListGraph (vector of tuples)
    vector<tuple<int, int, int>> arcTuples;
    for (const auto& e : edges) {
        arcTuples.push_back(make_tuple(e.u, e.v, e.w));
        if (isDirected == 0) {
            arcTuples.push_back(make_tuple(e.v, e.u, e.w));
        }
    }

    // Initialize Graphs
    AdjacencyMatrixGraph<int> amg(vexNum, arcTuples.size(), isDirected == 1);
    AdjacencyListGraph<int> alg(vexNum, arcTuples.size(), isDirected == 1);

    if (!amg.setVexer(vexList) || !amg.setArcs(arcTuples) ||
        !alg.setVexer(vexList) || !alg.setArcs(arcTuples)) {
        return -1;
    }

    // Output to file
    ofstream outfile(output_path);
    if (!outfile.is_open()) {
        cerr << "Error opening output file." << endl;
        return -1;
    }

    outfile << amg << endl;

    outfile << "Adjacency Table：" << endl;
    outfile << alg << endl;

    outfile << "Depth-first search (no recursion) " << endl;
    vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        outfile << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    outfile << endl;

    outfile << "BFS: " << endl;
    vector<int> bfs_res = alg.bfs();
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        outfile << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    outfile << endl;

    outfile.close();

    return 0;
}
